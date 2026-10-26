"use client";

import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Braces,
  Check,
  ChevronDown,
  Eye,
  EyeOff,
  Info,
  Languages,
  Loader2,
  Palette,
  Save,
  ScanText,
  Sparkles,
  Type,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { FontInfo } from "@/lib/types";
import { useAuth } from "@/lib/auth";
import { DictKey, useI18n } from "@/lib/i18n";
import { useToast } from "@/lib/theme";
import { Btn, IconBtn, LangThemeControls } from "@/components/ui";

const SECTIONS = [
  { key: "translator", icon: <Languages size={15} /> },
  { key: "ocr", icon: <ScanText size={15} /> },
  { key: "font", icon: <Type size={15} /> },
  { key: "chapter_id", icon: <Sparkles size={15} /> },
  { key: "inpaint", icon: <Palette size={15} /> },
  { key: "typography", icon: <Braces size={15} /> },
] as const;

const FONT_PATH_FIELDS = new Set(["path_normal", "path_sfx", "path_thinking"]);
const LONG_TEXT_FIELDS = new Set(["system_prompt", "user_prompt"]);

/** Raw config keys are opaque; these get friendly bilingual labels.
 *  Unlisted fields fall back to a humanized version of the raw key. */
const FIELD_LABELS: Record<string, DictKey> = {
  provider: "set.grp.provider",
  model: "set.model",
  temperature: "set.temperature",
  chunk_size: "set.chunkSize",
  system_prompt: "set.systemPrompt",
  user_prompt: "set.userPrompt",
  "openrouter.api_key": "set.keyOpenrouter",
  "gemini.api_key": "set.keyGemini",
  "custom.api_key": "set.keyCustom",
  "openrouter.model": "set.model",
  "gemini.model": "set.model",
  base_url: "set.baseUrl",
  path_normal: "set.fontNormal",
  path_sfx: "set.fontSfx",
  path_thinking: "set.fontThinking",
  size_min: "set.fontMin",
  size_max: "set.fontMax",
  stroke_width: "set.strokeWidth",
  stroke_color: "set.strokeColor",
  dpi: "set.dpi",
  method: "set.method",
  color: "set.stampColor",
  size: "set.stampSize",
  text_rec_score_thresh: "set.recScore",
  match_original_text_color: "set.matchColor",
  text_color_contrast_min: "set.contrastMin",
  ink_color_distance_threshold: "set.inkDistance",
  ink_quantization_step: "set.inkQuant",
};

const FIELD_HINTS: Partial<Record<string, DictKey>> = {
  temperature: "set.hintTemperature",
  chunk_size: "set.hintChunk",
  system_prompt: "set.hintSystemPrompt",
  user_prompt: "set.hintUserPrompt",
};

/** Ordered subsections per tab, grouped by what the fields configure.
 *  Fields not listed render under "Other"; nested objects (provider key
 *  cards) still render as their own fieldsets after the groups. */
const SECTION_GROUPS: Record<string, { key: string; fields: string[] }[]> = {
  translator: [
    {
      key: "provider",
      fields: ["provider", "temperature", "chunk_size"],
    },
    { key: "prompts", fields: ["system_prompt", "user_prompt"] },
  ],
  ocr: [
    {
      key: "engine",
      fields: [
        "pdf_type",
        "ocr_version",
        "dpi",
        "confidence_min",
        "text_rec_score_thresh",
        "ocr_enable_angle_cls",
      ],
    },
    {
      key: "detection",
      fields: [
        "dbscan_eps",
        "duplicate_iou_threshold",
        "long_strip_aspect_ratio_threshold",
        "size_consistency_threshold",
        "boundary_region_height",
        "boundary_dialogue_min_height",
        "angle_merge_threshold",
        "ocr_det_limit_side_len",
        "ocr_det_unclip_ratio",
        "ocr_det_box_thresh",
        "ocr_det_thresh",
      ],
    },
    {
      key: "pages",
      fields: [
        "ocr_max_side",
        "standard_max_side",
        "max_chunk_height",
        "cross_page_height",
        "enable_cross_page_merge",
      ],
    },
    {
      key: "strips",
      fields: ["manhwa_concat_width", "manhwa_concat_overlap"],
    },
  ],
  font: [
    { key: "fonts", fields: ["path_normal", "path_sfx", "path_thinking"] },
    { key: "size", fields: ["size_max", "size_min", "stroke_width", "tall_render_chunk_size"] },
  ],
  inpaint: [
    {
      key: "general",
      fields: ["method", "padding_x", "padding_y"],
    },
    { key: "opencv", fields: ["opencv_radius", "opencv_method"] },
    { key: "autoMode", fields: ["cv_auto_solid_ratio", "cv_auto_color_bucket", "cv_auto_mask_pad"] },
    { key: "neural", fields: ["lama_device"] },
    {
      key: "pcleaner",
      fields: ["pcleaner_profile", "pcleaner_cli_path"],
    },
  ],
  typography: [
    {
      key: "colorMatch",
      fields: [
        "match_original_text_color",
        "text_color_contrast_min",
        "ink_color_distance_threshold",
        "ink_quantization_step",
      ],
    },
  ],
  // chapter_id has only four fields — a flat grid needs no subsections.
};

/** Dropdowns only where the allowed values are known from the engine.
 *  The current value is always prepended if it isn't among the options,
 *  so an unusual saved value still renders. */
function enumOptions(
  leaf: string,
  value: unknown,
  t: (key: DictKey) => string,
): { value: string; label: string }[] | null {
  const cur = String(value ?? "");
  const withCurrent = (opts: { value: string; label: string }[]) =>
    cur && !opts.some((o) => o.value === cur) ? [{ value: cur, label: cur }, ...opts] : opts;

  switch (leaf) {
    case "provider":
      return withCurrent([
        { value: "openrouter", label: "OpenRouter" },
        { value: "gemini", label: "Gemini" },
        { value: "custom", label: `Custom — ${t("set.customHint")}` },
      ]);
    case "pdf_type":
      return withCurrent([
        { value: "manga", label: t("set.optManga") },
        { value: "manhwa", label: t("set.optManhwa") },
      ]);
    case "method":
      return withCurrent([
        { value: "cv_auto", label: t("set.optAutoInpaint") },
        { value: "opencv", label: "OpenCV" },
        { value: "color", label: t("set.optSolid") },
        { value: "pcleaner", label: "PCleaner" },
      ]);
    case "opencv_method":
      return withCurrent([
        { value: "ns", label: "Navier–Stokes" },
        { value: "telea", label: "Telea" },
      ]);
    default:
      return null;
  }
}

function isColor(v: unknown): boolean {
  return typeof v === "string" && /^#[0-9a-fA-F]{6}$/.test(v);
}

/** "dbscan_eps" → "Dbscan Eps" — fallback for fields without a dict label. */
function humanize(key: string): string {
  return key
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

type FieldGroup = { key: string; items: [string, unknown][] };

export default function SettingsPage() {
  const { t } = useI18n();
  const toast = useToast();
  const router = useRouter();
  const { me, loading: authLoading } = useAuth();
  const [config, setConfig] = useState<Record<string, Record<string, unknown>> | null>(null);
  const [fonts, setFonts] = useState<FontInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState("");
  const [dirty, setDirty] = useState(0);
  const [activeSection, setActiveSection] = useState("translator");


  const load = useCallback(async () => {
    try {
      setConfig(await api.get("/api/config"));
      setDirty(0);
    } catch (err) {
      toast.push(err instanceof Error ? err.message : t("toast.loadFailed"), "error");
    }
  }, [t, toast]);

  useEffect(() => {
    void load();
    void api
      .get<FontInfo[]>("/api/fonts")
      .then(setFonts)
      .catch(() => {});
  }, [load]);

  function setField(section: string, field: string, value: unknown) {
    setDirty((d) => d + 1);
    setConfig((c) => (c ? { ...c, [section]: { ...c[section], [field]: value } } : c));
  }

  async function save() {
    if (!config) return;
    setSaving(true);
    try {
      await api.put("/api/config", config);
      setSavedAt(new Date().toLocaleTimeString());
      setDirty(0);
      toast.push(t("toast.saved"), "success");
    } catch (err) {
      toast.push(err instanceof Error ? err.message : t("toast.saveFailed"), "error");
    } finally {
      setSaving(false);
    }
  }

  const { groups, nestedObjects } = useMemo(() => {
    if (!config) return { groups: [] as FieldGroup[], nestedObjects: [] as [string, unknown][] };
    const entries = Object.entries(config[activeSection] ?? {});
    const byName = new Map(entries);
    const defs = SECTION_GROUPS[activeSection] ?? [];

    let groups: FieldGroup[];
    if (defs.length === 0) {
      // No subsections defined: one flat grid, no headings.
      groups = [
        { key: "", items: entries.filter(([, v]) => typeof v !== "object" || v === null) },
      ];
    } else {
      groups = defs
        .map((g) => ({
          key: g.key,
          items: g.fields
            .filter((f) => byName.has(f))
            .map((f) => [f, byName.get(f)] as [string, unknown]),
        }))
        .filter((g) => g.items.length > 0);
      const listed = new Set(defs.flatMap((g) => g.fields));
      const rest = entries.filter(
        ([f, v]) => !listed.has(f) && (typeof v !== "object" || v === null),
      );
      if (rest.length > 0) groups.push({ key: "other", items: rest });
    }

    const nestedObjects = entries.filter(([, v]) => typeof v === "object" && v !== null);
    return { groups, nestedObjects };
  }, [config, activeSection]);

  if (authLoading || !config) {
    return (
      <main className="flex min-h-screen items-center justify-center text-muted">
        {t("common.loading")}
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-5xl p-6 pb-28">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <IconBtn label={t("nav.back")} onClick={() => router.push("/projects")}>
            <ArrowLeft size={16} className="rtl:rotate-180" />
          </IconBtn>
          <div>
            <h1 className="font-display text-2xl font-extrabold leading-tight">
              {t("set.title")}
            </h1>
            <p className="text-xs text-muted">{t("set.subtitle")}</p>
          </div>
        </div>
        <LangThemeControls />
      </header>

      {/* Section tabs */}
      <div className="card mb-5 flex flex-wrap gap-1 p-1.5" role="tablist">
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            role="tab"
            aria-selected={activeSection === s.key}
            onClick={() => setActiveSection(s.key)}
            className={`flex items-center gap-1.5 rounded-btn px-3.5 py-2 text-sm font-bold transition-colors ${
              activeSection === s.key
                ? "bg-primary text-primary-fg"
                : "text-muted hover:bg-surface2 hover:text-ink"
            }`}
          >
            {s.icon}
            {t(`set.sec.${s.key}`)}
          </button>
        ))}
      </div>

      <div className="card anim-fade-up p-6 sm:p-7">
        <p className="max-w-2xl text-sm leading-relaxed text-muted">
          {t(`set.desc.${activeSection}` as DictKey)}
        </p>
        {activeSection === "translator" && (
          <p className="mt-3 flex max-w-2xl items-start gap-2 rounded-inner border border-line bg-surface2 px-3.5 py-2.5 text-xs leading-relaxed text-muted">
            <Info size={14} className="mt-0.5 shrink-0 text-primary" />
            {t("set.keysHint")}
          </p>
        )}

        <div className="mt-6 space-y-7">
          {groups.map((g) => (
            <section key={g.key || "_flat"}>
              {g.key && (
                <h3 className="mb-3.5 flex items-center gap-3 text-[11px] font-extrabold uppercase tracking-[0.18em] text-faint">
                  {t(`set.grp.${g.key}` as DictKey)}
                  <span aria-hidden className="step-line h-px flex-1" />
                </h3>
              )}
              <div className="grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">
                {g.items.map(([field, value]) => (
                  <FieldRow
                    key={field}
                    field={field}
                    value={value}
                    fonts={fonts}
                    onChange={(v) => setField(activeSection, field, v)}
                  />
                ))}
              </div>
            </section>
          ))}

          {nestedObjects.map(([objKey, obj]) => {
            const entries = Object.entries(obj as Record<string, unknown>).filter(
              ([, v]) => typeof v !== "object",
            );
            const providerKey =
              objKey === "openrouter" || objKey === "gemini" || objKey === "custom"
                ? objKey
                : null;
            if (providerKey) {
              // Provider cards: highlight the active one, add a connection
              // test + a key-guide line per provider.
              return (
                <ProviderCard
                  key={objKey}
                  name={providerKey}
                  entries={entries}
                  isActive={String(config[activeSection].provider ?? "") === objKey}
                  obj={obj as Record<string, unknown>}
                  setField={setField}
                  section={activeSection}
                  translatorSection={config[activeSection]}
                />
              );
            }
            return (
              <fieldset key={objKey} className="rounded-2xl border border-line bg-surface2 p-5">
                <legend className="rounded-lg border-2 border-line-strong bg-surface px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-primary shadow-[2px_2px_0_0_var(--line)]">
                  {objKey}
                </legend>
                <div className="mt-3 grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">
                  {entries.map(([f, v]) => (
                    <FieldRow
                      key={f}
                      field={`${objKey}.${f}`}
                      value={v}
                      fonts={fonts}
                      onChange={(nv) =>
                        setField(activeSection, objKey, {
                          ...(config[activeSection][objKey] as Record<string, unknown>),
                          [f]: nv,
                        })
                      }
                    />
                  ))}
                </div>
              </fieldset>
            );
          })}
        </div>
      </div>

      {/* Sticky save bar */}
      <div
        className={`fixed inset-x-0 bottom-0 z-40 border-t border-line bg-elev/90 backdrop-blur-md transition-transform ${
          dirty > 0 ? "translate-y-0" : "translate-y-full"
        }`}
      >
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-6 py-3">
          <div className="flex min-w-0 items-center gap-2.5 text-xs font-bold text-warning">
            {dirty > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-warning/25 bg-warning/10 px-2.5 py-0.5">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-warning" />
                {dirty} {t("set.unsaved")}
              </span>
            )}
            {savedAt && (
              <span className="truncate text-success">
                {t("set.saved")} · {savedAt}
              </span>
            )}
          </div>
          <Btn onClick={() => void save()} disabled={saving}>
            {saving ? <Check size={14} /> : <Save size={14} />}
            {saving ? t("set.saving") : t("set.save")}
          </Btn>
        </div>
      </div>
    </main>
  );
}

function FieldRow({
  field,
  value,
  fonts,
  onChange,
}: {
  field: string;
  value: unknown;
  fonts: FontInfo[];
  onChange: (v: unknown) => void;
}) {
  const { t } = useI18n();
  const id = useId();
  const [showKey, setShowKey] = useState(false);
  const leaf = field.includes(".") ? field.split(".").pop()! : field;
  const labelKey = FIELD_LABELS[field] ?? FIELD_LABELS[leaf];
  const hintKey = FIELD_HINTS[leaf];
  // Long prompts and API keys need the full row width.
  const wide = LONG_TEXT_FIELDS.has(leaf) || leaf === "api_key";
  const enums = enumOptions(leaf, value, t);

  let control: React.ReactNode;
  if (typeof value === "boolean") {
    control = (
      <label htmlFor={id} className="inline-flex w-fit cursor-pointer items-center">
        <input
          id={id}
          type="checkbox"
          className="sr-only"
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span
          aria-hidden
          className={`relative inline-flex h-5 w-9 items-center rounded-full border transition-colors ${
            value ? "border-primary bg-primary" : "border-line bg-surface3"
          }`}
        >
          <span
            className={`absolute start-[3px] top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full bg-white shadow-sm transition-transform ${
              value ? "translate-x-4 rtl:-translate-x-4" : ""
            }`}
          />
        </span>
      </label>
    );
  } else if (isColor(value)) {
    control = <ColorField id={id} value={String(value)} onChange={onChange} />;
  } else if (FONT_PATH_FIELDS.has(leaf)) {
    control = (
      <div className="relative">
        <select
          id={id}
          className="input-base appearance-none pe-9"
          value={typeof value === "string" ? value.split(/[\\/]/).pop() ?? "" : ""}
          onChange={(e) => {
            const f = fonts.find(
              (x) => x.name === e.target.value.replace(/\.ttf$|\.otf$/i, ""),
            );
            onChange(f ? f.path : "");
          }}
        >
          <option value="">{t("set.autoDetect")}</option>
          {fonts.map((f) => (
            <option key={f.name} value={`${f.name}.ttf`}>
              {f.name}
            </option>
          ))}
        </select>
        <ChevronDown
          size={14}
          aria-hidden
          className="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-faint"
        />
      </div>
    );
  } else if (LONG_TEXT_FIELDS.has(leaf)) {
    control = (
      <textarea
        id={id}
        dir="auto"
        rows={leaf === "system_prompt" ? 10 : 6}
        className="input-base font-mono !text-xs leading-relaxed"
        defaultValue={String(value ?? "")}
        onBlur={(e) => onChange(e.target.value)}
      />
    );
  } else if (leaf === "api_key") {
    // Secrets: masked by default, eye-toggle for verification. Values still
    // round-trip via GET/PUT /api/config as before (self-hosted app).
    control = (
      <div className="flex items-center gap-1.5">
        <input
          id={id}
          type={showKey ? "text" : "password"}
          dir="ltr"
          autoComplete="off"
          spellCheck={false}
          className="input-base flex-1 font-mono !text-xs"
          value={String(value ?? "")}
          placeholder="sk-…"
          onChange={(e) => onChange(e.target.value)}
        />
        <IconBtn
          label={t(showKey ? "set.hideKey" : "set.showKey")}
          onClick={() => setShowKey((s) => !s)}
        >
          {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
        </IconBtn>
      </div>
    );
  } else if (enums) {
    control = (
      <div className="relative">
        <select
          id={id}
          className="input-base appearance-none pe-9"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        >
          {enums.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <ChevronDown
          size={14}
          aria-hidden
          className="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-faint"
        />
      </div>
    );
  } else if (typeof value === "number") {
    control = (
      <input
        id={id}
        type="number"
        step="any"
        dir="ltr"
        className="input-base"
        value={value}
        onChange={(e) =>
          onChange(Number.isFinite(Number(e.target.value)) ? Number(e.target.value) : 0)
        }
      />
    );
  } else {
    control = (
      <input
        id={id}
        dir="auto"
        className="input-base"
        value={String(value ?? "")}
        placeholder={leaf === "base_url" ? "https://host/v1" : t("set.emptyValue")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  return (
    <div className={wide ? "col-span-full" : undefined}>
      <label
        htmlFor={id}
        title={field}
        dir="auto"
        className="mb-1.5 block cursor-pointer text-xs font-bold text-ink"
      >
        {labelKey ? t(labelKey) : humanize(leaf)}
      </label>
      {control}
      {hintKey && (
        <p className="mt-1.5 text-[11px] leading-relaxed text-faint" dir="auto">
          {t(hintKey)}
        </p>
      )}
    </div>
  );
}

/** Provider card (OpenRouter / Gemini / Custom): highlights the provider
 *  currently selected in the dropdown, offers a one-shot connection test
 *  against the on-screen (possibly unsaved) values, and a per-provider
 *  guide for obtaining the API key. */
type TestState = {
  state: "idle" | "testing" | "ok" | "fail";
  detail?: string;
  ms?: number;
};

const PROVIDER_HELP: Record<string, { help: DictKey; url?: string }> = {
  openrouter: {
    help: "set.helpOpenrouter",
    url: "https://openrouter.ai/settings/keys",
  },
  gemini: {
    help: "set.helpGemini",
    url: "https://aistudio.google.com/apikey",
  },
  custom: { help: "set.helpCustom" },
};

function ProviderCard({
  name,
  entries,
  isActive,
  obj,
  setField,
  section,
  translatorSection,
}: {
  name: "openrouter" | "gemini" | "custom";
  entries: [string, unknown][];
  isActive: boolean;
  obj: Record<string, unknown>;
  setField: (section: string, field: string, value: unknown) => void;
  section: string;
  translatorSection: Record<string, unknown>;
}) {
  const { t } = useI18n();
  const [test, setTest] = useState<TestState>({ state: "idle" });
  const help = PROVIDER_HELP[name];

  async function runTest() {
    setTest({ state: "testing" });
    try {
      // Force the card's own provider so each card tests itself even when
      // another is selected, and reuse the on-screen values (unsaved OK).
      const body = { ...translatorSection, provider: name };
      const r = await api.post<{ ok: boolean; error?: string; latency_ms?: number }>(
        "/api/config/test-provider",
        body,
      );
      if (r.ok) setTest({ state: "ok", ms: r.latency_ms });
      else setTest({ state: "fail", detail: r.error || t("set.testFail") });
    } catch (err) {
      setTest({
        state: "fail",
        detail: err instanceof Error ? err.message : t("set.testFail"),
      });
    }
  }

  return (
    <fieldset
      className={`rounded-2xl border p-5 transition-colors ${
        isActive
          ? "border-primary bg-surface2 shadow-[3px_3px_0_0_var(--primary)]"
          : "border-line bg-surface2"
      }`}
    >
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary">
          {name}
        </span>
        {isActive && (
          <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider text-primary">
            {t("set.inUse")}
          </span>
        )}
        <button
          type="button"
          onClick={() => void runTest()}
          disabled={test.state === "testing"}
          className="ms-auto inline-flex items-center gap-1.5 rounded-btn border border-line-strong bg-elev px-3 py-1.5 text-[11px] font-bold text-ink transition-colors hover:bg-surface3 disabled:opacity-60"
        >
          {test.state === "testing" ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Zap size={13} className="text-warning" />
          )}
          {test.state === "testing" ? t("set.testTrying") : t("set.testConn")}
        </button>
      </div>

      {/* Key guide */}
      {help && (
        <p className="mt-2 text-[11px] leading-relaxed text-faint" dir="auto">
          {t(help.help)}{" "}
          {help.url && (
            <a
              href={help.url}
              target="_blank"
              rel="noreferrer"
              className="font-bold text-primary underline underline-offset-2 hover:opacity-80"
            >
              {t("set.helpKeys")} ↗
            </a>
          )}
        </p>
      )}

      {/* Test result */}
      {test.state === "ok" && (
        <p className="mt-2 text-[11px] font-bold text-success">
          ✓ {t("set.testOk")} · {test.ms}ms
        </p>
      )}
      {test.state === "fail" && (
        <p className="mt-2 text-[11px] font-bold text-danger" dir="auto">
          ✗ {t("set.testFail")}{test.detail ? ` — ${test.detail}` : ""}
        </p>
      )}

      {/* Fields */}
      <div className="mt-3 grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">
        {entries.map(([f, v]) => (
          <FieldRow
            key={f}
            field={`${name}.${f}`}
            value={v}
            fonts={[]}
            onChange={(nv) => setField(section, name, { ...obj, [f]: nv })}
          />
        ))}
      </div>
    </fieldset>
  );
}

/** Color picker: native swatch plus an editable hex field that only commits
 *  complete #rrggbb values (partial input stays local until valid). */
function ColorField({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (v: unknown) => void;
}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const valid = /^#[0-9a-fA-F]{6}$/.test(value);

  return (
    <div className="flex items-center gap-2">
      <input
        id={id}
        type="color"
        value={valid ? value : "#000000"}
        onChange={(e) => {
          setText(e.target.value);
          onChange(e.target.value);
        }}
        className="h-9 w-11 shrink-0 cursor-pointer rounded-lg border border-line bg-elev p-1"
      />
      <input
        dir="ltr"
        spellCheck={false}
        className="input-base w-28 font-mono !text-xs"
        value={text}
        placeholder="#000000"
        onChange={(e) => {
          setText(e.target.value);
          if (/^#[0-9a-fA-F]{6}$/.test(e.target.value)) onChange(e.target.value);
        }}
      />
    </div>
  );
}
