"use client";

import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import { MaskMark, TextBlock } from "@/lib/types";
import { resizeRectHandle, resizeRotatedHandle } from "@/lib/block-geometry";
import { downsamplePoints, strokeToPolygon } from "@/lib/stroke";
import { useI18n } from "@/lib/i18n";
import { usePreviewLayout } from "./usePreviewLayout";

// Editor tuning knobs (image-pixel space).
const MIN_BLOCK_W = 20; // smallest box accepted when drawing a new block
const MIN_BLOCK_H = 14;
const RESIZE_MIN = 10; // min size while resizing an existing block
const DRAFT_START_W = 120; // initial draft rect on double-click
const DRAFT_START_H = 50;
export const DEFAULT_BRUSH_WIDTH = 28; // clean-brush stroke width (image px)
const MARK_MIN_DIST = 3; // min distance between collected stroke points
const MARK_ERASE_PAD = 10; // bbox tolerance when erasing marks
// Polygon outline roughly doubles the point count — keep the centerline
// short enough that the stored polygon stays under the backend 2000 cap.
const MAX_STROKE_POINTS = 950;

export type CanvasTool = "select" | "brush" | "eraser" | "crop";
export interface CropRect { x1: number; y1: number; x2: number; y2: number }

interface Props {
  projectId: string;
  revision?: string;
  imageUrl: string | null | undefined;
  imageWidth: number;
  imageHeight: number;
  blocks: TextBlock[];
  selectedId: string | null;
  /** Extra ids in the active visual selection (Shift+click, marquee). */
  multiIds?: string[];
  onSelect: (id: string, additive: boolean) => void;
  onMarqueeSelect: (rect: CropRect) => void;
  onClearSelection: () => void;
  onGeometryChange: (id: string, geo: Partial<TextBlock>) => void;
  onTranslationCommit: (id: string, text: string) => void;
  /** Tab inside the inline textarea: commit + move to neighbor dialog. */
  onEditTab?: (id: string, dir: 1 | -1) => void;
  onAddBlock: (x1: number, y1: number, x2: number, y2: number) => void;
  /** Proofreading views (cleaned/rendered): no editing interactions. */
  readOnly?: boolean;
  tool?: CanvasTool;
  maskMarks?: MaskMark[];
  onAddMask?: (points: [number, number][]) => void;
  onDeleteMask?: (id: string) => void;
  /** Brush stroke width in image pixels (also the erased width). */
  brushWidth?: number;
  /** Controlled crop rectangle (image-pixel coords); drawn when tool is crop. */
  cropRect?: CropRect | null;
  onCropRect?: (rect: CropRect | null) => void;
  /** Fitted preview font sizes per block id — parent persists them on commit
      so preview and render agree. Ref-sink only; never triggers re-render. */
  onPreviewSizes?: (sizes: Record<string, number>) => void;
}

type CropLike = { x1: number; y1: number; x2: number; y2: number };

type DragState =
  | { kind: "move" | "resize"; id: string; startX: number; startY: number; orig: TextBlock; handle?: { sx: Sign; sy: Sign } }
  | { kind: "move-multi"; ids: { id: string; orig: TextBlock }[]; startX: number; startY: number }
  | { kind: "marquee"; startX: number; startY: number }
  | { kind: "brush" }
  | { kind: "erase" }
  | { kind: "crop"; startX: number; startY: number }
  | { kind: "pan"; startX: number; startY: number; scrollLeft: number; scrollTop: number }
  | null;

type HandleName = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";
type Sign = -1 | 0 | 1;

// Resize handles: n/s/e/w edges and the four corners → dragged sides.
const HANDLE_SIGNS: Record<HandleName, { sx: Sign; sy: Sign }> = {
  n: { sx: 0, sy: -1 }, s: { sx: 0, sy: 1 }, e: { sx: 1, sy: 0 }, w: { sx: -1, sy: 0 },
  ne: { sx: 1, sy: -1 }, nw: { sx: -1, sy: -1 }, se: { sx: 1, sy: 1 }, sw: { sx: -1, sy: 1 },
};
const HANDLE_NAMES = Object.keys(HANDLE_SIGNS) as HandleName[];


export const CanvasEditor = memo(function CanvasEditor({
  projectId,
  revision,
  imageUrl,
  imageWidth,
  imageHeight,
  blocks,
  selectedId,
  multiIds = [],
  onSelect,
  onMarqueeSelect,
  onClearSelection,
  onGeometryChange,
  onTranslationCommit,
  onEditTab,
  onAddBlock,
  readOnly = false,
  tool = "select",
  maskMarks = [],
  onAddMask,
  onDeleteMask,
  brushWidth = DEFAULT_BRUSH_WIDTH,
  cropRect = null,
  onCropRect,
  onPreviewSizes,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasScrollRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftText, setDraftText] = useState("");
  const preview = usePreviewLayout(projectId, blocks.map((block) =>
    block.id === editingId ? { ...block, translation: draftText } : block,
  ), revision);
  // Page zoom, as a fraction of the image's natural size. null = Fit (the
  // image is capped into the viewport). Ctrl+wheel zooms; the toolbar
  // button toggles 100% ↔ Fit.
  const [zoom, setZoom] = useState<number | null>(null);
  const [draftRect, setDraftRect] = useState<
    { x1: number; y1: number; x2: number; y2: number } | null
  >(null);
  const { t } = useI18n();

  // Handlers are captured in refs so the window-listener effect below can
  // keep stable deps — dragging calls onGeometryChange on every pointermove,
  // and resubscribing listeners per frame would be pure churn.
  const handlersRef = useRef({
    onSelect,
    onMarqueeSelect,
    onClearSelection,
    onGeometryChange,
    onAddBlock,
    onAddMask,
    onDeleteMask,
    onCropRect,
  });
  handlersRef.current = { onSelect, onMarqueeSelect, onClearSelection, onGeometryChange, onAddBlock, onAddMask, onDeleteMask, onCropRect };

  // Blocks and the active visual selection are read when a drag starts or a
  // new block preview is inserted — mirrored refs keep listeners stable.
  const blocksRef = useRef(blocks);
  blocksRef.current = blocks;
  const activeSelRef = useRef<string[]>([]);
  activeSelRef.current = selectedId
    ? [selectedId, ...multiIds.filter((id) => id !== selectedId)]
    : [...multiIds];

  const onEditTabRef = useRef(onEditTab);
  onEditTabRef.current = onEditTab;

  // Marks are read during erase drags without resubscribing listeners.
  const maskMarksRef = useRef(maskMarks);
  maskMarksRef.current = maskMarks;

  // Space-held + middle-button panning. The ref gates pointer handlers
  // synchronously; the state only drives the grab cursor. Inputs/textareas
  // keep typing spaces — the key handler ignores editable targets.
  const spaceRef = useRef(false);
  const [spaceHeld, setSpaceHeld] = useState(false);
  useEffect(() => {
    const editableTarget = (t: EventTarget | null) =>
      t instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName);
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || editableTarget(e.target)) return;
      e.preventDefault(); // first press only scrolls the page otherwise; repeats are harmless
      spaceRef.current = true;
      setSpaceHeld(true);
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      spaceRef.current = false;
      setSpaceHeld(false);
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      spaceRef.current = false;
      setSpaceHeld(false);
    };
  }, []);

  // Brush width is read on stroke end without resubscribing listeners.
  const brushWidthRef = useRef(brushWidth);
  brushWidthRef.current = brushWidth;

  // Ctrl+wheel zoom anchored at the cursor: a native (non-passive) listener
  // so preventDefault can stop browser zoom. The pointer position is stored
  // before React re-renders at the new scale; a layout effect then restores
  // the same image pixel under the cursor.
  const zoomAnchorRef = useRef<{ ax: number; ay: number; ex: number; ey: number; ratio: number } | null>(null);
  useEffect(() => {
    const el = canvasScrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey) || !imageWidth) return;
      e.preventDefault();
      const cRect = el.getBoundingClientRect();
      const imgRect = containerRef.current?.getBoundingClientRect();
      if (!imgRect || imgRect.width === 0) return;
      const s0 = imgRect.width / imageWidth;
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      const s1 = Math.min(8, Math.max(0.1, s0 * factor));
      if (Math.abs(s1 - s0) < 1e-6) return;
      zoomAnchorRef.current = {
        ax: el.scrollLeft + (e.clientX - cRect.left),
        ay: el.scrollTop + (e.clientY - cRect.top),
        ex: e.clientX - cRect.left,
        ey: e.clientY - cRect.top,
        ratio: s1 / s0,
      };
      setZoom(s1 / imageWidth);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [imageWidth]);

  useLayoutEffect(() => {
    const anchor = zoomAnchorRef.current;
    const el = canvasScrollRef.current;
    if (!anchor || !el) return;
    zoomAnchorRef.current = null;
    el.scrollLeft = anchor.ax * anchor.ratio - anchor.ex;
    el.scrollTop = anchor.ay * anchor.ratio - anchor.ey;
  }, [zoom]);

  // Live brush stroke (image coords); mirrored into state for rendering.
  const strokeRef = useRef<[number, number][] | null>(null);
  const [stroke, setStroke] = useState<[number, number][] | null>(null);
  const eraseDeletedRef = useRef<Set<string>>(new Set());

  // Marquee box-selection: mirrored ref for the pointerup read, state for
  // the live overlay render.
  const marqueeRef = useRef<CropLike | null>(null);
  const [marqueeRect, setMarqueeRect] = useState<CropLike | null>(null);

  // Middle-click starts panning anywhere; space-drag is gated by spaceRef.
  const isPanButton = (e: { button: number }) => e.button === 1;

  const eraseAt = useCallback((p: { x: number; y: number }) => {
    for (const m of maskMarksRef.current) {
      if (eraseDeletedRef.current.has(m.id)) continue;
      const xs = m.points.map((pt) => pt[0]);
      const ys = m.points.map((pt) => pt[1]);
      if (
        p.x >= Math.min(...xs) - MARK_ERASE_PAD &&
        p.x <= Math.max(...xs) + MARK_ERASE_PAD &&
        p.y >= Math.min(...ys) - MARK_ERASE_PAD &&
        p.y <= Math.max(...ys) + MARK_ERASE_PAD
      ) {
        eraseDeletedRef.current.add(m.id);
        handlersRef.current.onDeleteMask?.(m.id);
      }
    }
  }, []);

  // Selecting from the panel (or N-key) must reveal the box: tall pages in
  // actual-size mode can put it far outside the visible scroll area.
  useEffect(() => {
    if (!selectedId) return;
    containerRef.current
      ?.querySelector(`.block-box.selected`)
      ?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }, [selectedId]);

  const scale = useCallback(
    (displayWidth: number) => (imageWidth ? displayWidth / imageWidth : 1),
    [imageWidth],
  );

  const toImageCoords = useCallback(
    (clientX: number, clientY: number) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect || !imageWidth) return { x: 0, y: 0 };
      const s = scale(rect.width);
      return {
        x: Math.round((clientX - rect.left) / s),
        y: Math.round((clientY - rect.top) / s),
      };
    },
    [imageWidth, scale],
  );

  // rAF throttle: during a drag the parent re-renders on every geometry
  // update; coalescing pointermove bursts to one update per frame keeps the
  // whole workspace tree from re-rendering at input frequency.
  const frameRef = useRef<number | null>(null);
  const pendingGeoRef = useRef<Array<{ id: string; geo: Partial<TextBlock> }> | null>(null);

  const applyPendingGeo = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    const pending = pendingGeoRef.current;
    pendingGeoRef.current = null;
    if (pending) {
      for (const entry of pending) {
        handlersRef.current.onGeometryChange(entry.id, entry.geo);
      }
    }
  }, []);

  useEffect(() => {
    if (!drag && !draftRect) return;

    function onMove(e: PointerEvent) {
      if (drag) {
        const p = toImageCoords(e.clientX, e.clientY);
        if (drag.kind === "pan") {
          const el = canvasScrollRef.current;
          if (el) {
            el.scrollLeft = drag.scrollLeft - (e.clientX - drag.startX);
            el.scrollTop = drag.scrollTop - (e.clientY - drag.startY);
          }
          return;
        }
        if (drag.kind === "brush") {
          // Collect stroke points, skipping micro-movements.
          const pts = strokeRef.current;
          if (pts) {
            const last = pts[pts.length - 1];
            if (Math.hypot(p.x - last[0], p.y - last[1]) >= MARK_MIN_DIST) {
              strokeRef.current = [...pts, [p.x, p.y]];
              setStroke(strokeRef.current);
            }
          }
          return;
        }
        if (drag.kind === "erase") {
          eraseAt(p);
          return;
        }
        if (drag.kind === "crop") {
          // Free-direction drag: normalize so x1<=x2, y1<=y2, clamped inside.
          const x1 = Math.max(0, Math.min(drag.startX, p.x));
          const y1 = Math.max(0, Math.min(drag.startY, p.y));
          const x2 = Math.min(imageWidth, Math.max(drag.startX, p.x));
          const y2 = Math.min(imageHeight, Math.max(drag.startY, p.y));
          handlersRef.current.onCropRect?.({ x1, y1, x2, y2 });
          return;
        }
        if (drag.kind === "move") {
          const dx = p.x - drag.startX;
          const dy = p.y - drag.startY;
          const w = drag.orig.x2 - drag.orig.x1;
          const h = drag.orig.y2 - drag.orig.y1;
          const nx1 = Math.max(0, Math.min(drag.orig.x1 + dx, imageWidth - w));
          const ny1 = Math.max(0, Math.min(drag.orig.y1 + dy, imageHeight - h));
          pendingGeoRef.current = [
            { id: drag.id, geo: { x1: nx1, y1: ny1, x2: nx1 + w, y2: ny1 + h } },
          ];
        } else if (drag.kind === "move-multi") {
          // Same visual delta moves every member of the box-selection; each
          // block clamps to the image edges with its own size.
          const dx = p.x - drag.startX;
          const dy = p.y - drag.startY;
          pendingGeoRef.current = drag.ids.map(({ id, orig }) => {
            const w = orig.x2 - orig.x1;
            const h = orig.y2 - orig.y1;
            const nx1 = Math.max(0, Math.min(orig.x1 + dx, imageWidth - w));
            const ny1 = Math.max(0, Math.min(orig.y1 + dy, imageHeight - h));
            return { id, geo: { x1: nx1, y1: ny1, x2: nx1 + w, y2: ny1 + h } };
          });
        } else if (drag.kind === "marquee") {
          // Free-direction drag; normalized on pointerup by the marquee handler.
          const x1 = Math.max(0, Math.min(drag.startX, p.x));
          const y1 = Math.max(0, Math.min(drag.startY, p.y));
          const x2 = Math.min(imageWidth, Math.max(drag.startX, p.x));
          const y2 = Math.min(imageHeight, Math.max(drag.startY, p.y));
          marqueeRef.current = { x1, y1, x2, y2 };
          setMarqueeRect(marqueeRef.current);
          return;
        } else {
          const dx = p.x - drag.startX;
          const dy = p.y - drag.startY;
          const px = Math.max(0, Math.min(p.x, imageWidth));
          const py = Math.max(0, Math.min(p.y, imageHeight));
          const sx = drag.handle?.sx ?? 1;
          const sy = drag.handle?.sy ?? 1;
          const geo = drag.orig.rotation
            // Rotated: resize along the box's own axes from any corner/edge
            // handle (projecting the drag and pinning the opposite side).
            ? resizeRotatedHandle(drag.orig, sx, sy, dx, dy, RESIZE_MIN)
            : resizeRectHandle(
                drag.orig.x1, drag.orig.y1, drag.orig.x2, drag.orig.y2,
                sx, sy, px, py, RESIZE_MIN,
              );
          pendingGeoRef.current = [{ id: drag.id, geo }];
        }
        if (frameRef.current === null) {
          frameRef.current = requestAnimationFrame(() => {
            frameRef.current = null;
            applyPendingGeo();
          });
        }
      } else if (draftRect) {
        const p = toImageCoords(e.clientX, e.clientY);
        setDraftRect((r) =>
          r ? { ...r, x2: Math.max(r.x1 + 12, p.x), y2: Math.max(r.y1 + 12, p.y) } : r,
        );
      }
    }

    function onUp() {
      if (drag) {
        if (drag.kind === "marquee") {
          const r = marqueeRef.current;
          marqueeRef.current = null;
          setMarqueeRect(null);
          setDrag(null);
          // A tiny accidental drag is a plain click: clear selection.
          if (r && (Math.abs(r.x2 - r.x1) >= 10 || Math.abs(r.y2 - r.y1) >= 10)) {
            handlersRef.current.onMarqueeSelect(r);
          } else {
            handlersRef.current.onClearSelection();
          }
          return;
        }
        if (drag.kind === "brush") {
          const pts = strokeRef.current;
          strokeRef.current = null;
          setStroke(null);
          if (pts && pts.length > 0) {
            // Quick dabs/clicks yield 1-2 points but the backend requires
            // >= 3 (and clean ignores < 3) — pad with tiny nudges so a
            // single click still erases a dot instead of vanishing.
            const padded: [number, number][] = [...pts];
            while (padded.length < 3) {
              const [lx, ly] = padded[padded.length - 1];
              padded.push([lx + 2, ly]);
            }
            // Store the stroke as a width-aware polygon outline: the
            // cleaner fills this polygon for its inpaint mask, so the
            // chosen brush size is what actually gets erased.
            const line = downsamplePoints(padded, MAX_STROKE_POINTS);
            handlersRef.current.onAddMask?.(strokeToPolygon(line, brushWidthRef.current));
          }
        }
        // Land the final position synchronously before clearing drag state.
        applyPendingGeo();
        setDrag(null);
      } else if (draftRect) {
        const r = draftRect;
        setDraftRect(null);
        if (r.x2 - r.x1 > MIN_BLOCK_W && r.y2 - r.y1 > MIN_BLOCK_H) {
          handlersRef.current.onAddBlock(r.x1, r.y1, r.x2, r.y2);
        }
      }
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      // If the effect tears down mid-drag (page nav, image switch), don't
      // drop the last frame of movement.
      applyPendingGeo();
    };
  }, [drag, draftRect, imageWidth, imageHeight, toImageCoords, applyPendingGeo, eraseAt]);

  // Committing a translation also persists the preview's fitted font size
  // (via onTranslationCommit in the parent), so the size the user sees on
  // the canvas is the size the render job uses.
  const commitEdit = useCallback((blk: TextBlock, value: string) => {
    onTranslationCommit(blk.id, value);
    setEditingId(null);
  }, [onTranslationCommit]);

  // Report fitted preview font sizes upward (parent keeps them in a ref and
  // persists them alongside translation commits).
  useEffect(() => {
    if (!onPreviewSizes) return;
    const sizes: Record<string, number> = {};
    for (const [bid, layout] of Object.entries(preview.layouts)) {
      if (typeof layout.font_size === "number") sizes[bid] = layout.font_size;
    }
    onPreviewSizes(sizes);
  }, [preview.layouts, onPreviewSizes]);

  if (!imageUrl) {
    return (
      <div className="card flex h-96 items-center justify-center text-sm text-muted">
        {t("ws.noImage")}
      </div>
    );
  }

  return (
    <div className="relative w-full">
      {/* Zoom control — fit mode offers 100% (arrows out); any zoom level
          shows the percentage and clicking returns to Fit. Ctrl+wheel and
          Space-drag do the fine-grained work. */}
      {zoom === null ? (
        <button
          onClick={() => setZoom(1)}
          className="btn btn-ghost absolute end-2 top-2 z-10 h-8 w-8 !rounded-lg p-0"
          title={t("ws.zoom100")}
          aria-label={t("ws.zoom100")}
        >
          <Maximize2 size={14} />
        </button>
      ) : (
        <button
          onClick={() => setZoom(null)}
          className="btn btn-ghost absolute end-2 top-2 z-10 flex h-8 items-center gap-1.5 !rounded-lg px-2"
          title={t("ws.zoomFit")}
          aria-label={t("ws.zoomFit")}
        >
          <Minimize2 size={14} />
          <span className="text-[11px] font-bold" dir="ltr">{Math.round(zoom * 100)}%</span>
        </button>
      )}

      <div
        ref={canvasScrollRef}
        className={`relative mx-auto max-h-[75vh] w-full overflow-auto ${
          drag?.kind === "pan" ? "cursor-grabbing" : spaceHeld ? "cursor-grab" : ""
        }`}
        onPointerDown={(e) => {
          if (!(spaceRef.current || isPanButton(e))) return;
          if (drag) return; // a block/brush/crop drag owns the pointer already
          e.preventDefault();
          const el = canvasScrollRef.current;
          if (!el) return;
          setDrag({
            kind: "pan",
            startX: e.clientX,
            startY: e.clientY,
            scrollLeft: el.scrollLeft,
            scrollTop: el.scrollTop,
          });
        }}
        style={{ lineHeight: 0 }}
      >
      <div
        ref={containerRef}
        className="relative mx-auto w-fit select-none overflow-hidden rounded-2xl shadow-[0_16px_60px_-16px_rgba(0,0,0,0.55)] ring-1 ring-line"
        style={{ lineHeight: 0, cursor: tool !== "select" ? "crosshair" : undefined }}
        onPointerDown={(e) => {
          if (isPanButton(e) || spaceRef.current) return;
          if (readOnly) return;
          if (tool === "select") {
            // Blocks run their own handler; bubbling here only means an
            // empty-area click. That starts a marquee unless Shift is held.
            if ((e.target as HTMLElement).closest(".block-box")) return;
            if (e.button !== 0 || e.shiftKey) return;
            e.preventDefault();
            const p = toImageCoords(e.clientX, e.clientY);
            marqueeRef.current = { x1: p.x, y1: p.y, x2: p.x, y2: p.y };
            setMarqueeRect(marqueeRef.current);
            setDrag({ kind: "marquee", startX: p.x, startY: p.y });
            (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
            return;
          }
          e.preventDefault();
          const p = toImageCoords(e.clientX, e.clientY);
          if (tool === "crop") {
            const cx = Math.max(0, Math.min(p.x, imageWidth));
            const cy = Math.max(0, Math.min(p.y, imageHeight));
            handlersRef.current.onCropRect?.({ x1: cx, y1: cy, x2: cx, y2: cy });
            setDrag({ kind: "crop", startX: cx, startY: cy });
            (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
            return;
          }
          const nextDrag: DragState =
            tool === "brush" ? { kind: "brush" } : { kind: "erase" };
          if (tool === "brush") {
            strokeRef.current = [[p.x, p.y]];
            setStroke(strokeRef.current);
          } else {
            eraseDeletedRef.current = new Set();
            eraseAt(p);
          }
          setDrag(nextDrag);
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
        }}
        onDoubleClick={(e) => {
          if (readOnly || tool !== "select") return;
          if ((e.target as HTMLElement).closest(".block-box")) return;
          const p = toImageCoords(e.clientX, e.clientY);
          setDraftRect({
            x1: p.x,
            y1: p.y,
            x2: p.x + DRAFT_START_W,
            y2: p.y + DRAFT_START_H,
          });
        }}
      >
        {/* True aspect: h-auto overrides the height attribute so the image
            never stretches. Fit caps it inside the viewport; a zoom level
            renders the image at natural×zoom and the scroll wrapper pans.
            The container wraps the image exactly, so %-based block overlays
            stay aligned. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl}
          alt={t("ws.page")}
          width={imageWidth || undefined}
          height={imageHeight || undefined}
          className={zoom === null
            ? "block h-auto w-auto max-h-[75vh] max-w-full"
            : "block h-auto w-auto max-w-none"}
          style={zoom === null ? undefined : { width: (imageWidth || 0) * zoom }}
          draggable={false}
        />

        {/* Clean-brush marks + live stroke. The SVG viewBox matches image
            pixel space, so strokes stay aligned at any zoom. Root is
            pointer-events-none; polygons re-enable events in erase mode.
            Marks are stored as filled polygons (the same shape the cleaner
            fills for its inpaint mask); the live stroke previews the width
            as a thick polyline while painting. */}
        {(maskMarks.length > 0 || stroke) && (
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox={`0 0 ${imageWidth || 1} ${imageHeight || 1}`}
            preserveAspectRatio="none"
          >
            {maskMarks.map((m) => (
              <polygon
                key={m.id}
                points={m.points.map((p) => p.join(",")).join(" ")}
                fill={tool === "eraser" ? "var(--danger)" : "var(--primary)"}
                stroke={tool === "eraser" ? "var(--danger)" : "var(--primary-strong)"}
                strokeWidth={2}
                opacity={tool === "eraser" ? 0.7 : 0.45}
                style={{ pointerEvents: tool === "eraser" ? "all" : "none" }}
                onPointerDown={(e) => {
                  if (tool !== "eraser") return;
                  e.stopPropagation();
                  e.preventDefault();
                  handlersRef.current.onDeleteMask?.(m.id);
                }}
              />
            ))}
            {stroke && (
              <polyline
                points={stroke.map((p) => p.join(",")).join(" ")}
                fill="none"
                stroke="var(--primary-strong)"
                strokeWidth={brushWidth}
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity={0.6}
              />
            )}
          </svg>
        )}

      {blocks.map((blk) => {
        const align =
          blk.alignment === "left"
            ? "left"
            : blk.alignment === "right"
              ? "right"
              : "center";
        const boxW = blk.x2 - blk.x1;
        const boxH = blk.y2 - blk.y1;
        const layout = preview.layouts[blk.id];
        // Server sizes are image pixels. Container units scale inline editing
        // with the same box; SVG viewBox scales the preview at Fit and Actual.
        const fontSize = layout?.font_size
          ? `${(layout.font_size / (boxW || 1)) * 100}cqw` : "14px";
        return (
        <div
          key={blk.id}
          className={`block-box type-${blk.block_type} ${
            activeSelRef.current.includes(blk.id) ? "selected" : ""
          }`}
          style={{
            left: `${(blk.x1 / (imageWidth || 1)) * 100}%`,
            top: `${(blk.y1 / (imageHeight || 1)) * 100}%`,
            width: `${((blk.x2 - blk.x1) / (imageWidth || 1)) * 100}%`,
            height: `${((blk.y2 - blk.y1) / (imageHeight || 1)) * 100}%`,
            // Rotation spins box + text around the box center, matching the
            // renderer's rotated text layer. transform-origin defaults to center.
            transform: blk.rotation ? `rotate(${blk.rotation}deg)` : undefined,
            // Brush/eraser must stroke through boxes, not grab them.
            pointerEvents: tool === "select" ? undefined : "none",
          }}
          onPointerDown={(e) => {
            e.preventDefault();
            // Shift+click toggles membership in the visual selection — no
            // drag starts (the container doesn't receive this event).
            if (e.shiftKey && e.button === 0 && !spaceRef.current) {
              e.stopPropagation();
              handlersRef.current.onSelect(blk.id, true);
              return;
            }
            if (isPanButton(e) || spaceRef.current) return;
            handlersRef.current.onSelect(blk.id, false);
            setEditingId(null);
            const p = toImageCoords(e.clientX, e.clientY);
            // Part of an active box-selection? Drag the whole selection.
            const sel = activeSelRef.current;
            const byId = new Map(blocksRef.current.map((b) => [b.id, b]));
            if (sel.length > 1 && sel.includes(blk.id)) {
              const members = sel
                .map((id) => byId.get(id))
                .filter((b): b is TextBlock => !!b)
                .map((orig) => ({ id: orig.id, orig: { ...orig } }));
              setDrag({ kind: "move-multi", ids: members, startX: p.x, startY: p.y });
            } else {
              setDrag({ kind: "move", id: blk.id, startX: p.x, startY: p.y, orig: { ...blk } });
            }
            // Keep receiving pointermove/pointerup even if the cursor leaves
            // this element mid-drag (matches the Showcase slider behavior).
            (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          }}
          onDoubleClick={(e) => {
            e.stopPropagation();
            setDraftText(blk.translation);
            setEditingId(blk.id);
          }}
          title={`${blk.key} — ${blk.original_text}`}
        >
          {editingId === blk.id ? (
            <textarea
              autoFocus
              dir="rtl"
              className="fa-text h-full w-full resize-none bg-white p-1.5 leading-snug outline-none"
              style={{ color: blk.color || "#000000", fontSize, textAlign: align, fontFamily: layout?.fontFamily }}
              value={draftText}
              onChange={(e) => setDraftText(e.target.value)}
              onPointerDown={(e) => e.stopPropagation()}
              onBlur={(e) => {
                commitEdit(blk, e.target.value);
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") setEditingId(null);
                if (e.key === "Tab" && !e.nativeEvent.isComposing) {
                  // Tab moves to the neighbor dialog: commit first, then
                  // navigate (panel receives the focus tick).
                  e.preventDefault();
                  commitEdit(blk, (e.target as HTMLTextAreaElement).value);
                  onEditTabRef.current?.(blk.id, e.shiftKey ? -1 : 1);
                  return;
                }
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  commitEdit(blk, (e.target as HTMLTextAreaElement).value);
                }
              }}
            />
          ) : (
            layout?.fontFamily && !layout.unavailable ? (
              <svg
                className="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
                viewBox={`0 0 ${Math.max(1, boxW)} ${Math.max(1, boxH)}`}
                preserveAspectRatio="none"
                aria-label={blk.translation}
              >
                {layout.lines?.map((line, index) => (
                  <text
                    key={index}
                    x={line.x}
                    y={line.y}
                    textAnchor={layout.align === "right" ? "end" : layout.align === "left" ? "start" : "middle"}
                    style={{ fontFamily: layout.fontFamily, fontSize: layout.font_size, whiteSpace: "pre" }}
                    fill={blk.color || "#000000"}
                  >
                    {line.text}
                  </text>
                ))}
              </svg>
            ) : !layout?.skipped ? (
              <span className="pointer-events-none flex h-full items-center justify-center text-xs text-muted" role="status">
                {preview.failed ? t("ws.previewUnavailable") : "…"}
              </span>
            ) : null
          )}
          {HANDLE_NAMES.map((h) => (
            <span
              key={h}
              className={`resize-handle rh-${h}`}
              onPointerDown={(e) => {
                e.stopPropagation();
                e.preventDefault();
                handlersRef.current.onSelect(blk.id, e.shiftKey);
                const p = toImageCoords(e.clientX, e.clientY);
                setDrag({
                  kind: "resize", id: blk.id, startX: p.x, startY: p.y,
                  orig: { ...blk }, handle: HANDLE_SIGNS[h],
                });
                e.currentTarget.setPointerCapture(e.pointerId);
              }}
            />
          ))}
        </div>
        );
      })}

      {draftRect && (
        <div
          className="pointer-events-none absolute rounded-md border-2 border-dashed border-primary bg-primary/15"
          style={{
            left: `${(draftRect.x1 / (imageWidth || 1)) * 100}%`,
            top: `${(draftRect.y1 / (imageHeight || 1)) * 100}%`,
            width: `${((draftRect.x2 - draftRect.x1) / (imageWidth || 1)) * 100}%`,
            height: `${((draftRect.y2 - draftRect.y1) / (imageHeight || 1)) * 100}%`,
          }}
        />
      )}

      {/* Marquee box-selection overlay */}
      {marqueeRect && (
        <div
          className="pointer-events-none absolute rounded-md border-2 border-dashed border-primary bg-primary/10"
          style={{
            left: `${(marqueeRect.x1 / (imageWidth || 1)) * 100}%`,
            top: `${(marqueeRect.y1 / (imageHeight || 1)) * 100}%`,
            width: `${((marqueeRect.x2 - marqueeRect.x1) / (imageWidth || 1)) * 100}%`,
            height: `${((marqueeRect.y2 - marqueeRect.y1) / (imageHeight || 1)) * 100}%`,
          }}
        />
      )}

      {/* Crop selection: dim everything outside the kept rect. Overlay is
          pointer-events-none so a new drag can start anywhere on the image. */}
      {tool === "crop" && cropRect && (cropRect.x2 > cropRect.x1 || cropRect.y2 > cropRect.y1) && (
        <div
          className="pointer-events-none absolute rounded-sm border-2 border-dashed border-primary"
          style={{
            left: `${(cropRect.x1 / (imageWidth || 1)) * 100}%`,
            top: `${(cropRect.y1 / (imageHeight || 1)) * 100}%`,
            width: `${(Math.max(0, cropRect.x2 - cropRect.x1) / (imageWidth || 1)) * 100}%`,
            height: `${(Math.max(0, cropRect.y2 - cropRect.y1) / (imageHeight || 1)) * 100}%`,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.55)",
          }}
        >
          <span
            className="absolute -top-7 start-0 whitespace-nowrap rounded-md bg-black/75 px-2 py-0.5 text-[11px] font-bold text-white"
            dir="ltr"
          >
            {cropRect.x2 - cropRect.x1}×{cropRect.y2 - cropRect.y1}
          </span>
        </div>
      )}
      </div>
      </div>
    </div>
  );
});
