"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";

export default function NotFound() {
  const { t } = useI18n();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <div className="glow-blob -top-32 start-[35%] h-96 w-96" style={{ background: "var(--glow-b)" }} />
      <span className="section-tag">404</span>
      <h1 className="font-display text-2xl font-extrabold">{t("nf.title")}</h1>
      <p className="max-w-md text-sm leading-relaxed text-muted">{t("nf.desc")}</p>
      <Link href="/" className="btn btn-primary px-4 py-2 text-sm">
        {t("nf.back")}
      </Link>
    </main>
  );
}
