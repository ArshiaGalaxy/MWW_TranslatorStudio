"""Orchestrator: ties all OCR pipeline stages together.

Pipeline order (MUST be preserved):
    1. Document Analysis     (DocumentAnalyzer)
    2. Mode Selection        (Long Strip OR Standard)
    3. OCR per Page/Chunk    (detect_page / detect_page_long_strip)
    4. Remove Duplicates     (DuplicateDetector)
    5. (Optional) Cross-Page OCR with boundary gating
    6. Conservative Dialogue Merge
    7. Translation (downstream)
    8. Regional Inpainting
    9. Rendering
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from comic_translator.config import OCRConfig
from comic_translator.models import Block, OCRItem
from comic_translator.ocr import _cluster_items
from comic_translator.ocr_pipeline.cross_page_ocr import CrossPageOCR, CrossPageResult
from comic_translator.ocr_pipeline.dialogue_merger import DialogueMerger
from comic_translator.ocr_pipeline.duplicate_detector import DuplicateDetector
from comic_translator.ocr_pipeline.ocr_processor import OCRProcessor
from comic_translator.ocr_pipeline.page_splitter import Chunk, PageSplitter
from comic_translator.pdf import concatenate_pages_vertically, compute_page_offsets, render_page, resize_to_width

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    """OCR result for a single page.

    Attributes:
        page:   1-indexed page number.
        blocks: ``Block`` objects (from DBSCAN clustering).
        items:  Deduplicated raw ``OCRItem`` list (in page coordinates).
    """

    page: int
    blocks: list[Block]
    items: list[OCRItem]


# ── Stage 1–4: Per-page OCR with splitting + dedup ─────────────────────────


def detect_page(
    img: Image.Image,
    config: OCRConfig,
    page_index: int = 1,
    pages_dir: str | None = None,
) -> PageResult:
    """Full per-page OCR pipeline: split → OCR → restore → dedup → cluster.

    Produces ``Block`` objects directly.
    """
    splitter = PageSplitter(
        max_chunk_height=config.max_chunk_height,
        chunk_overlap=0,
    )
    processor = OCRProcessor()
    dedup = DuplicateDetector(iou_threshold=config.duplicate_iou_threshold)

    # --- Stage 1: Adaptive split ---
    chunks = splitter.split(img)

    # --- Stages 2 & 3: OCR per chunk + coordinate restoration ---
    all_items: list[OCRItem] = []
    for chunk in chunks:
        items = processor.process_chunk(chunk.image, config, y_offset=chunk.y_offset, pages_dir=pages_dir)
        all_items.extend(items)

    if not all_items:
        return PageResult(page=page_index, blocks=[], items=[])

    # --- Stage 4: Remove chunk duplicates ---
    deduped_items = dedup.remove(all_items)

    # --- Cluster into dialogs (existing logic) ---
    dialogs = _cluster_items(deduped_items, config)

    # Convert to Block objects.
    blocks = [Block.from_ocr(page_index, d) for d in dialogs]

    return PageResult(
        page=page_index,
        blocks=blocks,
        items=deduped_items,
    )


# ── Stage 5: Cross-page OCR ────────────────────────────────────────────────


def run_cross_page_pass(
    images: list[Image.Image],
    config: OCRConfig,
    page_results: list[PageResult | None] | None = None,
) -> list[CrossPageResult]:
    """Run cross-page OCR for consecutive page pairs with boundary gating.

    When ``page_results`` is provided, cross-page OCR is only performed
    for page pairs where boundary dialogue is detected (text boxes near
    the top or bottom edge of a page).  This avoids unnecessary OCR on
    page pairs where no dialogue spans the boundary.

    When ``page_results`` is ``None``, cross-page OCR runs for all pairs
    (backward-compatible behavior).
    """
    if not config.enable_cross_page_merge or len(images) < 2:
        return []

    cp_ocr = CrossPageOCR()
    results: list[CrossPageResult] = []

    for i in range(len(images) - 1):
        img_n = images[i]
        img_n1 = images[i + 1]
        page_n = i + 1
        page_n1 = i + 2

        # Boundary gating: skip if no evidence of cross-page dialogue.
        if page_results is not None:
            pr_n = page_results[i] if i < len(page_results) else None
            pr_n1 = page_results[i + 1] if (i + 1) < len(page_results) else None

            n_has_boundary = False
            n1_has_boundary = False

            if pr_n is not None and pr_n.blocks:
                n_has_boundary = _has_boundary_blocks(
                    pr_n.blocks, img_n.height, config.boundary_region_height,
                    config.boundary_dialogue_min_height,
                )
            if pr_n1 is not None and pr_n1.blocks:
                n1_has_boundary = _has_boundary_blocks(
                    pr_n1.blocks, img_n1.height, config.boundary_region_height,
                    config.boundary_dialogue_min_height,
                )

            if not n_has_boundary and not n1_has_boundary:
                logger.debug(
                    "Skipping cross-page OCR for pages %d-%d (no boundary dialogue)",
                    page_n, page_n1,
                )
                continue

        result = cp_ocr.process_pair(img_n, img_n1, page_n, page_n1, config)
        results.append(result)

    return results


def _has_boundary_blocks(
    blocks: list[Block],
    page_height: int,
    boundary_region: int,
    min_height: int,
) -> bool:
    """Check if any block touches the top or bottom boundary region."""
    top_limit = boundary_region
    bottom_limit = page_height - boundary_region

    for blk in blocks:
        if blk.y1 < top_limit and (blk.y2 - blk.y1) >= min_height:
            return True
        if blk.y2 > bottom_limit and (blk.y2 - blk.y1) >= min_height:
            return True
    return False


# ── Stage 6–7: Cross-page dedup + conservative merge ──────────────────────


def merge_cross_page(
    page_results: list[PageResult | None],
    cross_page_results: list[CrossPageResult],
    config: OCRConfig,
) -> dict[str, Block]:
    """Merge cross-page detections into per-page blocks.

    Steps:
        1. Build a lookup of blocks and items by page index (skip None entries).
        2. For each cross-page result:
           a. Deduplicate cross-page detections against per-page items.
           b. Merge dialogues that span page boundaries (conservative rules).
        3. Return updated block dict with merged entries.
    """
    merger = DialogueMerger(iou_threshold=config.duplicate_iou_threshold)
    dedup = DuplicateDetector(iou_threshold=config.duplicate_iou_threshold)

    # Build page → list of Block lookup (skip None entries).
    blocks_by_page: dict[int, list[Block]] = {}
    items_by_page: dict[int, list[OCRItem]] = {}
    for pr in page_results:
        if pr is None:
            continue
        blocks_by_page.setdefault(pr.page, []).extend(pr.blocks)
        items_by_page.setdefault(pr.page, []).extend(pr.items)

    # Result dict: page → list of Block.  We rebuild from blocks_by_page,
    # replacing merged pairs with their combined block.
    result_blocks: dict[int, list[Block]] = {}
    for pn, blks in blocks_by_page.items():
        result_blocks[pn] = list(blks)

    for cp_result in cross_page_results:
        page_n = cp_result.page_n
        page_n1 = cp_result.page_n1
        spans = cp_result.spans

        # Skip if either page has no blocks (e.g. cover page).
        if page_n not in result_blocks or page_n1 not in result_blocks:
            continue

        # --- Stage 6: Remove cross-page duplicates ---
        # Deduplicate page_n_items against per-page items on page N.
        n_per_page = items_by_page.get(page_n, [])
        n_deduped = dedup.remove(cp_result.page_n_items + n_per_page)
        # Deduplicate page_n1_items against per-page items on page N+1.
        n1_per_page = items_by_page.get(page_n1, [])
        n1_deduped = dedup.remove(cp_result.page_n1_items + n1_per_page)

        # Update items_by_page with deduped results (for subsequent pairs).
        items_by_page[page_n] = n_deduped
        items_by_page[page_n1] = n1_deduped

        # --- Stage 7: Conservative dialogue merge ---
        # Look for blocks near the boundary on each page.
        boundary_y = cp_result.boundary_y
        n_blocks = result_blocks.get(page_n, [])
        n1_blocks = result_blocks.get(page_n1, [])

        # Find candidate pairs: blk_n near bottom, blk_n1 near top.
        n_candidates = [
            b for b in n_blocks
            if b.y2 >= boundary_y - merger.max_boundary_gap
        ]
        n1_candidates = [
            b for b in n1_blocks
            if b.y1 <= merger.max_top_gap
        ]

        # Track which blocks have been consumed by a merge.
        used_n: set[int] = set()
        used_n1: set[int] = set()

        for blk_n in n_candidates:
            for blk_n1 in n1_candidates:
                idx_n = id(blk_n)
                idx_n1 = id(blk_n1)
                if idx_n in used_n or idx_n1 in used_n1:
                    continue
                if merger.should_merge(blk_n, blk_n1, spans):
                    # Find the best span (highest confidence) for merge text.
                    best_span: OCRItem | None = None
                    if spans:
                        best_span = max(spans, key=lambda s: s.confidence)

                    merged = merger.merge_blocks(blk_n, blk_n1, best_span)

                    # Remove original blocks from both pages; add merged to page N.
                    result_blocks[page_n] = [
                        b for b in result_blocks.get(page_n, [])
                        if b is not blk_n
                    ]
                    result_blocks[page_n1] = [
                        b for b in result_blocks.get(page_n1, [])
                        if b is not blk_n1
                    ]
                    result_blocks[page_n] = [merged] + result_blocks[page_n]

                    used_n.add(idx_n)
                    used_n1.add(idx_n1)
                    break

    # Flatten into a dict keyed by "p{page}_d{index}".
    all_blocks: dict[str, Block] = {}
    for pn in sorted(result_blocks.keys()):
        for idx, blk in enumerate(result_blocks[pn]):
            key = f"p{pn}_d{idx + 1}"
            all_blocks[key] = blk

    return all_blocks


# ── Manhwa Concatenation + Chunking OCR ──────────────────────────────────────


def run_manhwa_concat_ocr(
    pdf_path: str | Path,
    config: OCRConfig,
    cover_pages: set[int],
    skip_pages: set[int],
    total_pages: int,
    dpi: int,
    pages_dir: str | Path | None = None,
) -> tuple[dict[str, Block], list[PageResult | None], list[Path]]:
    """Run OCR for manhwa using concatenation + chunking approach.

    Flow:
    1. Render all non-skip pages at full DPI
    2. Separate covers from content pages
    3. Resize content pages to 1200px width
    4. Concatenate ALL content pages into ONE tall image
    5. Split tall image into:
       - Overlapping chunks for OCR (saved as page-overlap-{n}.jpg)
       - Non-overlapping chunks for display/inpaint (saved as page-{n}.jpg)
    6. OCR on overlapping chunks → coordinates in tall-image space
    7. Cluster into blocks with tall-image coordinates

    Args:
        pdf_path: Path to the PDF file.
        config: OCR configuration.
        cover_pages: Set of page numbers that are covers.
        skip_pages: Set of page numbers to skip entirely.
        total_pages: Total number of pages in the PDF.
        dpi: Render DPI.
        pages_dir: Directory to save chunk images. If None, chunks are not saved.

    Returns:
        (all_blocks, page_results, chunk_paths)
        - all_blocks: dict keyed by "p{chunk}_d{index}" with Block objects
        - page_results: list of PageResult (or None for covers/skips), indexed by page-1
        - chunk_paths: list of saved chunk image paths
    """
    logger.info("Manhwa concat OCR: rendering %d pages at %d DPI", total_pages, dpi)

    # ── Step 1: Render all non-skip pages ──
    all_images: list[Image.Image] = []
    page_nums: list[int] = []

    for pn in range(1, total_pages + 1):
        if pn in skip_pages:
            logger.info("Page %d: skipped by user", pn)
            continue
        img = render_page(pdf_path, pn, dpi)
        all_images.append(img)
        page_nums.append(pn)

    if not all_images:
        empty_results = [None] * total_pages
        return {}, empty_results, []

    # ── Step 2: Separate covers from content & resize to fixed width ──
    target_w = config.manhwa_concat_width
    content_images: list[Image.Image] = []
    content_page_nums: list[int] = []
    cover_page_offsets: list[int] = []  # offsets for covers (not in tall image)
    content_page_offsets: list[int] = []  # offset of each content page in tall image

    y_cursor = 0
    for img, pn in zip(all_images, page_nums):
        if pn in skip_pages :
            logger.info("Page %d: skipped", pn)
        if pn in cover_pages :
            logger.info("Page %d: cover (excluded from OCR)", pn)
            cover_page_offsets.append(y_cursor)
        else:
            img_resized = resize_to_width(img, target_w)
            content_images.append(img_resized)
            content_page_nums.append(pn)
            content_page_offsets.append(y_cursor)
            y_cursor += img_resized.height

    # ── Step 3: Concatenate ALL content pages into ONE tall image ──
    if not content_images:
        empty_results = [None] * total_pages
        return {}, empty_results, []

    combined = concatenate_pages_vertically(content_images)
    page_offsets = compute_page_offsets(content_images)
    logger.info(
        "Manhwa concat OCR: %d content pages -> single tall image %dx%d",
        len(content_images),
        combined.width,
        combined.height,
    )

    # ── Step 4: Split tall image for OCR (overlapping) and storage (non-overlapping) ──
    chunk_height = config.standard_max_side
    chunk_overlap = config.manhwa_concat_overlap

    # Overlapping chunks for OCR
    ocr_splitter = PageSplitter(
        max_chunk_height=chunk_height,
        chunk_overlap=chunk_overlap,
    )
    ocr_chunks = ocr_splitter.split(combined)

    # Non-overlapping chunks for storage/display
    save_splitter = PageSplitter(
        max_chunk_height=chunk_height,
        chunk_overlap=0,
    )
    save_chunks = save_splitter.split(combined)

    # ── Step 5: Save chunk images, overlap images, and the full tall image ──
    chunk_paths: list[Path] = []
    if pages_dir is not None:

        # Save full tall image for reuse in other tabs
        tall_path = Path(pages_dir) / "tall.jpg"
        if combined.mode != "RGB":
            combined = combined.convert("RGB")
        try:
            combined.save(tall_path, "JPEG", quality=90)
        except OSError:
            tall_path = Path(pages_dir) / "tall.png"
            combined.save(tall_path, "PNG")

        # Save page offsets so the tall image can be split back
        offsets_path = Path(pages_dir) / "page_offsets.json"
        import json
        offsets_path.write_text(json.dumps(page_offsets), encoding="utf-8")

        # Save non-overlapping chunks as page-{n}.jpg
        for ci, chunk in enumerate(save_chunks):
            chunk_path = Path(pages_dir) / f"page-{ci + 1}.jpg"
            chunk_img = chunk.image
            if chunk_img.mode != "RGB":
                chunk_img = chunk_img.convert("RGB")
            try:
                chunk_img.save(chunk_path, "JPEG", quality=85)
            except OSError:
                chunk_path = Path(pages_dir) / f"page-{ci + 1}.png"
                chunk_img.save(chunk_path, "PNG")
            chunk_paths.append(chunk_path)

        logger.info(
            "Saved tall image (%dx%d), %d chunk images + %d overlap images",
            combined.width, combined.height,
            len(save_chunks),
            len(ocr_chunks),
        )

    # ── Step 6: OCR each overlapping chunk ──
    processor = OCRProcessor()
    all_items: list[OCRItem] = []
    for chunk in ocr_chunks:
        items = processor.process_chunk(
            chunk.image, config, y_offset=chunk.y_offset, pages_dir=pages_dir
        )
        all_items.extend(items)

    logger.info(
        "OCR complete: %d items from %d chunks",
        len(all_items),
        len(ocr_chunks),
    )

    # ── Step 7: Dedup and cluster ──
    dedup = DuplicateDetector(iou_threshold=config.duplicate_iou_threshold)
    deduped_items = dedup.remove(all_items)

    # Cluster into blocks — coordinates are in tall-image space
    # Use chunk index as "page" for block keys
    dialogs = _cluster_items(deduped_items, config)
    all_blocks: dict[str, Block] = {}
    page_results: list[PageResult | None] = [None] * total_pages

    for j, dlg in enumerate(dialogs):
        key = f"d-{j + 1}"
        all_blocks[key] = Block.from_ocr(1, dlg)

    return all_blocks, page_results, chunk_paths


# ── Backward-compatible wrapper ─────────────────────────────────────────────


