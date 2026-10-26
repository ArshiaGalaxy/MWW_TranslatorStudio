"use client";

import { useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { Modal } from "@/components/ui";
import { api } from "@/lib/api";
import { Job } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

type Discovery = { token: string; images: { url: string; label: string }[] };
export function ChapterImportModal({ projectId, onClose, onImport, beforeImport }: {
  projectId: string; onClose: () => void; onImport: (job: Job) => void;
  beforeImport: () => Promise<void>;
}) {
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<Discovery | null>(null);
  const [order, setOrder] = useState<number[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function discover() {
    setBusy(true); setError(""); setResult(null);
    try {
      const data = await api.post<Discovery>(`/api/projects/${projectId}/chapter-images`, { url });
      setResult(data); setOrder(data.images.map((_, i) => i)); setSelected(data.images.map((_, i) => i));
    } catch (e) { setError(e instanceof Error ? e.message : t("toast.actionFailed")); }
    finally { setBusy(false); }
  }
  async function importPages() {
    if (!result) return;
    setBusy(true); setError("");
    try {
      await beforeImport();
      const job = await api.post<Job>(`/api/projects/${projectId}/import-pages`, {
        token: result.token, indices: order.filter(i => selected.includes(i)),
      });
      onImport(job); onClose();
    } catch (e) { setError(e instanceof Error ? e.message : t("toast.actionFailed")); }
    finally { setBusy(false); }
  }
  function move(position: number, delta: number) {
    setOrder(old => { const next = [...old]; [next[position], next[position + delta]] = [next[position + delta], next[position]]; return next; });
  }
  return <Modal title={t("pages.link")} onClose={() => { if (!busy) onClose(); }} wide>
    <p className="mb-4 text-sm text-muted">{t("pages.linkHint")}</p>
    <form onSubmit={e => { e.preventDefault(); void discover(); }} className="flex flex-wrap gap-2">
      <input type="url" required maxLength={2048} aria-label={t("pages.url")} placeholder="https://…/chapter-1" value={url}
        onChange={e => { setUrl(e.target.value); setResult(null); }} disabled={busy} className="input-base min-w-0 flex-1" dir="ltr" />
      <button disabled={busy} className="btn btn-primary" type="submit">{busy ? "…" : t("pages.find")}</button>
    </form>
    {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
    {result && <>
      <div className="my-3 flex items-center justify-between text-xs text-muted">
        <span>{selected.length}/{result.images.length} · {t("pages.selectHint")}</span>
        <button className="btn btn-ghost text-xs" onClick={() => setSelected(selected.length ? [] : [...order])}>{t("pages.toggleAll")}</button>
      </div>
      <div className="max-h-80 space-y-2 overflow-y-auto">
        {order.map((index, position) => <div key={index} className="flex items-center gap-2 rounded-lg border border-line p-2">
          <label className="flex min-w-0 flex-1 items-center gap-2 text-xs">
            <input type="checkbox" checked={selected.includes(index)} disabled={busy} onChange={e => setSelected(old => e.target.checked ? [...old, index] : old.filter(i => i !== index))} />
            <span className="min-w-0"><strong>{position + 1}. {result.images[index].label || t("ws.page")}</strong><span className="block truncate text-muted" dir="ltr" title={result.images[index].url}>{result.images[index].url}</span></span>
          </label>
          <button aria-label={t("pages.up")} disabled={busy || position === 0} className="btn btn-ghost p-1" onClick={() => move(position, -1)}><ArrowUp size={14} /></button>
          <button aria-label={t("pages.down")} disabled={busy || position === order.length - 1} className="btn btn-ghost p-1" onClick={() => move(position, 1)}><ArrowDown size={14} /></button>
        </div>)}
      </div>
      <button className="btn btn-primary mt-4" disabled={busy || !selected.length} onClick={() => void importPages()}>{t("pages.append")} ({selected.length})</button>
    </>}
  </Modal>;
}
