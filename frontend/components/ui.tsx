"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Moon, Sun, X } from "lucide-react";
import { DictKey, useI18n } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

/* ── Logo ─────────────────────────────────────────────────────────────── */

export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
      <rect x="3" y="3" width="42" height="42" rx="12" fill="#3155D9" />
      <path
        d="M14 17.5c0-2 1.5-3.5 3.5-3.5h13c2 0 3.5 1.5 3.5 3.5v9c0 2-1.5 3.5-3.5 3.5H23l-6 5v-5h-.5C15.5 30 14 28.5 14 26.5v-9z"
        fill="#fff"
        fillOpacity=".96"
      />
      <rect x="18" y="19" width="12" height="2.2" rx="1.1" fill="#3155D9" opacity=".85" />
      <rect x="18" y="24" width="7" height="2.2" rx="1.1" fill="#3155D9" opacity=".55" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="font-display text-lg font-bold tracking-tight">
      Vira <span className="text-primary">Studio</span>
    </span>
  );
}

/* ── Buttons ──────────────────────────────────────────────────────────── */

type BtnVariant = "primary" | "ghost" | "outline" | "danger";

export function Btn({
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant;
  size?: "sm" | "md" | "lg";
}) {
  const sizes = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-4 py-2 text-sm",
    lg: "px-6 py-3 text-base",
  };
  return (
    <button className={`btn btn-${variant} ${sizes[size]} ${className}`} {...rest}>
      {children}
    </button>
  );
}

export function IconBtn({
  label,
  className = "",
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      title={label}
      aria-label={label}
      className={`btn btn-ghost h-9 w-9 !rounded-xl p-0 ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

/* ── SplitButton ──────────────────────────────────────────────────────── */

/**
 * Action button fused with a dropdown picker (custom menu, not a native
 * <select>) — the main zone fires the action, the chevron zone opens the
 * menu. Menu styling follows the card tokens so dark/light and RTL come
 * free; the selected option carries a check mark.
 */
export function SplitButton({
  icon,
  label,
  onClick,
  options,
  value,
  onValueChange,
  variant = "ghost",
  disabled = false,
  menuLabel,
  title,
}: {
  icon?: ReactNode;
  label: string;
  onClick: () => void;
  options: readonly { value: string; label: string }[];
  value: string;
  onValueChange: (v: string) => void;
  variant?: "primary" | "ghost";
  disabled?: boolean;
  /** Accessible name for the chevron/menu zone (e.g. "OCR engine"). */
  menuLabel?: string;
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Dismiss on outside click / Escape while the menu is open.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative inline-flex">
      {/* Pill (clipped); the menu renders outside it so it can overflow */}
      <div className="inline-flex h-9 items-stretch overflow-hidden rounded-btn border border-line">
        <button
          onClick={onClick}
          disabled={disabled}
          title={title ?? label}
          className={`btn h-auto rounded-none! border-0! border-e! px-3.5 text-sm ${
            variant === "primary" ? "btn-primary hover:translate-y-0!" : "btn-ghost"
          }`}
        >
          {icon}
          {label}
        </button>
        <button
          onClick={() => setOpen((o) => !o)}
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={menuLabel}
          title={menuLabel}
          className={`flex w-7 cursor-pointer items-center justify-center bg-surface2 transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-45 ${
            open ? "text-primary-strong" : "text-muted"
          }`}
        >
          <ChevronDown
            size={14}
            className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          />
        </button>
      </div>

      {open && (
        <div
          role="listbox"
          className="card anim-pop absolute end-0 top-full z-30 mt-1.5 min-w-32 rounded-xl! p-1"
        >
          {options.map((o) => (
            <button
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              onClick={() => {
                onValueChange(o.value);
                setOpen(false);
              }}
              className={`flex w-full cursor-pointer items-center justify-between gap-3 rounded-lg px-2.5 py-1.5 text-start text-xs font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-primary ${
                o.value === value
                  ? "bg-primary/12 text-primary-strong"
                  : "text-muted hover:bg-surface2 hover:text-ink"
              }`}
            >
              {o.label}
              {o.value === value && <Check size={13} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Theme & language controls ────────────────────────────────────────── */

export function LangThemeControls() {
  const { locale, setLocale } = useI18n();
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex items-center gap-2">
      <div className="flex overflow-hidden rounded-xl border border-line bg-surface2 text-xs font-bold">
        {(["en", "fa"] as const).map((l) => (
          <button
            key={l}
            onClick={() => setLocale(l)}
            className={`w-10 h-8.5 transition-colors ${
              locale === l ? "bg-primary text-primary-fg" : "text-muted hover:text-ink"
            }`}
          >
            {l === "en" ? "EN" : "فا"}
          </button>
        ))}
      </div>
      <IconBtn
        label={theme === "dark" ? "Light mode" : "Dark mode"}
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      >
        {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
      </IconBtn>
    </div>
  );
}

/* ── Badges / progress ────────────────────────────────────────────────── */

const STATUS_KEY: Record<string, DictKey> = {
  created: "status.created",
  extracting: "status.extracting",
  ready: "status.ready",
  translating: "status.translating",
  applying: "status.applying",
  done: "status.done",
  failed: "status.failed",
};

const STATUS_STYLE: Record<string, string> = {
  created: "bg-surface3 text-muted border border-line",
  extracting: "text-warning bg-warning/10 border border-warning/25",
  ready: "text-success bg-success/10 border border-success/25",
  translating: "text-accent bg-accent/10 border border-accent/25",
  applying: "text-primary bg-primary/10 border border-primary/25",
  done: "text-success bg-success/15 border border-success/35",
  failed: "text-danger bg-danger/10 border border-danger/25",
};

export function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold ${
        STATUS_STYLE[status] ?? STATUS_STYLE.created
      }`}
    >
      {(status === "extracting" || status === "translating" || status === "applying") && (
        <span
          className="h-2 w-2 rounded-full bg-current"
          style={{ animation: "spin-slow 1.2s linear infinite", borderRadius: "50% 50% 50% 0" }}
        />
      )}
      {t(STATUS_KEY[status] ?? "status.created")}
    </span>
  );
}

export function ProgressBar({
  value,
  className = "",
}: {
  value: number;
  className?: string;
}) {
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-surface3 ${className}`}>
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{
          width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%`,
          background: "var(--primary)",
        }}
      />
    </div>
  );
}

const BLOCK_TYPE_BADGE: Record<string, string> = {
  dialog: "bg-primary/15 text-primary-strong",
  sfx: "bg-danger/15 text-danger",
  thinking: "bg-warning/15 text-warning",
  action: "bg-warning/10 text-warning",
  whisper: "bg-surface3 text-muted",
  narration: "bg-accent/15 text-accent",
  system: "bg-accent/10 text-accent",
  custom: "bg-surface3 text-muted",
};

export function BlockTypeBadge({ type }: { type: string }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
        BLOCK_TYPE_BADGE[type] ?? "bg-surface3 text-muted"
      }`}
    >
      {type}
    </span>
  );
}

/* ── Modal ────────────────────────────────────────────────────────────── */

export function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const { t } = useI18n();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className={`card anim-pop w-full ${wide ? "max-w-lg" : "max-w-md"} p-6`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-extrabold">{title}</h3>
          <IconBtn label={t("common.close")} onClick={onClose}>
            <X size={16} />
          </IconBtn>
        </div>
        {children}
      </div>
    </div>
  );
}

/* ── Skeletons / empty ────────────────────────────────────────────────── */

/* ── Reveal on scroll ─────────────────────────────────────────────────── */

export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            (e.target as HTMLElement).classList.add("in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`reveal ${className}`}
      style={{ transitionDelay: `${delay}s` }}
    >
      {children}
    </div>
  );
}
