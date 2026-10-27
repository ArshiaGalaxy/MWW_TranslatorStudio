"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Brush,
  CheckCheck,
  Crop,
  Download,
  Eraser,
  FileDown,
  HelpCircle,
  Link2,
  Languages,
  MousePointer2,
  Paintbrush,
  PenTool,
  Plus,
  RefreshCw,
  Redo2,
  ScanText,
  SkipForward,
  Trash2,
  Undo2,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { Job, MaskMark, Page, ProjectDetail, TextBlock } from "@/lib/types";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { useToast } from "@/lib/theme";
import { IconBtn, Modal, SplitButton, StatusBadge } from "@/components/ui";
import { parseTranslationText, serializeOcrText, TranslationEntry } from "@/lib/text-transfer";
import { JobBar, useActiveJob } from "@/components/workspace/JobBar";
import { useHistory } from "@/components/workspace/useHistory";
import { CanvasEditor, CanvasTool, CropRect, DEFAULT_BRUSH_WIDTH } from "@/components/workspace/CanvasEditor";
import { AppendPagesModal } from "@/components/workspace/AppendPagesModal";
import { BlockPanel } from "@/components/workspace/BlockPanel";
import { GuideModal } from "@/components/workspace/GuideModal";
import { ChapterImportModal } from "@/components/workspace/ChapterImportModal";

const OCR_VERSIONS = [
  { value: "PP-OCRv6", label: "PP-OCRv6" },
  { value: "PP-OCRv5", label: "PP-OCRv5" },
  { value: "PP-OCRv4", label: "PP-OCRv4" },
  { value: "PP-OCRv3", label: "PP-OCRv3" },
] as const;
const TRANSLATE_PROVIDERS = [
  { value: "openrouter", label: "OpenRouter" },
  { value: "gemini", label: "Gemini" },
  { value: "custom", label: "Custom" },
] as const;
const EXPORT_FORMATS = [
  { value: "pdf", label: "PDF" },
  { value: "zip", label: "ZIP" },
  { value: "psd", label: "PSD" },
] as const;

export default function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { me, loading: authLoading } = useAuth();
  const { t } = useI18n();
  const toast = useToast();

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [blocks, setBlocks] = useState<TextBlock[]>([]);
  const [maskMarks, setMaskMarks] = useState<MaskMark[]>([]);
  // Synchronous mirrors for reading current values inside callbacks
  // (history snapshots, fitted-size compare) without stale closures.
  const blocksRef = useRef<TextBlock[]>([]);
  blocksRef.current = blocks;
  const maskMarksRef = useRef<MaskMark[]>([]);
  maskMarksRef.current = maskMarks;
  // Latest fitted preview font sizes per block (CanvasEditor reports these
  // into a ref — never state — so preview traffic can't re-render the page).
  const fittedSizesRef = useRef<Record<string, number>>({});
  const [canvasTool, setCanvasTool] = useState<CanvasTool>("select");
  // Brush stroke width in image pixels — also the width that gets erased.
  // Persisted per browser so it survives reloads.
  const [brushSize, setBrushSize] = useState<number>(() => {
    try {
      const v = Number(localStorage.getItem("vira.brushSize"));
      return Number.isFinite(v)
        ? Math.min(120, Math.max(4, Math.round(v)))
        : DEFAULT_BRUSH_WIDTH;
    } catch {
      return DEFAULT_BRUSH_WIDTH;
    }
  });
  const changeBrushSize = useCallback((v: number) => {
    const clamped = Math.min(120, Math.max(4, Math.round(v)));
    setBrushSize(clamped);
    try {
      localStorage.setItem("vira.brushSize", String(clamped));
    } catch {
      /* private mode — size still works for this session */
    }
  }, []);
  const [selectedPage, setSelectedPage] = useState(1);
  const railRef = useRef<HTMLDivElement>(null);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  // Extra selected ids beyond the primary selection (Shift+click, marquee).
  // The primary id drives the panel/N-key/Tab flows; `multiIds` only adds
  // canvas group actions (drag-move, delete-all, style paste).
  const [multiIds, setMultiIds] = useState<string[]>([]);
  const [view, setView] = useState<"original" | "cleaned" | "rendered">("original");
  const [ocrVersion, setOcrVersion] = useState<string>("PP-OCRv6");
  const [providerName, setProviderName] = useState<string>("openrouter");
  const [exportFormat, setExportFormat] = useState<"pdf" | "zip" | "psd">("pdf");
  const patchTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const pendingPatches = useRef<Record<string, Partial<TextBlock>>>({});
  const lastSaveFailAt = useRef(0);
  const activePatches = useRef(new Set<Promise<unknown>>());
  const [transferOpen, setTransferOpen] = useState(false);
  const [transferScope, setTransferScope] = useState<"current" | "all">("current");
  const [transferText, setTransferText] = useState("");
  const [transferPreview, setTransferPreview] = useState<{
    entries: (TranslationEntry & { previous: string; page: number; key: string })[];
    skipped: number;
    unchanged: number;
  } | null>(null);
  const [transferConfirmed, setTransferConfirmed] = useState(false);
  const [transferError, setTransferError] = useState("");
  const [transferSaving, setTransferSaving] = useState(false);
  const transferBusy = useRef(false);

  const { job, running, beginJob, cancelJob } = useActiveJob(id);
  const [showLogs, setShowLogs] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [chapterOpen, setChapterOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Page | null>(null);
  const [deletingPage, setDeletingPage] = useState(false);
  const [appendOpen, setAppendOpen] = useState(false);
  const [cropRect, setCropRect] = useState<CropRect | null>(null);
  const [cropConfirm, setCropConfirm] = useState(false);
  const [cropping, setCropping] = useState(false);
  // One-click Finish: when true, each successful job auto-starts the next
  // pipeline step (clean → render → export) until the chain completes.
  const [chaining, setChaining] = useState(false);
  // Undo/redo for session edits (blocks + brush marks). Cleared whenever
  // server-side state regenerates (jobs, crop, append, delete-page).
  const {
    push: pushHistory, undo: undoHistory, redo: redoHistory,
    clear: clearHistory, canUndo, canRedo,
  } = useHistory();

  // After a successful clean/render the result is on another tab — switch to
  // it automatically, otherwise the page looks unchanged ("re-clean does
  // nothing"). Applied once the reloaded project actually has the image.
  const autoViewRef = useRef<null | "cleaned" | "rendered">(null);

  const loadProject = useCallback(async () => {
    try {
      setProject(await api.get<ProjectDetail>(`/api/projects/${id}/`));
    } catch (err) {
      setLoadError(true);
      toast.push(err instanceof Error ? err.message : t("toast.loadFailed"), "error");
    }
  }, [id, t, toast]);

  const loadBlocks = useCallback(async () => {
    try {
      setBlocks(await api.get<TextBlock[]>(`/api/projects/${id}/blocks/`));
    } catch (err) {
      toast.push(err instanceof Error ? err.message : t("toast.loadFailed"), "error");
    }
  }, [id, t, toast]);

  const loadMaskMarks = useCallback(async () => {
    try {
      setMaskMarks(await api.get<MaskMark[]>(`/api/projects/${id}/masks/`));
    } catch {
      /* marks are auxiliary — page still works without them */
    }
  }, [id]);

  useEffect(() => {
    void loadProject();
    void loadBlocks();
    void loadMaskMarks();
  }, [loadProject, loadBlocks, loadMaskMarks]);

  // Send any debounced-but-unsent patches: on unmount (timers die with the
  // component) and before starting a job that regenerates blocks — awaited
  // there so the backend never reads stale geometry/translations.
  const flushPendingPatches = useCallback(async (strict = false) => {
    const pending = Object.entries(pendingPatches.current).map(
      ([blockId, body]) => {
        delete pendingPatches.current[blockId];
        clearTimeout(patchTimers.current[blockId]);
        return api
          .patch(`/api/projects/${id}/blocks/${blockId}/`, body)
          .catch(() => {});
      },
    );
    await Promise.all(pending);
    if (strict) {
      await Promise.all(activePatches.current);
    }
  }, [id]);

  useEffect(() => {
    return () => {
      void flushPendingPatches();
    };
  }, [flushPendingPatches]);

  // Crop selection belongs to one page/view/tool — clear it on any switch.
  useEffect(() => {
    if (canvasTool !== "crop") setCropRect(null);
  }, [canvasTool]);
  useEffect(() => {
    setCropRect(null);
    setCropConfirm(false);
    setMultiIds([]);
  }, [selectedPage, view]);

  // Fully-inside counts for the crop confirm dialog live next to
  // pageBlocks below (they must be declared after it) — see cropStats.
  async function deletePage() {
    if (!deleteTarget || running || deletingPage) return;
    setDeletingPage(true);
    try {
      await flushPendingPatches(true);
      clearHistory();
      await api.delete(`/api/projects/${id}/pages/${deleteTarget.id}`);
      const remaining = (project?.pages ?? []).filter(p => p.id !== deleteTarget.id);
      if (selectedPage === deleteTarget.page_number) {
        setSelectedPage((remaining.find(p => p.page_number > selectedPage) ?? remaining.at(-1))?.page_number ?? 1);
        setSelectedBlockId(null);
      }
      setDeleteTarget(null);
      await Promise.all([loadProject(), loadBlocks(), loadMaskMarks()]);
    } catch (err) {
      toast.push(err instanceof Error ? err.message : t("toast.actionFailed"), "error");
    } finally { setDeletingPage(false); }
  }

  const startAction = useCallback(
    async (path: string, body?: unknown, resetUndo = false) => {
      if (deletingPage || deleteTarget || chapterOpen || appendOpen || cropConfirm || cropping) return;
      autoViewRef.current = null;
      setMultiIds([]); // jobs can regenerate blocks — extras go stale
      // History entries patch by block id: they stay valid across jobs that
      // only produce images (clean/render/apply) or rewrite existing
      // translations (translate). Only jobs that MINT new ids (extract,
      // re-OCR) invalidate them.
      if (resetUndo) clearHistory();
      try {
        // Extract/apply/regenerate blocks server-side; any unsaved edits would
        // either race or be overwritten, so push them out (and wait) first.
        await flushPendingPatches();
        const j = await api.post<Job>(path, body ?? {});
        beginJob(j);
      } catch (err) {
        toast.push(err instanceof Error ? err.message : t("toast.actionFailed"), "error");
      }
    },
    [flushPendingPatches, beginJob, t, toast, deletingPage, deleteTarget, chapterOpen, appendOpen, cropConfirm, cropping, clearHistory],
  );

  // Seed the provider dropdown from the project's translator config once.
  useEffect(() => {
    if (!project) return;
    const p = (project.translator_config as { provider?: string } | null)?.provider;
    if (typeof p === "string" && TRANSLATE_PROVIDERS.some((x) => x.value === p)) {
      setProviderName(p);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per project
  }, [project?.id]);

  const prevJobStatus = useRef<string | null>(null);
  useEffect(() => {
    if (!job) return;
    const prev = prevJobStatus.current;
    prevJobStatus.current = job.status;
    const finished =
      (prev === "running" || prev === "pending") &&
      (job.status === "success" || job.status === "failed" ||
       job.status === "cancelled");
    if (!finished) return;

    void loadProject();
    void loadBlocks();
    void loadMaskMarks();
    if (job.status === "success") {
      toast.push(`${job.kind}: ${t("toast.jobDone")}`, "success");
      // Queue the result tab; the effect below switches once the reloaded
      // project actually carries the new image (avoids a "no image" flash).
      if (job.kind === "clean") autoViewRef.current = "cleaned";
      else if (job.kind === "render") autoViewRef.current = "rendered";
    } else if (!job.error_message?.includes("Cancelled")) {
      toast.push(t("toast.jobFailed"), "error");
    }

    // Finish chain: after each successful step fire the next one; a failure
    // or cancel stops the chain. Backend _start_job only rejects non-terminal
    // jobs, so starting the next step here cannot 409.
    if (!chaining) return;
    if (job.status !== "success") {
      setChaining(false);
      return;
    }
    if (job.kind === "clean") {
      void startAction(`/api/projects/${id}/render/`, {
        chapter_id: project?.chapter_id ?? "",
      });
    } else if (job.kind === "render") {
      void startAction(`/api/projects/${id}/apply/`, {
        chapter_id: project?.chapter_id ?? "",
        formats: [exportFormat],
      });
    } else {
      setChaining(false);
      if (job.kind === "apply") {
        toast.push(t("toast.chainDone"), "success");
      }
    }
  }, [
    job, chaining, startAction, id, project?.chapter_id, exportFormat,
    loadProject, loadBlocks, loadMaskMarks, t, toast,
  ]);

  const pages: Page[] = useMemo(() => project?.pages ?? [], [project]);
  const currentPage = useMemo(
    () => pages.find((p) => p.page_number === selectedPage) ?? pages[0] ?? null,
    [pages, selectedPage],
  );

  useEffect(() => {
    if (pages.length && !pages.some(p => p.page_number === selectedPage)) {
      setSelectedPage(pages[0].page_number);
      setSelectedBlockId(null);
    }
  }, [pages, selectedPage]);

  // Consume a queued result-tab switch once the current page actually has
  // that image. A manual tab click or a new job cancels the queue.
  useEffect(() => {
    const v = autoViewRef.current;
    if (!v || !currentPage) return;
    if (
      (v === "cleaned" && currentPage.cleaned_image_url) ||
      (v === "rendered" && currentPage.rendered_image_url)
    ) {
      setView(v);
      autoViewRef.current = null;
    }
  }, [pages, currentPage]);

  // Keep the selected thumbnail visible (vertical rail + horizontal strip).
  useEffect(() => {
    railRef.current
      ?.querySelector(`[data-page="${selectedPage}"]`)
      ?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }, [selectedPage, pages.length]);

  const eraseMarkLocal = useCallback((markId: string) => {
    setMaskMarks((ms) => ms.filter((m) => m.id !== markId));
  }, []);

  const readdMark = useCallback(async (
    pageNumber: number,
    points: [number, number][],
  ): Promise<string> => {
    const created = await api.post<MaskMark>(`/api/projects/${id}/masks/`, {
      page_number: pageNumber,
      points,
    });
    setMaskMarks((ms) => [...ms, created]);
    return created.id;
  }, [id]);

  const addMaskMark = useCallback(
    async (points: [number, number][]) => {
      if (!currentPage) return;
      const pageNumber = currentPage.page_number;
      try {
        const mid = await readdMark(pageNumber, points);
        // One stroke = one undo step (strokes are discrete gestures).
        const holder = { id: mid };
        pushHistory({
          label: "mark",
          at: Date.now(),
          undo: () => {
            void api.delete(`/api/projects/${id}/masks/${holder.id}/`)
              .then(() => eraseMarkLocal(holder.id))
              .catch(() => {});
          },
          redo: () => {
            void readdMark(pageNumber, points).then((nid) => { holder.id = nid; });
          },
        });
      } catch (err) {
        toast.push(err instanceof Error ? err.message : t("toast.actionFailed"), "error");
      }
    },
    [currentPage, id, pushHistory, readdMark, eraseMarkLocal, t, toast],
  );

  const deleteMaskMark = useCallback(
    async (markId: string) => {
      const snap = maskMarksRef.current.find((m) => m.id === markId);
      // Optimistic: strokes vanish instantly while erasing.
      eraseMarkLocal(markId);
      try {
        await api.delete(`/api/projects/${id}/masks/${markId}/`);
        if (snap) {
          const holder = { id: markId };
          pushHistory({
            label: "unmark",
            at: Date.now(),
            undo: () => {
              void readdMark(snap.page_number, snap.points).then((nid) => { holder.id = nid; });
            },
            redo: () => {
              void api.delete(`/api/projects/${id}/masks/${holder.id}/`)
                .then(() => eraseMarkLocal(holder.id))
                .catch(() => {});
            },
          });
        }
      } catch {
        /* stale erase target — ignore; reload reconciles */
      }
    },
    [id, pushHistory, readdMark, eraseMarkLocal],
  );

  const pageBlocks = useMemo(
    () =>
      blocks
        .filter((b) => b.page_number === (currentPage?.page_number ?? -1))
        .sort((a, b) => a.order - b.order),
    [blocks, currentPage],
  );
  // Block overlay boxes only make sense in the editable Original view —
  // Cleaned/Rendered are proofreading views where boxes would obscure the
  // output. Memoized so the memoized CanvasEditor receives a stable array.
  const canvasBlocks = useMemo(
    () => (view === "original" ? pageBlocks : []),
    [pageBlocks, view],
  );

  // Fully-inside counts for the crop confirm dialog (the backend applies
  // the same rule: anything touching outside is deleted).
  const cropStats = useMemo(() => {
    if (!cropRect) return null;
    const { x1, y1, x2, y2 } = cropRect;
    const kept = pageBlocks.filter(
      (b) => b.x1 >= x1 && b.y1 >= y1 && b.x2 <= x2 && b.y2 <= y2,
    ).length;
    return { kept, removed: pageBlocks.length - kept };
  }, [cropRect, pageBlocks]);

  const cropReady =
    !!cropRect &&
    cropRect.x2 - cropRect.x1 >= 50 &&
    cropRect.y2 - cropRect.y1 >= 50;

  async function applyCrop() {
    if (!currentPage || !cropRect || !cropReady || running || cropping || deletingPage) return;
    setCropConfirm(false);
    setCropping(true);
    try {
      // Unsaved geometry would be clipped/stale server-side — push first.
      await flushPendingPatches(true);
      clearHistory();
      const result = await api.post<{
        width: number; height: number;
        kept_blocks: number; removed_blocks: number;
      }>(`/api/projects/${id}/pages/${currentPage.id}/crop`, cropRect);
      setCropRect(null);
      setCanvasTool("select");
      setSelectedBlockId(null);
      await Promise.all([loadProject(), loadBlocks(), loadMaskMarks()]);
      toast.push(
        t("pages.cropped", { kept: result.kept_blocks, removed: result.removed_blocks }),
        "success",
      );
    } catch (err) {
      toast.push(err instanceof Error ? err.message : t("toast.actionFailed"), "error");
    } finally {
      setCropping(false);
    }
  }

  /**
   * Raw optimistic update + debounced PATCH. Records nothing — undo/redo and
   * patchBlockLocal below both funnel through here.
   */
  const applyPatch = useCallback(
    (blockId: string, patch: Partial<TextBlock>) => {
      if (!blocksRef.current.some((b) => b.id === blockId)) return;
      // Live counter: a translation crossing the empty↔filled boundary moves
      // project.translated_count immediately, so the Render gate and the
      // "x/total" readout react to typing without waiting for a job or a
      // refetch. The debounced PATCH refreshes the server-side counts to match.
      const cur = blocksRef.current.find((b) => b.id === blockId);
      if (cur && typeof patch.translation === "string") {
        const was = cur.translation.trim() !== "";
        const now = patch.translation.trim() !== "";
        if (was !== now) {
          setProject((p) =>
            p
              ? { ...p, translated_count: Math.max(0, p.translated_count + (now ? 1 : -1)) }
              : p,
          );
        }
      }
      setBlocks((bs) => bs.map((b) => (b.id === blockId ? { ...b, ...patch } : b)));
      pendingPatches.current[blockId] = {
        ...pendingPatches.current[blockId],
        ...patch,
      };
      clearTimeout(patchTimers.current[blockId]);
      patchTimers.current[blockId] = setTimeout(() => {
        const body = pendingPatches.current[blockId];
        delete pendingPatches.current[blockId];
        if (!body) return;
        const request = api
          .patch(`/api/projects/${id}/blocks/${blockId}/`, body)
          .catch(() => {
            // Failed saves must be visible — this is the user's translation work.
            // Throttle to one toast per 5s so a drag burst doesn't spam.
            const now = Date.now();
            if (now - lastSaveFailAt.current > 5000) {
              lastSaveFailAt.current = now;
              toast.push(t("toast.saveFailed"), "error");
            }
          });
        activePatches.current.add(request);
      }, 500);
    },
    [id, t, toast],
  );

  /**
   * applyPatch + one history step. Successive patches to the same block are
   * MERGED, not replaced — otherwise "resize then type within 500ms" would
   * drop the geometry PATCH entirely. Rapid patches to the same block also
   * coalesce into a single undo step (whole drag / typing burst = one Z).
   * useCallback so memoized children (CanvasEditor/BlockPanel) receive a
   * stable prop and can actually skip re-renders.
   */
  const patchBlockLocal = useCallback(
    (blockId: string, patch: Partial<TextBlock>, opts?: { history?: boolean }) => {
      const cur = blocksRef.current.find((b) => b.id === blockId);
      const prev: Partial<TextBlock> = {};
      let changed = false;
      if (cur) {
        for (const k of Object.keys(patch) as (keyof TextBlock)[]) {
          if (cur[k] !== patch[k]) {
            (prev as Record<string, unknown>)[k] = cur[k];
            changed = true;
          }
        }
      }
      applyPatch(blockId, patch);
      if (!changed || opts?.history === false) return;
      const snap = { ...patch };
      pushHistory(
        {
          label: "edit",
          at: Date.now(),
          mergeKey: `block:${blockId}`,
          undo: () => applyPatch(blockId, prev),
          redo: () => applyPatch(blockId, snap),
        },
        1500,
      );
    },
    [applyPatch, pushHistory],
  );

  const commitTranslation = useCallback(
    (blockId: string, text: string) => {
      const cur = blocksRef.current.find((b) => b.id === blockId);
      if (cur && cur.translation !== text) {
        patchBlockLocal(blockId, { translation: text });
      }
      // Persist the preview's fitted size with the text, so the rendered
      // page uses the size shown on the canvas (not a stale/auto one).
      const fitted = fittedSizesRef.current[blockId];
      if (typeof fitted === "number" && cur && fitted !== cur.font_size_override) {
        patchBlockLocal(blockId, { font_size_override: fitted });
      }
    },
    [patchBlockLocal],
  );

  const reportPreviewSizes = useCallback((sizes: Record<string, number>) => {
    fittedSizesRef.current = sizes;
  }, []);

  // Drop any queued-but-unsent PATCH for a block that is going away —
  // otherwise the timer fires a 404 (or a saveFailed toast) after delete.
  const dropPendingPatch = useCallback((blockId: string) => {
    delete pendingPatches.current[blockId];
    clearTimeout(patchTimers.current[blockId]);
    delete patchTimers.current[blockId];
  }, []);

  const removeBlockLocal = useCallback((blockId: string) => {
    const removed = blocksRef.current.find((b) => b.id === blockId);
    const wasTranslated = !!removed && removed.translation.trim() !== "";
    dropPendingPatch(blockId);
    setBlocks((bs) => bs.filter((b) => b.id !== blockId));
    setSelectedBlockId((sel) => (sel === blockId ? null : sel));
    // Live counter: the server already adjusted total/translated counts
    // (DELETE refreshes them), so the local project keeps pace.
    setProject((p) =>
      p
        ? {
            ...p,
            total_blocks: Math.max(0, p.total_blocks - 1),
            translated_count: Math.max(0, p.translated_count - (wasTranslated ? 1 : 0)),
          }
        : p,
    );
  }, [dropPendingPatch]);

  // Re-create a block from a snapshot (undo of delete / redo of add).
  // Returns the new id. Server mints a fresh id/key — geometry, text and
  // style are restored, which is what matters.
  const restoreBlock = useCallback(async (snap: TextBlock): Promise<string> => {
    const created = await api.post<TextBlock>(`/api/projects/${id}/blocks/`, {
      page_number: snap.page_number,
      original_text: snap.original_text,
      translation: snap.translation,
      block_type: snap.block_type,
      x1: snap.x1, y1: snap.y1, x2: snap.x2, y2: snap.y2,
    });
    setBlocks((bs) => [...bs, created]);
    // Live counter: the created block already carries its old translation,
    // and the server-side create refreshed its own counts — mirror that.
    setProject((p) =>
      p
        ? {
            ...p,
            total_blocks: p.total_blocks + 1,
            translated_count: created.translation.trim() !== ""
              ? p.translated_count + 1
              : p.translated_count,
          }
        : p,
    );
    const { id: _omit, key: _key, page_number: _pn, order: _order,
      is_translated: _tr, ...rest } = snap;
    void _omit; void _key; void _pn; void _order; void _tr;
    applyPatch(created.id, rest);
    return created.id;
  }, [id, applyPatch]);

  const deleteBlockById = useCallback(async (blockId: string) => {
    const snap = blocksRef.current.find((b) => b.id === blockId);
    try {
      await api.delete(`/api/projects/${id}/blocks/${blockId}/`);
      removeBlockLocal(blockId);
      if (snap) {
        const holder = { id: blockId };
        pushHistory({
          label: "delete",
          at: Date.now(),
          undo: () => {
            void restoreBlock(snap).then((nid) => { holder.id = nid; });
          },
          redo: () => {
            void api.delete(`/api/projects/${id}/blocks/${holder.id}/`)
              .then(() => removeBlockLocal(holder.id))
              .catch(() => {});
          },
        });
      }
    } catch (err) {
      toast.push(err instanceof Error ? err.message : t("toast.deleteFailed"), "error");
    }
  }, [id, pushHistory, removeBlockLocal, restoreBlock, t, toast]);

  const addBlock = useCallback(
    async (x1: number, y1: number, x2: number, y2: number) => {
      if (!currentPage) return;
      try {
        const created = await api.post<TextBlock>(`/api/projects/${id}/blocks/`, {
          page_number: currentPage.page_number,
          x1,
          y1,
          x2,
          y2,
        });
        setBlocks((bs) => [...bs, created]);
        setSelectedBlockId(created.id);
        const snap = created;
        const holder = { id: created.id };
        pushHistory({
          label: "add",
          at: Date.now(),
          undo: () => {
            void api.delete(`/api/projects/${id}/blocks/${holder.id}/`)
              .then(() => removeBlockLocal(holder.id))
              .catch(() => {});
          },
          redo: () => {
            void restoreBlock(snap).then((nid) => {
              holder.id = nid;
              setSelectedBlockId(nid);
            });
          },
        });
      } catch (err) {
        toast.push(err instanceof Error ? err.message : t("toast.actionFailed"), "error");
      }
    },
    [currentPage, id, pushHistory, removeBlockLocal, restoreBlock, t, toast],
  );

  const deleteSelectedBlock = useCallback(async () => {
    if (!selectedBlockId) return;
    await deleteBlockById(selectedBlockId);
  }, [selectedBlockId, deleteBlockById]);

  // Undo/redo: flush unsent edits first so the inverse applies on top of
  // saved state (and re-queues itself to the server via applyPatch).
  // Blocked while a job/mutation runs — server state is regenerating.
  const doUndo = useCallback(async () => {
    if (running || deletingPage || cropping) return;
    await flushPendingPatches(true);
    undoHistory();
  }, [running, deletingPage, cropping, flushPendingPatches, undoHistory]);
  const doRedo = useCallback(async () => {
    if (running || deletingPage || cropping) return;
    await flushPendingPatches(true);
    redoHistory();
  }, [running, deletingPage, cropping, flushPendingPatches, redoHistory]);

  // Ordered cycle through this page's untranslated blocks; wraps so repeated
  // presses always land somewhere useful. -1 index (nothing selected or
  // selected block already translated) falls through to the first one.
  const hasUntranslated = useMemo(
    () => pageBlocks.some((b) => !b.translation.trim()),
    [pageBlocks],
  );
  const gotoNextUntranslated = useCallback(() => {
    const untranslated = pageBlocks.filter((b) => !b.translation.trim());
    if (!untranslated.length) return;
    const idx = untranslated.findIndex((b) => b.id === selectedBlockId);
    setSelectedBlockId(untranslated[(idx + 1) % untranslated.length].id);
  }, [pageBlocks, selectedBlockId]);

  // ── Multi-select ──────────────────────────────────────────────────────
  // Visual selection = [primary, ...multiIds]. Handlers mirror CanvasEditor.
  const selectOnly = useCallback((id: string | null) => {
    setSelectedBlockId(id);
    setMultiIds([]);
  }, []);

  // ── Style copy/paste ──────────────────────────────────────────────────
  const STYLE_KEYS = ["font_override", "font_size_override", "color", "alignment", "rotation"] as const;
  type StyleFields = Pick<TextBlock, (typeof STYLE_KEYS)[number]>;
  const [styleClipboard, setStyleClipboard] = useState<StyleFields | null>(null);

  const copyStyle = useCallback((blockId: string) => {
    const b = blocksRef.current.find((x) => x.id === blockId);
    if (!b) return;
    setStyleClipboard({
      font_override: b.font_override,
      font_size_override: b.font_size_override,
      color: b.color,
      alignment: b.alignment,
      rotation: b.rotation,
    });
    toast.push(t("ws.styleCopied"), "success");
  }, [t, toast]);

  const pasteStyle = useCallback((ids: string[]) => {
    if (!styleClipboard) {
      toast.push(t("ws.nothingToPaste"), "info");
      return;
    }
    let changed = 0;
    const prevMap = new Map<string, Partial<TextBlock>>();
    const nextMap = new Map<string, Partial<TextBlock>>();
    for (const bid of ids) {
      const b = blocksRef.current.find((x) => x.id === bid);
      if (!b) continue;
      const prev: Partial<TextBlock> = {};
      let blockChanged = false;
      for (const k of STYLE_KEYS) {
        if (b[k] !== styleClipboard[k]) {
          (prev as Record<string, unknown>)[k] = b[k];
          blockChanged = true;
        }
      }
      if (!blockChanged) continue;
      changed++;
      prevMap.set(bid, prev);
      nextMap.set(bid, { ...styleClipboard });
      patchBlockLocal(bid, { ...styleClipboard }, { history: false });
    }
    if (!changed) return;
    pushHistory({
      label: "style",
      at: Date.now(),
      undo: () => { for (const [bid, p] of prevMap) applyPatch(bid, p); },
      redo: () => { for (const [bid, p] of nextMap) applyPatch(bid, p); },
    });
    toast.push(t("ws.stylePasted"), "success");
  }, [styleClipboard, patchBlockLocal, applyPatch, pushHistory, t, toast]);

  const pasteStyleToSelection = useCallback(() => {
    pasteStyle(selectedBlockId ? [selectedBlockId, ...multiIds] : [...multiIds]);
  }, [selectedBlockId, multiIds, pasteStyle]);

  const pasteStyleToPage = useCallback(() => {
    pasteStyle(pageBlocks.map((b) => b.id));
  }, [pageBlocks, pasteStyle]);

  // Selecting from the panel (or N-key) must reveal the box: tall pages in
  // zoomed mode can put it far outside the visible scroll area.

  // Tab-through-dialogs: bumping this tick focuses the primary block's
  // panel textarea (panel effect) after the selection moves.
  const [panelFocusTick, setPanelFocusTick] = useState(0);

  const gotoNeighborBlock = useCallback((dir: 1 | -1) => {
    if (!pageBlocks.length) return;
    const idx = pageBlocks.findIndex((b) => b.id === selectedBlockId);
    const next = pageBlocks[(idx + dir + pageBlocks.length) % pageBlocks.length];
    setSelectedBlockId(next.id);
    setPanelFocusTick((v) => v + 1);
  }, [pageBlocks, selectedBlockId]);

  const tabFromCanvas = useCallback(
    (_id: string, dir: 1 | -1) => gotoNeighborBlock(dir),
    [gotoNeighborBlock],
  );

  const setActiveSelection = useCallback((ids: string[]) => {
    const [primary, ...rest] = ids;
    setSelectedBlockId(primary ?? null);
    setMultiIds(rest);
  }, []);

  const toggleSelectBlock = useCallback((id: string) => {
    const current = new Set(selectedBlockId ? [selectedBlockId, ...multiIds] : []);
    if (current.has(id)) {
      current.delete(id);
      // If the primary left the set, promote the first remaining id.
      if (id === selectedBlockId) {
        const nextPrimary = [...current][0] ?? null;
        current.delete(nextPrimary as string);
        setActiveSelection(
          nextPrimary ? [nextPrimary as string, ...[...current]] : [],
        );
      } else {
        setActiveSelection([selectedBlockId as string, ...[...current]]);
      }
    } else {
      current.add(id);
      setActiveSelection([...current]);
    }
  }, [selectedBlockId, multiIds, setActiveSelection]);

  const marqueeSelect = useCallback((rect: { x1: number; y1: number; x2: number; y2: number }) => {
    const hits = blocksRef.current
      .filter((b) =>
        b.page_number === (currentPage?.page_number ?? -1) &&
        b.x2 > rect.x1 && b.x1 < rect.x2 && b.y2 > rect.y1 && b.y1 < rect.y2)
      .sort((a, b) => a.order - b.order);
    if (!hits.length) return;
    setActiveSelection(hits.map((h) => h.id));
  }, [currentPage, setActiveSelection]);

  const clearSelection = useCallback(() => selectOnly(null), [selectOnly]);

  const selectBlockFromCanvas = useCallback((bid: string, additive: boolean) => {
    if (additive) toggleSelectBlock(bid);
    else selectOnly(bid);
  }, [toggleSelectBlock, selectOnly]);

  const deleteMulti = useCallback(async () => {
    const ids = selectedBlockId ? [selectedBlockId, ...multiIds] : [...multiIds];
    if (!ids.length) return;
    await flushPendingPatches();
    await Promise.all(ids.map((bid) => deleteBlockById(bid)));
    selectOnly(null);
  }, [selectedBlockId, multiIds, flushPendingPatches, deleteBlockById, selectOnly]);

  // Arrow-key nudging of the whole visual selection; one merged history
  // entry across bursts. ←/→ page nav happens only when nothing selected.
  const nudgeSelection = useCallback((dx: number, dy: number) => {
    const ids = selectedBlockId ? [selectedBlockId, ...multiIds] : [...multiIds];
    if ((!dx && !dy) || !ids.length || !currentPage) return;
    const prevs = new Map<string, { x1: number; y1: number; x2: number; y2: number }>();
    const nexts = new Map<string, { x1: number; y1: number; x2: number; y2: number }>();
    for (const bid of ids) {
      const b = blocksRef.current.find((x) => x.id === bid);
      if (!b) continue;
      const w = b.x2 - b.x1;
      const h = b.y2 - b.y1;
      const nx1 = Math.max(0, Math.round(Math.min(b.x1 + dx, currentPage.width - w)));
      const ny1 = Math.max(0, Math.round(Math.min(b.y1 + dy, currentPage.height - h)));
      prevs.set(bid, { x1: b.x1, y1: b.y1, x2: b.x2, y2: b.y2 });
      nexts.set(bid, { x1: nx1, y1: ny1, x2: nx1 + w, y2: ny1 + h });
      applyPatch(bid, { x1: nx1, y1: ny1, x2: nx1 + w, y2: ny1 + h });
    }
    if (!prevs.size) return;
    pushHistory({
      label: "move",
      at: Date.now(),
      mergeKey: "nudge",
      undo: () => { for (const [bid, g] of prevs) applyPatch(bid, g); },
      redo: () => { for (const [bid, g] of nexts) applyPatch(bid, g); },
    }, 700);
  }, [selectedBlockId, multiIds, currentPage, applyPatch, pushHistory]);

  const scopeBlocks = useMemo(
    () =>
      transferScope === "current"
        ? blocks.filter((b) => b.page_number === (currentPage?.page_number ?? -1))
        : blocks,
    [blocks, transferScope, currentPage],
  );

  const exportOcrText = useCallback(() => {
    const text = serializeOcrText(id as string, scopeBlocks);
    const blob = new Blob([text], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `translations-${id}-${transferScope === "current" ? `p${currentPage?.page_number ?? 1}` : "all"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [id, scopeBlocks, transferScope, currentPage]);

  const invalidatePreview = useCallback(() => {
    setTransferPreview(null);
    setTransferConfirmed(false);
    setTransferError("");
  }, []);

  const previewImport = useCallback(() => {
    try {
      const { entries, skipped } = parseTranslationText(
        transferText,
        id as string,
        scopeBlocks,
      );
      const byId = new Map(scopeBlocks.map((b) => [b.id, b]));
      setTransferPreview({
        entries: entries.map((e) => {
          const b = byId.get(e.id)!;
          return { ...e, previous: b.translation, page: b.page_number, key: b.key };
        }),
        skipped,
        unchanged: entries.filter((e) => byId.get(e.id)!.translation.trim() === e.translation.trim()).length,
      });
      setTransferConfirmed(false);
      setTransferError("");
    } catch (err) {
      setTransferPreview(null);
      setTransferConfirmed(false);
      setTransferError(
        err instanceof Error && ["format", "project", "duplicate", "unknown"].includes(err.message)
          ? t(`transfer.${err.message}` as Parameters<typeof t>[0])
          : t("transfer.format"),
      );
    }
  }, [transferText, id, scopeBlocks, t]);

  const applyImport = useCallback(async () => {
    if (!transferPreview || transferSaving || transferBusy.current) return;
    transferBusy.current = true;
    setTransferSaving(true);
    const failed: string[] = [];
    try {
      await flushPendingPatches(true);
      const byId = new Map(scopeBlocks.map((b) => [b.id, b]));
      const changed: { id: string; prev: string; next: string }[] = [];
      for (const entry of transferPreview.entries) {
        const b = byId.get(entry.id);
        if (!b) throw new Error("stale");
        if (b.translation.trim() === entry.translation.trim()) continue;
        changed.push({ id: entry.id, prev: b.translation, next: entry.translation });
        setBlocks((bs) => bs.map((x) => (x.id === entry.id ? { ...x, translation: entry.translation } : x)));
        try {
          await api.patch(`/api/projects/${id}/blocks/${entry.id}/`, { translation: entry.translation });
        } catch {
          failed.push(entry.id);
        }
      }
      if (failed.length) {
        toast.push(t("transfer.failed"), "error");
        const failedSet = new Set(failed);
        setTransferPreview({
          entries: transferPreview.entries.filter((e) => failedSet.has(e.id)),
          skipped: 0,
          unchanged: 0,
        });
        setTransferConfirmed(false);
      } else {
        setTransferOpen(false);
        setTransferText("");
        invalidatePreview();
        toast.push(t("transfer.saved"), "success");
        if (changed.length) {
          // One undo step for the whole import (only fully-saved rows).
          const ok = changed.filter((c) => !failed.includes(c.id));
          if (ok.length) {
            pushHistory({
              label: "import",
              at: Date.now(),
              undo: () => { for (const c of ok) applyPatch(c.id, { translation: c.prev }); },
              redo: () => { for (const c of ok) applyPatch(c.id, { translation: c.next }); },
            });
          }
        }
      }
      void loadProject();
    } catch (err) {
      if (err instanceof Error && err.message === "stale") {
        toast.push(t("transfer.stale"), "error");
      } else {
        toast.push(t("transfer.failed"), "error");
      }
    } finally {
      transferBusy.current = false;
      setTransferSaving(false);
    }
  }, [transferPreview, transferSaving, flushPendingPatches, scopeBlocks, id, t, toast, invalidatePreview, loadProject, applyPatch, pushHistory]);

  // Translate only the current page's untranslated blocks — backend accepts
  // block_ids, so re-doing one page never re-translates the project.
  const translatePage = useCallback(async () => {
    const ids = pageBlocks.filter((b) => !b.translation.trim()).map((b) => b.id);
    if (!ids.length) return;
    try {
      await flushPendingPatches();
      // No clearHistory: translate rewrites existing blocks by id — undo
      // entries stay valid (Ctrl+Z restores pre-translation text).
      const j = await api.post<Job>(`/api/projects/${id}/translate/`, {
        block_ids: ids,
        force: false,
        provider: providerName,
      });
      beginJob(j);
    } catch (err) {
      toast.push(err instanceof Error ? err.message : t("toast.actionFailed"), "error");
    }
  }, [pageBlocks, id, providerName, flushPendingPatches, beginJob, t, toast]);

  // Keyboard shortcuts: pages/views/delete/tool/undo. Native undo keeps
  // working inside inputs — app-level Ctrl+Z/Y only fires outside them
  // (Persian textareas are primary surfaces here).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const editable = !!target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.isComposing) {
        const k = e.key.toLowerCase();
        if (!editable && (k === "z" || k === "y")) {
          // Ctrl+Z = undo, Ctrl+Shift+Z / Ctrl+Y = redo.
          e.preventDefault();
          if (k === "y" || e.shiftKey) void doRedo();
          else void doUndo();
          return;
        }
      }
      // Tab / Shift+Tab: cycle dialogs. Acts when focus is outside inputs,
      // or inside a panel textarea (the usual "write → Tab → write" flow).
      // IME composing passes through untouched.
      const inPanelEditable = editable && !!target?.closest?.("[data-panel]");
      if (e.key === "Tab" && !e.isComposing && (inPanelEditable || !editable)) {
        e.preventDefault();
        // Tabbing away from a panel textarea commits what was typed here,
        // not later on blur (focus moves before the blur handler runs).
        if (inPanelEditable) {
          const holder = target?.closest?.("[data-block]");
          const bid = holder?.getAttribute("data-block") ?? null;
          const ta = target as HTMLTextAreaElement;
          if (bid && ta?.value !== undefined) commitTranslation(bid, ta.value);
        }
        gotoNeighborBlock(e.shiftKey ? -1 : 1);
        return;
      }
      if (editable) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (!pages.length) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        if (selectedBlockId || multiIds.length) {
          // Selection exists: arrows nudge it (Shift = 10px); pages switch
          // only when nothing is selected.
          const step = e.shiftKey ? 10 : 1;
          const dx = e.key === "ArrowRight" ? step : e.key === "ArrowLeft" ? -step : 0;
          const dy = e.key === "ArrowDown" ? step : e.key === "ArrowUp" ? -step : 0;
          void nudgeSelection(dx, dy);
          return;
        }
        const idx = pages.findIndex((p) => p.page_number === selectedPage);
        const delta = e.key === "ArrowRight" ? 1 : -1;
        const next = pages[Math.min(Math.max(idx + delta, 0), pages.length - 1)];
        if (next) setSelectedPage(next.page_number);
      } else if (e.key === "1" || e.key === "2" || e.key === "3") {
        const v = e.key === "1" ? "original" : e.key === "2" ? "cleaned" : "rendered";
        const cur = pages.find((p) => p.page_number === selectedPage);
        const ok =
          v === "original" ||
          (v === "cleaned" && cur?.cleaned_image_url) ||
          (v === "rendered" && cur?.rendered_image_url);
        if (ok) setView(v);
      } else if (e.key === "Delete" && (selectedBlockId || multiIds.length)) {
        if (multiIds.length) void deleteMulti();
        else void deleteSelectedBlock();
      } else if (e.key === "n" || e.key === "N") {
        gotoNextUntranslated();
      } else if (e.key === "Escape") {
        setCanvasTool("select");
        setCropRect(null);
        if (multiIds.length) setMultiIds([]);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pages, selectedPage, selectedBlockId, multiIds, deleteMulti, deleteSelectedBlock, nudgeSelection, gotoNextUntranslated, gotoNeighborBlock, commitTranslation, doUndo, doRedo]);

  // Cache-bust every page image with the project's last-change timestamp so
  // re-extracts / cleans / renders show up instantly instead of serving the
  // browser's cached copy (which made blocks appear misaligned).
  // Kept above the loading early-return — Rules of Hooks.
  const bust = useCallback(
    (url: string | null | undefined): string | undefined => {
      if (!url) return undefined;
      const v = project?.updated_at ?? job?.finished_at ?? null;
      return v ? `${url}?v=${encodeURIComponent(v)}` : url;
    },
    [project?.updated_at, job?.finished_at],
  );

  if (authLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center text-muted">
        {t("common.loading")}
      </main>
    );
  }

  if (loadError && !project) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 text-muted">
        <p>{t("ws.notFound")}</p>
        <Link href="/projects" className="btn btn-ghost px-4 py-2 text-sm">
          {t("ws.backToProjects")}
        </Link>
      </main>
    );
  }

  if (!project) {
    return (
      <main className="flex min-h-screen items-center justify-center text-muted">
        {t("common.loading")}
      </main>
    );
  }

  const canTranslate = project.total_blocks > 0 && !running;

  // Pipeline gating: clean → render → export, each step unlocking the next.
  // "Done" is read from the saved artifacts (cleaned/rendered page images),
  // so re-opening a fully processed project keeps every step available.
  // Clean has nothing to erase when no non-SFX block is translated and no
  // freehand marks exist — treat it as done so Render/Export don't dead-end.
  const cleanHasWork =
    blocks.some((b) => b.translation.trim() && b.block_type !== "sfx") ||
    maskMarks.length > 0;
  const cleanDone = pages.some((p) => p.cleaned_image_url) || !cleanHasWork;
  const renderDone = pages.some((p) => p.rendered_image_url);

  // Reason-aware tooltips: a locked button explains what to do next.
  const cleanTitle = !pages.length ? t("ws.needExtract") : t("ws.clean");
  const renderTitle = running
    ? t("ws.jobRunning")
    : !cleanDone
      ? t("ws.needClean")
      : project.translated_count === 0
        ? t("ws.needTranslate")
        : t("ws.render");
  const exportTitle = running
    ? t("ws.jobRunning")
    : !renderDone
      ? t("ws.needRender")
      : t("ws.export");

  return (
    <main className="flex min-h-screen flex-col bg-base p-3 [--radius-btn:6px] lg:h-dvh lg:min-h-0 lg:overflow-hidden lg:p-4">
      <header className="mb-3 flex shrink-0 flex-wrap items-center gap-3 border-b border-line pb-3">
        <button
          onClick={() => router.push("/projects")}
          className="btn btn-ghost h-9 w-9 !rounded-xl p-0"
          aria-label={t("nav.back")}
          title={t("nav.back")}
        >
          <ArrowLeft size={16} className="rtl:rotate-180" />
        </button>
        <h1 className="min-w-0 flex-1 truncate text-base font-bold text-white dark:text-white sm:flex-none sm:max-w-[30vw] [.light_&]:text-neutral-900" title={project.name}>{project.name}</h1>
        <StatusBadge status={project.status} />
        <div className="hidden items-center gap-1.5 sm:flex">
          <span className="chip">{project.total_pages} {t("dash.pages")}</span>
          <span className="chip">{project.total_blocks} {t("dash.blocks")}</span>
          <span className="chip">
            {project.translated_count}/{project.total_blocks}
          </span>
        </div>

        <div className="ms-auto flex items-center gap-2">
          <IconBtn label={t("ws.guide")} onClick={() => setGuideOpen(true)}>
            <HelpCircle size={16} />
          </IconBtn>
          <SplitButton
            icon={<FileDown size={14} />}
            label={t("ws.export")}
            menuLabel={t("ws.format")}
            variant="primary"
            disabled={running || !renderDone}
            title={exportTitle}
            options={EXPORT_FORMATS}
            value={exportFormat}
            onValueChange={(v) => setExportFormat(v as "pdf" | "zip" | "psd")}
            onClick={() =>
              void startAction(`/api/projects/${id}/apply/`, {
                chapter_id: project.chapter_id,
                formats: [exportFormat],
              })
            }
          />
        </div>
      </header>

      <div className="mb-3 flex shrink-0 flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {/* Extract pages + OCR engine version */}
          <SplitButton
            icon={<ScanText size={14} />}
            label={t("ws.extractPages")}
            menuLabel={t("ws.ocrEngine")}
            variant="ghost"
            disabled={running}
            options={OCR_VERSIONS}
            value={ocrVersion}
            onValueChange={setOcrVersion}
            onClick={() =>
              void startAction(
                `/api/projects/${id}/extract/`,
                {
                  pdf_type: project.pdf_type,
                  ocr_version: ocrVersion,
                },
                true, // extract mints new block ids — history can't survive
              )
            }
          />

          {/* Translate all + provider */}
          <SplitButton
            icon={<Languages size={14} />}
            label={t("ws.translateAll")}
            menuLabel={t("ws.provider")}
            variant="ghost"
            disabled={!canTranslate}
            options={TRANSLATE_PROVIDERS}
            value={providerName}
            onValueChange={setProviderName}
            onClick={() =>
              void startAction(`/api/projects/${id}/translate/`, {
                force: true,
                provider: providerName,
              })
            }
          />

          {/* Clean (inpaint originals away) */}
          <button
            onClick={() => void startAction(`/api/projects/${id}/clean/`, {})}
            disabled={running || !pages.length}
            className="btn btn-ghost h-9 px-3.5 text-sm"
            title={cleanTitle}
          >
            <Brush size={14} />
            {t("ws.clean")}
          </button>

          {/* Render text — unlocked once pages are cleaned */}
          <button
            onClick={() =>
              void startAction(`/api/projects/${id}/render/`, {
                chapter_id: project.chapter_id,
              })
            }
            disabled={running || !cleanDone || project.translated_count === 0}
            className="btn btn-ghost h-9 px-3.5 text-sm"
            title={renderTitle}
          >
            <PenTool size={14} />
            {t("ws.render")}
          </button>

        </div>
        <div className="ms-auto flex flex-wrap items-center gap-2 border-s border-line ps-2">
          <button
            onClick={() => setChapterOpen(true)}
            disabled={running}
            className="btn btn-ghost h-9 px-3.5 text-sm"
            title={t("pages.link")}
          >
            <Link2 size={14} />
            {t("pages.link")}
          </button>
          {/* Finish — auto-run the remaining pipeline steps clean → render →
              export, starting from the first incomplete stage. Any failure or
              cancel stops the chain (see the job-finish effect). */}
          <button
            onClick={() => {
              setChaining(true);
              if (!cleanDone) {
                void startAction(`/api/projects/${id}/clean/`, {});
              } else if (!renderDone) {
                void startAction(`/api/projects/${id}/render/`, {
                  chapter_id: project.chapter_id,
                });
              } else {
                void startAction(`/api/projects/${id}/apply/`, {
                  chapter_id: project.chapter_id,
                  formats: [exportFormat],
                });
              }
            }}
            disabled={running || !pages.length || project.translated_count === 0}
            className="btn btn-ghost h-9 px-3.5 text-sm"
            title={t("ws.finishHint")}
          >
            <CheckCheck size={14} />
            {chaining ? t("ws.finishing") : t("ws.finish")}
          </button>

          {/* OCR text export / translation import */}
          <button
            onClick={() => {
              invalidatePreview();
              setTransferOpen(true);
            }}
            disabled={running || !blocks.length}
            className="btn btn-ghost h-9 px-3.5 text-sm"
            title={t("transfer.title")}
          >
            <FileDown size={14} />
            {t("transfer.import")}
          </button>

        </div>
      </div>

      <JobBar job={job} running={running} showLogs={showLogs} setShowLogs={setShowLogs} onCancel={cancelJob} />

      {job?.status === "success" && (job.result?.files?.length ?? 0) > 0 && (
        <div className="card anim-pop mb-3 flex flex-wrap items-center gap-2.5 p-3">
          <span className="text-xs font-bold uppercase tracking-wider text-success">
            {t("ws.exportsReady")}
          </span>
          {(job.result?.files ?? []).map((f) => (
            <a
              key={f.url}
              href={f.url}
              download
              className="btn btn-outline px-3 py-1.5 text-xs"
            >
              <Download size={13} />
              {f.name}
            </a>
          ))}
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[88px_minmax(0,1fr)_minmax(320px,360px)] xl:grid-cols-[104px_minmax(0,1fr)_380px]">
        {/* Page rail — horizontal filmstrip below lg, vertical rail at lg+ */}
        <aside className="group/rail flex min-h-0 min-w-0 flex-col rounded-xl border border-line bg-surface p-2 max-lg:order-first">
          {/* Jump controls (lg+ only; the filmstrip scrolls instead) */}
          <div className="mb-2 hidden items-center justify-between gap-2 lg:flex">
            <span className="whitespace-nowrap text-[11px] font-bold text-muted">
              {t("ws.page")} {currentPage ? pages.indexOf(currentPage) + 1 : "-"}/{pages.length || "-"}
            </span>
            <button
              onClick={() => setAppendOpen(true)}
              disabled={running}
              className="btn btn-ghost p-1.5"
              title={t("pages.addPages")}
              aria-label={t("pages.addPages")}
            >
              <Plus size={13} />
            </button>
          </div>
          <div
            ref={railRef}
            className="flex flex-1 gap-2 max-h-full overflow-y-auto max-lg:overflow-x-auto p-1 max-lg:pb-1 lg:min-h-0 lg:flex-col"
          >
            {pages.map((p) => (
              <div
                key={p.id}
                className="relative w-20 shrink-0 lg:w-full"
              >
              <button
                data-page={p.page_number}
                onClick={() => setSelectedPage(p.page_number)}
                title={`${t("ws.page")} ${p.page_number}`}
                className={`relative block w-full overflow-hidden rounded-lg ring-2 transition-all ${
                  p.page_number === selectedPage
                    ? "ring-primary"
                    : "ring-transparent opacity-65 hover:opacity-100"
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={bust(p.image_url)}
                  width={p.width}
                  height={p.height}
                  alt={`p${p.page_number}`}
                  className="w-full"
                  loading="lazy"
                />
                <span className="absolute start-0 top-0 ltr:rounded-br-lg rtl:rounded-bl-lg bg-black/70 px-1.5 py-0.5 text-[10px] font-bold text-white">
                  {p.page_number}
                </span>
                {p.block_count > 0 && (
                  <span
                    className={`absolute bottom-0 end-0 ltr:rounded-tl-lg rtl:rounded-tr-lg bg-black/70 px-1.5 py-0.5 text-[10px] font-bold ${
                      p.translated_count === p.block_count
                        ? "text-success"
                        : "text-white"
                    }`}
                  >
                    {p.translated_count}/{p.block_count}
                  </span>
                )}
                {/* Pipeline state dots: cleaned (sky) + rendered (emerald) */}
                {(p.cleaned_image_url || p.rendered_image_url) && (
                  <span className="absolute bottom-0 start-0 flex items-center gap-1 bg-black/70 px-1.5 py-1 ltr:rounded-tr-lg rtl:rounded-tl-lg">
                    {p.cleaned_image_url && (
                      <span
                        title={t("ws.cleaned")}
                        className="h-1.5 w-1.5 rounded-full bg-sky-400"
                      />
                    )}
                    {p.rendered_image_url && (
                      <span
                        title={t("ws.rendered")}
                        className="h-1.5 w-1.5 rounded-full bg-emerald-400"
                      />
                    )}
                  </span>
                )}
              </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setDeleteTarget(p); }}
                  title={t("pages.delete")}
                  aria-label={`${t("pages.delete")} ${p.page_number}`}
                  disabled={running || deletingPage}
                  className="absolute top-1 end-1 z-10 rounded-md bg-black/70 p-1 text-white/80 transition-opacity hover:text-danger focus-visible:opacity-100 disabled:cursor-not-allowed disabled:opacity-40 [@media(hover:hover)]:opacity-0 group-hover/rail:opacity-100"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
            {pages.length === 0 && (
              <p className="p-2 text-center text-[11px] text-faint">{t("ws.noPages")}</p>
            )}
          </div>
          {/* Mobile: rail header is lg-only, so expose Add pages here */}
          <button
            onClick={() => setAppendOpen(true)}
            disabled={running}
            className="btn btn-ghost mt-2 w-full py-1.5 text-[11px] lg:hidden"
          >
            <Plus size={13} />
            {t("pages.addPages")}
          </button>
        </aside>

        {/* Canvas */}
        <section className="flex min-h-0 min-w-0 flex-col rounded-xl border border-line bg-surface">
          <div className="shrink-0 border-b border-line p-2 text-xs text-muted">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
              <span className="px-1 font-medium" dir="ltr">
                {t("ws.page")} {currentPage?.page_number ?? "-"}
                {currentPage ? ` · ${currentPage.width}×${currentPage.height}` : ""}
              </span>
              <div className="flex flex-wrap gap-1 rounded-lg bg-surface2 p-1">
                {(["original", "cleaned", "rendered"] as const).map((v) => {
                  const available =
                    v === "original" ||
                    (v === "cleaned" && currentPage?.cleaned_image_url) ||
                    (v === "rendered" && currentPage?.rendered_image_url);
                  return (
                    <button
                      key={v}
                      onClick={() => { autoViewRef.current = null; setView(v); }}
                      disabled={!available}
                      aria-pressed={view === v}
                      className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-35 ${
                        view === v
                          ? "bg-surface text-primary-strong shadow-sm"
                          : "text-muted hover:text-ink"
                      }`}
                    >
                      {t(v === "original" ? "ws.original" : v === "cleaned" ? "ws.cleaned" : "ws.rendered")}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 pt-2">
              {/* Group 0: undo/redo (session edits: blocks + brush marks) */}
              <div className="flex overflow-hidden rounded-lg border border-line">
                <button
                  onClick={() => void doUndo()}
                  disabled={!canUndo || running}
                  title={`${t("ws.undo")} (Ctrl+Z)`}
                  aria-label={t("ws.undo")}
                  className="bg-surface2 px-2.5 py-1 text-[11px] font-semibold text-muted transition-colors hover:text-ink disabled:opacity-35"
                >
                  <Undo2 size={12} />
                </button>
                <button
                  onClick={() => void doRedo()}
                  disabled={!canRedo || running}
                  title={`${t("ws.redo")} (Ctrl+Y)`}
                  aria-label={t("ws.redo")}
                  className="bg-surface2 border-s border-line px-2.5 py-1 text-[11px] font-semibold text-muted transition-colors hover:text-ink disabled:opacity-35"
                >
                  <Redo2 size={12} />
                </button>
              </div>
              {/* Group 1: tools */}
              <div className="flex overflow-hidden rounded-lg border border-line">
                {(
                  [
                    { tool: "select" as CanvasTool, icon: <MousePointer2 size={12} />, key: "ws.toolSelect" as const, needsBlocks: false },
                    { tool: "brush" as CanvasTool, icon: <Paintbrush size={12} />, key: "ws.toolBrush" as const, needsBlocks: false },
                    { tool: "eraser" as CanvasTool, icon: <Eraser size={12} />, key: "ws.toolEraser" as const, needsBlocks: false },
                    { tool: "crop" as CanvasTool, icon: <Crop size={12} />, key: "ws.toolCrop" as const, needsBlocks: true },
                  ]
                ).map(({ tool: tl, icon, key, needsBlocks }) => (
                  <button
                    key={tl}
                    onClick={() => setCanvasTool(tl)}
                    disabled={view !== "original" || (needsBlocks && project.total_blocks === 0)}
                    aria-pressed={canvasTool === tl}
                    title={t(key)}
                    className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-semibold transition-colors disabled:opacity-35 ${
                      canvasTool === tl
                        ? "bg-primary text-primary-fg rounded"
                        : "bg-surface2 text-muted hover:text-ink"
                    }`}
                  >
                    {icon}
                  </button>
                ))}
              </div>
              {/* Brush size: image pixels, live preview while painting */}
              {canvasTool === "brush" && view === "original" && (
                <div className="flex items-center gap-1.5" title={t("ws.brushSize")}>
                  <input
                    type="range"
                    min={4}
                    max={120}
                    step={2}
                    value={brushSize}
                    onChange={(e) => changeBrushSize(Number(e.target.value))}
                    aria-label={t("ws.brushSize")}
                    dir="ltr"
                    className="w-24 accent-primary"
                  />
                  <span className="w-12 shrink-0 text-center font-mono text-[10px] text-muted" dir="ltr">
                    {brushSize}px
                  </span>
                </div>
              )}

              {/* Group 2: block + page actions */}
              <div className="flex min-w-0 flex-wrap items-center gap-1 border-s border-line ps-2">
                {/* Jump to the next untranslated box (wraps around the page) */}
                <button
                  onClick={gotoNextUntranslated}
                  disabled={!hasUntranslated}
                  className="btn btn-ghost px-2.5 py-1 text-[11px]"
                  aria-label={t("ws.nextUntranslated")}
                  title={t("ws.nextUntranslated")}
                >
                  <SkipForward size={12} />
                  {t("ws.nextUntranslated")}
                </button>
                {/* Per-page re-clean: erases translated regions + brush marks */}
                <button
                  onClick={() =>
                    void startAction(`/api/projects/${id}/clean/`, {
                      page_number: currentPage?.page_number,
                    })
                  }
                  disabled={running || !currentPage}
                  className="btn btn-ghost px-2.5 py-1 text-[11px]"
                  title={t("ws.reclean")}
                >
                  <RefreshCw size={12} />
                  {t("ws.reclean")}
                </button>
                <button
                  onClick={() =>
                    void startAction(
                      `/api/projects/${id}/reocr/`,
                      {
                        page_number: currentPage?.page_number,
                        quality: "high",
                      },
                      true, // re-OCR mints new block ids — history can't survive
                    )
                  }
                  disabled={running || !currentPage}
                  className="btn btn-ghost px-2.5 py-1 text-[11px]"
                  title={t("ws.reocr")}
                >
                  <ScanText size={12} />
                  {t("ws.reocr")}
                </button>
                <button
                  onClick={() => void deleteSelectedBlock()}
                  disabled={!selectedBlockId}
                  className="btn btn-danger px-2.5 py-1 text-[11px]"
                  aria-label={t("ws.deleteBox")}
                  title={t("ws.deleteBox")}
                >
                  <Trash2 size={12} />
                  {t("ws.deleteBox")}
                </button>
              </div>

              {/* Crop strip: live rect size + apply/cancel while cropping */}
              {canvasTool === "crop" && (
                <div className="flex min-w-0 flex-wrap items-center gap-1 border-s border-line ps-2">
                  <span className="px-1 text-[11px] font-bold text-muted" dir="ltr" role="status">
                    {cropRect && (cropRect.x2 > cropRect.x1 || cropRect.y2 > cropRect.y1)
                      ? `${cropRect.x2 - cropRect.x1}×${cropRect.y2 - cropRect.y1}`
                      : t("ws.toolCrop")}
                  </span>
                  <button
                    onClick={() => setCropConfirm(true)}
                    disabled={!cropReady || running || cropping || !currentPage}
                    className="btn btn-ghost px-2.5 py-1 text-[11px]"
                    title={cropReady ? t("ws.cropApply") : t("pages.cropTooSmall")}
                  >
                    <Crop size={12} />
                    {t("ws.cropApply")}
                  </button>
                  <button
                    onClick={() => { setCropRect(null); setCanvasTool("select"); }}
                    disabled={cropping}
                    className="btn btn-ghost px-2.5 py-1 text-[11px]"
                  >
                    <X size={12} />
                    {t("ws.cropCancel")}
                  </button>
                </div>
              )}

            </div>
          </div>

          <div className="min-h-0 min-w-0 flex-1 overflow-auto rounded-b-xl bg-base p-3 lg:p-4">
          <CanvasEditor
            projectId={id}
            revision={project.updated_at}
            imageUrl={bust(
              view === "original"
                ? currentPage?.image_url
                : view === "cleaned"
                  ? currentPage?.cleaned_image_url
                  : currentPage?.rendered_image_url,
            )}
            imageWidth={currentPage?.width ?? 0}
            imageHeight={currentPage?.height ?? 0}
            blocks={canvasBlocks}
            selectedId={selectedBlockId}
            multiIds={multiIds}
            onSelect={selectBlockFromCanvas}
            onMarqueeSelect={marqueeSelect}
            onClearSelection={clearSelection}
            onGeometryChange={patchBlockLocal}
            onTranslationCommit={commitTranslation}
            onAddBlock={addBlock}
            onEditTab={tabFromCanvas}
            readOnly={view !== "original"}
            tool={canvasTool}
            brushWidth={brushSize}
            maskMarks={view === "original" ? maskMarks.filter((m) => m.page_number === (currentPage?.page_number ?? -1)) : []}
            onAddMask={addMaskMark}
            onDeleteMask={(mid) => void deleteMaskMark(mid)}
            cropRect={cropRect}
            onCropRect={setCropRect}
            onPreviewSizes={reportPreviewSizes}
          />
          </div>
        </section>

        {/* Blocks panel */}
        <aside className="flex min-h-0 min-w-0 flex-col max-lg:max-h-[90vh] lg:overflow-y-auto">
          <BlockPanel
            blocks={pageBlocks}
            selectedId={selectedBlockId}
            multiIds={multiIds}
            onSelect={(bid, additive) => { if (additive) toggleSelectBlock(bid); else selectOnly(bid); }}
            onDeleteMulti={() => void deleteMulti()}
            onPatch={patchBlockLocal}
            onCommitTranslation={commitTranslation}
            styleClipboard={styleClipboard}
            onCopyStyle={copyStyle}
            onPasteSelection={pasteStyleToSelection}
            onPastePage={pasteStyleToPage}
            focusTick={panelFocusTick}
            onTranslatePage={() => void translatePage()}
            translateDisabled={running || !hasUntranslated}
          />
        </aside>
      </div>

      {guideOpen && <GuideModal onClose={() => setGuideOpen(false)} />}

      {chapterOpen && (
        <ChapterImportModal
          projectId={id}
          onClose={() => setChapterOpen(false)}
          onImport={(job) => { clearHistory(); beginJob(job); void loadProject(); }}
          beforeImport={() => flushPendingPatches(true)}
        />
      )}

      {appendOpen && (
        <AppendPagesModal
          projectId={id}
          pageNumbers={pages.map((p) => p.page_number)}
          defaultAfter={currentPage?.page_number ?? null}
          onClose={() => setAppendOpen(false)}
          onAppended={(inserted) => {
            setAppendOpen(false);
            clearHistory();
            setSelectedPage(inserted[0]);
            setSelectedBlockId(null);
            void Promise.all([loadProject(), loadBlocks(), loadMaskMarks()]).then(() =>
              toast.push(t("pages.appended", { count: inserted.length }), "success"),
            );
          }}
        />
      )}

      {cropConfirm && cropRect && cropStats && (
        <Modal
          title={t("pages.cropTitle")}
          onClose={() => { if (!cropping) setCropConfirm(false); }}
        >
          <p className="text-sm text-muted">
            {cropStats.kept === 0
              ? t("pages.cropEmpty")
              : t("pages.cropBody", { kept: cropStats.kept, removed: cropStats.removed })}
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button className="btn btn-ghost" onClick={() => setCropConfirm(false)} disabled={cropping}>
              {t("pages.cancel")}
            </button>
            <button className="btn bg-danger text-white" onClick={() => void applyCrop()} disabled={cropping}>
              <Crop size={14} />
              {t("ws.cropApply")}
            </button>
          </div>
        </Modal>
      )}

      {deleteTarget && <Modal
        title={`${t("pages.delete")} ${deleteTarget.page_number}`}
        onClose={() => { if (!deletingPage) setDeleteTarget(null); }}
      >
        <p className="text-sm text-muted">{t("pages.deleteWarning")}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={() => setDeleteTarget(null)} disabled={deletingPage}>
            {t("pages.cancel")}
          </button>
          <button className="btn bg-danger text-white" onClick={() => void deletePage()} disabled={deletingPage}>
            <Trash2 size={14} />
            {t("pages.delete")}
          </button>
        </div>
      </Modal>}

      {transferOpen && (
        <Modal title={t("transfer.title")} onClose={() => setTransferOpen(false)} wide>
          <div className="max-h-[65vh] space-y-4 overflow-y-auto pe-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-muted">
                {t("transfer.scope")}
              </span>
              <div className="flex overflow-hidden rounded-lg border border-line">
                {(["current", "all"] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      setTransferScope(s);
                      invalidatePreview();
                    }}
                    className={`px-3 py-1.5 text-xs font-semibold transition-colors ${
                      transferScope === s
                        ? "bg-primary text-primary-fg"
                        : "bg-surface2 text-muted hover:text-ink"
                    }`}
                  >
                    {s === "current" ? t("transfer.current") : t("transfer.all")}
                  </button>
                ))}
              </div>
              <span className="text-xs text-muted">
                {scopeBlocks.length} {t("dash.blocks")}
              </span>
            </div>

            <button onClick={exportOcrText} disabled={!scopeBlocks.length} className="btn btn-outline w-full px-3 py-2 text-sm">
              <FileDown size={14} />
              {t("transfer.export")}
            </button>

            <label className="block space-y-2 text-sm font-medium">
              <span>{t("transfer.upload")}</span>
              <input
                type="file"
                accept=".json,.txt,application/json,text/plain"
                disabled={transferSaving}
                className="input-base w-full text-xs"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  invalidatePreview();
                  try {
                    const text = await file.text();
                    setTransferText(text);
                    invalidatePreview();
                  } catch {
                    setTransferError(t("transfer.readFailed"));
                  }
                }}
              />
            </label>

            <textarea
              value={transferText}
              onChange={(e) => {
                setTransferText(e.target.value);
                invalidatePreview();
              }}
              dir="auto"
              rows={8}
              placeholder={t("transfer.paste")}
              className="input-base w-full font-mono text-xs"
            />
            <p className="text-[11px] leading-relaxed text-muted">{t("transfer.hint")}</p>

            {transferError && (
              <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs font-bold text-danger">
                {transferError}
              </p>
            )}

            {transferPreview && (
              <div className="space-y-2 rounded-xl border border-line bg-surface2 p-3 text-xs">
                <div className="flex flex-wrap gap-2">
                  <span className="chip text-success">
                    {t("transfer.new")}: {transferPreview.entries.length - transferPreview.unchanged}
                  </span>
                  <span className="chip">
                    {t("transfer.replace")}: {transferPreview.entries.filter((e) => e.previous.trim()).length - transferPreview.unchanged}
                  </span>
                  <span className="chip">
                    {t("transfer.unchanged")}: {transferPreview.unchanged}
                  </span>
                  {transferPreview.skipped > 0 && (
                    <span className="chip">
                      {t("transfer.skipped")}: {transferPreview.skipped}
                    </span>
                  )}
                </div>
                {transferPreview.entries.some((e) => e.previous.trim()) && (
                  <div className="max-h-40 space-y-1.5 overflow-y-auto">
                    {transferPreview.entries
                      .filter((e) => e.previous.trim())
                      .map((e) => (
                        <div key={e.id} className="rounded-lg bg-surface p-2">
                          <p className="mb-1 text-[10px] font-bold text-faint" dir="ltr">
                            p{e.page} · {e.key}
                          </p>
                          <p className="truncate text-muted">{e.previous}</p>
                          <p className="truncate font-bold text-ink">{e.translation}</p>
                        </div>
                      ))}
                  </div>
                )}
                <label className="flex items-center gap-2 font-semibold text-ink">
                  <input
                    type="checkbox"
                    checked={transferConfirmed}
                    onChange={(e) => setTransferConfirmed(e.target.checked)}
                    className="h-4 w-4 accent-primary"
                  />
                  {t("transfer.confirm")}
                </label>
              </div>
            )}
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <button onClick={previewImport} disabled={!transferText.trim()} className="btn btn-outline px-4 py-2 text-sm">
              <ScanText size={14} />
              {t("transfer.preview")}
            </button>
            <button
              onClick={() => void applyImport()}
              disabled={!transferConfirmed || !transferPreview || transferSaving}
              className="btn btn-primary px-4 py-2 text-sm"
            >
              {transferSaving ? t("transfer.saving") : t("transfer.apply")}
            </button>
          </div>
        </Modal>
      )}
    </main>
  );
}

