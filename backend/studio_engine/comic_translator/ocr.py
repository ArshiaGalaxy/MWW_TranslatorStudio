"""OCR engine — PaddleOCR 3.7 + PP-OCRv6, English-only.

Simplified per user request:
- PaddleOCR 3.7 / PP-OCRv6 only, lang="en"
- No auto-SFX detection (manual via text_type only)
- No vertical recovery / no letter grouping — PP-OCRv6 handles vertical natively
- Single factory _get_ocr, single predict path via ocr.predict()

All legacy vertical helpers and duplicated clustering have been removed.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
import numpy as np
from PIL import Image
from sklearn.cluster import DBSCAN

from comic_translator.config import OCRConfig
from comic_translator.exceptions import OCRError
from comic_translator.models import OCRDialog, OCRItem

logger = logging.getLogger(__name__)


_ocr_cache: dict = {}


def _ocr_cache_key(config: OCRConfig) -> tuple:
    return (
        getattr(config, "ocr_version", "PP-OCRv6"),
        config.ocr_enable_angle_cls,
        config.ocr_det_limit_side_len,
        config.ocr_det_unclip_ratio,
        config.ocr_det_box_thresh,
        config.ocr_det_thresh,
    )


def to_legacy_format(result) -> list:
    """Change the result of PaddleOCR 3.x to format [(box, (text, score)), ...]."""
    lines = []
    if not result:
        return lines
    for line in result:
        if not isinstance(line, dict):
            continue
        polys = line.get("rec_polys") or []
        texts = line.get("rec_texts") or []
        scores = line.get("rec_scores") or []
        for poly, text, score in zip(polys, texts, scores):
            box = [[float(pt[0]), float(pt[1])] for pt in poly]
            lines.append([box, (str(text), float(score))])
    return lines


def _get_ocr(config: OCRConfig | None = None):
    """Return a (cached) PaddleOCR 3.7 instance configured from *config*.

    When *config* is None a default English PP-OCRv6 instance is returned
    (cached under key "default").
    """
    if config is None:
        key = "default"
        cached = _ocr_cache.get(key)
        if cached is not None:
            return cached
        try:
            from paddleocr import PaddleOCR

            logger.info("Loading PaddleOCR 3.7 (default, lang=en, PP-OCRv6)...")
            ocr = PaddleOCR(
                lang="en",
                device="cpu",
                ocr_version="PP-OCRv6",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_det_limit_side_len=1920,
                text_det_limit_type="max",
                text_det_box_thresh=0.3,
                text_det_thresh=0.2,
                text_det_unclip_ratio=2.0,
                text_rec_score_thresh=0.3,
                precision="fp16",
            )
            _ocr_cache[key] = ocr
            return ocr
        except ImportError as e:
            raise OCRError(
                "PaddleOCR not installed. Run: pip install paddleocr>=3.7 paddlepaddle>=3.0"
            ) from e

    key = _ocr_cache_key(config)
    cached = _ocr_cache.get(key)
    if cached is not None:
        return cached

    try:
        from paddleocr import PaddleOCR

        ocr_version = getattr(config, "ocr_version", "PP-OCRv6")
        logger.info(
            "Loading PaddleOCR 3.7 (%s, det_limit_side_len=%s, unclip=%s, angle_cls=%s, box_thresh=%s, det_thresh=%s)",
            ocr_version,
            config.ocr_det_limit_side_len,
            config.ocr_det_unclip_ratio,
            config.ocr_enable_angle_cls,
            config.ocr_det_box_thresh,
            config.ocr_det_thresh,
        )
        ocr = PaddleOCR(
            lang="en",
            device="cpu",
            ocr_version=ocr_version,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=bool(config.ocr_enable_angle_cls),
            text_det_limit_side_len=int(config.ocr_det_limit_side_len),
            text_det_limit_type="max",
            text_det_box_thresh=float(config.ocr_det_box_thresh),
            text_det_thresh=float(config.ocr_det_thresh),
            text_det_unclip_ratio=float(config.ocr_det_unclip_ratio),
            text_rec_score_thresh=float(config.text_rec_score_thresh),
            precision="fp16",
        )
        _ocr_cache[key] = ocr
        return ocr
    except ImportError as e:
        raise OCRError(
            "PaddleOCR not installed. Run: pip install paddleocr>=3.7 paddlepaddle>=3.0"
        ) from e


def _ocr_single_image(ocr, img: Image.Image, config: OCRConfig, pages_dir: str | None = None) -> list[OCRItem]:
    """Run OCR on a PIL Image with light preprocessing for better recall."""
    w, h = img.size
    max_side = getattr(config, "ocr_max_side", 3000)
    scale = 1.0

    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)

    try:
        from PIL import ImageEnhance

        img = ImageEnhance.Contrast(img).enhance(1.3)
    except Exception:
        pass

    if pages_dir:
        import random

        tmp_path = str(Path(pages_dir) / f"_ocr_tmp_{random.randint(10000, 99999)}.jpg")
        img.save(tmp_path, "JPEG", quality=95)
    else:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
            img.save(tmp_path, "JPEG", quality=95)

    try:
        result = ocr.predict(tmp_path)
        result = to_legacy_format(result)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not result:
        return []

    inv_scale = 1.0 / scale if scale != 1.0 else 1.0
    items: list[OCRItem] = []

    for line in result:
        if line is None:
            continue
        try:
            box, (text, score) = line
        except (ValueError, TypeError):
            continue

        if score < config.confidence_min or not text.strip():
            continue

        if scale != 1.0:
            box = [[int(p[0] * inv_scale), int(p[1] * inv_scale)] for p in box]

        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x1, y1 = min(xs), min(ys)
        x2, y2 = max(xs), max(ys)
        bh = max(y2 - y1, 1)
        # PP-OCRv6 handles vertical natively; keep orientation horizontal
        # and let box angle be preserved via DBSCAN merging only.
        # Detect vertical purely from aspect for rendering hint if needed.
        orientation = "horizontal"

        items.append(
            OCRItem(
                text=text.strip(),
                box=box,
                cx=(x1 + x2) / 2,
                cy=(y1 + y2) / 2,
                height=bh,
                confidence=float(score),
                orientation=orientation,
            )
        )

    return items


def _box_angle(box: list) -> float:
    """Compute the orientation angle (in degrees) of a text line from its quadrilateral box."""
    dx = box[1][0] - box[0][0]
    dy = box[1][1] - box[0][1]
    return math.degrees(math.atan2(dy, dx))


def _dialog_median_angle(dialog: OCRDialog) -> float:
    """Compute the median text orientation angle for a dialog (in degrees)."""
    angles = [_box_angle(box) for box in dialog.text_boxes]
    return float(np.median(angles)) if angles else 0.0


def _angle_diff(a: float, b: float) -> float:
    """Smallest angular difference between two angles (handles 180° wrap)."""
    diff = abs(a - b) % 180.0
    return min(diff, 180.0 - diff)


def _dialog_median_height(dialog: OCRDialog) -> float:
    """Estimate the median text-line height from a dialog's text boxes."""
    heights = []
    for box in dialog.text_boxes:
        ys = [p[1] for p in box]
        heights.append(max(ys) - min(ys))
    return float(np.median(heights)) if heights else 0.0


def _merge_nearby_dialogs(
    dialogs: list[OCRDialog],
    median_h: float = 0.0,
    angle_threshold: float = 10.0,
) -> list[OCRDialog]:
    """Merge adjacent dialog clusters that are likely part of the same bubble.

    Conservative rules — all must pass. SFX is never merged (but sfx is
    always False now; kept as guard).
    """
    if len(dialogs) <= 1:
        return dialogs

    max_y_gap = max(20, median_h) if median_h > 0 else 20

    merged: list[OCRDialog] = []
    used = [False] * len(dialogs)

    for i, d in enumerate(dialogs):
        if used[i]:
            continue
        if d.sfx:
            merged.append(d)
            used[i] = True
            continue

        best = None
        best_idx = -1
        for j, other in enumerate(dialogs):
            if i == j or used[j] or other.sfx:
                continue

            x_overlap = not (d.x2 < other.x1 or other.x2 < d.x1)
            if not x_overlap:
                continue
            overlap_w = min(d.x2, other.x2) - max(d.x1, other.x1)
            narrower_w = min(d.x2 - d.x1, other.x2 - other.x1)
            if narrower_w > 0 and overlap_w / narrower_w < 0.3:
                continue

            y_gap = min(abs(d.y2 - other.y1), abs(other.y2 - d.y1))
            if y_gap > max_y_gap:
                continue

            d_cx = (d.x1 + d.x2) / 2
            d_cy = (d.y1 + d.y2) / 2
            o_cx = (other.x1 + other.x2) / 2
            o_cy = (other.y1 + other.y2) / 2
            center_dist = math.hypot(d_cx - o_cx, d_cy - o_cy)
            max_center_dist = max(50, 3 * median_h)
            if center_dist > max_center_dist:
                continue

            d_h = _dialog_median_height(d)
            o_h = _dialog_median_height(other)
            if d_h > 0 and o_h > 0:
                height_ratio = min(d_h, o_h) / max(d_h, o_h)
                if height_ratio < 0.85:
                    continue

            if angle_threshold > 0 and d_h > 0 and o_h > 0:
                d_angle = _dialog_median_angle(d)
                o_angle = _dialog_median_angle(other)
                if _angle_diff(d_angle, o_angle) > angle_threshold:
                    continue

            d_stripped = d.text.strip()
            if d_stripped and d_stripped[-1] not in ".!?":
                best = other
                best_idx = j
                break

        if best is not None:
            combined_text = d.text.rstrip() + "\n" + best.text.lstrip()
            new_x1 = min(d.x1, best.x1)
            new_y1 = min(d.y1, best.y1)
            new_x2 = max(d.x2, best.x2)
            new_y2 = max(d.y2, best.y2)
            new_text_boxes = d.text_boxes + best.text_boxes
            merged.append(
                OCRDialog(
                    text=combined_text,
                    x1=new_x1,
                    y1=new_y1,
                    x2=new_x2,
                    y2=new_y2,
                    sfx=False,
                    text_boxes=new_text_boxes,
                    orientation=d.orientation if d.orientation == best.orientation else "horizontal",
                )
            )
            used[i] = True
            used[best_idx] = True
        else:
            if not used[i]:
                merged.append(d)
                used[i] = True

    return merged


def _cluster_items(items: list[OCRItem], config: OCRConfig) -> list[OCRDialog]:
    """DBSCAN cluster raw OCR items into dialog groups."""
    if not items:
        return []

    median_h = np.median([it.height for it in items])
    points = np.array([[it.cx / median_h, it.cy / median_h] for it in items])
    labels = DBSCAN(eps=config.dbscan_eps, min_samples=1).fit_predict(points)

    groups: dict[int, list[OCRItem]] = {}
    for label, item in zip(labels, items):
        groups.setdefault(int(label), []).append(item)

    dialogs: list[OCRDialog] = []
    for group in groups.values():
        group.sort(key=lambda x: x.cy)
        x1 = int(min(min(p[0] for p in g.box) for g in group))
        y1 = int(min(min(p[1] for p in g.box) for g in group))
        x2 = int(max(max(p[0] for p in g.box) for g in group))
        y2 = int(max(max(p[1] for p in g.box) for g in group))
        # Orientation from PP-OCRv6 is horizontal; keep simple.
        text = "\n".join(g.text for g in group)
        text_boxes = [[(int(p[0]), int(p[1])) for p in g.box] for g in group]
        dialogs.append(
            OCRDialog(
                text=text,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                sfx=False,
                text_boxes=text_boxes,
                orientation="horizontal",
            )
        )

    dialogs.sort(key=lambda d: (d.y1 // 150, d.x1))

    merged = _merge_nearby_dialogs(
        dialogs,
        float(median_h),
        getattr(config, "angle_merge_threshold", 10.0),
    )

    return merged


# ── Backward-compatible wrappers (deprecated) ────────────────────────────────


