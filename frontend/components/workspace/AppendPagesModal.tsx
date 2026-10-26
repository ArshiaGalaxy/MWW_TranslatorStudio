"use client";

import { useEffect, useRef, useState } from "react";
import { FileUp, LoaderCircle, X } from "lucide-react";
import { Modal } from "@/components/ui";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const ACCEPT = "image/jpeg,image/png,image/webp,image/gif";
const MAX_FILES = 20;
const MAX_ONE = 20 * 1024 * 1024;
const MAX_TOTAL = 500 * 1024 * 1024;

export function AppendPagesModal({ projectId, pageNumbers, defaultAfter, onClose, onAppended }: {
  projectId: string;
  pageNumbers: number[];
  defaultAfter: number | null;
  onClose: () => void;
  onAppended: (inserted: number[]) => void;
}) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [urls, setUrls] = useState<string[]>([]);
  const [position, setPosition] = useState<string>(
    defaultAfter === null ? "end" : String(defaultAfter),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Revoke preview object URLs when replaced or unmounted.
  useEffect(() => () => urls.forEach((u) => URL.revokeObjectURL(u)), [urls]);

  function addFiles(next: FileList | File[] | null) {
    if (!next || busy) return;
    setError("");
    const list = [...files, ...Array.from(next)];
    const images = list.filter((f) => f.type.startsWith("image/"));
    if (images.length !== list.length) {
      setError(t("pages.imagesOnly"));
      return;
    }
    if (images.length === 0 || images.length > MAX_FILES) {
      setError(t("pages.maxFiles", { max: MAX_FILES }));
      return;
    }
    if (images.some((f) => f.size > MAX_ONE || f.size === 0)) {
      setError(t("pages.maxOneFile"));
      return;
    }
    if (images.reduce((s, f) => s + f.size, 0) > MAX_TOTAL) {
      setError(t("pages.maxTotal"));
      return;
    }
    urls.forEach((u) => URL.revokeObjectURL(u));
    setUrls(images.map((f) => URL.createObjectURL(f)));
    setFiles(images);
  }

  function removeFile(index: number) {
    URL.revokeObjectURL(urls[index]);
    setFiles((fs) => fs.filter((_, i) => i !== index));
    setUrls((us) => us.filter((_, i) => i !== index));
  }

  async function upload() {
    if (!files.length || busy) return;
    setBusy(true);
    setError("");
    try {
      const body = new FormData();
      files.forEach((f) => body.append("images", f, f.name));
      // Backend accepts "start" | "end" | "<page number after which to insert>".
      body.append("position", position === "start" || position === "end" ? position : String(Number(position)));
      const result = await api.uploadForm<{ inserted: number[] }>(
        `/api/projects/${projectId}/pages/append`, body,
      );
      onAppended(result.inserted);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("toast.actionFailed"));
      setBusy(false);
    }
  }

  return (
    <Modal title={t("pages.addPages")} onClose={() => { if (!busy) onClose(); }} wide>
      <p className="mb-4 text-sm text-muted">{t("pages.appendHint")}</p>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple
        disabled={busy}
        className="sr-only"
        aria-label={t("pages.chooseImages")}
        onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed border-line-strong bg-surface2/50 px-4 py-6 text-sm transition-colors hover:border-primary disabled:opacity-50"
      >
        <FileUp size={22} className="text-primary" />
        <span className="font-bold">{t("pages.chooseImages")}</span>
        <span className="text-xs text-muted">{t("pages.imagesOnly")}</span>
      </button>
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}

      {files.length > 0 && (
        <>
          <div className="mt-4 grid max-h-72 grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-4">
            {files.map((f, i) => (
              <div key={`${f.name}-${i}`} className="relative overflow-hidden rounded-lg border border-line">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={urls[i]} alt={f.name} loading="lazy" className="aspect-[3/4] w-full object-cover" />
                <span className="absolute start-1 top-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-bold text-white">{i + 1}</span>
                <button
                  type="button"
                  onClick={() => removeFile(i)}
                  disabled={busy}
                  aria-label={`${t("pages.removeImage")} ${f.name}`}
                  title={t("pages.removeImage")}
                  className="absolute bottom-1 end-1 rounded-md bg-black/70 p-1.5 text-white/90 hover:bg-danger hover:text-white disabled:opacity-50"
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>

          <label className="mt-4 block text-sm font-medium">
            <span className="mb-2 block text-xs font-bold uppercase tracking-wider text-muted">
              {t("pages.insertPosition")}
            </span>
            <select
              value={position}
              onChange={(e) => setPosition(e.target.value)}
              disabled={busy}
              className="input-base"
            >
              <option value="start">{t("pages.insertStart")}</option>
              {pageNumbers.map((n) => (
                <option key={n} value={String(n)}>
                  {t("pages.insertAfter", { page: n })}
                </option>
              ))}
              <option value="end">{t("pages.insertEnd")}</option>
            </select>
          </label>

          <button
            type="button"
            onClick={() => void upload()}
            disabled={busy || !files.length}
            className="btn btn-primary mt-4 w-full py-2.5 text-sm"
          >
            {busy ? <LoaderCircle size={15} className="animate-spin" /> : null}
            {busy ? t("pages.uploading") : t("pages.upload", { count: files.length })}
          </button>
        </>
      )}
    </Modal>
  );
}
