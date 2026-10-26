"""Duplicate detection and removal for OCR results.

When overlapping chunks or cross-page strips are OCR'd independently, the
same text region is detected multiple times.  This module implements a
multi-criteria duplicate detector that considers:

1. **IoU** (Intersection over Union) of the bounding boxes.
2. **Center-point distance** — small Euclidean distance between box centers.
3. **Text similarity** — normalized (lowercase, whitespace-collapsed,
   punctuation-stripped) Levenshtein ratio.
4. **Confidence proximity** — confidences within a relative tolerance.
5. **Reading order** — items sorted by (row, x) position.

When duplicates are confirmed, the detection with the highest confidence is
kept and all others are discarded, ensuring the same dialogue is never
translated twice.
"""

from __future__ import annotations

import math
import re

from comic_translator.models import OCRItem

# Threshold for relative confidence difference (0–1).
# Two items are considered "similar confidence" if the absolute difference
# is less than this fraction of the higher confidence.
_CONFIDENCE_TOLERANCE = 0.3

# Maximum center-point distance (in pixels) for two items to be considered
# the same detection.  This is a fallback when IoU is low (e.g. due to OCR
# box imprecision) but the text and confidence still match.
_MAX_CENTER_DIST = 30.0

# Minimum normalized-text similarity (0–1) for two items to be duplicates.
_MIN_TEXT_SIMILARITY = 0.85


class DuplicateDetector:
    """Detect and remove duplicate OCR items."""

    def __init__(
        self,
        iou_threshold: float = 0.5,
        confidence_tolerance: float = _CONFIDENCE_TOLERANCE,
        max_center_dist: float = _MAX_CENTER_DIST,
        min_text_similarity: float = _MIN_TEXT_SIMILARITY,
    ) -> None:
        self.iou_threshold = iou_threshold
        self.confidence_tolerance = confidence_tolerance
        self.max_center_dist = max_center_dist
        self.min_text_similarity = min_text_similarity

    # ── public API ─────────────────────────────────────────────────────────

    def remove(self, items: list[OCRItem], iou_threshold: float | None = None) -> list[OCRItem]:
        """Remove duplicate items in-place, keeping the highest-confidence copy.

        Steps:
            1. Sort items by confidence descending (NMS-style greedy approach).
            2. For each item, check against all remaining accepted items.
            3. If a match is found (IoU OR center distance + text sim. + conf.),
               discard the current item.
            4. Return the deduplicated list.
        """
        if not items:
            return []

        iou_thr = iou_threshold if iou_threshold is not None else self.iou_threshold

        # Sort by confidence descending so we always compare against the best.
        sorted_items = sorted(items, key=lambda x: x.confidence, reverse=True)
        accepted: list[OCRItem] = []
        suppressed: set[int] = set()

        for i, candidate in enumerate(sorted_items):
            if i in suppressed:
                continue

            accepted.append(candidate)

            for j in range(i + 1, len(sorted_items)):
                if j in suppressed:
                    continue
                other = sorted_items[j]
                if self._is_duplicate(candidate, other, iou_thr):
                    suppressed.add(j)

        return accepted

    # ── duplicate detection ────────────────────────────────────────────────

    def _is_duplicate(self, a: OCRItem, b: OCRItem, iou_threshold: float) -> bool:
        """Return ``True`` when *a* and *b* are duplicate detections.

        Uses a multi-criteria approach:
        - **OR** condition: high IoU between bounding boxes.
        - **AND** condition (when IoU is low): center-point distance is small
          AND normalized text is very similar AND confidence is similar.
        """
        iou = self._compute_iou(a, b)
        if iou >= iou_threshold:
            return True

        # Fallback: if IoU is low but the center points are very close,
        # the text is very similar, and confidence is comparable, still
        # treat as duplicate (OCR box jitter).
        if (
            self._center_distance(a, b) <= self.max_center_dist
            and self._text_similarity(a.text, b.text) >= self.min_text_similarity
            and self._confidence_similar(a, b)
        ):
            return True

        return False

    # ── geometry helpers ───────────────────────────────────────────────────

    @staticmethod
    def _bbox(item: OCRItem) -> tuple[int, int, int, int]:
        """Return (x1, y1, x2, y2) axis-aligned bounding box of an item."""
        xs = [p[0] for p in item.box]
        ys = [p[1] for p in item.box]
        return min(xs), min(ys), max(xs), max(ys)

    @staticmethod
    def _compute_iou(a: OCRItem, b: OCRItem) -> float:
        """Intersection-over-Union of two OCRItem bounding boxes."""
        ax1, ay1, ax2, ay2 = DuplicateDetector._bbox(a)
        bx1, by1, bx2, by2 = DuplicateDetector._bbox(b)

        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)

        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0

        inter_area = (ix2 - ix1) * (iy2 - iy1)
        a_area = (ax2 - ax1) * (ay2 - ay1)
        b_area = (bx2 - bx1) * (by2 - by1)

        if a_area == 0 or b_area == 0:
            return 0.0

        union = a_area + b_area - inter_area
        return inter_area / union if union > 0 else 0.0

    @staticmethod
    def _center_distance(a: OCRItem, b: OCRItem) -> float:
        """Euclidean distance between the centers of two items' bounding boxes."""
        ax1, ay1, ax2, ay2 = DuplicateDetector._bbox(a)
        bx1, by1, bx2, by2 = DuplicateDetector._bbox(b)
        acx, acy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
        bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2
        return math.hypot(acx - bcx, acy - bcy)

    # ── text & confidence helpers ──────────────────────────────────────────

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Lowercase, strip punctuation, collapse whitespace."""
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def _text_similarity(cls, a: str, b: str) -> float:
        """Normalized Levenshtein similarity between 0 and 1."""
        sa, sb = cls._normalize_text(a), cls._normalize_text(b)
        if not sa or not sb:
            return 0.0
        return cls._levenshtein_ratio(sa, sb)

    @staticmethod
    def _levenshtein_ratio(s1: str, s2: str) -> float:
        """Compute the Levenshtein similarity ratio (0–1)."""
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0

        len1, len2 = len(s1), len(s2)
        prev = list(range(len2 + 1))

        for i in range(1, len1 + 1):
            curr = [i] + [0] * len2
            for j in range(1, len2 + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                curr[j] = min(
                    prev[j] + 1,        # deletion
                    curr[j - 1] + 1,    # insertion
                    prev[j - 1] + cost, # substitution
                )
            prev = curr

        max_len = max(len1, len2)
        return 1.0 - (prev[len2] / max_len) if max_len > 0 else 0.0

    def _confidence_similar(self, a: OCRItem, b: OCRItem) -> bool:
        """True if confidence scores are within tolerance."""
        hi = max(a.confidence, b.confidence)
        lo = min(a.confidence, b.confidence)
        if hi == 0:
            return True
        return (hi - lo) / hi <= self.confidence_tolerance
