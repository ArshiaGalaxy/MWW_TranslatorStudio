"use client";

import { useCallback, useRef, useState } from "react";
import { MoveHorizontal } from "lucide-react";
import { useI18n } from "@/lib/i18n";

/**
 * Before/after drag slider over a real manga page pair. The Persian output
 * is the base layer; the original page sits on top clipped to the left of
 * the handle. The frame is dir="ltr" in both locales so the page
 * orientation never flips when the app goes RTL.
 */
export function BeforeAfter({
  before,
  after,
  beforeLabel,
  afterLabel,
  width = "min(100%, 470px)",
  maxHeight = "74vh",
}: {
  before: string;
  after: string;
  beforeLabel: string;
  afterLabel: string;
  width?: string;
  maxHeight?: string;
}) {
  const { t, locale } = useI18n();
  const [pos, setPos] = useState(50);
  const [dragging, setDragging] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const update = useCallback((clientX: number) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const pct = ((clientX - rect.left) / rect.width) * 100;
    setPos(Math.max(4, Math.min(96, pct)));
  }, []);

  return (
    <div className="flex justify-center">
      {/* Explicit width is required: the images are absolutely positioned, so
          fit-content would collapse the frame to zero width (empty panel). */}
      <div
        ref={ref}
        dir="ltr"
        className={`compare-frame relative select-none overflow-hidden ${
          dragging ? "cursor-grabbing" : "cursor-grab"
        }`}
        style={{ aspectRatio: "1500 / 2190", width, maxHeight }}
        onPointerDown={(e) => {
          setDragging(true);
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          update(e.clientX);
        }}
        onPointerMove={(e) => dragging && update(e.clientX)}
        onPointerUp={() => setDragging(false)}
        onPointerLeave={() => setDragging(false)}
      >
        {/* after (Persian) — base layer */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={after}
          alt={afterLabel}
          loading="lazy"
          decoding="async"
          className="absolute inset-0 h-full w-full object-contain object-top"
          draggable={false}
        />
        {/* before (original) — clipped to left of handle */}
        <div
          className="absolute inset-0"
          style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={before}
            alt={beforeLabel}
            loading="lazy"
            decoding="async"
            className="absolute inset-0 h-full w-full object-contain object-top"
            draggable={false}
          />
        </div>

        {/* handle — solid cobalt, no glow */}
        <div
          className="pointer-events-none absolute inset-y-0 z-10 w-[2px] bg-ink"
          style={{ left: `${pos}%`, opacity: 0.55 }}
        >
          <div
            className={`absolute top-1/2 left-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full text-white shadow-md transition-transform ${
              dragging ? "scale-110" : ""
            }`}
            style={{ background: "var(--primary)" }}
          >
            <MoveHorizontal size={17} />
          </div>
        </div>

        {/* labels */}
        <span className="absolute top-3 left-3 rounded-lg bg-ink/75 px-2.5 py-1 text-[11px] font-bold text-white">
          {beforeLabel}
        </span>
        <span className="fa-text absolute top-3 right-3 rounded-lg px-2.5 py-1 text-[11px] font-bold text-white" style={{ background: "var(--primary)" }}>
          {afterLabel}
        </span>
        {!dragging && pos === 50 && (
          <span
            className={`absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-ink/75 px-4 py-1.5 text-[11px] font-semibold text-white transition-opacity duration-500 ${
              locale === "fa" ? "fa-text" : ""
            }`}
          >
            {t("landing.dragCompare")}
          </span>
        )}
      </div>
    </div>
  );
}
