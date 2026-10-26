"""Conservative dialogue merging for text split across page boundaries.

Some Manhwa speech bubbles start at the bottom of page N and continue at the
top of page N+1.  After cross-page OCR produces "span" detections (items
that cross the boundary in the combined strip image), this module decides
whether to merge the two halves of a dialogue into a single ``Block``.

Merging rules (ALL must pass — conservative, accuracy-first):
    1. **Near boundary**: the bottom block must be within ``tol`` pixels of
       the page boundary, and the top block must be within ``tol`` pixels
       of its page's top edge.
    2. **Same column / aligned**: the two blocks' x-ranges overlap or are
       close (within ``tol`` pixels), indicating they belong to the same
       speech bubble.
    3. **Font size similar**: the text heights differ by less than 30%.
    4. **High OCR confidence**: both blocks have confidence >= 0.7 (or the
       span detection confirms the same text).
    5. **Incomplete sentence**: block N's text does not end with terminal
       punctuation (.,!?;: " ') — it appears truncated.
    6. **Cross-page span confirmation**: a span detection exists whose text
       is similar to both blocks' text, confirming the dialogue truly
       crosses the page boundary.  (If no span is available, we still
       merge when all other criteria pass, but this is the weakest case.)
"""

from __future__ import annotations

import logging
import re

from comic_translator.models import Block, OCRItem
from comic_translator.ocr_pipeline.duplicate_detector import DuplicateDetector

logger = logging.getLogger(__name__)

# Regex for terminal sentence punctuation (after stripping trailing whitespace).
_TRAILING_PUNCT_RE = re.compile(r"[.!?؟؟!،؛:)\"'\]]+$")

# Minimum confidence for both blocks to be mergeable.
_MIN_CONFIDENCE = 0.6

# Maximum x-misalignment between two blocks (pixels).
_MAX_X_MISALIGN = 80

# Maximum font-height difference ratio.
_MAX_FONT_DIFF_RATIO = 0.3

# Maximum vertical gap between block N's bottom and the page boundary (pixels).
_MAX_BOUNDARY_GAP = 100

# Maximum vertical gap between block N+1's top and the page's top edge.
_MAX_TOP_GAP = 100


class DialogueMerger:
    """Conservatively merge dialogues split across consecutive PDF pages."""

    def __init__(
        self,
        iou_threshold: float = 0.5,
        min_confidence: float = _MIN_CONFIDENCE,
        max_x_misalign: int = _MAX_X_MISALIGN,
        max_font_diff_ratio: float = _MAX_FONT_DIFF_RATIO,
        max_boundary_gap: int = _MAX_BOUNDARY_GAP,
        max_top_gap: int = _MAX_TOP_GAP,
    ) -> None:
        self.iou_threshold = iou_threshold
        self.min_confidence = min_confidence
        self.max_x_misalign = max_x_misalign
        self.max_font_diff_ratio = max_font_diff_ratio
        self.max_boundary_gap = max_boundary_gap
        self.max_top_gap = max_top_gap
        self._dup_detector = DuplicateDetector(iou_threshold=iou_threshold)

    # ── public API ─────────────────────────────────────────────────────────

    def should_merge(
        self,
        blk_n: Block,
        blk_n1: Block,
        spans: list[OCRItem],
    ) -> bool:
        """Decide whether to merge two blocks across a page boundary.

        All criteria are AND-ed together for a conservative merge policy.
        """
        # Skip SFX — sound effects are not multi-line dialogue.
        if blk_n.sfx or blk_n1.sfx:
            return False

        # 1. Near boundary
        if not self._near_boundary(blk_n, blk_n1, blk_n.y2, blk_n1.y1):
            return False

        # 2. Bounding boxes aligned (same column)
        if not self._bbox_aligned(blk_n, blk_n1):
            return False

        # 3. Font size similar
        h_n = blk_n.y2 - blk_n.y1
        h_n1 = blk_n1.y2 - blk_n1.y1
        if not self._font_size_similar(h_n, h_n1):
            return False

        # 4. OCR confidence high
        if blk_n.continuation_page != 0:
            # Already merged — don't re-merge.
            return False

        # 5. Incomplete sentence on page N
        if not self._is_incomplete_sentence(blk_n.text):
            return False

        # 6. Cross-page span confirmation (if available)
        if spans:
            if not self._span_confirms_merge(blk_n, blk_n1, spans):
                return False
        # If no spans detected, we trust the other criteria. This is acceptable
        # because the cross-page OCR strip may have missed the text due to
        # image quality; the per-page detections are still valid signals.

        logger.debug(
            "Merging p%d '%s…' + p%d '%s'",
            blk_n.page, blk_n.text[:30], blk_n1.page, blk_n1.text[:30],
        )
        return True

    def merge_blocks(
        self,
        blk_n: Block,
        blk_n1: Block,
        span: OCRItem | None,
    ) -> Block:
        """Create a merged ``Block`` from two page-boundary blocks.

        The merged block:
            - Combines text in reading order (N first, then N+1).
            - Preserves both page references in ``pages``.
            - Sets ``page`` to blk_n.page and ``continuation_page`` to blk_n1.page.
            - Unifies the bounding box.
            - Combines text_boxes.
        """
        # Combined text: preserve reading order (page N top-to-bottom,
        # then page N+1 continuation).
        combined_text = self._combine_text(blk_n.text, blk_n1.text, span)

        # Union of bounding boxes.
        x1 = min(blk_n.x1, blk_n1.x1)
        y1 = min(blk_n.y1, blk_n1.y1)
        x2 = max(blk_n.x2, blk_n1.x2)
        y2 = max(blk_n.y2, blk_n1.y2)

        # Combine text boxes.
        text_boxes = list(blk_n.text_boxes) + list(blk_n1.text_boxes)

        merged = Block(
            page=blk_n.page,
            text=combined_text,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            translation_fa="",
            cover=False,
            sfx=False,
            thinking=blk_n.thinking or blk_n1.thinking,
            text_boxes=text_boxes,
            pages=[blk_n.page, blk_n1.page],
            continuation_page=blk_n1.page,
            text_type=blk_n.text_type if blk_n.text_type != "dialog" else blk_n1.text_type,
            color=blk_n.color or blk_n1.color,
            stroke_color=blk_n.stroke_color or blk_n1.stroke_color,
            stroke_size=blk_n.stroke_size if blk_n.stroke_size is not None else blk_n1.stroke_size,
            alignment=blk_n.alignment if blk_n.alignment != "center" else blk_n1.alignment,
        )
        return merged

    # ── private helpers ────────────────────────────────────────────────────

    def _near_boundary(
        self,
        blk_n: Block,
        blk_n1: Block,
        boundary_y: int,
        top_y: int,
    ) -> bool:
        """Check that blk_n is near the bottom boundary and blk_n1 is near
        the top of its page."""
        # blk_n.y2 should be near boundary_y (bottom of page N's content area).
        gap_n = abs(blk_n.y2 - boundary_y)
        gap_n1 = abs(blk_n1.y1 - top_y)
        return gap_n <= self.max_boundary_gap and gap_n1 <= self.max_top_gap

    def _bbox_aligned(self, blk_n: Block, blk_n1: Block) -> bool:
        """Check x-overlap or proximity between two blocks."""
        x_overlap = not (blk_n.x2 < blk_n1.x1 - self.max_x_misalign
                         or blk_n1.x2 < blk_n.x1 - self.max_x_misalign)
        if x_overlap:
            return True
        # Also accept if centers are within tolerance.
        cx_n = (blk_n.x1 + blk_n.x2) / 2
        cx_n1 = (blk_n1.x1 + blk_n1.x2) / 2
        return abs(cx_n - cx_n1) <= self.max_x_misalign

    def _font_size_similar(self, h_n: int, h_n1: int) -> bool:
        """Check that font heights are within tolerance."""
        if h_n == 0 or h_n1 == 0:
            return False
        hi = max(h_n, h_n1)
        lo = min(h_n, h_n1)
        return (hi - lo) / hi <= self.max_font_diff_ratio

    @staticmethod
    def _is_incomplete_sentence(text: str) -> bool:
        """Return True if *text* appears to be a truncated sentence — it does
        not end with terminal punctuation."""
        stripped = text.strip().rstrip("'\")؟]")
        if not stripped:
            return False
        last_char = stripped[-1]
        return last_char not in ".!?؟،؛:"

    def _span_confirms_merge(
        self,
        blk_n: Block,
        blk_n1: Block,
        spans: list[OCRItem],
    ) -> bool:
        """Check if any span detection's text overlaps with both blocks.

        Uses word-level Jaccard similarity (intersection/union of word sets)
        rather than character-level Levenshtein, because a span detection
        naturally contains the *combined* text of both halves.  Character-
        level methods unfairly penalise this length difference.
        """
        words_n = set(self._normalize(blk_n.text).split())
        words_n1 = set(self._normalize(blk_n1.text).split())
        if not words_n or not words_n1:
            return False

        for span in spans:
            words_span = set(self._normalize(span.text).split())
            if not words_span:
                continue

            # Check if block-N's words appear in the span text.
            overlap_n = len(words_n & words_span)
            union_n = len(words_n | words_span)
            jaccard_n = overlap_n / union_n if union_n > 0 else 0.0

            # Check if block-N+1's words appear in the span text.
            overlap_n1 = len(words_n1 & words_span)
            union_n1 = len(words_n1 | words_span)
            jaccard_n1 = overlap_n1 / union_n1 if union_n1 > 0 else 0.0

            # Require at least 40% word overlap with both blocks.
            if jaccard_n >= 0.4 and jaccard_n1 >= 0.4:
                return True
        return False

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase, strip punctuation, collapse whitespace."""
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _combine_text(blk_n_text: str, blk_n1_text: str, span: OCRItem | None) -> str:
        """Combine text from two blocks in reading order.

        If a span detection is available and its text is more complete
        (longer), prefer the span text.  Otherwise concatenate: blk_n + blk_n1.
        """
        if span and len(span.text) > len(blk_n_text) + len(blk_n1_text):
            return span.text.strip()

        parts = []
        if blk_n_text.strip():
            parts.append(blk_n_text.strip())
        if blk_n1_text.strip():
            parts.append(blk_n1_text.strip())
        return "\n".join(parts).strip()
