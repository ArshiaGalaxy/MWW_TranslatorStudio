"""Shared utilities for all inpainting backends.

Three-mask architecture:
  1. CORE MASK:      Binary mask covering ONLY detected text pixels.
                     Uses OCR polygons when available, bbox as fallback.
  2. INFERENCE MASK: Binary mask derived from core via controlled dilation.
                     Covers anti-aliasing and gives model repair context.
  3. BLEND MASK:     Used ONLY for final compositing.
                     Minimal 1-2px feathering allowed. Never passed to model.

Key invariant: Neural models receive BINARY masks. Feathering is ONLY for
the final composite step and is kept to 1-2px to avoid halo.

Coordinate systems:
  - ORIGINAL SPACE: Full page image coordinates
  - ROI SPACE:      Cropped region around text (after crop_region)
  - SCALED SPACE:   After downscale_if_needed (model input size)
  - PADDED SPACE:   After snap_to_8 padding (model input dimensions)

Every function must know which coordinate system it operates in.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)


# ── Memory management ────────────────────────────────────────────────────────


# ── Geometry helpers ──────────────────────────────────────────────────────────


# ── Snap-to-8 padding (from manga-cleaner reference) ─────────────────────────


# ── Format conversion ─────────────────────────────────────────────────────────


def pil_to_cv2(img: Image.Image) -> np.ndarray:
    arr = np.array(img)
    if arr.ndim == 3 and arr.shape[2] == 3:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return arr


def cv2_to_pil(arr: np.ndarray) -> Image.Image:
    if arr.ndim == 3 and arr.shape[2] == 3:
        return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))
    return Image.fromarray(arr)


# ── Mask building ─────────────────────────────────────────────────────────────


def dilate_polygon(
    pts: list[tuple[int, int]], pad_x: int, pad_y: int, w: int, h: int,
) -> list[tuple[int, int]]:
    """Expand polygon vertices outward from centroid by pad_x/pad_y pixels."""
    if not pts or (pad_x == 0 and pad_y == 0):
        return list(pts)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    result = []
    for px, py in pts:
        dx, dy = px - cx, py - cy
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < 1e-6:
            result.append((max(0, min(w, px + pad_x)), max(0, min(h, py + pad_y))))
        else:
            result.append((
                max(0, min(w, round(px + pad_x * dx / dist))),
                max(0, min(h, round(py + pad_y * dy / dist))),
            ))
    return result


def feather_mask(mask: Image.Image, radius: int = 2) -> Image.Image:
    """Apply minimal Gaussian blur for BLEND masks ONLY.

    Never use this for inference masks.
    Radius should be 1-2px maximum.
    """
    if radius <= 0:
        return mask
    return mask.filter(ImageFilter.GaussianBlur(radius=radius))


def binary_mask(mask: Image.Image) -> Image.Image:
    """Threshold a mask to binary (0 or 255)."""
    return mask.point(lambda x: 255 if x > 128 else 0)


def _normalize_text_boxes(text_boxes: list | None) -> list[list[tuple[int, int]]]:
    """Normalize text_boxes to a flat list of polygon point lists."""
    if not text_boxes:
        return []
    result = []
    for box in text_boxes:
        while isinstance(box, list) and len(box) == 1 and isinstance(box[0], list):
            box = box[0]
        if isinstance(box, list) and len(box) > 0:
            first = box[0]
            if isinstance(first, (list, tuple)) and len(first) >= 2:
                result.append([(int(p[0]), int(p[1])) for p in box])
    return result


# ── Three-mask architecture ──────────────────────────────────────────────────


def dilate_mask(
    mask: Image.Image,
    core_px: int = 3,
    context_px: int = 8,
    image_width: int = 0,
) -> Image.Image:
    """Apply true dilation to expand mask for model context.

    Uses cv2.dilate with elliptical kernel for natural expansion.
    Scales dilation proportionally for large images (>=2000px wide).
    """
    mask_np = np.array(mask)
    if mask_np.ndim == 3:
        mask_np = mask_np[:, :, 0]

    total_px = core_px + context_px
    if total_px <= 0:
        return mask

    if image_width >= 2000:
        scale = 1.0 + (image_width - 2000) / 3000
        total_px = max(total_px, int(total_px * min(scale, 1.5)))

    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (total_px * 2 + 1, total_px * 2 + 1),
    )
    dilated = cv2.dilate(mask_np, kernel, iterations=1)
    return Image.fromarray(dilated, mode="L")


# ── Combined masks (batch processing) ────────────────────────────────────────


def build_combined_core_mask(
    image_size: tuple[int, int],
    regions: list[dict],
) -> Image.Image:
    """Build combined core mask for batch processing."""
    w, h = image_size
    mask = Image.new("L", image_size, 0)
    draw = ImageDraw.Draw(mask)

    for region in regions:
        rx1, ry1 = region["x1"], region["y1"]
        rx2, ry2 = region["x2"], region["y2"]
        # Sanitize: ensure x1 <= x2, y1 <= y2
        if rx1 > rx2:
            rx1, rx2 = rx2, rx1
        if ry1 > ry2:
            ry1, ry2 = ry2, ry1
        text_boxes = region.get("text_boxes", [])
        normalized = _normalize_text_boxes(text_boxes) if text_boxes else []

        if normalized:
            for pts in normalized:
                draw.polygon(pts, fill=255)
        else:
            draw.rectangle(
                [max(0, rx1), max(0, ry1), min(w, rx2), min(h, ry2)],
                fill=255,
            )
    return mask


def build_combined_inference_mask(
    image_size: tuple[int, int],
    regions: list[dict],
    core_px: int = 3,
    context_px: int = 8,
) -> Image.Image:
    """Build combined binary inference mask for batch processing."""
    core = build_combined_core_mask(image_size, regions)
    dilated = dilate_mask(core, core_px=core_px, context_px=context_px,
                          image_width=image_size[0])
    return binary_mask(dilated)


# ── Legacy mask builders (backward compatible) ────────────────────────────────


def build_mask_pil(
    image_size: tuple[int, int],
    x1: int, y1: int, x2: int, y2: int,
    text_boxes: list | None = None,
    pad_x: int = 6,
    pad_y: int = 6,
    feather: bool = False,
) -> Image.Image:
    """Legacy mask builder for ONNX/OpenCV backends.

    Uses polygons when available, padded bbox as fallback.
    """
    w, h = image_size
    mask = Image.new("L", image_size, 0)
    draw = ImageDraw.Draw(mask)
    normalized = _normalize_text_boxes(text_boxes) if text_boxes else []
    if normalized:
        for pts in normalized:
            draw.polygon(dilate_polygon(pts, pad_x, pad_y, w, h), fill=255)
    else:
        # Sanitize coordinates to prevent numpy "Coordinate lower < upper" errors
        sx1, sy1, sx2, sy2 = (max(0, x1), max(0, y1), min(w, x2), min(h, y2))
        if sx1 > sx2:
            sx1, sx2 = sx2, sx1
        if sy1 > sy2:
            sy1, sy2 = sy2, sy1
        rx1, ry1 = max(0, sx1 - pad_x), max(0, sy1 - pad_y)
        rx2, ry2 = min(w, sx2 + pad_x), min(h, sy2 + pad_y)
        draw.rectangle([rx1, ry1, rx2, ry2], fill=255)
    if feather:
        mask = feather_mask(mask)
    return mask


def build_combined_mask(
    image_size: tuple[int, int],
    regions: list[dict],
    pad_x: int = 6,
    pad_y: int = 6,
    ox: int = 0,
    oy: int = 0,
    scale: float = 1.0,
    feather: bool = False,
) -> Image.Image:
    """Legacy combined mask builder for ONNX/OpenCV backends."""
    mw, mh = image_size
    mask = Image.new("L", image_size, 0)
    draw = ImageDraw.Draw(mask)
    for region in regions:
        rx1 = round((region["x1"] - ox) * scale)
        ry1 = round((region["y1"] - oy) * scale)
        rx2 = round((region["x2"] - ox) * scale)
        ry2 = round((region["y2"] - oy) * scale)
        # Sanitize: ensure x1 <= x2, y1 <= y2 (inverted coords cause numpy errors)
        if rx1 > rx2:
            rx1, rx2 = rx2, rx1
        if ry1 > ry2:
            ry1, ry2 = ry2, ry1
        text_boxes = region.get("text_boxes", [])
        normalized = _normalize_text_boxes(text_boxes) if text_boxes else []
        if normalized:
            for pts in normalized:
                scaled_pts = [
                    (max(0, min(mw, round((px - ox) * scale))),
                     max(0, min(mh, round((py - oy) * scale))))
                    for px, py in pts
                ]
                draw.polygon(dilate_polygon(scaled_pts, pad_x, pad_y, mw, mh), fill=255)
        else:
            r1 = max(0, rx1 - pad_x)
            r2 = max(0, ry1 - pad_y)
            r3 = min(mw, rx2 + pad_x)
            r4 = min(mh, ry2 + pad_y)
            draw.rectangle([r1, r2, r3, r4], fill=255)
    if feather:
        mask = feather_mask(mask)
    return mask


def build_iopoint_combined_mask(
    image_size: tuple[int, int],
    regions: list[dict],
    pad_x: int = 10,
    pad_y: int = 10,
) -> Image.Image:
    """Build combined inference mask for batch processing. Returns BINARY mask."""
    core = min(pad_x, pad_y) // 2
    context = max(pad_x, pad_y)
    return build_combined_inference_mask(
        image_size, regions,
        core_px=core, context_px=context,
    )


# ── Mask refinement ───────────────────────────────────────────────────────────


# ── Connected components ──────────────────────────────────────────────────────


def find_connected_components(
    mask: Image.Image,
    min_area: int = 100,
) -> list[tuple[int, int, int, int]]:
    """Find connected components in a binary mask.

    Returns list of (x1, y1, x2, y2) bounding boxes.
    """
    mask_np = np.array(mask)
    if mask_np.ndim == 3:
        mask_np = mask_np[:, :, 0]
    binary = (mask_np > 0).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=8,
    )
    components = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < min_area:
            continue
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        components.append((x, y, x + w, y + h))
    return components


# ── Blob-centered tiling (from manga-cleaner reference) ──────────────────────


# ── Quality evaluation ────────────────────────────────────────────────────────


# ── Edge blending ─────────────────────────────────────────────────────────────


def cv2_edge_blend(
    mask_np: np.ndarray, result: np.ndarray, original: np.ndarray,
) -> np.ndarray:
    """Blend inpainted result with original using feathered mask.

    Uses the full mask (not just edge) so the interior is fully inpainted.
    Feathers the outer boundary with Gaussian blur for smooth transitions.
    Formula: original * (1 - feathered) + result * feathered
    """
    if original.ndim == 3 and original.shape[2] == 4:
        original = cv2.cvtColor(original, cv2.COLOR_BGRA2BGR)
    if result.ndim == 3 and result.shape[2] == 4:
        result = cv2.cvtColor(result, cv2.COLOR_BGRA2BGR)

    feathered = cv2.GaussianBlur(mask_np.astype(np.float32), (5, 5), 0) / 255.0
    feathered_3ch = feathered[..., None] if feathered.ndim == 2 else feathered
    return (original.astype(np.float32) * (1.0 - feathered_3ch) +
            result.astype(np.float32) * feathered_3ch).astype(np.uint8)


# ── Region clustering ─────────────────────────────────────────────────────────


# ── Background complexity analysis ────────────────────────────────────────────


# ── Smart triage ──────────────────────────────────────────────────────────────


# ── ONNX helpers ──────────────────────────────────────────────────────────────


