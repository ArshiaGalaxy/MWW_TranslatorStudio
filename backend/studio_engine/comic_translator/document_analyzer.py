"""Adaptive Document Analysis: characterize PDFs before OCR to select the
optimal processing mode.

The analyzer inspects page dimensions (via PyMuPDF, no rendering) and
automatically chooses between Long Strip Mode and Standard Mode.

Long Strip Mode is used for Manhwa-style documents where pages are
significantly taller than wide.  Standard Mode is used for normal manga
/comic pages or Manhwa that is already split into short pages.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class DocumentMode(str, Enum):
    """Processing mode selected by the document analyzer."""

    LONG_STRIP = "long_strip"
    STANDARD = "standard"


@dataclass(frozen=True)
class DocumentAnalysis:
    """Result of analyzing a PDF document's page characteristics."""

    mode: DocumentMode
    total_pages: int
    avg_width: float
    avg_height: float
    avg_aspect_ratio: float
    size_consistency: float
    long_strip_pages: int

    def summary(self) -> str:
        return (
            f"DocumentAnalysis(mode={self.mode.value}, pages={self.total_pages}, "
            f"avg_size={self.avg_width:.0f}x{self.avg_height:.0f}, "
            f"aspect_ratio={self.avg_aspect_ratio:.2f}, "
            f"consistency={self.size_consistency:.3f}, "
            f"long_strip_pages={self.long_strip_pages}, "
        )


@dataclass
class DocumentAnalyzer:
    """Analyzes a PDF to determine the optimal OCR processing mode.

    Parameters
    ----------
    long_strip_aspect_ratio_threshold:
        Pages with height/width ratio above this are considered long strips.
        Default: 1.5
    size_consistency_threshold:
        Maximum allowed coefficient of variation of page sizes.
        Pages with sizes within this fraction of the average are considered
        consistent.  Default: 0.15
    """

    long_strip_aspect_ratio_threshold: float = 1.5
    size_consistency_threshold: float = 0.15

    def analyze(
        self,
        pdf_path: str | Path,
        config: object,
    ) -> DocumentAnalysis:
        """Analyze a PDF and return the detected mode and statistics.

        Parameters
        ----------
        pdf_path: Path to the PDF file.
        config: OCRConfig (or any object with a ``dpi`` attribute).

        Returns
        -------
        DocumentAnalysis with the detected mode and page statistics.
        """
        try:
            import fitz
        except ImportError as e:
            raise ImportError(
                "PyMuPDF is required for document analysis. "
                "Run: pip install PyMuPDF"
            ) from e

        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        doc = fitz.open(str(path))
        total = len(doc)

        if total == 0:
            doc.close()
            return DocumentAnalysis(
                mode=DocumentMode.STANDARD,
                total_pages=0,
                avg_width=0.0,
                avg_height=0.0,
                avg_aspect_ratio=1.0,
                size_consistency=0.0,
                long_strip_pages=0,
            )

        widths: list[float] = []
        heights: list[float] = []

        for page in doc:
            rect = page.rect
            widths.append(rect.width)
            heights.append(rect.height)

        doc.close()

        avg_w = sum(widths) / total
        avg_h = sum(heights) / total
        avg_ar = avg_h / avg_w if avg_w > 0 else 1.0

        # Size consistency: coefficient of variation of page areas.
        areas = [w * h for w, h in zip(widths, heights)]
        mean_area = sum(areas) / total
        if mean_area > 0:
            variance = sum((a - mean_area) ** 2 for a in areas) / total
            std_area = math.sqrt(variance)
            size_consistency = std_area / mean_area
        else:
            size_consistency = 0.0

        # Count pages that are long strips (aspect ratio above threshold).
        long_strip_count = sum(
            1 for w, h in zip(widths, heights)
            if w > 0 and (h / w) > self.long_strip_aspect_ratio_threshold
        )

        # Determine mode.
        # Long Strip Mode: most pages are long strips AND aspect ratio is high.
        # Use Long Strip Mode if > 60% of pages are long strips.
        long_strip_ratio = long_strip_count / total if total > 0 else 0.0
        mode = (
            DocumentMode.LONG_STRIP
            if long_strip_ratio > 0.6 and avg_ar > self.long_strip_aspect_ratio_threshold
            else DocumentMode.STANDARD
        )

        analysis = DocumentAnalysis(
            mode=mode,
            total_pages=total,
            avg_width=avg_w,
            avg_height=avg_h,
            avg_aspect_ratio=avg_ar,
            size_consistency=size_consistency,
            long_strip_pages=long_strip_count,
        )

        logger.info("Document analysis complete: %s", analysis.summary())
        return analysis


