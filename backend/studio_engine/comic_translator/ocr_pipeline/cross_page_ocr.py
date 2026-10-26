"""Cross-page OCR for Manhwa speech bubbles split across page boundaries.

Some speech bubbles in long Manhwa PDFs continue from the bottom of page N
to the top of page N+1.  To detect such splits without re-running OCR on
entire pages, this module crops only a narrow strip from the bottom of page
N and the top of page N+1, concatenates them vertically, and runs OCR on
the tiny combined image.

Detections are then classified as:
    - **spans**:   text crossing the page boundary (most important).
    - **page_n**:  text only in page N's strip.
    - **page_n1**: text only in page N+1's strip.

Coordinate restoration delegates to ``CoordinateRestorer.restore_cross_page``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from PIL import Image

from comic_translator.config import OCRConfig
from comic_translator.models import OCRItem
from comic_translator.ocr import _get_ocr, _ocr_single_image
from comic_translator.ocr_pipeline.coordinate_restorer import CoordinateRestorer

logger = logging.getLogger(__name__)


@dataclass
class CrossPageResult:
    """Result of a cross-page OCR pass for one consecutive page pair.

    Attributes:
        page_n:        Page index of the first page (1-indexed).
        page_n1:       Page index of the second page.
        spans:         Detections crossing the page boundary.
                       Coordinates are in page-N coordinate space.
        page_n_items:  Detections fully in page N's bottom strip, restored
                       to page-N coordinates.
        page_n1_items: Detections fully in page N+1's top strip, restored
                       to page-N+1 coordinates.
        boundary_y:    Y-coordinate (in page-N space) of the strip boundary.
    """

    page_n: int
    page_n1: int
    spans: list[OCRItem] = field(default_factory=list)
    page_n_items: list[OCRItem] = field(default_factory=list)
    page_n1_items: list[OCRItem] = field(default_factory=list)
    boundary_y: int = 0


class CrossPageOCR:
    """Run OCR on boundary strips of consecutive page pairs."""

    def __init__(self) -> None:
        self._ocr = _get_ocr()
        self._restorer = CoordinateRestorer()

    # ── public API ─────────────────────────────────────────────────────────

    def crop_bottom_strip(self, img: Image.Image, height: int) -> Image.Image:
        """Crop the bottom *height* pixels of *img*."""
        h = img.size[1]
        y_start = max(0, h - height)
        return img.crop((0, y_start, img.size[0], h))

    def crop_top_strip(self, img: Image.Image, height: int) -> Image.Image:
        """Crop the top *height* pixels of *img*."""
        return img.crop((0, 0, img.size[0], height))

    def process_pair(
        self,
        img_n: Image.Image,
        img_n1: Image.Image,
        page_n: int,
        page_n1: int,
        config: OCRConfig,
        pages_dir: str | None = None,
    ) -> CrossPageResult:
        """Run cross-page OCR on two consecutive page images.

        Steps:
            1. Crop bottom strip of page N, top strip of page N+1.
            2. Resize both to a common width (if different), track scale.
            3. Vertically concatenate → combined image.
            4. Run OCR only on the combined image (no full-page OCR).
            5. Restore coordinates via ``CoordinateRestorer.restore_cross_page``.
        """
        strip_h = config.cross_page_height

        # --- Stage 1: crop strips ---
        bottom_n = self.crop_bottom_strip(img_n, strip_h)
        top_n1 = self.crop_top_strip(img_n1, strip_h)

        # Offset of the bottom strip within page N (for coordinate restoration).
        page_n_h = img_n.size[1]
        n_strip_y_offset = max(0, page_n_h - bottom_n.size[1])

        # --- Stage 2: resize to common width ---
        target_w = max(bottom_n.width, top_n1.width)

        n_inv_x = bottom_n.width / target_w
        n1_inv_x = top_n1.width / target_w

        if bottom_n.width != target_w or top_n1.width != target_w:
            bottom_resized = bottom_n.resize(
                (target_w, bottom_n.height), Image.LANCZOS
            )
            top_resized = top_n1.resize(
                (target_w, top_n1.height), Image.LANCZOS
            )
        else:
            bottom_resized = bottom_n.copy()
            top_resized = top_n1.copy()

        # --- Stage 3: concatenate ---
        boundary_combined = bottom_resized.height
        combined = Image.new(
            "RGB",
            (target_w, bottom_resized.height + top_resized.height),
            (255, 255, 255),
        )
        combined.paste(bottom_resized, (0, 0))
        combined.paste(top_resized, (0, bottom_resized.height))

        # --- Stage 4: OCR on combined image only ---
        raw_items = _ocr_single_image(self._ocr, combined, config, pages_dir=pages_dir)

        # --- Stage 5: restore coordinates to per-page spaces ---
        # No vertical scaling (heights preserved); only x is rescaled.
        spans, page_n_items, page_n1_items = self._restorer.restore_cross_page(
            raw_items,
            boundary_combined=boundary_combined,
            n_inv_x=n_inv_x,
            n_inv_y=1.0,
            n_strip_y_offset=n_strip_y_offset,
            n1_inv_x=n1_inv_x,
            n1_inv_y=1.0,
        )

        logger.info(
            "Cross-page OCR (p%d→p%d): %d spans, %d page-n, %d page-n1",
            page_n, page_n1, len(spans), len(page_n_items), len(page_n1_items),
        )

        return CrossPageResult(
            page_n=page_n,
            page_n1=page_n1,
            spans=spans,
            page_n_items=page_n_items,
            page_n1_items=page_n1_items,
            boundary_y=n_strip_y_offset + bottom_n.height,
        )
