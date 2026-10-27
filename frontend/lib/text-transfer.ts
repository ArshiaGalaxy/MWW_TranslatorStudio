import type { TextBlock } from "./types";

export interface TranslationEntry {
  id: string;
  translation: string;
}

export function serializeOcrText(projectId: string, blocks: TextBlock[]): string {
  const entries = [...blocks]
    .sort((a, b) => a.page_number - b.page_number || a.order - b.order || a.id.localeCompare(b.id))
    .map((block) => [
      `[[${block.id}]]`,
      { original: block.original_text, translated: block.translation },
    ]);
  return JSON.stringify({ project_id: projectId, blocks: Object.fromEntries(entries) }, null, 2) + "\n";
}

export function parseTranslationText(
  text: string,
  projectId: string,
  blocks: TextBlock[],
): { entries: TranslationEntry[]; skipped: number } {
  const source = text.replace(/^\uFEFF/, "").trim();
  if (source.startsWith("{")) {
    let data: unknown;
    try {
      data = JSON.parse(source);
    } catch {
      throw new Error("format");
    }
    const isObject = (value: unknown): value is Record<string, unknown> =>
      typeof value === "object" && value !== null && !Array.isArray(value);
    if (!isObject(data) || typeof data.project_id !== "string" || !isObject(data.blocks)) {
      throw new Error("format");
    }
    if (data.project_id !== projectId) throw new Error("project");
    const allowed = new Set(blocks.map((block) => block.id));
    const entries: TranslationEntry[] = [];
    let skipped = 0;
    const items = Object.entries(data.blocks);
    if (!items.length) throw new Error("format");
    for (const [key, value] of items) {
      const marker = /^\[\[([^\s\[\]]+)\]\]$/.exec(key);
      if (!marker || !isObject(value) || typeof value.original !== "string" || typeof value.translated !== "string") {
        throw new Error("format");
      }
      const id = marker[1];
      if (!allowed.has(id)) throw new Error("unknown");
      if (!value.translated.trim()) skipped++;
      else entries.push({ id, translation: value.translated });
    }
    return { entries, skipped };
  }
  // Continue accepting previously exported marker-based text files.
  const lines = text.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").split("\n");
  const header = /^\[\[Vira-OCR 1 PROJECT ([^\s\]]+)\]\]$/.exec(lines[0]);
  if (!header) throw new Error("format");
  if (header[1] !== projectId) throw new Error("project");
  const allowed = new Map(blocks.map((block) => [block.id, block]));
  const seen = new Set<string>();
  const entries: TranslationEntry[] = [];
  let skipped = 0;
  let index = 1;
  while (index < lines.length) {
    if (!lines[index].trim()) {
      index++;
      continue;
    }
    const marker = /^\[\[BLOCK ([^\s\]]+) PAGE (\d+)\]\]$/.exec(lines[index++]);
    if (!marker) throw new Error("format");
    const block = allowed.get(marker[1]);
    if (!block || block.page_number !== Number(marker[2])) throw new Error("unknown");
    if (seen.has(block.id)) throw new Error("duplicate");
    seen.add(block.id);
    const content: string[] = [];
    while (index < lines.length && lines[index] !== "[[END]]") {
      const line = lines[index++];
      if (line.startsWith("[[")) throw new Error("format");
      if (line.startsWith("\\") && !/^\\(\\|\[\[)/.test(line)) throw new Error("format");
      content.push(line.startsWith("\\") ? line.slice(1) : line);
    }
    if (index === lines.length) throw new Error("format");
    index++;
    const translation = content.join("\n");
    if (!translation.trim()) skipped++;
    else entries.push({ id: block.id, translation });
  }
  if (!seen.size) throw new Error("format");
  return { entries, skipped };
}
