"""Adaptive page splitting for tall Manhwa pages.

Splits pages whose height exceeds a configurable threshold into overlapping
horizontal chunks.  Each chunk retains its original page index and a vertical
offset so that OCR coordinates can later be restored to the full-page
coordinate system.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass
class Chunk:
    """A cropped region of a page image.

    Attributes:
        y_offset: Vertical pixel offset of the chunk's top edge within the
                  original page image.
        image:    The cropped PIL image for this chunk.
    """

    y_offset: int
    image: Image.Image


class PageSplitter:
    """Split tall page images into overlapping horizontal chunks.

    The splitter is stateless beyond its parameters; the same instance can
    be reused for every page in a document.
    """

    def __init__(self, max_chunk_height: int = 1800, chunk_overlap: int = 300) -> None:
        self.max_chunk_height = max_chunk_height
        self.chunk_overlap = chunk_overlap

    # ── public API ─────────────────────────────────────────────────────────

    def split(self, img: Image.Image) -> list[Chunk]:
        """Split *img* into overlapping chunks.

        If the page height does not exceed ``max_chunk_height`` a single
        chunk (the full page) is returned.
        """
        w, h = img.size
        if h <= self.max_chunk_height:
            return [Chunk(y_offset=0, image=img.copy())]

        chunks: list[Chunk] = []
        for y_start, y_end in self._compute_chunk_bounds(h):
            crop = img.crop((0, y_start, w, y_end))
            chunks.append(Chunk(y_offset=y_start, image=crop))
        return chunks

    # ── internal ───────────────────────────────────────────────────────────

    def _compute_chunk_bounds(self, total_h: int) -> list[tuple[int, int]]:
        """Generate top-to-bottom (y_start, y_end) tuples with overlap.

        Step = max_chunk_height - chunk_overlap.
        The last chunk always extends to ``total_h`` so no pixels are lost.
        """
        if total_h <= self.max_chunk_height:
            return [(0, total_h)]

        step = self.max_chunk_height - self.chunk_overlap
        if step <= 0:
            # Overlap would eat the entire chunk — fall back to a single chunk.
            return [(0, total_h)]

        bounds: list[tuple[int, int]] = []
        y_start = 0
        while y_start < total_h:
            y_end = y_start + self.max_chunk_height
            if y_end >= total_h:
                # Final chunk: snap to end.
                y_end = total_h
                bounds.append((y_start, y_end))
                break
            bounds.append((y_start, y_end))
            y_start += step

        # Ensure the last chunk covers the bottom edge.
        if bounds and bounds[-1][1] < total_h:
            last_start = max(0, total_h - self.max_chunk_height)
            bounds.append((last_start, total_h))

        return bounds
