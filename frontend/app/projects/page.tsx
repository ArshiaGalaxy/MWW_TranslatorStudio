"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, BookOpenText, FileUp, LoaderCircle, LogOut, Plus, RefreshCw, Search, Settings2, Trash2, X } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { DictKey, useI18n } from "@/lib/i18n";
import { useToast } from "@/lib/theme";
import { Project } from "@/lib/types";
import { Btn, IconBtn, LangThemeControls, Logo, ProgressBar, StatusBadge, Wordmark } from "@/components/ui";
import { CreateProjectDialog, ProjectDialog } from "@/components/projects/ProjectDialog";

const STATUSES: { value: string; label: DictKey }[] = [
  { value: "created", label: "status.created" },
  { value: "extracting", label: "status.extracting" },
  { value: "ready", label: "status.ready" },
  { value: "translating", label: "status.translating" },
  { value: "applying", label: "status.applying" },
  { value: "done", label: "status.done" },
  { value: "failed", label: "status.failed" },
];

export default function ProjectsPage() {
  const { me, loading, logout } = useAuth();
  const router = useRouter();
  const { t, locale } = useI18n();
  const toast = useToast();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [creating, setCreating] = useState(false);
  const [initialFile, setInitialFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState(false);
  const deletingRef = useRef(false);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const request = ++requestId.current;
    setRefreshing(true);
    setLoadError(false);
    try {
      const result = await api.get<Project[]>("/api/projects/");
      if (request === requestId.current) setProjects(result);
    } catch {
      if (request === requestId.current) setLoadError(true);
    } finally {
      if (request === requestId.current) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      // This is a request generation counter, not a DOM ref.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      requestId.current++;
    };
  }, [loading, router, load]);

  const visible = useMemo(() => {
    const query = search.trim().toLocaleLowerCase(locale);
    return (projects ?? []).filter((project) =>
      (!status || project.status === status) &&
      (!type || project.pdf_type === type) &&
      (!query || `${project.name} ${project.chapter_id}`.toLocaleLowerCase(locale).includes(query)),
    );
  }, [projects, search, status, type, locale]);
  const filtered = !!(search.trim() || status || type);
  const number = (value: number) => value.toLocaleString(locale);

  function openCreate(file: File | null = null) {
    setInitialFile(file);
    setCreating(true);
  }

  function clearFilters() {
    setSearch(""); setStatus(""); setType("");
  }

  async function remove() {
    if (!deleting || deletingRef.current) return;
    deletingRef.current = true;
    setDeleteBusy(true);
    setDeleteError(false);
    try {
      await api.delete(`/api/projects/${deleting.id}/`);
      // Invalidate a refresh started before deletion so it cannot restore the card.
      requestId.current++;
      setRefreshing(false);
      setProjects((items) => items?.filter((p) => p.id !== deleting.id) ?? null);
      setDeleting(null);
      toast.push(t("dash.deleted"), "success");
    } catch {
      setDeleteError(true);
    } finally {
      deletingRef.current = false;
      setDeleteBusy(false);
    }
  }

  if (loading) {
    return <main className="flex min-h-screen items-center justify-center gap-3 text-muted" role="status"><LoaderCircle size={20} className="animate-spin" />{t("common.loading")}</main>;
  }

  return (
    <main className="min-h-screen">
      <header className="border-b border-line bg-elev/70">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-8">
          <Link href="/" className="flex items-center gap-2.5"><Logo /><Wordmark /></Link>
          <div className="flex items-center gap-1.5 sm:gap-3">
            <LangThemeControls />
            <span className="mx-1 h-5 w-px bg-line" aria-hidden />
            <IconBtn label={t("nav.settings")} onClick={() => router.push("/settings")}><Settings2 size={17} /></IconBtn>
            <IconBtn label={t("nav.signOut")} onClick={() => { void logout().catch(() => {}); }}><LogOut size={17} /></IconBtn>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-12">
        <div className="mb-8 flex flex-wrap items-start justify-between gap-5">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="font-display text-3xl font-extrabold tracking-tight sm:text-4xl">{t("dash.myProjects")}</h1>
              {projects && <span className="rounded-full border border-line bg-elev px-3 py-1 text-sm font-semibold text-muted">{number(projects.length)}</span>}
            </div>
            <p className="mt-3 text-sm leading-relaxed text-muted sm:text-base">{t("dash.libraryIntro")}</p>
          </div>
          <Btn onClick={() => openCreate()} className="min-h-11"><Plus size={18} />{t("dash.newProject")}</Btn>
        </div>

        {(projects?.length ?? 0) > 0 && <section aria-label={t("dash.filterProjects")} className="mb-6">
          <div className="flex flex-col gap-3 rounded-card border border-line bg-elev p-3 sm:flex-row sm:items-center">
            <div className="relative min-w-0 flex-1">
              <Search size={18} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-muted" />
              <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("dash.search")} aria-label={t("dash.search")} className="input-base !min-h-11 !ps-10 !pe-10" />
              {search && <button type="button" aria-label={t("dash.clearSearch")} onClick={() => setSearch("")} className="absolute end-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-muted hover:text-ink"><X size={16} /></button>}
            </div>
            <div className="grid grid-cols-[1fr_1fr_auto] gap-2 sm:flex">
              <select aria-label={t("dash.filterStatus")} value={status} onChange={(e) => setStatus(e.target.value)} className="input-base min-w-0 !min-h-11 sm:!w-auto">
                <option value="">{t("dash.allStatuses")}</option>
                {STATUSES.map((s) => <option key={s.value} value={s.value}>{t(s.label)}</option>)}
              </select>
              <select aria-label={t("dash.filterType")} value={type} onChange={(e) => setType(e.target.value)} className="input-base min-w-0 !min-h-11 sm:!w-auto">
                <option value="">{t("dash.allTypes")}</option>
                <option value="manga">{t("dash.manga")}</option>
                <option value="manhwa">{t("dash.manhwa")}</option>
              </select>
              <IconBtn label={t("dash.refresh")} disabled={refreshing} onClick={() => void load()} className="!h-11 !w-11"><RefreshCw size={17} className={refreshing ? "animate-spin" : ""} /></IconBtn>
            </div>
          </div>
          <div className="mt-3 flex min-h-7 items-center justify-between gap-3 text-xs text-muted">
            <p role="status">{t("dash.showing", { count: number(visible.length), total: number(projects!.length) })}</p>
            {filtered && <button type="button" onClick={clearFilters} className="rounded px-2 py-1 font-semibold text-primary hover:underline">{t("dash.clearFilters")}</button>}
          </div>
        </section>}

        {loadError && <div role="alert" className="mb-6 flex flex-wrap items-center gap-4 rounded-card border border-danger/25 bg-danger/5 p-5">
          <AlertCircle size={22} className="shrink-0 text-danger" />
          <div className="min-w-0 flex-1"><h2 className="font-bold">{t("dash.loadError")}</h2><p className="mt-1 text-sm text-muted">{t("dash.loadErrorHint")}</p></div>
          <Btn variant="outline" disabled={refreshing} onClick={() => void load()}><RefreshCw size={16} />{t("dash.retry")}</Btn>
        </div>}

        {projects === null ? (!loadError && <div aria-label={t("common.loading")} role="status" className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => <div key={i} className="overflow-hidden rounded-card border border-line bg-elev"><div className="skeleton h-44" /><div className="space-y-4 p-5"><div className="skeleton h-5 w-3/4" /><div className="skeleton h-3 w-1/2" /><div className="skeleton h-2 w-full" /></div></div>)}
        </div>) : projects.length === 0 ? (
          <section
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragOver(false); }}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files[0]) openCreate(e.dataTransfer.files[0]); }}
            className={`flex flex-col items-center rounded-card border-2 border-dashed px-6 py-16 text-center transition-colors sm:py-24 ${dragOver ? "border-primary bg-primary/10" : "border-line-strong bg-elev/60"}`}
          >
            <span className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-primary/15 bg-primary/5 text-primary"><FileUp size={30} /></span>
            <h2 className="font-display text-2xl font-extrabold">{t("dash.emptyTitle")}</h2>
            <p className="mt-3 max-w-sm text-sm leading-relaxed text-muted">{t("dash.emptySub")}</p>
            <Btn className="mt-7 min-h-11" onClick={() => openCreate()}><Plus size={17} />{t("dash.newProject")}</Btn>
            <p className="mt-4 text-xs text-muted">{t("dash.pdfOnly")}</p>
          </section>
        ) : visible.length === 0 ? (
          <section className="rounded-card border border-line bg-elev px-6 py-16 text-center">
            <Search size={28} className="mx-auto mb-4 text-muted" /><h2 className="text-xl font-bold">{t("dash.noMatches")}</h2>
            <p className="mt-2 text-sm text-muted">{t("dash.noMatchesHint")}</p>
            <Btn variant="outline" className="mt-6" onClick={clearFilters}>{t("dash.clearFilters")}</Btn>
          </section>
        ) : <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((p) => <ProjectCard key={p.id} p={p} onDelete={() => { setDeleteError(false); setDeleting(p); }} />)}
        </div>}
      </div>

      {creating && <CreateProjectDialog initialFile={initialFile} onClose={() => setCreating(false)} onCreated={(project) => { setCreating(false); router.push(`/projects/${project.id}`); }} />}
      {deleting && <ProjectDialog title={t("dash.deleteTitle")} busy={deleteBusy} onClose={() => setDeleting(null)}>
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-danger/10 text-danger"><Trash2 size={22} /></div>
        <p className="break-words text-sm leading-relaxed text-muted">{t("dash.deleteBody", { name: deleting.name })}</p>
        {deleteError && <p role="alert" className="mt-4 text-sm text-danger">{t("dash.deleteError")}</p>}
        <div className="mt-6 flex justify-end gap-3">
          <Btn variant="ghost" disabled={deleteBusy} onClick={() => setDeleting(null)}>{t("modal.cancel")}</Btn>
          <Btn variant="danger" disabled={deleteBusy} onClick={() => void remove()}>{deleteBusy ? <LoaderCircle size={16} className="animate-spin" /> : <Trash2 size={16} />}{t(deleteBusy ? "dash.deleting" : "dash.delete")}</Btn>
        </div>
      </ProjectDialog>}
    </main>
  );
}

function ProjectCard({ p, onDelete }: { p: Project; onDelete: () => void }) {
  const { t, locale } = useI18n();
  const [imageError, setImageError] = useState(false);
  const progress = Math.max(0, Math.min(100, p.progress_percent || 0));
  const number = (value: number) => value.toLocaleString(locale);

  return (
    <article className="group flex min-w-0 flex-col overflow-hidden rounded-card border border-line bg-elev transition-shadow hover:shadow-card">
      <Link href={`/projects/${p.id}`} className="flex flex-1 flex-col outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary">
        <div className="relative flex h-44 items-center justify-center overflow-hidden border-b border-line bg-surface2">
          <div className="flex flex-col items-center gap-2 text-muted"><BookOpenText size={32} strokeWidth={1.3} /><span className="text-xs">{t("dash.previewPending")}</span></div>
          {/* Backend media may not exist until extraction; keep a local fallback. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {!imageError && <img
            src={`/media/projects/${p.id}/pages/page-1.jpg`}
            alt=""
            loading="lazy"
            className="absolute inset-0 h-full w-full object-cover object-top motion-safe:transition-transform motion-safe:duration-500 motion-safe:group-hover:scale-[1.03]"
            onError={() => setImageError(true)}
          />}
          <span className="absolute bottom-3 start-3 rounded-lg bg-elev px-2.5 py-1 text-xs font-semibold text-ink shadow-sm">{t(p.pdf_type === "manhwa" ? "dash.manhwa" : "dash.manga")}</span>
        </div>
        <div className="flex flex-1 flex-col p-5">
          <div className="mb-3 flex items-center"><StatusBadge status={p.status} /></div>
          <h2 className="line-clamp-2 break-words text-lg font-bold leading-snug transition-colors group-hover:text-primary-strong" dir="auto">{p.name}</h2>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
            <span>{number(p.total_pages)} {t("dash.pages")}</span>
            {p.chapter_id && <span className="max-w-full truncate" dir="auto">{p.chapter_id}</span>}
          </div>
          {p.status === "failed" && <p className="mt-4 flex items-start gap-2 rounded-inner bg-danger/10 p-3 text-xs text-danger"><AlertCircle size={15} className="shrink-0" /><span>{t("dash.projectFailed")}</span></p>}
          <div className="mt-auto pt-6">
            <div className="mb-2 flex items-center justify-between gap-2 text-xs text-muted"><span>{t("dash.translationProgress")}</span><span className="font-semibold tabular-nums text-ink">{new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 }).format(progress / 100)}</span></div>
            <div role="meter" aria-label={t("dash.translationProgress")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
              <ProgressBar value={progress / 100} />
            </div>
            <p className="mt-2 text-xs text-muted">{p.total_blocks ? t("dash.translatedOf", { a: number(p.translated_count), b: number(p.total_blocks) }) : t("dash.waitingForOcr")}</p>
          </div>
        </div>
      </Link>
      <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-3">
        <Link href={`/projects/${p.id}`} className="inline-flex min-h-10 items-center gap-2 rounded text-sm font-semibold text-primary hover:underline">{t(p.status === "failed" ? "dash.reviewProject" : "dash.open")}<ArrowRight size={15} className="rtl:rotate-180" /></Link>
        <IconBtn label={t("dash.deleteNamed", { name: p.name })} onClick={onDelete} className="!h-10 !w-10 text-muted hover:!text-danger"><Trash2 size={16} /></IconBtn>
      </div>
    </article>
  );
}
