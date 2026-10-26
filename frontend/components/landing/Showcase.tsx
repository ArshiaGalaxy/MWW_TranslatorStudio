"use client";

import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { BeforeAfter } from "@/components/landing/BeforeAfter";

interface Pair {
  id: string;
  label: string;
  before: string;
  after: string;
}

const PAIRS: Pair[] = [
  {
    id: "dandadan",
    label: "Dandadan · Ch. 241",
    before: "/showcase/dandadan-before.jpg",
    after: "/showcase/dandadan-after.jpg",
  },
  {
    id: "spy",
    label: "Spy × Family · Ch. 131",
    before: "/showcase/spy-before.jpg",
    after: "/showcase/spy-after.jpg",
  },
];

/**
 * Real-output viewer: chapter selector pills + the active chapter's
 * before/after pair. Same two real page pairs the pipeline produced —
 * this section is a product proof, not a gallery.
 */
export function Showcase() {
  const { t } = useI18n();
  const [active, setActive] = useState<Pair>(PAIRS[0]);

  return (
    <div className="mx-auto max-w-3xl">
      {/* chapter pills — selected is the only cobalt element */}
      <div className="mb-5 flex flex-wrap justify-center gap-2">
        {PAIRS.map((p) => (
          <button
            key={p.id}
            onClick={() => setActive(p)}
            className={`rounded-xl border px-4 py-2 text-xs font-bold transition-colors ${
              active.id === p.id
                ? "border-primary bg-primary text-primary-fg"
                : "border-line bg-surface text-muted hover:border-line-strong hover:text-ink"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      <BeforeAfter
        key={active.id}
        before={active.before}
        after={active.after}
        beforeLabel={`${t("landing.labelOriginal")}`}
        afterLabel={`${t("landing.labelPersian")}`}
      />
    </div>
  );
}
