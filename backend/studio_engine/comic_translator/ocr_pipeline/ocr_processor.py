"""OCR processing for individual image chunks.

Wraps the existing ``_ocr_single_image`` function from ``comic_translator.ocr``
and ensures that:
1. The PaddleOCR confidence score is captured into ``OCRItem.confidence``.
2. All detected bounding-box coordinates and centers are shifted by the
   chunk's vertical offset so they refer to the *original page* coordinate
   system, not the chunk-local one.
"""

from __future__ import annotations

import logging

from PIL import Image

from comic_translator.config import OCRConfig
from comic_translator.models import OCRItem
from comic_translator.ocr import _get_ocr, _ocr_single_image
from comic_translator.ocr_pipeline.coordinate_restorer import CoordinateRestorer

logger = logging.getLogger(__name__)


class OCRProcessor:
    """Run PaddleOCR on a single chunk image and restore page coordinates."""

    def __init__(self) -> None:
        self._ocr = None
        self._restorer = CoordinateRestorer()

    # ── public API ─────────────────────────────────────────────────────────

    def process_chunk(self, chunk_image: Image.Image, config: OCRConfig,
                      y_offset: int = 0, pages_dir: str | None = None) -> list[OCRItem]:
        """Run OCR on *chunk_image* and shift all coordinates by *y_offset*.

        Args:
            chunk_image: PIL image of the cropped chunk.
            config:      OCR configuration.
            y_offset:    Vertical offset of this chunk within the full page.
            pages_dir:   Optional directory for temp files (project folder).

        Returns:
            List of ``OCRItem`` whose coordinates are in the full-page
            coordinate system.
        """
        if self._ocr is None:
            self._ocr = _get_ocr(config)
        items = _ocr_single_image(self._ocr, chunk_image, config, pages_dir=pages_dir)
        # Restore coordinates: shift by chunk's vertical offset.
        self._restorer.restore_chunk_items(items, y_offset)
        return items
