"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PreviewTextLayout, TextBlock } from "@/lib/types";

const loadedFonts = new Map<string, Promise<string>>();
let nextFontId = 0;
export function loadFont(url: string): Promise<string> {
  let pending = loadedFonts.get(url);
  if (!pending) {
    const family = `RenderPreview${nextFontId++}`;
    pending = new FontFace(family, `url(${JSON.stringify(url)})`).load().then((font) => {
      document.fonts.add(font);
      return family;
    }).catch((error) => {
      loadedFonts.delete(url);
      throw error;
    });
    loadedFonts.set(url, pending);
  }
  return pending;
}

type LoadedLayout = PreviewTextLayout & { fontFamily?: string };

export function usePreviewLayout(projectId: string, blocks: TextBlock[], revision?: string) {
  const payload = JSON.stringify(blocks.map((b) => ({
    id: b.id, translation: b.translation, block_type: b.block_type,
    x1: b.x1, y1: b.y1, x2: b.x2, y2: b.y2,
    font_override: b.font_override, font_size_override: b.font_size_override,
    alignment: b.alignment, rotation: b.rotation ?? 0,
  })));
  const pageNumber = blocks[0]?.page_number;
  const key = `${projectId}:${pageNumber}:${revision}:${payload}`;
  const [result, setResult] = useState<{ key: string; layouts: Record<string, LoadedLayout>; failed: boolean } | null>(null);

  useEffect(() => {
    if (!pageNumber || payload === "[]") return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const drafts = JSON.parse(payload);
        const layouts: Record<string, LoadedLayout> = {};
        for (let i = 0; i < drafts.length; i += 100) {
          if (cancelled) return;
          Object.assign(layouts, await api.post<Record<string, PreviewTextLayout>>(
            `/api/projects/${projectId}/preview-layout`,
            { page_number: pageNumber, blocks: drafts.slice(i, i + 100) },
          ));
        }
        await Promise.all(Object.values(layouts).map(async (layout) => {
          if (layout.font_url) {
            try { layout.fontFamily = await loadFont(layout.font_url); }
            catch { layout.unavailable = true; }
          }
        }));
        if (!cancelled) setResult({ key, layouts, failed: false });
      } catch {
        if (!cancelled) setResult({ key, layouts: {}, failed: true });
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [projectId, pageNumber, payload, revision, key]);

  const current = result?.key === key ? result : null;
  return {
    layouts: current?.layouts ?? {},
    pending: blocks.length > 0 && !current,
    failed: current?.failed || Object.values(current?.layouts ?? {}).some((l) => l.unavailable),
  };
}
