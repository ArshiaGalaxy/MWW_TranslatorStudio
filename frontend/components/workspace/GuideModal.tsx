"use client";

import { ReactNode } from "react";
import {
  ArrowRightLeft,
  BoxSelect,
  Brush,
  Copy,
  Download,
  Eraser,
  Image as ImageIcon,
  Languages,
  Maximize2,
  MousePointerClick,
  Move,
  MoveVertical,
  Paintbrush,
  Pencil,
  PenTool,
  RefreshCw,
  ScanText,
  Trash2,
  ZoomIn,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Modal } from "@/components/ui";

/* ── Canvas guide modal ────────────────────────────────────────────────
   Opened from the workspace header "?" button. Reorganizes the tiny
   canvas hint line into five scannable sections; scrolls on short
   screens (Modal itself is not scrollable). */

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h4 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted">
        {title}
      </h4>
      <div className="space-y-1.5">{children}</div>
    </section>
  );
}

function Row({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 text-xs leading-relaxed">
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-surface2 text-muted">
        {icon}
      </span>
      <span className="text-muted">{children}</span>
    </div>
  );
}

export function GuideModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();

  // Pipeline order mirrors the header buttons left-to-right.
  const workflow = [
    { icon: <ScanText size={13} />, label: t("ws.extractPages"), desc: t("guide.stepExtract") },
    { icon: <Languages size={13} />, label: t("ws.translateAll"), desc: t("guide.stepTranslate") },
    { icon: <Brush size={13} />, label: t("ws.clean"), desc: t("guide.stepClean") },
    { icon: <PenTool size={13} />, label: t("ws.render"), desc: t("guide.stepRender") },
    { icon: <Download size={13} />, label: t("ws.export"), desc: t("guide.stepExport") },
  ];

  const views = [
    { icon: <ImageIcon size={13} />, label: t("ws.original"), desc: t("guide.viewOriginal") },
    { icon: <Brush size={13} />, label: t("ws.cleaned"), desc: t("guide.viewCleaned") },
    { icon: <PenTool size={13} />, label: t("ws.rendered"), desc: t("guide.viewRendered") },
  ];

  const editing = [
    { icon: <Move size={13} />, text: t("guide.editMove") },
    { icon: <Maximize2 size={13} />, text: t("guide.editResize") },
    { icon: <Pencil size={13} />, text: t("guide.editText") },
    { icon: <MousePointerClick size={13} />, text: t("guide.editAdd") },
    { icon: <Trash2 size={13} />, text: t("guide.editDelete") },
    { icon: <ZoomIn size={13} />, text: t("guide.editZoom") },
    { icon: <BoxSelect size={13} />, text: t("guide.editMulti") },
    { icon: <MoveVertical size={13} />, text: t("guide.editNudge") },
    { icon: <ArrowRightLeft size={13} />, text: t("guide.editTab") },
    { icon: <Copy size={13} />, text: t("guide.editStyle") },
  ];

  const brush = [
    { icon: <Paintbrush size={13} />, text: t("guide.brushPaint") },
    { icon: <Eraser size={13} />, text: t("guide.brushErase") },
    { icon: <RefreshCw size={13} />, text: t("guide.brushReclean") },
    { icon: <ScanText size={13} />, text: t("guide.brushReocr") },
  ];

  const shortcuts = [
    { keys: "← / →", label: t("guide.scPages") },
    { keys: "1 / 2 / 3", label: t("guide.scViews") },
    { keys: "N", label: t("guide.scNext") },
    { keys: "Tab", label: t("guide.scTab") },
    { keys: "Shift+Arrows", label: t("guide.scNudge") },
    { keys: "Ctrl+Wheel", label: t("guide.scZoom") },
    { keys: "Del", label: t("ws.deleteBox") },
    { keys: "Esc", label: t("ws.toolSelect") },
  ];

  return (
    <Modal title={t("ws.guide")} onClose={onClose} wide>
      <div className="max-h-[65vh] space-y-5 overflow-y-auto pe-1">
        <Section title={t("guide.workflow")}>
          {workflow.map((s) => (
            <Row key={s.label} icon={s.icon}>
              <span className="font-bold text-ink">{s.label}</span>
              <span className="mx-1.5 opacity-40">·</span>
              {s.desc}
            </Row>
          ))}
        </Section>

        <Section title={t("guide.views")}>
          {views.map((v) => (
            <Row key={v.label} icon={v.icon}>
              <span className="font-bold text-ink">{v.label}</span>
              <span className="mx-1.5 opacity-40">·</span>
              {v.desc}
            </Row>
          ))}
        </Section>

        <Section title={t("guide.editing")}>
          {editing.map((e) => (
            <Row key={e.text} icon={e.icon}>
              {e.text}
            </Row>
          ))}
        </Section>

        <Section title={t("guide.cleanBrush")}>
          {brush.map((b) => (
            <Row key={b.text} icon={b.icon}>
              {b.text}
            </Row>
          ))}
        </Section>

        <Section title={t("guide.shortcuts")}>
          {shortcuts.map((s) => (
            <div key={s.keys} className="flex items-center gap-2.5 text-xs">
              <kbd
                dir="ltr"
                className="min-w-16 rounded-md border border-line bg-surface2 px-1.5 py-0.5 text-center text-[10px] font-bold"
              >
                {s.keys}
              </kbd>
              <span className="text-muted">{s.label}</span>
            </div>
          ))}
        </Section>
      </div>
    </Modal>
  );
}
