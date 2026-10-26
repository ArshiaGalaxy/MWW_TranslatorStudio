"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useI18n } from "@/lib/i18n";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useI18n();

  useEffect(() => {
    // Surface the failure in the console — the only place left to look once
    // the boundary replaces the crashed subtree.
    console.error(error);
  }, [error]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <div className="glow-blob -top-32 start-[35%] h-96 w-96" style={{ background: "var(--glow-a)" }} />
      <span className="section-tag">ERR</span>
      <h1 className="font-display text-2xl font-extrabold">{t("err.title")}</h1>
      <p className="max-w-md text-sm leading-relaxed text-muted">{t("err.desc")}</p>
      <div className="flex gap-2.5">
        <button onClick={reset} className="btn btn-primary px-4 py-2 text-sm">
          {t("err.retry")}
        </button>
        <Link href="/" className="btn btn-ghost px-4 py-2 text-sm">
          {t("nf.back")}
        </Link>
      </div>
    </main>
  );
}
