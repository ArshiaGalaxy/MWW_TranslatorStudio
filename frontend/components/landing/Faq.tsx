"use client";

import { ChevronDown } from "lucide-react";
import { DictKey, useI18n } from "@/lib/i18n";

/** FAQ accordion — native <details>, zero JS, thin dividers. */
export function Faq({ items }: { items: { q: DictKey; a: DictKey }[] }) {
  const { t } = useI18n();
  return (
    <div className="compare-frame mx-auto max-w-2xl px-6 py-2">
      {items.map(({ q, a }) => (
        <details key={q} className="faq-item">
          <summary>
            <span dir="auto">{t(q)}</span>
            <ChevronDown size={17} className="faq-chevron" />
          </summary>
          <p className="faq-body" dir="auto">
            {t(a)}
          </p>
        </details>
      ))}
    </div>
  );
}
