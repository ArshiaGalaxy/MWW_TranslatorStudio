"""PDF to image conversion and image-to-PDF/ZIP output."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from PIL import Image

from comic_translator.config import OCRConfig
from comic_translator.exceptions import PDFError

logger = logging.getLogger(__name__)


def get_pdf_page_count(pdf_path: str | Path) -> int:
    """Get total page count without loading images."""
    try:
        import fitz
    except ImportError as e:
        raise PDFError("PyMuPDF not installed. Run: pip install PyMuPDF") from e
    doc = None
    try:
        if not Path(pdf_path).exists():
            raise PDFError(f"PDF file not found: {pdf_path}")
        doc = fitz.open(str(pdf_path))
        return len(doc)
    except PDFError:
        raise
    except Exception as e:
        raise PDFError(f"Failed to read PDF: {e}") from e
    finally:
        if doc is not None:
            doc.close()


def render_page(pdf_path: str | Path, page_num: int, dpi: int = 200) -> Image.Image:
    """Render a single page (1-indexed) to PIL Image using PyMuPDF."""
    try:
        import fitz
    except ImportError as e:
        raise PDFError("PyMuPDF not installed. Run: pip install PyMuPDF") from e
    doc = None
    try:
        doc = fitz.open(str(pdf_path))
        if not 1 <= page_num <= len(doc):
            raise PDFError(
                f"Page {page_num} out of range (PDF has {len(doc)} pages)")
        page = doc[page_num - 1]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    except PDFError:
        raise
    except Exception as e:
        raise PDFError(f"Failed to render page {page_num}: {e}") from e
    finally:
        # Close even on error paths — an open handle keeps the PDF locked
        # on Windows until GC happens to collect it.
        if doc is not None:
            doc.close()


def standardize_image(img: Image.Image, max_side: int) -> Image.Image:
    """Downscale an image so its longest side is at most ``max_side`` (LANCZOS).

    Images already within the limit are returned unchanged.  All pages are
    normalized to this size so OCR, preview and inpainting share one
    coordinate space.
    """
    w, h = img.size
    if max(w, h) <= max_side:
        return img
    scale = max_side / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def resize_to_width(img: Image.Image, target_width: int) -> Image.Image:
    """Resize image to target width while maintaining aspect ratio."""
    w, h = img.size
    if w == target_width:
        return img
    scale = target_width / w
    return img.resize((target_width, int(h * scale)), Image.LANCZOS)


def pdf_to_images(pdf_path: str | Path, config: OCRConfig) -> list[Image.Image]:
    """Convert PDF pages to PIL Images using PyMuPDF (fast)."""
    try:
        import fitz
    except ImportError as e:
        raise PDFError("PyMuPDF not installed. Run: pip install PyMuPDF") from e

    try:
        doc = fitz.open(str(pdf_path))
        zoom = config.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        images: list[Image.Image] = []

        for page in doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            # Standardize to config.ocr.standard_max_side
            img = standardize_image(img, config.standard_max_side)
            images.append(img)

        return images
    except Exception as e:
        raise PDFError(f"Failed to convert PDF: {e}") from e
    finally:
        if doc is not None:
            doc.close()


def save_pdf(
    images: list[Image.Image], output_path: str | Path, dpi: int = 200, quality: int = 75,
) -> Path:
    """Save a list of images as a multi-page PDF with JPEG compression.

    Uses PyMuPDF for better compression and smaller file sizes.
    Default quality=85 provides good balance between size and quality.
    """
    if not images:
        raise PDFError("No images to save")

    output_path = Path(output_path)
    doc = None
    try:
        import fitz
        doc = fitz.open()
        for img in images:
            buf = io.BytesIO()
            # Convert to RGB if needed (PDF doesn't support RGBA)
            if img.mode == "RGBA":
                img = img.convert("RGB")
            # Use JPEG with optimize flag for smaller size
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            page = doc.new_page(width=img.width, height=img.height)
            page.insert_image(page.rect, stream=buf.getvalue())
        # Use garbage=4 for maximum compression and deflate=True for zlib compression
        doc.save(str(output_path), deflate=True, garbage=4, clean=True)
        return output_path
    except ImportError:
        pass  # fall through to the Pillow fallback below
    except Exception as e:
        raise PDFError(f"Failed to save PDF: {e}") from e
    finally:
        if doc is not None:
            doc.close()

    # Fallback: use Pillow with compression
    images[0].save(
        str(output_path),
        save_all=True,
        append_images=images[1:],
        format="PDF",
        quality=quality,
        resolution=dpi,
        optimize=True,
    )
    return output_path


def save_webp_zip(
    images: list[Image.Image], output_path: str | Path, quality: int = 85,
    chunk_height: int = 8192,
) -> Path:
    """Save images as WebP files inside a ZIP archive.

    Each page is resized to 1200px wide and, if taller than ``chunk_height``
    (default 8192px), split vertically into multiple ``chunk_height`` slices.
    Pages shorter than the cap keep their natural height (no padding), so the
    maximum height of any WebP in the archive is ``chunk_height``.
    """
    if not images:
        raise PDFError("No images to save")

    output_path = Path(output_path)

    # 1) Normalize to 1200px width and split tall pages into chunk_height slices.
    frames: list[Image.Image] = []
    target_w = 1200
    for img in images:
        if img.width != target_w:
            img = img.resize(
                (target_w, max(1, int(round(img.height * target_w / img.width)))),
                Image.LANCZOS,
            )
        w, h = img.size
        if h > chunk_height:
            for y in range(0, h, chunk_height):
                frames.append(img.crop((0, y, w, min(y + chunk_height, h))))
        else:
            frames.append(img)

    # 2) Write frames to the ZIP.
    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for i, frame in enumerate(frames):
            buf = io.BytesIO()
            frame.save(buf, format="WEBP", quality=quality, method=6)
            zf.writestr(f"page_{i + 1:03d}.webp", buf.getvalue())

    return output_path


def concatenate_pages_vertically(images: list[Image.Image]) -> Image.Image:
    """Stack all page images vertically into one tall image.

    All images are resized to the same width (the maximum width) before stacking.
    Returns the concatenated PIL Image.
    """
    if not images:
        raise ValueError("No images to concatenate")
    if len(images) == 1:
        return images[0].copy()

    max_w = max(img.width for img in images)
    total_h = sum(img.height for img in images)

    # Resize all images to the same width (maintain aspect ratio)
    resized: list[Image.Image] = []
    for img in images:
        if img.width != max_w:
            img = img.resize((max_w, int(img.height * max_w / img.width)), Image.LANCZOS)
        resized.append(img)

    combined = Image.new("RGB", (max_w, total_h), (255, 255, 255))
    y_offset = 0
    for img in resized:
        combined.paste(img, (0, y_offset))
        y_offset += img.height

    return combined


def compute_page_offsets(images: list[Image.Image]) -> list[int]:
    """Compute the y-offset for each page in a vertically concatenated image.

    All images are assumed to be resized to the same width as the concatenated image.
    Returns a list of y-offsets, one per page.
    """
    if not images:
        return []

    max_w = max(img.width for img in images)
    offsets: list[int] = []
    y_offset = 0
    for img in images:
        offsets.append(y_offset)
        if img.width != max_w:
            y_offset += int(img.height * max_w / img.width)
        else:
            y_offset += img.height

    return offsets
