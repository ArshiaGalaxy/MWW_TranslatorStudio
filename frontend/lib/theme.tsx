"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type Theme = "dark" | "light";

interface ThemeCtx {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

const Ctx = createContext<ThemeCtx>({ theme: "light", setTheme: () => {} });

function initialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const saved = window.localStorage.getItem("vira.theme");
  return saved === "dark" ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("light");

  useEffect(() => {
    setThemeState(initialTheme());
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.classList.toggle("light", theme === "light");
  }, [theme]);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    window.localStorage.setItem("vira.theme", t);
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);

/* ── Toasts ───────────────────────────────────────────────────────────── */

type ToastKind = "success" | "error" | "info";
interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

const ToastCtx = createContext<{
  push: (message: string, kind?: ToastKind) => void;
}>({ push: () => {} });

let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);

  const push = useCallback((message: string, kind: ToastKind = "info") => {
    const id = nextId++;
    setItems((ts) => [...ts, { id, kind, message }]);
    setTimeout(() => {
      setItems((ts) => ts.filter((x) => x.id !== id));
    }, 4200);
  }, []);

  // Stable identity: pages keep `toast` in effect/callback deps — an
  // unstable value here would re-run them on every toast lifecycle event.
  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed bottom-5 left-1/2 z-[100] flex w-full max-w-sm -translate-x-1/2 flex-col items-center gap-2 px-4"
      >
        {items.map((t) => (
          <div
            key={t.id}
            className="anim-pop pointer-events-auto flex w-full items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 shadow-[0_12px_40px_-10px_rgba(0,0,0,0.5)]"
            style={{ animation: "toast-in .25s cubic-bezier(.22,1,.36,1) both" }}
          >
            <span
              className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                t.kind === "success"
                  ? "bg-success"
                  : t.kind === "error"
                    ? "bg-danger"
                    : "bg-primary"
              }`}
            />
            <p className="text-sm font-medium">{t.message}</p>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
