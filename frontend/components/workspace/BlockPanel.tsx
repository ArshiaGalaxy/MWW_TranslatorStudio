"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import { Check, ClipboardPaste, Copy, Languages, LayoutGrid, Search, Trash2, X } from "lucide-react";
import { FontInfo, TextBlock } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { FontPicker } from "@/components/workspace/FontPicker";
import { BlockTypeBadge } from "@/components/ui";
const TYPE_ACCENT: Record<string, string> = {
  sfx: "border-s-danger/60",
  thinking: "border-s-warning/60",
};

interface Props {
  blocks: TextBlock[];
  selectedId: string | null;
  /** Extra ids in the active visual selection; canvas-side group actions
      (marquee, Shift+click) use the canvas, this panel offers delete-all. */
  multiIds?: string[];
  onSelect: (id: string, additive: boolean) => void;
  onDeleteMulti?: () => void;
  onPatch: (id: string, patch: Partial<TextBlock>) => void;
  /** Fired on blur of a translation field — parent persists text + fitted size. */
  onCommitTranslation?: (id: string, text: string) => void;
  /** Translate only this page's untranslated blocks. */
  onTranslatePage?: () => void;
  translateDisabled?: boolean;
  /** Increments to request focus on the primary block's panel textarea
      (the Tab-through-dialogs flow). */
  focusTick?: number;
  /** Style copy/paste (Task 6): clipboard lives in the page component. */
  styleClipboard?: Pick<TextBlock, "font_override" | "font_size_override" | "color" | "alignment" | "rotation"> | null;
  onCopyStyle?: (id: string) => void;
  onPasteSelection?: () => void;
  onPastePage?: () => void;
}

export const BlockPanel = memo(function BlockPanel({
  blocks,
  selectedId,
  multiIds = [],
  onSelect,
  onDeleteMulti,
  onPatch,
  onCommitTranslation,
  onTranslatePage,
  translateDisabled = false,
  focusTick = 0,
  styleClipboard = null,
  onCopyStyle,
  onPasteSelection,
  onPastePage,
}: Props) {
  const { t } = useI18n();
  const listRef = useRef<HTMLDivElement>(null);
  const [search, setSearch] = useState("");
  const [untranslatedOnly, setUntranslatedOnly] = useState(false);
  const [fonts, setFonts] = useState<FontInfo[]>([]);
  const [fontsError, setFontsError] = useState(false);
  const [fontsRetry, setFontsRetry] = useState(0);

  // Font list for the per-block font picker (visible error row + retry on
  // failure instead of a silently empty dropdown).
  useEffect(() => {
    let cancelled = false;
    setFontsError(false);
    api
      .get<FontInfo[]>("/api/fonts")
      .then((list) => {
        if (!cancelled) setFonts(list);
      })
      .catch(() => {
        if (!cancelled) setFontsError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [fontsRetry]);

  const selected = useMemo(
    () => blocks.find((b) => b.id === selectedId) ?? null,
    [blocks, selectedId],
  );

  // Client-side filter over the already-fetched page blocks (the canvas
  // needs the full set anyway, so this can never go stale).
  const visibleBlocks = useMemo(() => {
    const q = search.trim().toLowerCase();
    return blocks.filter((b) => {
      if (untranslatedOnly && b.is_translated) return false;
      if (
        q &&
        !b.original_text.toLowerCase().includes(q) &&
        !b.translation.toLowerCase().includes(q) &&
        !b.key.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
  }, [blocks, search, untranslatedOnly]);

  useEffect(() => {
    if (!selectedId || !listRef.current) return;
    const el = listRef.current.querySelector(`[data-block="${selectedId}"]`);
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedId]);

  // Tab flow: when the page bumps focusTick, the primary block's textarea
  // takes focus so typing continues without touching the mouse.
  useEffect(() => {
    if (!focusTick || !selectedId || !listRef.current) return;
    const ta = listRef.current.querySelector<HTMLTextAreaElement>(
      `[data-block="${selectedId}"] textarea`,
    );
    if (!ta) return;
    ta.focus();
    const len = ta.value.length;
    ta.setSelectionRange(len, len);
  }, [focusTick, selectedId]);

  return (
    <div className="flex h-full flex-col" data-panel>
      {/* Filter bar */}
      <div className="mb-2.5 flex shrink-0 items-center gap-2">
        <div className="relative flex-1">
          <Search
            size={13}
            className="pointer-events-none absolute start-2.5 top-1/2 -translate-y-1/2 text-faint"
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("ws.searchBlocks")}
            aria-label={t("ws.searchBlocks")}
            className="w-full rounded-xl border border-line bg-elev py-1.5 pe-7 ps-8 text-xs outline-none transition-colors placeholder:text-faint focus:border-primary"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute end-2 top-1/2 -translate-y-1/2 text-faint transition-colors hover:text-ink"
              aria-label={t("common.close")}
            >
              <X size={12} />
            </button>
          )}
        </div>
        <button
          onClick={() => setUntranslatedOnly((v) => !v)}
          aria-pressed={untranslatedOnly}
          title={t("ws.filterUntranslated")}
          className={`flex h-8 shrink-0 items-center gap-1 rounded-xl border px-2.5 text-[11px] font-semibold transition-colors ${
            untranslatedOnly
              ? "border-warning/40 bg-warning/12 text-warning"
              : "border-line bg-surface2 text-muted hover:text-ink"
          }`}
        >
          {untranslatedOnly && <Check size={12} />}
          <span >{t("ws.filterUntranslated")}</span>
        </button>
        {onTranslatePage && (
          <button
            onClick={onTranslatePage}
            disabled={translateDisabled}
            title={t("ws.translatePage")}
            aria-label={t("ws.translatePage")}
            className="btn btn-ghost flex h-8 shrink-0 items-center gap-1 rounded-xl px-2.5 text-[11px] font-semibold disabled:opacity-40"
          >
            <Languages size={12} />
            <span>{t("ws.translatePage")}</span>
          </button>
        )}
      </div>

      {/* Multi-selection strip: count + group actions */}
      {multiIds.length > 0 && (
        <div className="card-flat mb-2.5 flex shrink-0 items-center gap-2 px-3 py-2">
          <span className="min-w-0 flex-1 truncate text-[11px] font-semibold text-ink" data-multi-count>
            {t("ws.multiSelected", { n: multiIds.length + (selectedId ? 1 : 0) })}
          </span>
          {onDeleteMulti && (
            <button
              onClick={onDeleteMulti}
              title={t("ws.deleteAll")}
              className="btn btn-ghost flex h-7 shrink-0 items-center gap-1 rounded-lg px-2 text-[11px] font-semibold text-danger hover:!text-danger"
            >
              <Trash2 size={12} />
              {t("ws.deleteAll")}
            </button>
          )}
        </div>
      )}

      {selected && (
        <div className="card-flat mb-2.5 shrink-0 p-3.5">
          <div className="mb-2.5 flex items-center justify-between">
            <span className="font-mono text-xs text-primary-strong">{selected.key}</span>
            <span className="font-mono text-[10px] text-faint" dir="ltr">
              {selected.x1},{selected.y1} · {selected.x2 - selected.x1}×{selected.y2 - selected.y1}
            </span>
          </div>
          {/* Style copy/paste: font, size, color, alignment, rotation in one go */}
          {onCopyStyle && (
            <div className="mb-2.5 flex items-center gap-1.5 border-b border-line pb-2.5">
              <button
                onClick={() => onCopyStyle(selected.id)}
                title={t("ws.copyStyle")}
                aria-label={t("ws.copyStyle")}
                className="btn btn-ghost grid h-7 w-7 place-items-center rounded-lg p-0"
              >
                <Copy size={13} />
              </button>
              <button
                onClick={onPasteSelection}
                disabled={!styleClipboard || !onPasteSelection}
                title={t("ws.pasteStyle")}
                aria-label={t("ws.pasteStyle")}
                className="btn btn-ghost grid h-7 w-7 place-items-center rounded-lg p-0 disabled:opacity-40"
              >
                <ClipboardPaste size={13} />
              </button>
              <button
                onClick={onPastePage}
                disabled={!styleClipboard || !onPastePage}
                title={t("ws.applyStylePage")}
                aria-label={t("ws.applyStylePage")}
                className="btn btn-ghost flex h-7 items-center gap-1 rounded-lg px-2 text-[10px] font-semibold disabled:opacity-40"
              >
                <LayoutGrid size={12} />
                {t("ws.applyStylePage")}
              </button>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2.5">
            <label className="text-[11px] font-medium text-muted">
              {t("ws.font")}
              <FontPicker
                fonts={fonts}
                value={selected.font_override}
                onChange={(path) => onPatch(selected.id, { font_override: path })}
              />
              {fontsError && (
                <span className="mt-1 flex items-center gap-2 text-[10px] text-danger">
                  {t("ws.fontsFailed")}
                  <button
                    type="button"
                    onClick={() => setFontsRetry((v) => v + 1)}
                    className="font-bold underline"
                  >
                    {t("ws.retry")}
                  </button>
                </span>
              )}
            </label>
            <label className="text-[11px] font-medium text-muted">
              {t("ws.fontSize")}
              <input
                type="number"
                min={6}
                max={120}
                className="input-base mt-1 !py-1.5"
                placeholder="auto"
                value={selected.font_size_override ?? ""}
                onChange={(e) =>
                  onPatch(selected.id, {
                    font_size_override: e.target.value ? Number(e.target.value) : null,
                  })
                }
              />
            </label>
            <label className="text-[11px] font-medium text-muted">
              {t("ws.alignment")}
              <select
                className="input-base mt-1 !py-1.5"
                value={selected.alignment}
                onChange={(e) => onPatch(selected.id, { alignment: e.target.value })}
              >
                <option value="">{t("set.inherit")}</option>
                <option value="center">center</option>
                <option value="right">right (RTL)</option>
                <option value="left">left</option>
              </select>
            </label>
            <label className="text-[11px] font-medium text-muted">
              {t("ws.color")}
              <span className="mt-1 flex items-center gap-1.5">
                <input
                  type="color"
                  className="h-[34px] w-full cursor-pointer rounded-lg border border-line bg-elev p-1 outline-none focus:border-primary"
                  value={selected.color || "#000000"}
                  onChange={(e) => onPatch(selected.id, { color: e.target.value })}
                />
                <span
                  className="shrink-0 rounded-md border border-line px-1.5 py-1 font-mono text-[10px] uppercase text-muted"
                  title={selected.color || "inherit"}
                  style={{ background: selected.color || "transparent" }}
                />
              </span>
            </label>
            <label className="col-span-2 text-[11px] font-medium text-muted">
              {t("ws.rotation")}
              <span className="mt-1 flex items-center gap-3" dir="ltr">
                <input
                  type="range"
                  min={-180}
                  max={180}
                  step={1}
                  aria-label={t("ws.rotation")}
                  className="min-w-0 flex-1 accent-primary"
                  value={selected.rotation ?? 0}
                  onChange={(e) => onPatch(selected.id, { rotation: Number(e.target.value) })}
                />
                <input
                  type="number"
                  min={-180}
                  max={180}
                  step={1}
                  aria-label={t("ws.rotationDegrees")}
                  className="input-base !w-20 !py-1.5"
                  value={selected.rotation ?? 0}
                  onChange={(e) => {
                    const value = e.target.valueAsNumber;
                    if (Number.isFinite(value)) onPatch(selected.id, { rotation: Math.max(-180, Math.min(180, value)) });
                  }}
                />
              </span>
            </label>
          </div>
        </div>
      )}

      <div ref={listRef} className="min-h-0 max-h-96 lg:max-h-none flex-1 space-y-2 overflow-y-auto pe-1">
        {blocks.length === 0 && (
          <p className="p-6 text-center text-xs text-faint">{t("ws.noBlocks")}</p>
        )}
        {blocks.length > 0 && visibleBlocks.length === 0 && (
          <p className="p-6 text-center text-xs text-faint">{t("ws.noMatch")}</p>
        )}
        {visibleBlocks.map((blk) => {
          const isSel = blk.id === selectedId;
          const isMulti = !isSel && multiIds.includes(blk.id);
          return (
            <div
              key={blk.id}
              data-block={blk.id}
              onClick={(e) => onSelect(blk.id, e.shiftKey)}
              className={`cursor-pointer rounded-xl border bg-surface p-2.5 transition-all ${
                isSel
                  ? "border-success bg-success/8 shadow-[0_0_0_1px_var(--success)]"
                  : isMulti
                    ? "border-primary bg-primary/8 shadow-[0_0_0_1px_var(--primary)]"
                    : `border-transparent hover:border-line ${TYPE_ACCENT[blk.block_type] ?? ""}`
              }`}
            >
              <div className="mb-1.5 flex items-center gap-2">
                <span className="font-mono text-[10px] text-faint">{blk.key}</span>
                <BlockTypeBadge type={blk.block_type} />
                {!blk.is_translated && (
                  <span className="ms-auto rounded bg-surface3 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-muted">
                    {t("ws.untranslated")}
                  </span>
                )}
              </div>

              <p
                dir="ltr"
                className="mb-1.5 line-clamp-2 rounded-md bg-base px-2 py-1 text-[11px] leading-snug text-muted"
                title={blk.original_text}
              >
                {blk.original_text || "(empty)"}
              </p>

              <textarea
                dir="rtl"
                className="fa-text w-full resize-none rounded-lg border border-transparent bg-elev px-2.5 py-2 text-sm
                leading-relaxed outline-none transition-colors focus:border-primary h-20"
                placeholder={t("ws.translationPlaceholder")}
                value={blk.translation}
                onChange={(e) => onPatch(blk.id, { translation: e.target.value })}
                onBlur={(e) => onCommitTranslation?.(blk.id, e.target.value)}
                onClick={(e) => e.stopPropagation()}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
});
