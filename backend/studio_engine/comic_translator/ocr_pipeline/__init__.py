"""OCR preprocessing pipeline for long Manhwa PDFs.

Modules:
    document_analyzer  — analyze PDF to select optimal processing mode
    page_splitter       — splits tall pages into overlapping chunks
    ocr_processor       — runs PaddleOCR per chunk, restores chunk coordinates
    coordinate_restorer — maps OCR results back to original page coordinate space
    duplicate_detector  — removes duplicate detections using IoU + text + confidence
    cross_page_ocr      — OCR pass on bottom/top strips of consecutive page pairs
    dialogue_merger     — conservatively merges dialogues split across page boundaries
    ocr_pipeline        — orchestrator tying all stages together
"""

from __future__ import annotations

from comic_translator.document_analyzer import (
    DocumentAnalysis,
    DocumentAnalyzer,
    DocumentMode,
)
from comic_translator.ocr_pipeline.coordinate_restorer import CoordinateRestorer
from comic_translator.ocr_pipeline.cross_page_ocr import CrossPageOCR, CrossPageResult
from comic_translator.ocr_pipeline.dialogue_merger import DialogueMerger
from comic_translator.ocr_pipeline.duplicate_detector import DuplicateDetector
from comic_translator.ocr_pipeline.ocr_pipeline import (
    PageResult,
    detect_page,
    merge_cross_page,
    run_cross_page_pass,
    run_manhwa_concat_ocr,
)
from comic_translator.ocr_pipeline.ocr_processor import OCRProcessor
from comic_translator.ocr_pipeline.page_splitter import Chunk, PageSplitter

__all__ = [
    "Chunk",
    "DocumentAnalysis",
    "DocumentAnalyzer",
    "DocumentMode",
    "PageSplitter",
    "OCRProcessor",
    "CoordinateRestorer",
    "DuplicateDetector",
    "CrossPageOCR",
    "CrossPageResult",
    "DialogueMerger",
    "PageResult",
    "detect_page",
    "run_cross_page_pass",
    "merge_cross_page",
    "run_manhwa_concat_ocr",
]
