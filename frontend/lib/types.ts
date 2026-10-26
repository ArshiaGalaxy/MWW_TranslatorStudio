export interface Project {
  id: string;
  name: string;
  status: string;
  pdf_type: "manga" | "manhwa";
  chapter_id: string;
  total_pages: number;
  total_blocks: number;
  translated_count: number;
  progress_percent: number;
  detected_mode: string;
  error_message: string;
  created_at: string;
  updated_at: string;
  uses_page_sources: boolean;
}

export interface ProjectDetail extends Project {
  pdf_file: string;
  cover_pages: number[];
  skip_pages: number[];
  ocr_config: Record<string, unknown>;
  font_config: Record<string, unknown>;
  inpaint_config: Record<string, unknown>;
  translator_config: Record<string, unknown>;
  chapter_id_config: Record<string, unknown>;
  active_job: Job | null;
  pages: Page[];
}

export interface Page {
  id: string;
  page_number: number;
  width: number;
  height: number;
  is_cover: boolean;
  is_skipped: boolean;
  image_url: string;
  cleaned_image_url: string;
  rendered_image_url: string;
  block_count: number;
  translated_count: number;
}

export type BlockType =
  | "dialog"
  | "sfx"
  | "thinking"
  | "action"
  | "whisper"
  | "narration"
  | "system"
  | "custom";

export const BLOCK_TYPES: BlockType[] = [
  "dialog",
  "sfx",
  "thinking",
  "action",
  "whisper",
  "narration",
  "system",
  "custom",
];

export interface TextBlock {
  id: string;
  key: string;
  page_number: number;
  original_text: string;
  translation: string;
  block_type: BlockType;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color: string;
  stroke_color: string;
  stroke_size: number | null;
  alignment: string;
  font_override: string;
  font_size_override: number | null;
  orientation: "horizontal" | "vertical";
  rotation: number;
  order: number;
  is_translated: boolean;
  font_type: string;
}

export interface PreviewTextLayout {
  skipped?: boolean;
  unavailable?: boolean;
  font_size?: number;
  font_url?: string;
  align?: "left" | "right" | "center";
  rotation?: number;
  lines?: { text: string; x: number; y: number }[];
}

export interface MaskMark {
  id: string;
  page_number: number;
  /** Freehand stroke as [[x, y], ...] in image-pixel coordinates. */
  points: [number, number][];
  created_at: string;
}

export interface Job {
  id: string;
  project: string;
  kind: "extract" | "translate" | "apply" | "clean" | "render" | "reocr" | "import_pages";
  status: "pending" | "running" | "success" | "failed" | "cancelled";
  progress: number;
  stage: string;
  params: Record<string, unknown>;
  result: { files?: { name: string; url: string }[]; [k: string]: unknown };
  logs: string[];
  error_message: string;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
}

export interface FontInfo {
  name: string;
  path: string;
  url: string;
}
