"use client";

import { FormEvent, ReactNode, useEffect, useId, useRef, useState } from "react";
import { ArrowRight, Check, ChevronDown, FileText, FileUp, LoaderCircle, X, Link2, Globe, CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Job, Project } from "@/lib/types";
import { Btn, IconBtn } from "@/components/ui";

export function ProjectDialog({ title, busy = false, onClose, children }: {
  title: string;
  busy?: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const { t } = useI18n();

  useEffect(() => {
    const dialog = ref.current;
    const previousOverflow = document.body.style.overflow;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-busy={busy}
      className="m-auto max-h-[90dvh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto rounded-card border border-line bg-elev p-0 text-ink shadow-2xl backdrop:bg-black/60 backdrop:backdrop-blur-sm"
      onCancel={(e) => { e.preventDefault(); if (!busy) onClose(); }}
      onKeyDown={(e) => {
        if (e.key !== "Tab") return;
        const focusable = Array.from(e.currentTarget.querySelectorAll<HTMLElement>(
          'button, input, select, textarea, summary, a[href], [tabindex]',
        )).filter((el) => el.tabIndex >= 0 && !el.matches(":disabled") && el.getClientRects().length > 0);
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!first) { e.preventDefault(); return; }
        if (e.shiftKey && (document.activeElement === first || document.activeElement === e.currentTarget)) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        }
      }}
      onClick={(e) => {
        if (e.target !== e.currentTarget || busy) return;
        const rect = e.currentTarget.getBoundingClientRect();
        if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) onClose();
      }}
    >
      <div className="flex items-center justify-between gap-4 border-b border-line px-6 py-4">
        <h2 id={titleId} className="font-display text-xl font-extrabold">{title}</h2>
        <IconBtn label={t("common.close")} disabled={busy} onClick={onClose}><X size={18} /></IconBtn>
      </div>
      <div className="p-6">{children}</div>
    </dialog>
  );
}

function isPdf(file: File) {
  return file.size > 0 && (file.type === "application/pdf" || (!file.type && /\.pdf$/i.test(file.name)));
}

export function CreateProjectDialog({ initialFile, onClose, onCreated }: {
  initialFile: File | null;
  onClose: () => void;
  onCreated: (project: Project) => void;
}) {
  const { t } = useI18n();
  const inputId = useId();
  const errorId = useId();
  const fileRef = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);
  const [file, setFile] = useState<File | null>(initialFile && isPdf(initialFile) ? initialFile : null);
  const [name, setName] = useState(initialFile && isPdf(initialFile) ? initialFile.name.replace(/\.pdf$/i, "") : "");
  const [pdfType, setPdfType] = useState("manga");
  const [fileError, setFileError] = useState(!!initialFile && !isPdf(initialFile));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  // Link mode state (preview-first: discover globally, then create + import)
  const [activeTab, setActiveTab] = useState<"file" | "link">("file");
  const [chapterUrl, setChapterUrl] = useState("");
  const [discoveredImages, setDiscoveredImages] = useState<Array<{url: string; label: string}>>([]);
  const [discoveryToken, setDiscoveryToken] = useState("");
  const [discoveryTruncated, setDiscoveryTruncated] = useState(false);
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState("");
  const [importing, setImporting] = useState(false);
  const [importStatus, setImportStatus] = useState("");

  async function pollJob(jobId: string): Promise<Job> {
    const deadline = Date.now() + 10 * 60 * 1000;
    for (;;) {
      const job = await api.get<Job>(`/api/jobs/${jobId}/`);
      if (job.status === "success" || job.status === "failed" || job.status === "cancelled") return job;
      setImportStatus(job.stage || `${Math.round((job.progress || 0) * 100)}%`);
      if (Date.now() > deadline) throw new Error("import timeout");
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  function selectFile(next: File | null) {
    if (!next) return;
    setError("");
    if (!isPdf(next)) {
      setFileError(true);
      return;
    }
    setFileError(false);
    setFile(next);
    setName(next.name.replace(/\.pdf$/i, ""));
  }

  async function discoverImages() {
    if (!chapterUrl.trim()) return;
    setDiscoverError("");
    setDiscovering(true);
    setDiscoveredImages([]);
    setDiscoveryToken("");
    setDiscoveryTruncated(false);
    setSelectedIndices(new Set());
    try {
      // Global preview endpoint — no project exists yet at this point.
      const response = await api.post<{images: Array<{url: string; label: string}>; token: string; truncated?: boolean}>("/api/chapter-images", {url: chapterUrl.trim()});
      setDiscoveredImages(response.images);
      setDiscoveryToken(response.token);
      setDiscoveryTruncated(!!response.truncated);
      // Default to all pages selected; uncheck/delete the unwanted ones.
      setSelectedIndices(new Set(response.images.map((_, i) => i)));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setDiscoverError(message || t("dash.linkError"));
    } finally {
      setDiscovering(false);
    }
  }

  function toggleSelectAll() {
    if (selectedIndices.size === discoveredImages.length) {
      setSelectedIndices(new Set());
    } else {
      setSelectedIndices(new Set(discoveredImages.keys()));
    }
  }

  function toggleIndex(index: number) {
    const next = new Set(selectedIndices);
    if (next.has(index)) {
      next.delete(index);
    } else {
      next.add(index);
    }
    setSelectedIndices(next);
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (activeTab === "file") {
      if (!file || fileError || inFlight.current) return;
    } else {
      // Link mode needs a stored preview token + at least one selected page.
      if (selectedIndices.size === 0 || !discoveryToken || inFlight.current) return;
    }
    const form = new FormData(e.currentTarget);
    const body = new FormData();

    if (activeTab === "file") {
      body.append("pdf_file", file!);
      body.append("uses_page_sources", "false");
    } else {
      body.append("uses_page_sources", "true");
      body.append("source_url", chapterUrl.trim());
    }

    body.append("name", name.trim() || (activeTab === "file" ? file!.name.replace(/\.pdf$/i, "") : "Imported Chapter"));
    body.append("pdf_type", pdfType);
    body.append("chapter_id", String(form.get("chapter_id") ?? "").trim());
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const project = await api.uploadForm<Project>("/api/projects/", body);

      // Link mode: download the selected pages in original quality (server
      // archives originals + standardized JPGs) and wait for the import job
      // before opening, so the workspace never lands on an empty project.
      if (activeTab === "link") {
        setImporting(true);
        setImportStatus(t("dash.importing"));
        try {
          const indices = Array.from(selectedIndices).sort((a, b) => a - b);
          const job = await api.post<Job>(`/api/projects/${project.id}/import-pages/`, {
            token: discoveryToken,
            indices
          });
          const done = await pollJob(job.id);
          if (done.status !== "success") {
            throw new Error(done.error_message || t("dash.uploadError"));
          }
          const fresh = await api.get<Project>(`/api/projects/${project.id}/`);
          onCreated(fresh);
          return;
        } catch (err: unknown) {
          // Project already exists (visible after closing) — surface why the
          // page download failed so the user can retry from the workspace.
          const message = err instanceof Error ? err.message : String(err);
          setError(message || t("dash.uploadError"));
          inFlight.current = false;
          setBusy(false);
          return;
        } finally {
          setImporting(false);
          setImportStatus("");
        }
      }

      onCreated(project);
    } catch (err: unknown) {
      // Surface the server's reason (status + body) next to the generic
      // hint — otherwise every failure looks identical and can't be fixed.
      const detail = err instanceof Error && err.message ? ` (${err.message})` : "";
      setError(`${t("dash.uploadError")}${detail}`);
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <ProjectDialog title={t("dash.newProject")} busy={busy} onClose={onClose}>
      <p className="mb-5 text-sm leading-relaxed text-muted">{t("dash.createIntro")}</p>
      <form onSubmit={submit}>
        {/* Tab Switcher */}
        <div className="mb-5 flex gap-1 rounded-inner bg-surface2/50 p-1" role="tablist" aria-label={t("dash.newProject")}>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "file"}
            onClick={() => setActiveTab("file")}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition-colors ${activeTab === "file" ? "bg-elev text-ink shadow-sm" : "text-muted hover:text-ink"}`}
            disabled={busy}
          >
            <FileText size={16} />
            {t("dash.fileTab")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "link"}
            onClick={() => setActiveTab("link")}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition-colors ${activeTab === "link" ? "bg-elev text-ink shadow-sm" : "text-muted hover:text-ink"}`}
            disabled={busy}
          >
            <Globe size={16} />
            {t("dash.linkTab")}
          </button>
        </div>

        <fieldset disabled={busy} className="min-w-0 space-y-5">
          {/* File Tab */}
          {activeTab === "file" && (
            <>
              <div
                className={`relative rounded-inner border-2 border-dashed p-5 text-center transition-colors ${dragOver ? "border-primary bg-primary/10" : "border-line-strong bg-surface2/50"}`}
                onDragOver={(e) => { e.preventDefault(); if (!busy) setDragOver(true); }}
                onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragOver(false); }}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  if (!busy) selectFile(e.dataTransfer.files[0] ?? null);
                }}
              >
                {file ? <FileText size={28} className="mx-auto mb-3 text-primary" /> : <FileUp size={28} className="mx-auto mb-3 text-primary" />}
                <p className="break-words text-sm font-bold" dir="auto">{file ? file.name : t("dash.dropPdf")}</p>
                <p className="mt-1 text-xs text-muted">{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB · PDF` : t("dash.pdfOnly")}</p>
                <input
                  ref={fileRef}
                  id={inputId}
                  type="file"
                  accept="application/pdf,.pdf"
                  className="sr-only"
                  tabIndex={-1}
                  aria-label={t("dash.file")}
                  onChange={(e) => { selectFile(e.target.files?.[0] ?? null); e.target.value = ""; }}
                />
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  <Btn type="button" variant="outline" onClick={() => fileRef.current?.click()}>
                    {file ? t("dash.replaceFile") : t("dash.chooseFile")}
                  </Btn>
                  {file && <Btn type="button" variant="ghost" onClick={() => { setFile(null); setName(""); setFileError(false); }}>{t("dash.removeFile")}</Btn>}
                </div>
              </div>
              {fileError && <p role="alert" className="text-sm text-danger">{t("dash.invalidPdf")}</p>}

              {file && <>
                <label className="block">
                  <span className="mb-2 block text-sm font-semibold">{t("dash.projectName")}</span>
                  <input value={name} onChange={(e) => setName(e.target.value)} className="input-base" maxLength={200} dir="auto" />
                </label>
                <fieldset>
                  <legend className="mb-2 text-sm font-semibold">{t("dash.type")}</legend>
                  <div className="grid grid-cols-2 gap-3">
                    {(["manga", "manhwa"] as const).map((type) => (
                      <label key={type} className={`relative cursor-pointer rounded-inner border p-3 transition-colors focus-within:ring-2 focus-within:ring-primary ${pdfType === type ? "border-primary bg-primary/5" : "border-line bg-surface"}`}>
                        <input type="radio" name="pdf_type" value={type} checked={pdfType === type} onChange={() => setPdfType(type)} className="sr-only" />
                        <span className="flex items-center justify-between gap-2 text-sm font-bold">{t(type === "manga" ? "dash.manga" : "dash.manhwa")}{pdfType === type && <Check size={15} className="text-primary" />}</span>
                        <span className="mt-1 block text-xs text-muted">{t(type === "manga" ? "dash.mangaHint" : "dash.manhwaHint")}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <details className="group rounded-inner border border-line px-4 py-3">
                  <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-semibold [&::-webkit-details-marker]:hidden">
                    {t("dash.additionalDetails")}<ChevronDown size={16} className="transition-transform group-open:rotate-180" />
                  </summary>
                  <label className="mt-4 block">
                    <span className="mb-2 block text-xs text-muted">{t("dash.chapterId")}</span>
                    <input name="chapter_id" className="input-base" maxLength={100} dir="auto" />
                  </label>
                </details>
              </>}
            </>
          )}

          {/* Link Tab */}
          {activeTab === "link" && (
            <>
              <div className="space-y-4">
                <label className="block">
                  <span className="mb-2 block text-sm font-semibold">{t("dash.chapterUrl")}</span>
                  <div className="flex gap-2">
                    <input
                      type="url"
                      value={chapterUrl}
                      onChange={(e) => setChapterUrl(e.target.value)}
                      placeholder={t("dash.chapterUrlHint")}
                      className="input-base flex-1"
                      maxLength={2048}
                      disabled={busy || discovering}
                    />
                    <Btn
                      type="button"
                      variant={discovering ? "outline" : "primary"}
                      onClick={discoverImages}
                      disabled={busy || discovering || !chapterUrl.trim()}
                    >
                      {discovering ? <LoaderCircle size={16} className="animate-spin" /> : <Link2 size={16} />}
                      {discovering ? t("common.loading") : t("dash.findImages")}
                    </Btn>
                  </div>
                  {discoverError && <p className="mt-2 text-sm text-danger" role="alert">{discoverError}</p>}
                  {!discoverError && !discovering && chapterUrl.trim() && <p className="mt-2 text-xs text-muted">{t("dash.chapterUrlHint")}</p>}
                </label>

                {discoveredImages.length > 0 && (
                  <fieldset>
                    <legend className="mb-3 flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold">{t("dash.selectImagesHint")}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-muted" role="status">
                          {selectedIndices.size}/{discoveredImages.length}
                        </span>
                        <label className="flex items-center gap-1.5 text-xs text-muted cursor-pointer">
                          <input
                            type="checkbox"
                            checked={discoveredImages.length > 0 && selectedIndices.size === discoveredImages.length}
                            onChange={toggleSelectAll}
                            className="rounded border-line text-primary focus:ring-primary"
                          />
                          {selectedIndices.size === discoveredImages.length ? t("dash.clearSelection") : t("dash.selectAll")}
                        </label>
                      </div>
                    </legend>
                    {discoveryTruncated && <p className="mb-2 text-xs text-muted">{t("dash.truncatedHint")}</p>}
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 max-h-80 overflow-y-auto p-2 border border-line rounded-inner">
                      {discoveredImages.map((image, index) => {
                        const selected = selectedIndices.has(index);
                        return (
                        <div key={index} className={`relative group rounded-inner overflow-hidden border-2 transition-colors ${selected ? "border-primary bg-primary/5" : "border-transparent hover:border-line"}`}>
                          <button
                            type="button"
                            onClick={() => toggleIndex(index)}
                            aria-pressed={selected}
                            aria-label={`${image.label || `Page ${index + 1}`} — ${selected ? t("dash.clearSelection") : t("dash.selectAll")}`}
                            className="block w-full cursor-pointer"
                          >
                            <img
                              src={image.url}
                              alt={image.label || `Page ${index + 1}`}
                              loading="lazy"
                              className={`w-full aspect-[3/4] object-cover transition-opacity ${selected ? "" : "opacity-50 grayscale"}`}
                              onError={(e) => { e.currentTarget.style.display = 'none'; }}
                            />
                            <span className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity">
                              {selected && <CheckCircle2 size={28} className="text-primary" />}
                            </span>
                            <span className="absolute bottom-0 left-0 right-0 p-2 pe-8 bg-gradient-to-t from-black/70 to-transparent text-xs text-white truncate">
                              {image.label || `Page ${index + 1}`}
                            </span>
                          </button>
                          <span className={`absolute top-1.5 start-1.5 rounded px-1.5 py-0.5 text-[10px] font-bold ${selected ? "bg-primary text-white" : "bg-black/60 text-white"}`}>
                            {index + 1}
                          </span>
                          <button
                            type="button"
                            onClick={() => toggleIndex(index)}
                            aria-label={t("dash.removeImage")}
                            title={t("dash.removeImage")}
                            className="absolute bottom-1 end-1 rounded-md bg-black/70 p-1.5 text-white/90 transition-colors hover:bg-danger hover:text-white"
                          >
                            <X size={13} />
                          </button>
                        </div>
                        );
                      })}
                    </div>
                  </fieldset>
                )}

                {discoveredImages.length > 0 && (
                  <>
                    <label className="block">
                      <span className="mb-2 block text-sm font-semibold">{t("dash.projectName")}</span>
                      <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("dash.importedChapter")} className="input-base" maxLength={200} dir="auto" />
                    </label>
                    <fieldset>
                      <legend className="mb-2 text-sm font-semibold">{t("dash.type")}</legend>
                      <div className="grid grid-cols-2 gap-3">
                        {(["manga", "manhwa"] as const).map((type) => (
                          <label key={type} className={`relative cursor-pointer rounded-inner border p-3 transition-colors focus-within:ring-2 focus-within:ring-primary ${pdfType === type ? "border-primary bg-primary/5" : "border-line bg-surface"}`}>
                            <input type="radio" name="pdf_type" value={type} checked={pdfType === type} onChange={() => setPdfType(type)} className="sr-only" />
                            <span className="flex items-center justify-between gap-2 text-sm font-bold">{t(type === "manga" ? "dash.manga" : "dash.manhwa")}{pdfType === type && <Check size={15} className="text-primary" />}</span>
                            <span className="mt-1 block text-xs text-muted">{t(type === "manga" ? "dash.mangaHint" : "dash.manhwaHint")}</span>
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <label className="block">
                      <span className="mb-2 block text-xs text-muted">{t("dash.chapterId")}</span>
                      <input name="chapter_id" className="input-base" maxLength={100} dir="auto" />
                    </label>
                    {importing && importStatus && <p role="status" className="text-xs text-muted">{importStatus}</p>}
                  </>
                )}
              </div>
            </>
          )}
        </fieldset>

        {error && <p id={errorId} role="alert" className="mt-4 rounded-inner bg-danger/10 p-3 text-sm text-danger">{error}</p>}
        <div className="mt-6 flex flex-wrap items-center justify-end gap-3 border-t border-line pt-5">
          <Btn type="button" variant="ghost" disabled={busy} onClick={onClose}>{t("modal.cancel")}</Btn>
          <Btn
            type="submit"
            disabled={
              busy ||
              (activeTab === "file" && (!file || fileError)) ||
              (activeTab === "link" && (selectedIndices.size === 0 || !discoveryToken)) ||
              (activeTab === "link" && importing)
            }
            aria-describedby={error ? errorId : undefined}
          >
            {(busy || (activeTab === "link" && importing)) ? <LoaderCircle size={16} className="animate-spin" /> : <ArrowRight size={16} className="rtl:rotate-180" />}
            {busy ? (activeTab === "link" && importing && importStatus ? importStatus : t("dash.importing")) : (activeTab === "link" ? `${t("dash.createAndOpen")} (${selectedIndices.size})` : t("dash.createAndOpen"))}
          </Btn>
        </div>
        {busy && <p role="status" className="mt-3 text-center text-xs text-muted">{activeTab === "link" ? t("dash.importing") : t("dash.uploadWait")}</p>}
      </form>
    </ProjectDialog>
  );
}
