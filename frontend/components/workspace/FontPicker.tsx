"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { loadFont } from "@/components/workspace/usePreviewLayout";
import { useI18n } from "@/lib/i18n";
import { FontInfo } from "@/lib/types";

/** Sample rendered in each font so the shape is recognizable at a glance. */
const SAMPLE = "مانگا Manga ۱۲۳";

function stemOf(path: string): string {
  return (path.split(/[\\/]/).pop() ?? "").replace(/\.ttf$|\.otf$/i, "");
}

interface Props {
  fonts: FontInfo[];
  /** Stored font_override value (an absolute path), or "" to inherit. */
  value: string;
  onChange: (path: string) => void;
}

/**
 * Per-block font picker. A native <select> can't render a different font in
 * each option, so this shows a custom dropdown where every row previews its
 * sample in that actual font (loaded via the FontFace API, same source the
 * canvas preview uses).
 */
export function FontPicker({ fonts, value, onChange }: Props) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  // font name -> loaded CSS family (fills in as font files finish loading)
  const [families, setFamilies] = useState<Record<string, string>>({});
  /** Any font file failed to load while the dropdown was open. */
  const [failed, setFailed] = useState(false);
  const [retryTick, setRetryTick] = useState(0);
  const currentStem = value ? stemOf(value) : "";
  const currentFont = useMemo(
    () => fonts.find((f) => f.name === currentStem) ?? null,
    [fonts, currentStem],
  );

  // Load the current font (if any) even while closed, so the button itself
  // previews it.
  useEffect(() => {
    if (!currentFont) return;
    let cancelled = false;
    loadFont(currentFont.url)
      .then((family) => {
        if (!cancelled) setFamilies((m) => ({ ...m, [currentFont.name]: family }));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [currentFont]);

  // Opening the dropdown loads every font so each row previews its own.
  // Failed loads surface once as an inline retry row (not per-row noise).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    fonts.forEach((f) => {
      loadFont(f.url)
        .then((family) => {
          if (!cancelled) setFamilies((m) => (m[f.name] ? m : { ...m, [f.name]: family }));
        })
        .catch(() => {
          if (!cancelled) setFailed(true);
        });
    });
    return () => {
      cancelled = true;
    };
  }, [open, fonts, retryTick]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const pick = (path: string) => {
    onChange(path);
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={currentFont ? currentFont.name : t("set.inherit")}
        className="flex w-full items-center gap-1.5 rounded-lg border border-line bg-elev px-2.5 py-1.5 text-xs outline-none transition-colors hover:border-primary focus:border-primary"
      >
        {currentFont && families[currentFont.name] ? (
          <span
            className="fa-text min-w-0 flex-1 truncate rounded-md bg-[#f8f5ec] px-1.5 py-0.5 text-[13px] leading-snug text-[#141824]"
            dir="rtl"
            style={{ fontFamily: families[currentFont.name] }}
          >
            {currentFont.name}
          </span>
        ) : (
          <span className="min-w-0 flex-1 truncate">{currentFont ? currentFont.name : t("set.inherit")}</span>
        )}
        <ChevronDown size={13} aria-hidden className="pointer-events-none shrink-0 text-faint" />
      </button>

      {open && (
        <>
          {/* Click-away catcher */}
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} aria-hidden />
          <div
            role="listbox"
            aria-label={t("ws.font")}
            className="absolute inset-x-0 z-30 mt-1 max-h-64 overflow-y-auto rounded-xl border border-line bg-elev p-1 shadow-lg"
          >
            <button
              type="button"
              role="option"
              aria-selected={!currentFont}
              onClick={() => pick("")}
              className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-start text-base hover:bg-surface3"
            >
              {t("set.inherit")}
            </button>
            {fonts.map((f) => (
              <button
                type="button"
                key={f.name}
                role="option"
                aria-selected={f.name === currentStem}
                onClick={() => pick(f.path)}
                className="flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-start hover:bg-surface3"
              >
                <span
                  className="fa-text flex min-w-0 flex-1 items-center justify-center overflow-hidden rounded-md bg-[#f8f5ec] px-1.5 py-1 text-[15px] leading-snug text-[#141824]"
                  dir="rtl"
                  style={families[f.name] ? { fontFamily: families[f.name] } : undefined}
                >
                  <span className="truncate">{SAMPLE}</span>
                </span>
                <span className="shrink-0 font-mono text-[10px] text-faint">{f.name}</span>
              </button>
            ))}
            {/* Fonts set outside this list (e.g. by import) keep appearing even
                if they're no longer in the fonts folder. */}
            {currentStem && !fonts.some((f) => f.name === currentStem) && (
              <button
                type="button"
                role="option"
                aria-selected
                onClick={() => pick(value)}
                className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-start hover:bg-surface3"
              >
                <span className="font-mono text-xs text-muted" dir="ltr">
                  {currentStem}
                </span>
              </button>
            )}
            {failed && (
              <div className="flex items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-[11px] text-danger">
                <span>{t("ws.fontsFailed")}</span>
                <button
                  type="button"
                  onClick={() => {
                    setFailed(false);
                    setRetryTick((v) => v + 1);
                  }}
                  className="shrink-0 font-bold underline"
                >
                  {t("ws.retry")}
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
