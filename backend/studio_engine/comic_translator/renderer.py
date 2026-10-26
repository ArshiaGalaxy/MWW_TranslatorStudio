"""Persian text rendering on images."""

from __future__ import annotations

import colorsys
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageFont

from comic_translator.config import ChapterIDConfig, FontConfig, InpaintConfig
from comic_translator.typography import TextColorRules

if TYPE_CHECKING:
    from comic_translator.models import Block

logger = logging.getLogger(__name__)


# ── Progress Tracking ────────────────────────────────────────────────────────


@dataclass
class RenderProgress:
    """Detailed progress tracker for render operations.

    Reports granular progress including:
    - Current phase (inpaint, draw_text, split, etc.)
    - Per-page / per-region progress
    - Timing information
    - Overall percentage
    """

    total_regions: int = 0
    total_pages: int = 0
    processed_regions: int = 0
    processed_pages: int = 0
    start_time: float = field(default_factory=time.time)
    last_message: str = ""

    def start_phase(self, phase: str, total: int = 0) -> None:
        """Start a new phase (e.g. 'inpaint', 'draw_text', 'split')."""
        if total > 0:
            if phase in ("inpaint", "draw_text"):
                self.total_regions = total
            elif phase in ("split", "load"):
                self.total_pages = total

    def update(self, message: str = "", increment: int = 1) -> float:
        """Update progress. Returns current percentage (0.0–1.0)."""
        self.processed_regions += increment
        self.last_message = message
        return self.percentage

    def update_page(self, page_num: int, total: int, message: str = "") -> float:
        """Update page-level progress. Returns current percentage."""
        self.processed_pages = page_num
        self.total_pages = total
        return self.percentage

    def finish_phase(self) -> None:
        """Mark current phase as complete (kept for progress-adapter API)."""
        return

    def finish(self) -> dict:
        """Finish tracking. Returns summary dict."""
        total_elapsed = time.time() - self.start_time
        summary = {
            "total_pages": self.total_pages,
            "total_regions": self.total_regions,
            "elapsed": f"{total_elapsed:.1f}s",
            "regions_per_sec": (
                self.processed_regions / total_elapsed
                if total_elapsed > 0 else 0
            ),
        }
        return summary

    @property
    def percentage(self) -> float:
        """Overall progress percentage (0.0–1.0)."""
        if self.total_regions > 0:
            return min(1.0, self.processed_regions / self.total_regions)
        if self.total_pages > 0:
            return min(1.0, self.processed_pages / self.total_pages)
        return 0.0

    @property
    def elapsed_str(self) -> str:
        """Formatted elapsed time since start."""
        elapsed = time.time() - self.start_time
        if elapsed < 60:
            return f"{elapsed:.1f}s"
        return f"{int(elapsed // 60)}m {int(elapsed % 60)}s"


_SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
_FONTS_DIR = _SCRIPT_DIR / "fonts"

# ── Caches ───────────────────────────────────────────────────────────────────

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_MEASURE_DUMMY = Image.new("RGB", (1, 1))
_MEASURE_DRAW = ImageDraw.Draw(_MEASURE_DUMMY)
# Cache holds (image_ref, array) so a stale id() can never serve another
# image's pixels: after GC an id may be reused by a fresh Image, and without
# the reference check that image would silently inherit the old array.
_np_array_cache: dict[int, tuple[Image.Image, Any]] = {}


def _as_np_array(image: Image.Image):
    """Convert PIL image to numpy array, with per-image caching."""
    import numpy as np

    img_id = id(image)
    cached = _np_array_cache.get(img_id)
    if cached is not None and cached[0] is image:
        return cached[1]
    arr = np.array(image)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    _np_array_cache[img_id] = (image, arr)
    return arr


def _invalidate_np_cache(image: Image.Image) -> None:
    """Remove cached numpy array for an image that has been modified."""
    _np_array_cache.pop(id(image), None)


# ── Text Type Defaults ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class TypeDefaults:
    size_factor: float = 1.0
    color: str | None = None
    stroke_color: str | None = None
    stroke_factor: float = 1.0
    alignment: str = "center"
    font_pattern: str = "*Mikhak*"


TYPE_DEFAULTS: dict[str, TypeDefaults] = {
    "dialog":    TypeDefaults(size_factor=1.0,  alignment="center",  font_pattern="*Mikhak*"),
    "sfx":       TypeDefaults(size_factor=1.0,  alignment="center",  font_pattern="*AFSANEH*"),
    "think":     TypeDefaults(size_factor=0.85, stroke_factor=0.5, alignment="center",  font_pattern="*AFSANEH*"),
    "action":    TypeDefaults(size_factor=1.2,  stroke_factor=1.5, alignment="center",  font_pattern="*Mikhak*"),
    "whisper":   TypeDefaults(size_factor=0.8,  color="#AAAAAA", stroke_color="#555555", stroke_factor=0.5, alignment="center", font_pattern="Vazir*"),
    "narration": TypeDefaults(size_factor=1.0,  alignment="rtl",    font_pattern="*Mikhak*"),
    "system":    TypeDefaults(size_factor=0.9,  color="#4A90D9", stroke_color="#FFFFFF", stroke_factor=0.8, alignment="center", font_pattern="Vazir*"),
    "custom":    TypeDefaults(size_factor=1.0,  alignment="center",  font_pattern="*Mikhak*"),
}


@dataclass
class ResolvedStyle:
    font_path: str | None = None
    font_size_max: int = 60
    text_color: str | None = None
    stroke_color: str | None = None
    stroke_width: int = 1
    alignment: str = "center"
    size_factor: float = 1.0
    orientation: str = "horizontal"
    rotation: float = 0.0


def resolve_style(
    text_type: str,
    font_config: FontConfig | None = None,
    color_override: str | None = None,
    stroke_color_override: str | None = None,
    stroke_size_override: int | None = None,
    alignment_override: str | None = None,
    font_override: str | None = None,
    font_size_override: int | None = None,
    orientation_override: str | None = None,
    rotation: float = 0.0,
) -> ResolvedStyle:
    """Resolve final rendering style by merging type defaults with per-block overrides."""
    defaults = TYPE_DEFAULTS.get(text_type, TYPE_DEFAULTS["dialog"])

    fp = font_override
    if not fp:
        fp = _auto_find_font(defaults.font_pattern, "Vazir.ttf")

    stroke_w = stroke_size_override if stroke_size_override is not None else max(1, int(font_config.stroke_width * defaults.stroke_factor)) if font_config else 1

    return ResolvedStyle(
        font_path=fp,
        font_size_max=font_size_override if font_size_override is not None else (font_config.size_max if font_config else 60),
        text_color=color_override or defaults.color,
        stroke_color=stroke_color_override or defaults.stroke_color,
        stroke_width=stroke_w,
        alignment=alignment_override or defaults.alignment,
        size_factor=defaults.size_factor,
        orientation=orientation_override or "horizontal",
        rotation=rotation,
    )


def _auto_find_font(glob_pattern: str, fallback_name: str = "Vazir.ttf") -> str | None:
    """Auto-find a font by glob pattern in fonts dir, then project root."""
    if _FONTS_DIR.exists():
        matches = sorted(_FONTS_DIR.glob(glob_pattern))
        if matches:
            return str(matches[0])
    candidate = _SCRIPT_DIR / fallback_name
    if candidate.exists():
        return str(candidate)
    for f in _SCRIPT_DIR.iterdir():
        if f.suffix.lower() in (".ttf", ".woff2"):
            return str(f)
    return None


def find_font(font_config: FontConfig | None = None, font_type: str = "normal") -> str | None:
    """Find a suitable TTF font for Persian text rendering by type."""
    if font_config:
        if font_type == "sfx" and font_config.path_sfx:
            path = font_config.path_sfx
            if Path(path).exists():
                return path
            # path_sfx set but not found — skip path_normal, go to auto-detect
        elif font_type == "thinking" and font_config.path_thinking:
            path = font_config.path_thinking
            if path and Path(path).exists():
                return path
            # path_thinking set but not found or empty — go to auto-detect
        elif font_type == "normal" and font_config.path_normal:
            path = font_config.path_normal
            if Path(path).exists():
                return path

    patterns = {
        "normal": "*Mikhak*",
        "sfx": "*AFSANEH*",
        "thinking": "*AFSANEH*",
    }
    fallbacks = {
        "normal": "Vazir.ttf",
        "sfx": "Vazir.ttf",
        "thinking": "Vazir.ttf",
    }
    pat = patterns.get(font_type, "*Mikhak*")
    fb = fallbacks.get(font_type, "Vazir.ttf")
    result = _auto_find_font(pat, fb)
    if result:
        return result

    candidates = [
        _SCRIPT_DIR / "Vazir.ttf",
        _SCRIPT_DIR / "vazir.ttf",
        Path(r"C:\Windows\Fonts\tahoma.ttf"),
        Path(r"C:\Windows\Fonts\Tahoma.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    for f in _SCRIPT_DIR.iterdir():
        if f.suffix.lower() == ".ttf":
            return str(f)
    return None


def _load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    key = (font_path or "", size)
    if font_path is None:
        return ImageFont.load_default()
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    try:
        font = ImageFont.truetype(font_path, size)
    except Exception:
        # Do NOT cache the default bitmap font under the failed key: it has no
        # Persian glyphs, and caching would silently degrade every later
        # render for this (path, size) to tofu boxes. Log once and fall back.
        logger.warning("Font load failed for %s size %s — using default",
                       font_path, size)
        return ImageFont.load_default()
    _font_cache[key] = font
    return font


def _reshape_persian(text: str) -> str:
    """Apply Arabic reshaping and BiDi for Persian text."""
    return text


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap each explicit line, preserving manual breaks and blank lines."""
    lines: list[str] = []
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        current_line = ""
        for word in paragraph.split():
            test = (current_line + " " + word).strip()
            try:
                tw = _text_width(test, font)
            except Exception:
                tw = len(test) * 8
            if tw <= max_width:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        lines.append(current_line)

    return lines


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> float:
    """Get text width, with fallback."""
    try:
        return _MEASURE_DRAW.textlength(text, font=font)
    except Exception:
        return len(text) * 8


def _sample_bg_color(image: Image.Image, x1: int, y1: int, x2: int, y2: int) -> str:
    """Sample the actual background color from outside the text box (numpy fast)."""
    import numpy as np

    w, h = image.size
    gap = 8
    band = 5

    arr = _as_np_array(image)

    samples = []

    # Top strip
    tx1, tx2 = max(0, x1 - gap - band), min(w, x2 + gap + band)
    ty1, ty2 = max(0, y1 - gap - band), max(0, y1 - gap)
    if tx2 > tx1 and ty2 > ty1:
        samples.append(arr[ty1:ty2, tx1:tx2].reshape(-1, 3))

    # Bottom strip
    by1, by2 = min(h, y2 + gap + 1), min(h, y2 + gap + band + 1)
    if tx2 > tx1 and by2 > by1:
        samples.append(arr[by1:by2, tx1:tx2].reshape(-1, 3))

    # Left strip
    lx1, lx2 = max(0, x1 - gap - band), max(0, x1 - gap)
    ly1, ly2 = max(0, y1), min(h, y2)
    if lx2 > lx1 and ly2 > ly1:
        samples.append(arr[ly1:ly2, lx1:lx2].reshape(-1, 3))

    # Right strip
    rx1, rx2 = min(w, x2 + gap + 1), min(w, x2 + gap + band + 1)
    if rx2 > rx1 and ly2 > ly1:
        samples.append(arr[ly1:ly2, rx1:rx2].reshape(-1, 3))

    if not samples:
        return "#FFFFFF"

    all_px = np.concatenate(samples, axis=0)[:, :3]
    if all_px.shape[0] == 0:
        return "#FFFFFF"
    step = 12
    quantized = (all_px // step) * step
    # Count unique rows
    unique, counts = np.unique(quantized, axis=0, return_counts=True)
    best = unique[counts.argmax()]
    return f"#{int(best[0]):02x}{int(best[1]):02x}{int(best[2]):02x}"


def _sample_interior_color(image: Image.Image, x1: int, y1: int, x2: int, y2: int) -> str | None:
    """Sample the dominant color inside the bounding box (numpy fast).
    Returns the color if the interior is mostly uniform (speech bubble),
    None if it's varied (text on artwork).
    """
    import numpy as np

    w, h = image.size
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    sample_r = min((x2 - x1) // 4, (y2 - y1) // 4, 20)

    # Define region of interest
    rx1, ry1 = max(0, cx - sample_r), max(0, cy - sample_r)
    rx2, ry2 = min(w, cx + sample_r + 1), min(h, cy + sample_r + 1)
    if rx2 - rx1 < 5 or ry2 - ry1 < 5:
        return None

    arr = _as_np_array(image)
    region = arr[ry1:ry2, rx1:rx2, :3]

    # Sample with stride 3
    step_px = 3
    samples = region[::step_px, ::step_px].reshape(-1, 3)

    if len(samples) < 10:
        return None

    step = 16
    quantized = (samples // step) * step
    unique, counts = np.unique(quantized, axis=0, return_counts=True)
    top_idx = counts.argmax()
    top_count = int(counts[top_idx])
    uniformity = top_count / len(quantized)

    if uniformity > 0.6:
        best = unique[top_idx]
        return f"#{int(best[0]):02x}{int(best[1]):02x}{int(best[2]):02x}"
    return None


def _to_hex(color: str) -> str:
    """Convert color name or hex to #RRGGBB format."""
    if color.startswith("#"):
        return color
    # Named colors map
    named = {
        "black": "#000000", "white": "#FFFFFF", "red": "#FF0000",
        "green": "#008000", "blue": "#0000FF", "yellow": "#FFFF00",
        "cyan": "#00FFFF", "magenta": "#FF00FF", "gray": "#808080",
        "grey": "#808080", "orange": "#FFA500", "purple": "#800080",
        "pink": "#FFC0CB", "brown": "#A52A2A", "transparent": "#FFFFFF",
    }
    return named.get(color.lower(), "#000000")


def _luminance(hex_color: str) -> float:
    """Calculate relative luminance of a hex color (0=black, 1=white)."""
    hex_color = _to_hex(hex_color).lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _pick_text_color(bg_color: str) -> str:
    """Pick black or white text for best contrast against background."""
    return "#000000" if _luminance(bg_color) > 0.4 else "#FFFFFF"


# ── Original-text color sampling ────────────────────────────────────────────


def _sample_original_text_color(
    image: Image.Image,
    x1: int, y1: int, x2: int, y2: int,
    text_boxes: list | None = None,
    text_color_rules: TextColorRules | None = None,
) -> str | None:
    """Estimate the color of the ORIGINAL text strokes inside a region.

    MUST be called on an image that still contains the original text
    (before erase/inpaint).  Returns a hex string, or ``None`` when no
    reliable text color can be determined.

    Algorithm:
      1. Estimate the region background color (interior, else surrounding).
      2. Restrict analysis to the OCR text-box polygons (or the whole box).
      3. Keep only "ink" pixels — those far from the background.
      4. Quantize and return the dominant ink color.
    """
    import numpy as np

    rules = text_color_rules or TextColorRules()
    w, h = image.size
    x1 = max(0, int(x1))
    y1 = max(0, int(y1))
    x2 = min(w, int(x2))
    y2 = min(h, int(y2))
    if x2 - x1 < 6 or y2 - y1 < 6:
        return None

    arr = _as_np_array(image)
    region = arr[y1:y2, x1:x2, :3].astype(np.float64)

    bg_hex = _sample_interior_color(image, x1, y1, x2, y2) or _sample_bg_color(
        image, x1, y1, x2, y2
    )
    bg = np.array([int(bg_hex[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float64)

    mask = np.zeros((y2 - y1, x2 - x1), dtype=bool)
    if text_boxes:
        mask_img = Image.new("L", (x2 - x1, y2 - y1), 0)
        mask_draw = ImageDraw.Draw(mask_img)
        for poly in text_boxes:
            pts = [(px - x1, py - y1) for px, py in poly]
            if len(pts) >= 3:
                mask_draw.polygon(pts, fill=255)
        mask = np.asarray(mask_img) > 128
    else:
        # Shrink slightly so bubble borders are not treated as ink.
        inset_x = max(1, (x2 - x1) // 10)
        inset_y = max(1, (y2 - y1) // 10)
        mask[inset_y:y2 - y1 - inset_y, inset_x:x2 - x1 - inset_x] = True

    region = region[mask]
    if region.shape[0] < rules.ink_min_sample_count * 2:
        return None

    dist = np.abs(region - bg).sum(axis=1)
    ink = region[dist > rules.ink_color_distance_threshold]
    if ink.shape[0] < rules.ink_min_sample_count:
        return None

    step = max(1, int(rules.ink_quantization_step))
    quant = (ink // step) * step
    uniq, counts = np.unique(quant, axis=0, return_counts=True)
    best = uniq[int(counts.argmax())]
    return f"#{int(best[0]):02x}{int(best[1]):02x}{int(best[2]):02x}"


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG relative luminance of an sRGB tuple."""
    vals = [c / 255.0 for c in rgb]
    linear = [
        v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in vals
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(color_a: str, color_b: str) -> float:
    """WCAG contrast ratio between two hex colors."""
    a = (int(_to_hex(color_a)[i:i + 2], 16) for i in (1, 3, 5))
    b = (int(_to_hex(color_b)[i:i + 2], 16) for i in (1, 3, 5))
    la, lb = _relative_luminance(tuple(a)), _relative_luminance(tuple(b))
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _adjust_color_contrast(
    text_hex: str,
    bg_hex: str,
    min_ratio: float,
) -> str | None:
    """Adjust a text color's lightness (preserving hue) until it contrasts.

    Returns the adjusted hex color, or ``None`` when even black/white cannot
    reach the required ratio (caller should then fall back to B/W picking).
    """
    if _contrast_ratio(text_hex, bg_hex) >= min_ratio:
        return text_hex

    rgb = tuple(int(text_hex[i:i + 2], 16) for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(*(c / 255.0 for c in rgb))

    # Candidates ordered by lightness distance from the original (least
    # intrusive first), trying darkening and lightening in both directions.
    steps = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.75, 0.90]
    candidates = []
    for d in steps:
        for sign in (-1, 1):
            cand = min(1.0, max(0.0, l + sign * d))
            candidates.append((abs(cand - l), cand))
    candidates = sorted(dict.fromkeys(candidates))

    for _, cand_l in candidates:
        r, g, b = colorsys.hls_to_rgb(h, cand_l, s)
        cand_hex = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
        if _contrast_ratio(cand_hex, bg_hex) >= min_ratio:
            return cand_hex
    return None


def _resolve_text_color(
    bg_color: str,
    text_color_rules: TextColorRules | None,
    style_text_color: str | None,
    original_text_color: str | None,
) -> str:
    """Resolve the final text color following the typography precedence:

    1. per-block / style fixed color;
    2. original-text color match (luminance-adjusted to stay readable);
    3. black/white contrast fallback.
    """
    if style_text_color:
        return _to_hex(style_text_color)

    rules = text_color_rules or TextColorRules()
    if not rules.match_original_text_color:
        return _pick_text_color(bg_color)

    if original_text_color:
        adjusted = _adjust_color_contrast(
            _to_hex(original_text_color), _to_hex(bg_color), rules.contrast_min_ratio
        )
        if adjusted:
            return adjusted

    return _pick_text_color(bg_color)


def sample_original_text_colors(
    image: Image.Image,
    region_blocks: list[tuple[str, "Block"]],
    text_color_rules: TextColorRules | None,
) -> dict[str, str]:
    """Sample the original rendered text color for each region.

    Called during the **Clean** step, *before* the original text is erased, so
    that the sampled color reflects the actual on-page text rather than the
    inpainted background.

    Returns a mapping ``{region_key: "#rrggbb"}`` containing only the regions
    whose original color should be preserved (i.e. when
    ``text_color_rules.match_original_text_color`` is true). Regions whose
    color cannot be sampled confidently are skipped.
    """
    rules = text_color_rules or TextColorRules()
    if not rules.match_original_text_color:
        return {}

    colors: dict[str, str] = {}
    for key, blk in region_blocks:
        if not blk.text.strip() or blk.is_sfx:
            continue
        color = _sample_original_text_color(
            image, blk.x1, blk.y1, blk.x2, blk.y2, blk.text_boxes, rules
        )
        if color:
            colors[key] = color
    return colors


def _dilate_rect(
    x1: int, y1: int, x2: int, y2: int,
    pad_x: int, pad_y: int, img_w: int, img_h: int,
) -> tuple[int, int, int, int]:
    """Dilate a rectangle by `pad_x`/`pad_y` pixels, clamped to image bounds."""
    return (
        max(0, x1 - pad_x),
        max(0, y1 - pad_y),
        min(img_w, x2 + pad_x),
        min(img_h, y2 + pad_y),
    )


def erase_region(
    draw: ImageDraw.Draw, x1: int, y1: int, x2: int, y2: int,
    color: str = "#FFFFFF", image: Image.Image | None = None,
    text_boxes: list | None = None, pad: int = 6,
    inpaint_config: InpaintConfig | None = None,
) -> str:
    """Erase text regions. Supports three methods:
    - 'color': solid background-color fill (fast, simple)
    - 'opencv': OpenCV Navier-Stokes inpainting (fast, decent quality)
    - 'lama': LaMa neural inpainting (best quality, requires torch)
    """
    if image is None:
        draw.rectangle([x1 - pad, y1 - pad, x2 + pad, y2 + pad], fill=color)
        return color

    method = inpaint_config.method if inpaint_config else "color"
    bg_hex = _sample_bg_color(image, x1, y1, x2, y2)
    img_w, img_h = image.size

    pad_x = inpaint_config.padding_x if inpaint_config else pad
    pad_y = inpaint_config.padding_y if inpaint_config else pad

    if method in ("cv_auto", "opencv", "pcleaner"):
        try:
            from comic_translator.inpaint import inpaint

            dx1, dy1, dx2, dy2 = _dilate_rect(x1, y1, x2, y2, pad_x, pad_y, img_w, img_h)
            result = inpaint(
                image, dx1, dy1, dx2, dy2,
                text_boxes=text_boxes, pad_x=pad_x, pad_y=pad_y,
                method=method,
                opencv_radius=inpaint_config.opencv_radius if inpaint_config else 5,
                opencv_method=inpaint_config.opencv_method if inpaint_config else "ns",
                device=inpaint_config.lama_device if inpaint_config else "auto",
                pcleaner_profile=(
                    inpaint_config.pcleaner_profile if inpaint_config else None
                ),
                pcleaner_cli_path=(
                    inpaint_config.pcleaner_cli_path if inpaint_config else None
                ),
            )
            image.paste(result)
            _invalidate_np_cache(image)
            return bg_hex
        except Exception as e:
            logger.warning("%s inpaint failed, falling back to color fill: %s", method, e)

    interior = _sample_interior_color(image, x1, y1, x2, y2)
    fill_hex = interior if interior else bg_hex
    r, g, b = int(fill_hex[1:3], 16), int(fill_hex[3:5], 16), int(fill_hex[5:7], 16)
    fill = (r, g, b, 255) if image.mode == "RGBA" else (r, g, b)

    if text_boxes:
        for pts in text_boxes:
            draw.polygon(pts, fill=fill)
    dx1, dy1, dx2, dy2 = _dilate_rect(x1, y1, x2, y2, pad_x, pad_y, img_w, img_h)
    draw.rectangle([dx1, dy1, dx2, dy2], fill=fill)

    _invalidate_np_cache(image)
    return bg_hex


def fit_font_size(
    text: str, font_path: str | None, box_w: int, box_h: int,
    size_max: int = 60, size_min: int = 15,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Fit text using the user-configured size bounds as hard limits.

    Starts AT ``size_max`` (the sidebar value is the actual rendered size
    whenever it fits). Only shrinks — down to ``size_min`` — when the wrapped
    text overflows the box. ``size_min`` is a hard floor: text is never drawn
    smaller than that even if it overflows.
    """
    size_min = min(size_min, size_max)
    fs = int(size_max)

    while fs > size_min:
        font = _load_font(font_path, fs)
        lines = _wrap_text(text, font, box_w - 8)
        spacing = max(8, fs // 3)
        total_h = spacing * (len(lines) - 1) + len(lines) * fs * 2
        if total_h <= box_h:
            return font, lines, fs
        fs -= 2

    # Hard floor: draw at size_min even if it overflows the box — callers
    # unpack the tuple, so this must never fall through to an implicit None.
    font = _load_font(font_path, size_min)
    lines = _wrap_text(text, font, box_w - 8)
    return font, lines, size_min


def _normalize_alignment(alignment: str | None) -> str:
    """Map the panel's left/right (and legacy ltr/rtl) onto one canonical set."""
    if alignment in ("right", "rtl"):
        return "right"
    if alignment in ("left", "ltr"):
        return "left"
    return "center"


def text_layout(
    text: str, box_w: int, box_h: int, font_config: FontConfig,
    font_path: str | None = None, font_type: str = "normal",
    size_factor: float = 1.0, font_size_max: int | None = None,
    alignment: str = "center",
) -> dict:
    """The shared image-pixel layout used by rendering and editor previews."""
    fp = font_path or find_font(font_config, font_type)
    effective_max = max(
        font_config.size_min,
        font_size_max if font_size_max is not None
        else int(font_config.size_max * size_factor),
    )
    font, lines, fs = fit_font_size(
        _reshape_persian(text), fp, box_w, box_h,
        effective_max, font_config.size_min,
    )
    spacing = max(8, fs // 3)
    joined = "\n".join(lines)
    align = _normalize_alignment(alignment)
    bbox = _MEASURE_DRAW.multiline_textbbox(
        (0, 0), joined, font=font, spacing=spacing,
        align={"left": "left", "right": "right", "center": "center"}[align],
    )
    return dict(font=font, font_path=fp, font_size=fs, lines=lines,
                spacing=spacing, joined=joined, bbox=bbox, align=align)


def draw_persian(
    image: Image.Image,
    text: str,
    x1: int, y1: int, x2: int, y2: int,
    font_config: FontConfig,
    font_path: str | None = None,
    text_color: str | None = None,
    font_type: str = "normal",
    alignment: str = "center",
    stroke_color: str | None = None,
    stroke_width: int | None = None,
    size_factor: float = 1.0,
    font_size_max: int | None = None,
    original_text_color: str | None = None,
    text_color_rules: TextColorRules | None = None,
    orientation: str = "horizontal",
    rotation: float = 0.0,
) -> Image.Image:
    """Render Persian text within a bounding box on the image.
    Adds a contrasting stroke outline for readability.

    When ``text_color`` is ``None`` and ``original_text_color`` is provided,
    the original text color (luminance-adjusted for readability) is used
    instead of the plain black/white fallback.
    """
    if not text.strip():
        return image

    draw = ImageDraw.Draw(image)
    box_w = x2 - x1
    box_h = y2 - y1

    if box_w < 10 or box_h < 10:
        return image

    layout = text_layout(text, box_w, box_h, font_config, font_path,
                         font_type, size_factor, font_size_max, alignment)
    font = layout["font"]

    if text_color is None:
        bg = _sample_bg_color(image, x1, y1, x2, y2)
        text_color = _resolve_text_color(
            bg, text_color_rules, None, original_text_color
        )

    # Stroke: use override if provided, else auto-pick
    sw = stroke_width if stroke_width is not None else font_config.stroke_width
    if sw > 0:
        if stroke_color:
            stroke_fill = stroke_color
        else:
            stroke_fill = "#FFFFFF" if _luminance(text_color) < 0.5 else "#000000"
    else:
        stroke_fill = None

    spacing = layout["spacing"]
    joined = layout["joined"]
    bbox = layout["bbox"]
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Alignment
    align = layout["align"]
    if align == "right":
        sx = x2 - text_w - 4
    elif align == "left":
        sx = x1 + 4
    else:  # center
        sx = x1 + max(0, (box_w - text_w) // 2)
    sy = y1 + max(0, (box_h - text_h) // 2)

    if rotation:
        # Rotate the entire local box, not a tight glyph crop: this preserves
        # left/right alignment and pivots about the same center as the editor.
        layer = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
        draw_persian(
            layer, text, 0, 0, box_w, box_h, font_config, font_path,
            text_color=text_color, font_type=font_type, alignment=alignment,
            stroke_color=stroke_color, stroke_width=sw, size_factor=size_factor,
            font_size_max=font_size_max, orientation=orientation,
        )
        rotated = layer.rotate(-rotation, expand=True,
                               resample=Image.Resampling.BICUBIC)
        image.paste(rotated, (round((x1 + x2 - rotated.width) / 2),
                              round((y1 + y2 - rotated.height) / 2)), rotated)
        _invalidate_np_cache(image)
        return image

    if orientation == "horizontal":
        if sw > 0:
            draw.multiline_text((sx, sy), joined, fill=text_color, font=font,
                stroke_width=sw, stroke_fill=stroke_fill, spacing=spacing, align=align)
        else:
            draw.multiline_text((sx, sy), joined, fill=text_color, font=font,
                            spacing=spacing, align=align)
    else:
        # Vertical text: render on a transparent layer and rotate clockwise.
        isw = int(sw)
        itext_w = int(text_w)
        itext_h = int(text_h)
        layer = Image.new("RGBA", (itext_w + isw * 2, itext_h + isw * 2), (0, 0, 0, 0))
        ldraw = ImageDraw.Draw(layer)
        lx = isw
        ly = isw
        if isw > 0:
            ldraw.multiline_text((lx, ly), joined, fill=text_color, font=font,
                stroke_width=isw, stroke_fill=stroke_fill, spacing=spacing, align=align)
        else:
            ldraw.multiline_text((lx, ly), joined, fill=text_color, font=font,
                                 spacing=spacing, align=align)
        layer = layer.rotate(-90, expand=True)
        rx = x1 + max(0, (box_w - layer.width) // 2)
        ry = y1 + max(0, (box_h - layer.height) // 2)
        image.paste(layer, (rx, ry), layer)
        _invalidate_np_cache(image)
        return image

    _invalidate_np_cache(image)
    return image


def render_on_tall_image(
    page_images: list[Image.Image],
    regions: list[tuple[str, int, int, int, int, str, str, list | None, str, ResolvedStyle | None]],
    config: FontConfig,
    chapter_id: str = "",
    chapter_config: ChapterIDConfig | None = None,
    font_path: str | None = None,
    progress: RenderProgress | None = None,
    chunk_size: int | None = None,
    original_text_colors: dict[str, str] | None = None,
    text_color_rules: TextColorRules | None = None,
) -> tuple[list[Image.Image], dict]:
    """Render text on a vertically concatenated tall image, then split back.

    Uses chunked processing to avoid creating a single giant image that
    spans the entire chapter.  Pages are grouped into configurable chunks;
    each chunk is concatenated, rendered, and split independently so that
    only a fraction of the chapter is in memory at any time.

    ``original_text_colors`` maps region key -> original text color sampled
    BEFORE inpainting; used so the translated text keeps the original color.

    The public API is backward-compatible – existing callers that do not
    pass ``chunk_size`` will use the value from ``config.tall_render_chunk_size``.

    Args:
        page_images: List of per-page PIL Images.
        regions: List of (key, x1, y1, x2, y2, text, text_color, text_boxes,
                 font_type, style) where y1/y2 are in the concatenated
                 coordinate space.
        config: Font configuration (includes ``tall_render_chunk_size``).
        chapter_id: Optional chapter ID to stamp.
        chapter_config: Chapter ID style config.
        font_path: Optional font path override.
        progress: Optional progress tracker.
        chunk_size: Override the number of pages per chunk.  ``None`` uses
                    ``config.tall_render_chunk_size``.

    Returns:
        (output_images, stats) where output_images is a list of per-page
        rendered images and stats is a dict with timing/count info.
    """
    from comic_translator.pdf import (
        compute_page_offsets,
        concatenate_pages_vertically,
    )

    stats: dict = {"total_regions": len(regions), "pages": len(page_images)}
    render_start = time.time()

    # ── Validate inputs ────────────────────────────────────────────────
    if not page_images:
        if progress:
            progress.finish()
        return [], stats

    num_pages = len(page_images)

    # Resolve chunk size with validation
    effective_chunk_size = chunk_size if chunk_size is not None else config.tall_render_chunk_size
    if effective_chunk_size <= 0:
        effective_chunk_size = 1
    effective_chunk_size = min(effective_chunk_size, num_pages)

    # ── Normalise widths ───────────────────────────────────────────────
    # All pages must share the same width so that the concatenated image
    # and the per-chunk images are consistent.
    global_max_w = max(img.width for img in page_images)
    normalized_pages: list[Image.Image] = []
    for img in page_images:
        if img.width != global_max_w:
            normalized_pages.append(
                img.resize(
                    (global_max_w, int(img.height * global_max_w / img.width)),
                    Image.LANCZOS,
                )
            )
        else:
            normalized_pages.append(img)

    # ── Compute global page offsets ────────────────────────────────────
    page_offsets = compute_page_offsets(normalized_pages)

    # Fast path: nothing to render and no chapter ID
    if not regions and not (chapter_id and chapter_config):
        output = [img.copy() for img in normalized_pages]
        stats["rendered_regions"] = 0
        stats["elapsed"] = f"{time.time() - render_start:.1f}s"
        stats["render_time"] = time.time() - render_start
        if progress:
            progress.finish()
        return output, stats

    # ── Build chunks of page indices ───────────────────────────────────
    chunks: list[list[int]] = [
        list(range(start, min(start + effective_chunk_size, num_pages)))
        for start in range(0, num_pages, effective_chunk_size)
    ]

    # ── Phase: Draw text on chunked tall images ────────────────────────
    if progress:
        progress.start_phase("draw_text", total=len(regions))

    output_images: list[Image.Image] = [None] * num_pages  # type: ignore[list-item]
    rendered_count = 0

    for chunk_page_indices in chunks:
        # --- concatenate chunk ---
        chunk_pages = [normalized_pages[i] for i in chunk_page_indices]
        chunk_tall = concatenate_pages_vertically(chunk_pages)
        chunk_page_offsets = compute_page_offsets(chunk_pages)

        # Global y-range of this chunk
        chunk_global_start = page_offsets[chunk_page_indices[0]]
        chunk_global_end = chunk_global_start + chunk_tall.height

        # --- select & convert regions ---
        chunk_regions: list[tuple[str, int, int, int, int, str, str, list | None, str, ResolvedStyle | None]] = []
        for region in regions:
            key, x1, y1, x2, y2, text, text_color, text_boxes, font_type = region[:9]
            style = region[9] if len(region) > 9 else None

            # Skip regions that don't overlap this chunk
            if y2 <= chunk_global_start or y1 >= chunk_global_end:
                continue

            # Convert to chunk-local coordinates (Y only)
            local_y1 = max(0, y1 - chunk_global_start)
            local_y2 = min(chunk_tall.height, y2 - chunk_global_start)

            chunk_regions.append(
                (key, x1, local_y1, x2, local_y2,
                 text, text_color, text_boxes, font_type, style)
            )

        # --- render regions on chunk ---
        for idx, region in enumerate(chunk_regions):
            key, x1, y1, x2, y2, text, text_color, text_boxes, font_type = region[:9]
            style = region[9] if len(region) > 9 else None

            if not text.strip():
                if progress:
                    progress.update(f"Skip empty: {key}")
                continue

            if text_color is None:
                interior = _sample_interior_color(chunk_tall, x1, y1, x2, y2)
                bg = interior if interior else _sample_bg_color(chunk_tall, x1, y1, x2, y2)
                if original_text_colors is not None:
                    orig_color = original_text_colors.get(key)
                elif text_color_rules is None or text_color_rules.match_original_text_color:
                    orig_color = _sample_original_text_color(
                        chunk_tall, x1, y1, x2, y2, text_boxes, text_color_rules
                    )
                else:
                    orig_color = None
                text_color = _resolve_text_color(
                    bg, text_color_rules,
                    style.text_color if style else None, orig_color,
                )

            kw = dict(
                alignment=style.alignment if style else "center",
                stroke_color=style.stroke_color if style else None,
                stroke_width=style.stroke_width if style else None,
                size_factor=style.size_factor if style else 1.0,
                font_size_max=style.font_size_max if style else None,
                orientation=style.orientation if style else "horizontal",
                rotation=style.rotation if style else 0.0,
            )
            chunk_tall = draw_persian(
                chunk_tall, text, x1, y1, x2, y2,
                config, style.font_path if style else font_path,
                text_color=text_color, font_type=font_type,
                **kw,
            )
            rendered_count += 1

            if progress:
                progress.update(f"[{rendered_count}/{len(regions)}] {key}")

        # --- split chunk back to individual pages ---
        for page_idx_in_chunk, page_idx_global in enumerate(chunk_page_indices):
            y_start = chunk_page_offsets[page_idx_in_chunk]
            if page_idx_in_chunk + 1 < len(chunk_page_offsets):
                y_end = chunk_page_offsets[page_idx_in_chunk + 1]
            else:
                y_end = chunk_tall.height

            if y_end > y_start:
                output_images[page_idx_global] = chunk_tall.crop(
                    (0, y_start, chunk_tall.width, y_end)
                )

        # --- release chunk memory ---
        del chunk_tall
        # Invalidate any stale numpy cache entries.  The cache is keyed by
        # id(image) which may be reused by Python for new objects.
        _np_array_cache.clear()

    # Safety: fill any pages that were somehow missed (shouldn't happen)
    for i in range(num_pages):
        if output_images[i] is None:
            output_images[i] = normalized_pages[i].copy()

    # ── Phase: Draw chapter ID ─────────────────────────────────────────
    # Draw per-page, matching render_page_list behaviour.  Each page gets
    # the chapter ID in a corner that avoids that page's regions.
    if chapter_id and chapter_config:
        for i in range(num_pages):
            page_y_start = page_offsets[i]
            page_h = output_images[i].height

            page_occupied: list[tuple[int, int, int, int]] = []
            for _, x1, y1, x2, y2, *_ in regions:
                if y2 > page_y_start and y1 < page_y_start + page_h:
                    local_y1 = max(0, y1 - page_y_start)
                    local_y2 = min(page_h, y2 - page_y_start)
                    page_occupied.append((x1, local_y1, x2, local_y2))

            output_images[i] = draw_chapter_id(
                output_images[i], chapter_id, chapter_config, font_path,
                occupied_rects=page_occupied,
            )

    if progress:
        progress.finish_phase()

    stats["rendered_regions"] = rendered_count
    stats["chunk_size"] = effective_chunk_size
    stats["chunks"] = len(chunks)
    stats["elapsed"] = f"{time.time() - render_start:.1f}s"
    stats["render_time"] = time.time() - render_start

    if progress:
        progress.finish()

    return output_images, stats


def render_page_list(
    page_images: list[Image.Image],
    pages_map: dict[int, list[tuple[str, Any]]],
    translations: dict[str, str],
    config: FontConfig,
    chapter_id: str = "",
    chapter_config: ChapterIDConfig | None = None,
    font_path: str | None = None,
    use_batch_inpaint: bool = False,
    progress: RenderProgress | None = None,
    original_text_colors: dict[str, str] | None = None,
    text_color_rules: TextColorRules | None = None,
) -> tuple[list[Image.Image], dict]:
    """Render translations on a list of page images (per-page mode).

    Processes each page sequentially with detailed progress reporting.

    Args:
        page_images: List of per-page PIL Images.
        pages_map: Dict of page_number -> list of (key, Block) tuples.
        translations: Dict of key -> Persian translation text.
        config: Font configuration.
        chapter_id: Optional chapter ID to stamp.
        chapter_config: Chapter ID style config.
        font_path: Optional font path override.
        use_batch_inpaint: Whether inpainting was already done (skip erase).
        progress: Optional progress tracker.
        original_text_colors: Optional pre-sampled {key -> hex} original text
            colors (sampled BEFORE inpainting).  When ``None`` and the image
            still contains the original text, the color is sampled here.
        text_color_rules: Typography text-color rules; defaults to matching
            the original text color with a 3.0 contrast floor.

    Returns:
        (output_images, stats) where output_images is a list of rendered images.
    """
    stats: dict = {"total_pages": len(page_images), "total_regions": 0}
    render_start = time.time()

    total_regions = sum(
        len([k for k, b in pages_map.get(pn + 1, [])
             if not b.sfx and translations.get(k, "").strip()])
        for pn in range(len(page_images))
    )
    stats["total_regions"] = total_regions

    if progress:
        progress.start_phase("draw_text", total=total_regions)

    output_images: list[Image.Image] = []
    rendered_count = 0

    for pn_idx in range(len(page_images)):
        page_num = pn_idx + 1
        page_regions = pages_map.get(page_num, [])
        has_work = any(
            translations.get(k, "").strip() and not b.is_sfx
            for k, b in page_regions
        ) or (chapter_id and chapter_config)
        img = page_images[pn_idx].copy() if has_work else page_images[pn_idx]

        if progress:
            progress.update_page(
                pn_idx + 1, len(page_images),
                f"Page {pn_idx + 1}/{len(page_images)} "
                f"({rendered_count}/{total_regions} regions done)",
            )

        page_rects: list[tuple[int, int, int, int]] = []
        for key, blk in page_regions:
            fa = translations.get(key, "").strip()
            if not fa or blk.is_sfx:
                continue

            if use_batch_inpaint:
                interior = _sample_interior_color(img, blk.x1, blk.y1, blk.x2, blk.y2)
                bg_color = interior if interior else _sample_bg_color(img, blk.x1, blk.y1, blk.x2, blk.y2)
            else:
                bg_color = _sample_bg_color(img, blk.x1, blk.y1, blk.x2, blk.y2)

            style = resolve_style(
                blk.text_type, config,
                color_override=blk.color,
                stroke_color_override=blk.stroke_color,
                stroke_size_override=blk.stroke_size,
                alignment_override=blk.alignment,
                font_override=blk.font_override,
                font_size_override=blk.font_size_override,
            )
            if original_text_colors is not None:
                orig_color = original_text_colors.get(key)
            elif text_color_rules is None or text_color_rules.match_original_text_color:
                orig_color = _sample_original_text_color(
                    page_images[pn_idx], blk.x1, blk.y1, blk.x2, blk.y2,
                    blk.text_boxes, text_color_rules,
                )
            else:
                orig_color = None
            tc = _resolve_text_color(bg_color, text_color_rules, style.text_color, orig_color)
            img = draw_persian(
                img, fa, blk.x1, blk.y1, blk.x2, blk.y2,
                config, style.font_path, text_color=tc, font_type=blk.font_type,
                alignment=style.alignment, stroke_color=style.stroke_color,
                stroke_width=style.stroke_width, size_factor=style.size_factor,
                font_size_max=style.font_size_max,
                rotation=blk.rotation,
            )
            page_rects.append((blk.x1, blk.y1, blk.x2, blk.y2))
            rendered_count += 1

            if progress:
                progress.update(f"[{rendered_count}/{total_regions}] {key}")

        if chapter_id and chapter_config:
            img = draw_chapter_id(
                img, chapter_id, chapter_config, font_path,
                occupied_rects=page_rects,
            )

        output_images.append(img)

    if progress:
        progress.finish_phase()
        progress.finish()

    stats["rendered_regions"] = rendered_count
    stats["elapsed"] = f"{time.time() - render_start:.1f}s"
    stats["render_time"] = time.time() - render_start

    return output_images, stats


def draw_chapter_id(
    image: Image.Image,
    chapter_id: str,
    config: ChapterIDConfig,
    font_path: str | None = None,
    occupied_rects: list[tuple[int, int, int, int]] | None = None,
) -> Image.Image:
    """Draw chapter ID in a corner that doesn't overlap any occupied region.

    Tries corners in order: top-right, top-left, bottom-right, bottom-left.
    Falls back to top-right if all corners overlap.
    """
    draw = ImageDraw.Draw(image)
    if config.size > 0:
        fs = config.size
    else:
        fs = max(120, image.width // 12)
    font = _load_font(font_path, fs)

    text = str(chapter_id)
    tw = _text_width(text, font)

    # Get text height
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        th = max(bbox[3] - bbox[1], 1)
    except Exception:
        th = fs

    margin = image.width // 35
    padx = margin * 0.3
    pady = margin * 0.3

    rects = occupied_rects or []

    def _overlaps(ox: int, oy: int) -> bool:
        tx1, ty1 = ox - padx, oy - pady
        tx2, ty2 = ox + tw + padx, oy + th + pady
        for rx1, ry1, rx2, ry2 in rects:
            if not (tx2 < rx1 or tx1 > rx2 or ty2 < ry1 or ty1 > ry2):
                return True
        return False

    candidates = [
        ("top-right", image.width - tw - margin, margin),
        ("top-left", margin, margin),
        ("bottom-right", image.width - tw - margin, image.height - th - margin),
        ("bottom-left", margin, image.height - th - margin),
    ]

    x, y = candidates[0][1], candidates[0][2]
    for _, cx, cy in candidates:
        if not _overlaps(cx, cy):
            x, y = cx, cy
            break

    if config.stroke_width > 0:
        draw.text((x, y), text, fill=config.color, font=font,
                  stroke_width=config.stroke_width, stroke_fill=config.stroke_color)
    else:
        draw.text((x, y), text, fill=config.color, font=font)
    return image
