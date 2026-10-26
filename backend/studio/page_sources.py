"""Durable page collections; source PDFs are never modified."""
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile

from django.conf import settings
from django.db import transaction
from django.db.models import F
from PIL import Image

from .jobs import _lock_for
from .models import Job, Page, Project

# Upload-append bounds (mirror chapter_import so link and file flows agree).
APPEND_MAX_FILES = 20
APPEND_MAX_IMAGE = 20 * 1024 * 1024
APPEND_MAX_TOTAL = 500 * 1024 * 1024
APPEND_FORMATS = ("JPEG", "PNG", "WEBP", "GIF")
APPEND_MAX_PIXELS = 40_000_000

CROP_MIN_SIDE = 50


@contextmanager
def page_mutation(project):
    lock = _lock_for(str(project.pk))
    if not lock.acquire(blocking=False):
        raise RuntimeError("A project job is still running")
    try:
        if project.jobs.filter(status__in=[Job.Status.PENDING, Job.Status.RUNNING]).exists():
            raise RuntimeError("A project job is still running")
        yield
    finally:
        lock.release()


def root_for(project):
    return Path(settings.MEDIA_ROOT) / "projects" / str(project.pk)


def preserve_sources(project):
    """Prepare complete copies before switching the DB source flag."""
    if project.uses_page_sources:
        return
    root = root_for(project)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as stage:
        for page in project.pages.all():
            source = root / "pages" / f"page-{page.page_number}.jpg"
            if not source.is_file():
                raise ValueError(f"Original image missing for page {page.page_number}")
            shutil.copyfile(source, Path(stage) / source.name)
        sources = root / "sources"
        sources.mkdir(exist_ok=True)
        for source in Path(stage).iterdir():
            source.replace(sources / source.name)
    project.uses_page_sources = True
    project.save(update_fields=["uses_page_sources"])


def refresh_collection(project):
    project.total_pages = project.pages.count()
    project.total_blocks = project.blocks.count()
    project.translated_count = project.blocks.exclude(translation="").count()
    project.status = Project.Status.READY if project.total_pages else Project.Status.CREATED
    project.save(update_fields=["total_pages", "total_blocks", "translated_count", "status", "updated_at"])
    transaction.on_commit(lambda: shutil.rmtree(root_for(project) / "outputs", ignore_errors=True))
    project.jobs.filter(kind=Job.Kind.APPLY).update(result={})


def delete_page(page):
    project = page.project
    with page_mutation(project), transaction.atomic():
        preserve_sources(project)
        number = page.page_number
        page.delete()
        project.cover_pages = [n for n in project.cover_pages if n != number]
        project.skip_pages = [n for n in project.skip_pages if n != number]
        project.save(update_fields=["cover_pages", "skip_pages"])
        refresh_collection(project)
        def cleanup():
            for folder in ("sources", "pages", "cleaned", "rendered"):
                (root_for(project) / folder / f"page-{number}.jpg").unlink(missing_ok=True)
            # Archival originals keep their source extension — clear any of them.
            originals_dir = root_for(project) / "sources_original"
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                (originals_dir / f"page-{number}{ext}").unlink(missing_ok=True)
        transaction.on_commit(cleanup)


def append_pages(project, files, original_files=None, position="end"):
    """Called by the import worker while it owns the project job lock.

    `files` are standardized JPGs used by the OCR/render pipeline.
    `original_files` (optional, same order) are exact source bytes archived
    under `sources_original/` for original-quality download.
    `position`: "end" (default), "start", or an int page number meaning
    "insert AFTER that page". Mid-inserts shift later pages up by renumbering
    (bulk UPDATE + reverse-order file renames) so numbering stays dense ints.

    NOTE: the sync upload view wraps this in `page_mutation()` itself — do
    NOT take the lock here or the background worker (which already holds it)
    would deadlock on its non-reentrant acquire.
    """
    from django.db.models import Max
    root = root_for(project)
    written = []
    try:
        with transaction.atomic():
            preserve_sources(project)
            existing = list(project.pages.order_by("page_number")
                            .values_list("page_number", flat=True))
            if position == "start":
                pos = 1
            elif isinstance(position, int):
                if position not in existing:
                    raise ValueError(f"No page {position} to insert after")
                pos = position + 1
            else:  # "end"
                pos = (existing[-1] if existing else 0) + 1
            if existing and pos <= existing[-1]:
                _shift_pages(project, pos, len(files))
            number = pos
            created = []
            for idx, file in enumerate(files):
                with Image.open(file) as im:
                    width, height = im.size
                for folder in ("sources", "pages"):
                    dest = root / folder / f"page-{number}.jpg"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(file, dest)
                    written.append(dest)
                if original_files is not None and idx < len(original_files):
                    src = Path(original_files[idx])
                    dest = root / "sources_original" / f"page-{number}{src.suffix.lower() or '.jpg'}"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dest)
                    written.append(dest)
                Page.objects.create(project=project, page_number=number, width=width, height=height)
                created.append(number)
                number += 1
            refresh_collection(project)
            return created
    except Exception:
        for file in written:
            file.unlink(missing_ok=True)
        raise


def _shift_pages(project, pos, count):
    """Shift every page_number >= pos up by count (descending, collision-free).

    File renames go in reverse numeric order so no target is ever occupied;
    the DB update goes through a large-offset two-step so the
    unique_together (project, page_number) never collides mid-update.
    Cover/skip lists store raw page numbers and are remapped too. Blocks and
    mask marks follow automatically (they FK to Page rows).
    """
    from django.db.models import Max
    root = root_for(project)
    top = project.pages.aggregate(n=Max("page_number"))["n"] or 0
    # 1) Files, highest first.
    for number in range(top, pos - 1, -1):
        for folder in ("sources", "pages", "cleaned", "rendered"):
            src = root / folder / f"page-{number}.jpg"
            if src.is_file():
                dest = root / folder / f"page-{number + count}.jpg"
                dest.parent.mkdir(parents=True, exist_ok=True)
                src.replace(dest)
        originals = root / "sources_original"
        if originals.is_dir():
            for src in originals.glob(f"page-{number}.*"):
                src.replace(originals / f"page-{number + count}{src.suffix}")
    # 2) Rows, via offset hop to dodge unique_together collisions.
    big = top + count + 1_000_000
    project.pages.filter(page_number__gte=pos).update(page_number=F("page_number") + big)
    project.pages.filter(page_number__gte=pos + big).update(
        page_number=F("page_number") - (big - count))
    # 3) Cover/skip lists.
    project.cover_pages = [n + count if n >= pos else n for n in project.cover_pages]
    project.skip_pages = [n + count if n >= pos else n for n in project.skip_pages]
    project.save(update_fields=["cover_pages", "skip_pages"])


def prepare_uploaded_images(uploaded):
    """Validate + standardize uploaded image files for append.

    Returns (jpg_paths, original_paths) inside a TemporaryDirectory — the
    caller owns the temp dir lifetime (consume before it closes). Raises
    ValueError with a user-facing message on any rejection.
    """
    import warnings
    from io import BytesIO
    from PIL import ImageOps

    files = list(uploaded)
    if not files or len(files) > APPEND_MAX_FILES:
        raise ValueError(f"Upload 1 to {APPEND_MAX_FILES} images at a time")
    stage = tempfile.TemporaryDirectory()
    jpgs, originals = [], []
    total = 0
    ext_of = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}
    for index, upload in enumerate(files):
        data = upload.read()
        total += len(data)
        if len(data) > APPEND_MAX_IMAGE:
            raise ValueError(f"{upload.name}: image exceeds 20 MB")
        if total > APPEND_MAX_TOTAL:
            raise ValueError("Images exceed 500 MB in total")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.format not in APPEND_FORMATS:
                        raise ValueError(f"{upload.name}: JPEG, PNG, WEBP or GIF only")
                    if image.width * image.height > APPEND_MAX_PIXELS:
                        raise ValueError(f"{upload.name}: image is too large")
                    pil_format = image.format
                    image.load()
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((4000, 16000), Image.Resampling.LANCZOS)
                    jpg = Path(stage.name) / f"{index}.jpg"
                    image.save(jpg, quality=95)
                    jpgs.append(jpg)
        except ValueError:
            raise
        except Exception:
            raise ValueError(f"{upload.name}: not a readable image")
        opath = Path(stage.name) / f"{index}_original{ext_of.get(pil_format, '.jpg')}"
        opath.write_bytes(data)
        originals.append(opath)
    # Attach the stage so it survives until the caller is done.
    return jpgs, originals, stage


def crop_page(project, number, x1, y1, x2, y2):
    """Crop one page to an image-pixel rect; remap its blocks and marks.

    Keeps ONLY fully-inside text blocks and mask marks (anything touching
    outside is deleted), shifts survivors by (-x1, -y1), crops the stored
    images, and invalidates cleaned/rendered derivatives for rebuild.
    Returns a summary dict.
    """
    for name, value in (("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)):
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if x2 - x1 < CROP_MIN_SIDE or y2 - y1 < CROP_MIN_SIDE:
        raise ValueError(f"Crop must be at least {CROP_MIN_SIDE}x{CROP_MIN_SIDE} px")
    with page_mutation(project), transaction.atomic():
        try:
            page = project.pages.get(page_number=number)
        except Page.DoesNotExist:
            raise ValueError(f"No page {number}") from None
        width, height = page.width, page.height
        if not width or not height:
            with Image.open(root_for(project) / "sources" / f"page-{number}.jpg") as im:
                width, height = im.size
        if not (x1 < x2 <= width and y1 < y2 <= height):
            raise ValueError("Crop rectangle is outside the page")
        preserve_sources(project)
        root = root_for(project)
        box = (x1, y1, x2, y2)
        new_w, new_h = x2 - x1, y2 - y1

        def _crop_jpg(path):
            with Image.open(path) as im:
                im.crop(box).save(path, "JPEG", quality=95)

        for folder in ("sources", "pages"):
            path = root / folder / f"page-{number}.jpg"
            if not path.is_file():
                if folder == "pages":
                    # Rebuild a missing preview from the (already cropped)
                    # source instead of failing.
                    shutil.copyfile(root / "sources" / f"page-{number}.jpg", path)
                    continue
                raise ValueError(f"Original image missing for page {number}")
            _crop_jpg(path)
        # Archival originals: crop best-effort, drop on format failure so no
        # stale full-size copy survives next to the cropped pipeline images.
        for opath in (root / "sources_original").glob(f"page-{number}.*"):
            try:
                with Image.open(opath) as im:
                    cropped = im.crop(box)
                    if opath.suffix.lower() == ".gif":
                        opath.unlink()
                        cropped.convert("RGB").save(opath.with_suffix(".png"))
                    else:
                        cropped.save(opath)
            except Exception:
                opath.unlink(missing_ok=True)
        # Derivatives no longer match — Clean/Render rebuild them.
        for folder in ("cleaned", "rendered"):
            (root / folder / f"page-{number}.jpg").unlink(missing_ok=True)

        kept_blocks = removed_blocks = 0
        for block in project.blocks.filter(page=page):
            inside = block.x1 >= x1 and block.y1 >= y1 and block.x2 <= x2 and block.y2 <= y2
            if not inside:
                block.delete()
                removed_blocks += 1
                continue
            block.x1 -= x1
            block.y1 -= y1
            block.x2 -= x1
            block.y2 -= y1
            if block.text_boxes:
                block.text_boxes = [
                    [[x - x1, y - y1] for x, y in line]
                    for line in block.text_boxes
                ]
            block.save(update_fields=["x1", "y1", "x2", "y2", "text_boxes"])
            kept_blocks += 1

        kept_marks = removed_marks = 0
        for mark in project.mask_marks.filter(page=page):
            points = mark.points or []
            if len(points) >= 3 and all(x1 <= x <= x2 and y1 <= y <= y2 for x, y in points):
                mark.points = [[x - x1, y - y1] for x, y in points]
                mark.save(update_fields=["points"])
                kept_marks += 1
            else:
                mark.delete()
                removed_marks += 1

        page.width, page.height = new_w, new_h
        page.save(update_fields=["width", "height"])
        refresh_collection(project)
        return {
            "page_number": number,
            "width": new_w,
            "height": new_h,
            "kept_blocks": kept_blocks,
            "removed_blocks": removed_blocks,
            "kept_marks": kept_marks,
            "removed_marks": removed_marks,
        }


def source_image(project, number):
    if not project.pages.filter(page_number=number).exists():
        raise ValueError("Page no longer exists")
    with Image.open(root_for(project) / "sources" / f"page-{number}.jpg") as im:
        return im.copy()
