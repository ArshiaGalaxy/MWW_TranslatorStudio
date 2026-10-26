"""Coordinate restoration utilities.

Provides a single ``CoordinateRestorer`` class that is responsible for
converting OCR detections from any local coordinate space back to the
original page coordinate space.

Two use-cases:
1. **Chunk restoration**: After OCR on a cropped chunk, add the chunk's
   vertical offset to all box coordinates.
2. **Cross-page restoration**: After OCR on a concatenated strip (bottom of
   page N + top of page N+1), classify each detection as belonging to page N,
   page N+1, or spanning the boundary, and map coordinates back accordingly.
"""

from __future__ import annotations

from comic_translator.models import OCRItem


class CoordinateRestorer:
    """Restore OCR coordinates to original page coordinate space."""

    # ── chunk restoration ──────────────────────────────────────────────────

    @staticmethod
    def restore_chunk_items(items: list[OCRItem], y_offset: int) -> None:
        """Shift each item's coordinates by *y_offset* (in-place).

        Used when OCR was run on a cropped chunk; the y_offset is the
        chunk's top edge within the full page.
        """
        if y_offset == 0:
            return
        for it in items:
            CoordinateRestorer._shift_item(it, y_offset)

    @staticmethod
    def _shift_item(item: OCRItem, delta: int) -> None:
        """In-place integer vertical shift of a single OCRItem."""
        if delta == 0:
            return
        item.cy += delta
        item.box = [[p[0], p[1] + delta] for p in item.box]

    # ── cross-page restoration ─────────────────────────────────────────────

    @staticmethod
    def restore_cross_page(
        items: list[OCRItem],
        boundary_combined: int,
        n_inv_x: float,
        n_inv_y: float,
        n_strip_y_offset: int,
        n1_inv_x: float,
        n1_inv_y: float,
    ) -> tuple[list[OCRItem], list[OCRItem], list[OCRItem]]:
        """Restore detections from the combined strip image to per-page spaces.

        The combined image is formed by stacking the *bottom* strip of page N
        on top of the *top* strip of page N+1.  In the combined image:

        - y ∈ [0, boundary_combined)    → belongs to page N
        - y ∈ [boundary_combined, ...)  → belongs to page N+1

        Detections that straddle the boundary are classified as **spans**
        and their coordinates are kept in a page-N coordinate space.

        Args:
            items:             Detections in combined-image coordinates.
            boundary_combined: Height of page N's strip in the combined image.
            n_inv_x / n_inv_y: Inverse scale factors for page N strip
                                (combined coords → original page N coords).
            n_strip_y_offset:  Y-offset of page N's strip within original page N.
            n1_inv_x / n1_inv_y: Inverse scale factors for page N+1 strip.

        Returns:
            ``(spans, page_n_items, page_n1_items)`` where spans are in
            page-N coordinate space (extended past the boundary),
            page_n_items are in page-N space,
            page_n1_items are in page-N+1 space.
        """
        spans: list[OCRItem] = []
        page_n_items: list[OCRItem] = []
        page_n1_items: list[OCRItem] = []

        for it in items:
            box_ys = [p[1] for p in it.box]
            y_min = min(box_ys)
            y_max = max(box_ys)

            if y_min < boundary_combined and y_max > boundary_combined:
                # --- span: crosses the page boundary ---
                restored = OCRItem(
                    text=it.text,
                    box=[[p[0] * n_inv_x, p[1] * n_inv_y] for p in it.box],
                    cx=it.cx * n_inv_x,
                    cy=it.cy * n_inv_y,
                    height=int(round(it.height * n_inv_y)),
                    confidence=it.confidence,
                )
                CoordinateRestorer._shift_item(restored, n_strip_y_offset)
                spans.append(restored)
            elif y_max <= boundary_combined:
                # --- page N only ---
                restored = OCRItem(
                    text=it.text,
                    box=[[p[0] * n_inv_x, p[1] * n_inv_y] for p in it.box],
                    cx=it.cx * n_inv_x,
                    cy=it.cy * n_inv_y,
                    height=int(round(it.height * n_inv_y)),
                    confidence=it.confidence,
                )
                CoordinateRestorer._shift_item(restored, n_strip_y_offset)
                page_n_items.append(restored)
            else:
                # --- page N+1 only ---
                restored = OCRItem(
                    text=it.text,
                    box=[[p[0] * n1_inv_x, (p[1] - boundary_combined) * n1_inv_y]
                         for p in it.box],
                    cx=it.cx * n1_inv_x,
                    cy=(it.cy - boundary_combined) * n1_inv_y,
                    height=int(round(it.height * n1_inv_y)),
                    confidence=it.confidence,
                )
                page_n1_items.append(restored)

        return spans, page_n_items, page_n1_items
