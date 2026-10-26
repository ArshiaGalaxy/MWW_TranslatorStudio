"use client";

import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Eraser,
  FileDown,
  Languages,
  MousePointer2,
  PenLine,
  PenTool,
  ScanText,
  Type,
  Users,
} from "lucide-react";
import { DictKey, useI18n } from "@/lib/i18n";
import { LangThemeControls, Logo, Reveal, Wordmark } from "@/components/ui";
import { Showcase } from "@/components/landing/Showcase";
import { BeforeAfter } from "@/components/landing/BeforeAfter";
import { Faq } from "@/components/landing/Faq";

/* eslint-disable @next/next/no-img-element */

const SPY = {
  before: "/showcase/spy-before.jpg",
  after: "/showcase/spy-after.jpg",
};

export default function LandingPage() {
  const { t } = useI18n();
  const ctaHref = "/projects";

  const features: { icon: React.ReactNode; t: DictKey; d: DictKey }[] = [
    { icon: <ScanText size={18} />, t: "landing.f1.t", d: "landing.f1.d" },
    { icon: <Languages size={18} />, t: "landing.f2.t", d: "landing.f2.d" },
    { icon: <MousePointer2 size={18} />, t: "landing.f3.t", d: "landing.f3.d" },
    { icon: <Eraser size={18} />, t: "landing.f4.t", d: "landing.f4.d" },
    { icon: <Type size={18} />, t: "landing.f5.t", d: "landing.f5.d" },
    { icon: <FileDown size={18} />, t: "landing.f6.t", d: "landing.f6.d" },
  ];

  const workflow: { icon: React.ReactNode; t: DictKey }[] = [
    { icon: <ScanText size={18} />, t: "landing.wf.detect" },
    { icon: <Languages size={18} />, t: "landing.wf.translate" },
    { icon: <Eraser size={18} />, t: "landing.wf.clean" },
    { icon: <PenTool size={18} />, t: "landing.wf.typeset" },
    { icon: <FileDown size={18} />, t: "landing.wf.export" },
  ];

  const automation: { n: string; t: DictKey; d: DictKey }[] = [
    { n: "01", t: "landing.auto.s1.t", d: "landing.auto.s1.d" },
    { n: "02", t: "landing.auto.s2.t", d: "landing.auto.s2.d" },
    { n: "03", t: "landing.auto.s3.t", d: "landing.auto.s3.d" },
    { n: "04", t: "landing.auto.s4.t", d: "landing.auto.s4.d" },
  ];

  const howSteps: { n: string; t: DictKey; d: DictKey }[] = [
    { n: "01", t: "landing.step1.t", d: "landing.step1.d" },
    { n: "02", t: "landing.step2.t", d: "landing.step2.d" },
    { n: "03", t: "landing.step3.t", d: "landing.step3.d" },
    { n: "04", t: "landing.step4.t", d: "landing.step4.d" },
  ];

  const audiences: { icon: React.ReactNode; t: DictKey; d: DictKey }[] = [
    { icon: <PenLine size={18} />, t: "landing.who1.t", d: "landing.who1.d" },
    { icon: <Users size={18} />, t: "landing.who2.t", d: "landing.who2.d" },
    { icon: <BookOpen size={18} />, t: "landing.who3.t", d: "landing.who3.d" },
  ];

  const faqItems: { q: DictKey; a: DictKey }[] = [
    { q: "landing.faq1q", a: "landing.faq1a" },
    { q: "landing.faq2q", a: "landing.faq2a" },
    { q: "landing.faq3q", a: "landing.faq3a" },
    { q: "landing.faq4q", a: "landing.faq4a" },
    { q: "landing.faq5q", a: "landing.faq5a" },
  ];

  return (
    <main className="min-h-screen">
      {/* ── Navbar ─────────────────────────────────────────────────────── */}
      <nav className="fixed inset-x-0 top-0 z-50 border-b border-line bg-base/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
          <Link href="/" className="flex items-center gap-2.5">
            <Logo />
            <Wordmark />
          </Link>
          <div className="hidden items-center gap-7 text-sm font-medium text-muted md:flex">
            <a href="#features" className="transition-colors hover:text-ink">
              {t("nav.features")}
            </a>
            <a href="#output" className="transition-colors hover:text-ink">
              {t("nav.output")}
            </a>
            <a href="#how" className="transition-colors hover:text-ink">
              {t("nav.how")}
            </a>
          </div>
          <div className="flex items-center gap-2.5">
            <LangThemeControls />
            <Link
              href={ctaHref}
              className="btn btn-primary hidden! px-4 py-2 text-sm sm:flex!"
            >
              {t("landing.openStudio")}
              <ArrowRight size={15} className="rtl:rotate-180" />
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ───────────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-5 pb-16 pt-28 md:pt-36">
        <div className="grid items-center gap-12 lg:grid-cols-[1fr_1.05fr]">
          <div className="anim-fade-up">
            <h1 className="font-display text-4xl font-extrabold leading-[1.12] tracking-tight sm:text-5xl" dir="auto">
              <span className="block">{t("landing.heroTitle1")}</span>
              <span className="block">
                <span className="text-primary">{t("landing.heroAccent")}</span>{" "}
                {t("landing.heroTitle3")}
              </span>
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted" dir="auto">
              {t("landing.heroSub")}
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3.5">
              <Link href={ctaHref} className="btn btn-primary !px-7 !py-3.5 !text-base">
                {t("landing.openStudio")}
                <ArrowRight size={17} className="rtl:rotate-180" />
              </Link>
            </div>
            <div className="mt-10 flex max-w-xl flex-wrap gap-2.5">
              {(
                [
                  "landing.chip.persian",
                  "landing.chip.ai",
                  "landing.chip.scanlation",
                ] as DictKey[]
              ).map((k) => (
                <span key={k} className="chip !px-3.5 !py-1.5 !text-xs font-semibold">
                  {t(k)}
                </span>
              ))}
            </div>
          </div>

          {/* Real product demo: original page → Persian page. The manga stays
              the loudest element; the card is just a paper frame around it. */}
          <Reveal delay={0.1}>
            <div className="compare-frame p-4 sm:p-5" dir="ltr">
              <div className="flex items-stretch justify-center gap-3 sm:gap-4">
                <figure className="flex min-w-0 flex-1 flex-col items-center gap-2.5">
                  <div className="compare-page w-full overflow-hidden">
                    <img
                      src="/showcase/dandadan-before.jpg"
                      alt={t("landing.labelOriginal")}
                      className="block aspect-[1500/2190] w-full object-cover object-top"
                      fetchPriority="high"
                      draggable={false}
                    />
                  </div>
                  <figcaption className="text-[11px] font-bold uppercase tracking-wider text-muted">
                    {t("landing.labelOriginal")}
                  </figcaption>
                </figure>

                <div className="flex items-center">
                  <span
                    className="flex h-10 w-10 items-center justify-center rounded-full text-white"
                    style={{ background: "var(--primary)" }}
                    aria-hidden
                  >
                    <ArrowRight size={18} className="rtl:rotate-180" />
                  </span>
                </div>

                <figure className="flex min-w-0 flex-1 flex-col items-center gap-2.5">
                  <div className="compare-page w-full overflow-hidden">
                    <img
                      src="/showcase/dandadan-after.jpg"
                      alt={t("landing.labelPersian")}
                      className="block aspect-[1500/2190] w-full object-cover object-top"
                      fetchPriority="high"
                      draggable={false}
                    />
                  </div>
                  <figcaption className="fa-text text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--primary)" }}>
                    {t("landing.labelPersian")}
                  </figcaption>
                </figure>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── Workflow strip ─────────────────────────────────────────────── */}
      <section className="border-y border-line bg-elev/60">
        <div className="mx-auto max-w-6xl px-5 py-12">
          <Reveal className="flex flex-col items-center text-center">
            <h2 className="font-display text-xl font-extrabold sm:text-2xl" dir="auto">
              {t("landing.wfTitle")}
            </h2>
            <p className="mt-2 text-sm text-muted" dir="auto">
              {t("landing.wfSub")}
            </p>
          </Reveal>
          <Reveal delay={0.1}>
            <div className="group mt-9 flex items-start justify-center gap-2 overflow-x-auto pb-1 sm:gap-0">
              {workflow.map((s, i) => (
                <div key={s.t} className="flex shrink-0 items-center sm:min-w-0">
                  <div className="flex w-[4.5rem] flex-col items-center gap-2 text-center sm:w-24">
                    <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-elev text-primary">
                      {s.icon}
                    </span>
                    <span className="text-xs font-bold text-muted" dir="auto">
                      {t(s.t)}
                    </span>
                  </div>
                  {i < workflow.length - 1 && (
                    <span className="mx-1 flex items-center sm:mx-2">
                      <span className="step-line hidden h-[3px] w-8 sm:block lg:w-12" />
                      <ArrowRight
                        size={13}
                        className="text-muted/70 transition-transform duration-200 group-hover:translate-x-0.5 rtl:rotate-180"
                      />
                    </span>
                  )}
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── Features (CH. 01) ──────────────────────────────────────────── */}
      <section id="features" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-24">
        <Reveal className="flex flex-col items-center text-center">
          <span className="section-tag mb-5">CH. 01</span>
          <h2 className="font-display max-w-2xl text-3xl font-extrabold sm:text-4xl" dir="auto">
            {t("landing.featuresTitle")}
          </h2>
          <p className="mt-3 max-w-md text-muted" dir="auto">
            {t("landing.featuresSub")}
          </p>
        </Reveal>

        <div className="mt-14 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f, i) => (
            <Reveal key={f.t} delay={(i % 3) * 0.1} className="h-full">
              <div className="h-full rounded-card border border-line bg-elev p-6 transition-all duration-200 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-card">
                <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  {f.icon}
                </div>
                <h3 className="mb-2 font-bold" dir="auto">{t(f.t)}</h3>
                <p className="text-sm leading-relaxed text-muted" dir="auto">{t(f.d)}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── See the difference ─────────────────────────────────────────── */}
      <section id="compare" className="border-y border-line bg-elev/60">
        <div className="mx-auto max-w-6xl scroll-mt-20 px-5 py-24">
          <Reveal className="flex flex-col items-center text-center">
            <span className="section-tag mb-5">{t("landing.diffTag")}</span>
            <h2 className="font-display text-3xl font-extrabold sm:text-4xl" dir="auto">
              {t("landing.diffTitle")}
            </h2>
            <p className="mt-3 max-w-md text-muted" dir="auto">
              {t("landing.diffSub")}
            </p>
          </Reveal>
          <Reveal delay={0.15} className="mt-12">
            <BeforeAfter
              before={SPY.before}
              after={SPY.after}
              beforeLabel={t("landing.labelOriginal")}
              afterLabel={t("landing.labelPersian")}
              width="min(100%, 540px)"
              maxHeight="78vh"
            />
          </Reveal>
        </div>
      </section>

      {/* ── Real output (CH. 02) ───────────────────────────────────────── */}
      <section id="output" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-24">
        <Reveal className="flex flex-col items-center text-center">
          <span className="section-tag mb-5">CH. 02</span>
          <h2 className="font-display text-3xl font-extrabold sm:text-4xl" dir="auto">
            {t("landing.outputTitle")}
          </h2>
          <p className="mt-3 max-w-md text-muted" dir="auto">
            {t("landing.outputSub")}
          </p>
        </Reveal>
        <Reveal delay={0.15} className="mt-12">
          <Showcase />
        </Reveal>
      </section>

      {/* ── Automation value ───────────────────────────────────────────── */}
      <section className="border-y border-line bg-elev/60">
        <div className="mx-auto max-w-6xl px-5 py-24">
          <Reveal className="flex flex-col items-center text-center">
            <h2 className="font-display max-w-2xl text-3xl font-extrabold sm:text-4xl" dir="auto">
              {t("landing.autoTitle")}
            </h2>
            <p className="mt-3 max-w-xl text-muted" dir="auto">
              {t("landing.autoSub")}
            </p>
          </Reveal>

          <div className="mt-14 grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {automation.map((s, i) => (
              <Reveal key={s.n} delay={i * 0.1}>
                <div className="border-s-2 border-line ps-5">
                  <span className="font-display text-3xl font-extrabold text-primary">
                    {s.n}
                  </span>
                  <h3 className="mt-2 font-bold" dir="auto">{t(s.t)}</h3>
                  <p className="mt-1 text-sm text-muted" dir="auto">{t(s.d)}</p>
                </div>
              </Reveal>
            ))}
          </div>

          <Reveal delay={0.1}>
            <p className="mt-16 text-center font-display text-xl font-extrabold sm:text-2xl" dir="auto">
              {t("landing.auto.closingA")}{" "}
              <span className="text-primary">{t("landing.auto.closingB")}</span>
            </p>
          </Reveal>
        </div>
      </section>

      {/* ── How it works (CH. 03) ──────────────────────────────────────── */}
      <section id="how" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-24">
        <Reveal className="flex flex-col items-center text-center">
          <span className="section-tag mb-5">CH. 03</span>
          <h2 className="font-display text-3xl font-extrabold sm:text-4xl" dir="auto">
            {t("landing.howTitle")}
          </h2>
        </Reveal>

        <div className="relative mt-16">
          {/* dotted timeline — horizontal on desktop only */}
          <div className="step-line absolute inset-x-16 top-[1.8rem] hidden h-[3px] lg:block" />
          <div className="flex flex-col gap-10 lg:grid lg:grid-cols-4 lg:gap-6">
            {howSteps.map((s, i) => (
              <Reveal key={s.n} delay={i * 0.12}>
                <div className="flex items-start gap-4 lg:flex-col lg:items-center lg:text-center">
                  <span className="step-tile shrink-0" style={{ "--tilt": "0deg" } as React.CSSProperties}>
                    {s.n}
                  </span>
                  <div>
                    <h3 className="font-bold" dir="auto">{t(s.t)}</h3>
                    <p className="mt-1 max-w-[260px] text-sm text-muted lg:mx-auto" dir="auto">
                      {t(s.d)}
                    </p>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── Who it is for ──────────────────────────────────────────────── */}
      <section className="border-y border-line bg-elev/60">
        <div className="mx-auto max-w-6xl px-5 py-24">
          <Reveal className="flex flex-col items-center text-center">
            <h2 className="font-display text-3xl font-extrabold sm:text-4xl" dir="auto">
              {t("landing.whoTitle")}
            </h2>
          </Reveal>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {audiences.map((a, i) => (
              <Reveal key={a.t} delay={i * 0.1} className="h-full">
                <div className="h-full rounded-card border border-line bg-elev p-6 transition-all duration-200 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-card">
                  <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    {a.icon}
                  </div>
                  <h3 className="mb-2 font-bold" dir="auto">{t(a.t)}</h3>
                  <p className="text-sm leading-relaxed text-muted" dir="auto">{t(a.d)}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── FAQ ────────────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl scroll-mt-20 px-5 py-24">
        <Reveal className="flex flex-col items-center text-center">
          <h2 className="font-display text-3xl font-extrabold sm:text-4xl" dir="auto">
            {t("landing.faqTitle")}
          </h2>
        </Reveal>
        <Reveal delay={0.1} className="mt-10">
          <Faq items={faqItems} />
        </Reveal>
      </section>

      {/* ── Final CTA — deep ink, full bleed ───────────────────────────── */}
      <section
        className="relative overflow-hidden"
        style={{ background: "var(--end-panel-ink)" }}
      >
        <div className="halftone-floor" />
        <div className="relative mx-auto max-w-3xl px-5 py-24 text-center">
          <h2 className="font-display text-3xl font-extrabold text-white sm:text-4xl" dir="auto">
            {t("landing.ctaTitle")}
          </h2>
          <p className="mx-auto mt-4 max-w-md leading-relaxed text-white/70" dir="auto">
            {t("landing.ctaSub")}
          </p>
          <Link
            href={ctaHref}
            className="btn btn-primary mt-9 !px-8 !py-3.5 !text-base"
          >
            {t("landing.openStudio")}
            <ArrowRight size={17} className="rtl:rotate-180" />
          </Link>
          <p className="mt-8 text-xs font-semibold tracking-wide text-white/50" dir="auto">
            {t("landing.ctaLine")}
          </p>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer className="border-t border-line">
        <div className="mx-auto max-w-6xl px-5 py-12">
          <div className="flex flex-col items-start justify-between gap-8 sm:flex-row">
            <div className="max-w-sm">
              <Link href="/" className="flex items-center gap-2.5">
                <Logo />
                <Wordmark />
              </Link>
              <p className="mt-3 text-sm leading-relaxed text-muted" dir="auto">
                {t("landing.footer")}
              </p>
            </div>
            <nav className="flex flex-col gap-2.5 text-sm font-medium text-muted">
              <a href="#features" className="transition-colors hover:text-ink">
                {t("nav.features")}
              </a>
              <a href="#output" className="transition-colors hover:text-ink">
                {t("nav.output")}
              </a>
              <a href="#how" className="transition-colors hover:text-ink">
                {t("nav.how")}
              </a>
            </nav>
            <LangThemeControls />
          </div>
          <p className="mt-10 text-xs text-faint">{t("landing.copyright")}</p>
        </div>
      </footer>
    </main>
  );
}
