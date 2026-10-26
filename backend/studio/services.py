"""Background services wrapping the vendored comic_translator engine.

All heavy imports are lazy (inside functions) so Django boots quickly and
can still serve non-engine endpoints when AI dependencies are missing.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from pathlib import Path

import requests

from django.conf import settings
from django.db import transaction
from PIL import Image

from .jobs import JobCancelled, JobContext
from .models import Project, Page, TextBlock, GlobalSetting

logger = logging.getLogger(__name__)

# 100 MP is ~8x the Pillow default but still caps a crafted-PDF OOM; a 400-dpi
# re-OCR page tops out far below this.
Image.MAX_IMAGE_PIXELS = 100_000_000


# ── Config helpers ───────────────────────────────────────────────────────────


def _read_seed_config() -> dict:
    """Seed config: studio_engine/config.json if present, else dataclass defaults."""
    from django.conf import settings as dj_settings

    seed = Path(getattr(dj_settings, "ENGINE_DIR")) / "config.json"
    if seed.exists():
        try:
            return json.loads(seed.read_text(encoding="utf-8"))
        except JobCancelled:
            raise
        except Exception:
            logger.warning("Failed to parse seed config %s", seed)

    try:
        from comic_translator.config import AppConfig
        from dataclasses import asdict

        cfg = AppConfig()
        return {
            "ocr": asdict(cfg.ocr),
            "font": asdict(cfg.font),
            "chapter_id": asdict(cfg.chapter_id),
            "inpaint": asdict(cfg.inpaint),
            "translator": asdict(cfg.translator),
        }
    except JobCancelled:
        raise
    except Exception:
        return {}


def _allowed_config_sections() -> dict[str, set[str]]:
    """Whitelist of editable config paths, derived from the engine dataclasses.

    PUT /api/config merges raw client JSON into the config the engine later
    consumes; without this filter an authenticated client could plant keys
    like `inpaint.pcleaner_cli_path` (later passed to subprocess) or anything
    else the engine might treat as a path/flag. Paths are dotted; the JSON
    schema nests provider keys under translator.openrouter / translator.gemini
    while the dataclass flattens them, so the JSON shape is whitelisted here.
    """
    from dataclasses import fields

    from comic_translator.config import (
        ChapterIDConfig, FontConfig, InpaintConfig, OCRConfig,
    )
    from comic_translator.typography import TypographyConfig

    return {
        "ocr": {f.name for f in fields(OCRConfig)},
        "font": {f.name for f in fields(FontConfig)},
        "chapter_id": {f.name for f in fields(ChapterIDConfig)},
        "inpaint": {f.name for f in fields(InpaintConfig)},
        "typography": {f.name for f in fields(TypographyConfig)},
        "translator": {"provider", "model", "temperature", "chunk_size",
                        "system_prompt", "user_prompt"},
        "translator.openrouter": {"model", "api_key"},
        "translator.gemini": {"model", "api_key"},
        "translator.custom": {"model", "api_key", "base_url"},
    }


def _prune_config(data: dict, allowed: dict[str, set[str]],
                  path: str = "", warn: bool = True) -> dict:
    """Drop unknown sections/keys so arbitrary values can't reach the engine.

    `allowed` maps a dotted path to the set of valid child keys. Leaves are
    kept as-is; a key is recursed into only when a child rule exists and the
    value is a dict, so a bad payload can't poison the shape the engine's
    `_build_config` relies on (e.g. translator.openrouter must stay a dict).
    Set `warn=False` for pruning that isn't triggered by a client payload
    (e.g. serving a stored config that predates a field removal).
    """
    pruned: dict = {}
    section = allowed.get(path)
    for key, value in data.items():
        key_path = f"{path}.{key}" if path else key
        if section is not None and key in section:
            pruned[key] = value
        elif key_path in allowed and isinstance(value, dict):
            pruned[key] = _prune_config(value, allowed, key_path, warn)
        else:
            if warn:
                logger.warning("config update: dropped unknown key %r", key_path)
    return pruned


def _validate_config_paths(cfg: dict) -> None:
    """Reject config values that would point the engine at arbitrary files."""
    font = cfg.get("font") or {}
    for key in ("path_normal", "path_sfx", "path_thinking"):
        val = font.get(key)
        if val and not _path_inside(val, Path(settings.FONTS_DIR)):
            raise ValueError(f"font.{key} must point inside the fonts directory")

    inpaint = cfg.get("inpaint") or {}
    cli = inpaint.get("pcleaner_cli_path")
    if cli and not Path(cli).is_file():
        raise ValueError("inpaint.pcleaner_cli_path must be an existing file")


def _path_inside(path_str: str, root: Path) -> bool:
    try:
        return Path(path_str).resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


# ── Provider connection test (Settings → Translator) ────────────────────────

_TEST_DIALOGS = {"hello": "Hello, world!"}
_TEST_SYSTEM_FALLBACK = (
    "You translate comic dialogue. Reply with the same JSON, values "
    "translated to Persian. Reply with JSON only.")

_TEST_TIMEOUT = 30  # seconds per single attempt


def run_provider_test(tc) -> dict:
    """Fire ONE tiny real request against the configured provider/model pair.

    Unlike the real translate path this never falls back to other models —
    the point is to verify *this* key/model/endpoint combination, so a bad
    key answers in seconds instead of minutes. Returns
    {"ok": True, "model": str, "latency_ms": int} or
    {"ok": False, "model": str, "error": str}.
    """
    provider = (tc.provider or "").strip().lower()
    dialogs = _TEST_DIALOGS
    user_prompt = (tc.user_prompt or
                   "Translate this JSON:\n\n{dialogs}\n\nReturn JSON only.").replace(
        "{dialogs}", json.dumps(dialogs, ensure_ascii=False))
    system_prompt = tc.system_prompt or _TEST_SYSTEM_FALLBACK
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}]

    if provider == "openrouter":
        model = tc.openrouter_model
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {tc.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/comic-translator",
        }
        payload = {"model": model, "temperature": tc.temperature, "messages": messages}
    elif provider == "gemini":
        if not tc.gemini_api_key:
            model = tc.gemini_model or "gemini-2.0-flash"
            return {"ok": False, "model": model,
                    "error": "Gemini API key not set — get a free key at "
                             "aistudio.google.com/apikey and save it in this card."}
        model = tc.gemini_model or "gemini-2.0-flash"
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent")
        headers = {"Content-Type": "application/json", "x-goog-api-key": tc.gemini_api_key}
        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": tc.temperature},
        }
    elif provider == "custom":
        model = tc.custom_model or "default"
        if not tc.custom_base_url:
            return {"ok": False, "model": model,
                    "error": "Custom provider base URL not set — "
                             "fill the Base URL field in the Custom card."}
        base = tc.custom_base_url.strip().rstrip("/")
        url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if tc.custom_api_key:
            headers["Authorization"] = f"Bearer {tc.custom_api_key}"
        payload = {"model": model, "temperature": tc.temperature, "messages": messages}
    else:
        raise ValueError(f"Unknown provider {tc.provider!r}")

    started = time.perf_counter()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_TEST_TIMEOUT)
    except requests.RequestException as e:
        return {"ok": False, "model": model,
                "error": f"{type(e).__name__}: {e}"[:240]}
    latency_ms = int((time.perf_counter() - started) * 1000)

    if resp.status_code != 200:
        return {"ok": False, "model": model,
                "error": _test_error_message(resp)[:240]}

    if not _test_response_text(resp, provider).strip():
        return {"ok": False, "model": model, "latency_ms": latency_ms,
                "error": "Empty response from the model"}
    return {"ok": True, "model": model, "latency_ms": latency_ms}

def _test_error_message(resp) -> str:
    """Best-effort human message from an error response body."""
    try:
        data = resp.json()
    except JobCancelled:
        raise
    except Exception:
        return f"HTTP {resp.status_code}: {resp.text[:200]}"
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict) and err.get("message"):
        return f"HTTP {resp.status_code}: {err['message']}"
    if isinstance(err, str) and err:
        return f"HTTP {resp.status_code}: {err}"
    if isinstance(data, dict) and data.get("message"):
        return f"HTTP {resp.status_code}: {data['message']}"
    return f"HTTP {resp.status_code}: {resp.text[:200]}"


def _test_response_text(resp, provider: str) -> str:
    """Extract the model's text from a successful completion response."""
    try:
        data = resp.json()
    except JobCancelled:
        raise
    except Exception:
        return ""
    if provider == "gemini":
        candidates = data.get("candidates") or []
        parts = ((candidates[0].get("content") or {}).get("parts")) if candidates else []
        return "".join(p.get("text", "") for p in (parts or []) if isinstance(p, dict))
    choices = (data.get("choices") or [{}])
    return str((choices[0].get("message") or {}).get("content", ""))


def _ensure_provider_subobjects(cfg: dict) -> dict:
    """Seed missing provider cards so the UI always renders them.

    Provider cards in Settings render from the nested objects present in the
    stored config; a stored value predating a provider (e.g. custom) would
    otherwise show no card for it even though the engine supports it. Fill
    each missing card with empty editable fields — existing values stay.
    """
    translator = cfg.get("translator")
    if not isinstance(translator, dict):
        translator = cfg["translator"] = {}
    for name, fields in (
        ("openrouter", ("model", "api_key")),
        ("gemini", ("model", "api_key")),
        ("custom", ("model", "api_key", "base_url")),
    ):
        card = translator.get(name)
        if not isinstance(card, dict):
            card = translator[name] = {}
        for f in fields:
            card.setdefault(f, "")
    return cfg


def get_global_config() -> dict:
    """Return the global config dict (seeded from engine defaults on first call).

    Pruned against the editable whitelist on the way out so keys removed from
    the engine dataclasses — or left over in an older stored value — never
    reach the API or the engine build step.
    """
    obj, _ = GlobalSetting.objects.get_or_create(key="config")
    if not obj.value:
        obj.value = _read_seed_config()
        obj.save()
    return _ensure_provider_subobjects(
        _prune_config(obj.value or {}, _allowed_config_sections(), warn=False))


def update_global_config(data: dict) -> dict:
    allowed = _allowed_config_sections()
    data = _prune_config(data, allowed)

    obj, _ = GlobalSetting.objects.get_or_create(key="config")
    current = obj.value or {}

    def _merge(dst: dict, src: dict) -> None:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                _merge(dst[k], v)
            else:
                dst[k] = v

    _merge(current, data)
    # Re-prune the merged value so keys dropped from the engine dataclasses
    # disappear from storage on the next save instead of lingering forever.
    current = _prune_config(current, allowed, warn=False)
    _validate_config_paths(current)

    obj.value = current
    obj.save()
    return current


def _get_config(project: Project):
    """Build engine AppConfig from global config + project overrides."""
    from comic_translator.config import _build_config

    base = get_global_config()

    def merged(section: str) -> dict:
        override = getattr(project, f"{section}_config", None) or {}
        combined = dict(base.get(section) or {})
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(combined.get(k), dict):
                # Nested dicts (e.g. translator.openrouter) merge key-by-key.
                # Project *_config snapshots are written once at creation and
                # have no edit UI, so an EMPTY string in the snapshot (e.g. an
                # api_key saved in Settings afterwards) must not clobber the
                # global value — otherwise jobs for pre-existing projects run
                # keyless and the provider raises "API key not set".
                sub = dict(combined[k])
                for sk, sv in v.items():
                    if sv == "" and sub.get(sk):
                        continue
                    sub[sk] = sv
                combined[k] = sub
            elif not (v == "" and combined.get(k)):
                combined[k] = v
        return combined

    raw = {
        "ocr": merged("ocr"),
        "font": merged("font"),
        "chapter_id": merged("chapter_id"),
        "inpaint": merged("inpaint"),
        "translator": merged("translator"),
        "typography": base.get("typography") or {},
    }
    return _build_config(raw)


# ── Media helpers ────────────────────────────────────────────────────────────


def _project_media(project: Project) -> Path:
    return Path(settings.MEDIA_ROOT) / "projects" / str(project.id)


def _pages_dir(project: Project) -> Path:
    return _project_media(project) / "pages"


def _save_page_jpg(project: Project, page_number: int, image: Image.Image,
                   subdir: str = "pages") -> None:
    out_dir = _project_media(project) / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(out_dir / f"page-{page_number}.jpg", "JPEG", quality=90, optimize=True)


def _load_page_image(project: Project, page_number: int) -> Image.Image | None:
    path = _pages_dir(project) / f"page-{page_number}.jpg"
    if not path.exists():
        if project.uses_page_sources:
            from .page_sources import source_image
            return source_image(project, page_number)
        return None
    with Image.open(path) as image:
        return image.copy()


# ── Extract ──────────────────────────────────────────────────────────────────


def run_extract(ctx: JobContext) -> dict:
    """OCR extraction job. ctx.job.params: covers, skip_pages, pdf_type, standard_max_side."""
    from comic_translator.pdf import get_pdf_page_count, render_page, resize_to_width, standardize_image
    from comic_translator.document_analyzer import DocumentAnalyzer, DocumentMode

    project: Project = ctx.job.project
    params = ctx.job.params or {}
    config = _get_config(project)

    covers = set(params.get("covers") or [])
    skip_pages = set(params.get("skip_pages") or [])
    pdf_type = params.get("pdf_type")
    if pdf_type:
        project.pdf_type = pdf_type

    # Apply one-shot overrides
    std_side = params.get("standard_max_side")
    if std_side:
        from dataclasses import replace
        config = replace(config, ocr=replace(config.ocr, standard_max_side=int(std_side)))
    ocr_version = params.get("ocr_version")
    if ocr_version:
        from dataclasses import replace
        config = replace(config, ocr=replace(config.ocr, ocr_version=str(ocr_version)))
        ctx.log(f"OCR version override: {ocr_version}")

    project.cover_pages = sorted(covers)
    project.skip_pages = sorted(skip_pages)
    project.status = Project.Status.EXTRACTING
    project.error_message = ""
    project.save(update_fields=["cover_pages", "skip_pages", "status",
                                "pdf_type", "error_message"])

    if project.uses_page_sources:
        return _extract_stored_pages(ctx)

    pdf_path = project.pdf_file.path
    total = get_pdf_page_count(pdf_path)
    project.total_pages = total
    project.save(update_fields=["total_pages"])
    ctx.log(f"PDF has {total} pages")

    # Wipe previous extraction results. Transactional so a crash between the
    # wipe and the re-persist below cannot leave the project with no OCR data
    # (the persist happens at the very end of this job; the transaction only
    # spans the wipe, keeping the long OCR phase outside it).
    with transaction.atomic():
        project.blocks.all().delete()
        project.pages.all().delete()

    # Stale derived previews would otherwise surface as cleaned/rendered
    # artifacts of the NEW extraction (reuse logic keys off these files).
    for sub in ("cleaned", "rendered"):
        shutil.rmtree(_project_media(project) / sub, ignore_errors=True)

    analyzer = DocumentAnalyzer(
        long_strip_aspect_ratio_threshold=config.ocr.long_strip_aspect_ratio_threshold,
        size_consistency_threshold=config.ocr.size_consistency_threshold,
    )
    analysis = analyzer.analyze(pdf_path, config.ocr)
    use_long_strip = analysis.mode == DocumentMode.LONG_STRIP
    project.detected_mode = analysis.mode.value
    ctx.log(f"Document mode: {analysis.mode.value} ({analysis.total_pages} pages, "
            f"{analysis.avg_width:.0f}x{analysis.avg_height:.0f})")

    pages_dir = str(_pages_dir(project))
    Path(pages_dir).mkdir(parents=True, exist_ok=True)
    is_manhwa_concat = use_long_strip and project.pdf_type == Project.PDFType.MANHWA

    all_blocks: dict[str, object] = {}
    page_results = []

    if is_manhwa_concat:
        from comic_translator.ocr_pipeline import run_manhwa_concat_ocr
        ctx.check_cancelled()
        ctx.progress(0.05, "Manhwa concat: rendering + OCR")
        ctx.log("Manhwa concat mode: pages are concatenated, OCR'd, and stored "
                "as display chunks")
        all_blocks, _page_results, chunk_paths = run_manhwa_concat_ocr(
            pdf_path, config.ocr, covers, skip_pages, total, config.ocr.dpi,
            pages_dir=pages_dir,
        )
        ctx.log(f"OCR done: {len(all_blocks)} blocks on tall strip "
                f"({len(chunk_paths)} chunks saved)")

        # ── Persist each display chunk as a Page (webtoon split-page model) ──
        chunk_sizes: list[tuple[int, int]] = []
        for cp in chunk_paths:
            with Image.open(cp) as im:
                chunk_sizes.append((im.width, im.height))
        for ci, (w, hgt) in enumerate(chunk_sizes):
            Page.objects.update_or_create(
                project=project, page_number=ci + 1,
                defaults={"width": w, "height": hgt},
            )

        # ── Map blocks from tall-strip coords → chunk-local coords ──
        # Engine returns keys "d-{n}" with page=1 and coordinates relative to
        # the concatenated image. Assign every block to the chunk that
        # contains its vertical center and shift/clamp into local space.
        offsets = [0]
        for _, hgt in chunk_sizes[:-1]:
            offsets.append(offsets[-1] + hgt)
        total_h = offsets[-1] + chunk_sizes[-1][1] if chunk_sizes else 0

        remapped: dict[str, object] = {}
        per_chunk_counter: dict[int, int] = {}
        for j, (old_key, blk) in enumerate(all_blocks.items()):
            cy = min(max((blk.y1 + blk.y2) // 2, 0), max(total_h - 1, 0))
            ci = len(chunk_sizes) - 1
            for idx in range(len(chunk_sizes)):
                if offsets[idx] <= cy < offsets[idx] + chunk_sizes[idx][1]:
                    ci = idx
                    break
            off = offsets[ci]
            x1 = max(0, blk.x1)
            y1 = max(0, blk.y1 - off)
            x2 = min(chunk_sizes[ci][0], blk.x2)
            y2 = min(chunk_sizes[ci][1], blk.y2 - off)
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue

            from comic_translator.models import Block as EngineBlock
            local = EngineBlock(
                page=ci + 1,
                text=blk.text,
                x1=x1, y1=y1, x2=x2, y2=y2,
                translation_fa=blk.translation_fa,
                sfx=blk.sfx,
                thinking=blk.thinking,
                text_boxes=[
                    [[x, y - off] for x, y in tb] for tb in (blk.text_boxes or [])
                ],
                text_type=blk.text_type,
                orientation=getattr(blk, "orientation", "") or "horizontal",
            )
            n = per_chunk_counter.get(ci, 0) + 1
            per_chunk_counter[ci] = n
            key = f"p{ci + 1}_d{n}"
            remapped[key] = _Keyed(key, local)

        all_blocks = remapped
        ctx.log(f"Mapped {len(all_blocks)} blocks across {len(chunk_sizes)} chunks")

    else:
        from comic_translator.ocr_pipeline import detect_page
        ocr_start = time.time()
        page_images = []
        for pn in range(1, total + 1):
            if pn in covers:
                ctx.log(f"Page {pn}: cover (skipped)")
                page_results.append(None)
                continue
            if pn in skip_pages:
                ctx.log(f"Page {pn}: skipped by user")
                page_results.append(None)
                continue

            ctx.check_cancelled()
            img = render_page(pdf_path, pn, config.ocr.dpi)
            img = resize_to_width(img, 1200)
            img = standardize_image(img, config.ocr.standard_max_side)
            if img.width == 0 or img.height == 0:
                ctx.log(f"Page {pn}: invalid image, skipping")
                page_results.append(None)
                continue

            pr = detect_page(img, config.ocr, page_index=pn, pages_dir=pages_dir)
            page_results.append(pr)
            page_images.append((pn, img))

            _save_page_jpg(project, pn, img)
            Page.objects.update_or_create(
                project=project, page_number=pn,
                defaults={"width": img.width, "height": img.height},
            )
            for j, blk in enumerate(pr.blocks):
                key = f"p{pn}_d{j + 1}"
                all_blocks[key] = _Keyed(key, blk)
            ctx.progress(0.05 + 0.6 * pn / total,
                         f"OCR page {pn}/{total}: {len(pr.blocks)} blocks")

        # Cross-page merge (aligned lists of processed pages only)
        if config.ocr.enable_cross_page_merge and total > 1 and len(page_images) > 1:
            from comic_translator.ocr_pipeline import run_cross_page_pass, merge_cross_page

            aligned_imgs = [img for pn, img in page_images]
            aligned_results = [page_results[pn - 1] for pn, _ in page_images]
            cross_results = run_cross_page_pass(aligned_imgs, config.ocr, aligned_results)
            if cross_results:
                merged = merge_cross_page(aligned_results, cross_results, config.ocr)
                if merged:
                    all_blocks = merged
                    ctx.log(f"Cross-page merge: {len(all_blocks)} blocks total")
            else:
                ctx.log("No boundary dialogue detected — cross-page OCR skipped")
            ctx.progress(0.7, "Cross-page pass done")

        ctx.log(f"OCR finished in {time.time() - ocr_start:.1f}s: "
                f"{len(all_blocks)} blocks")

    # Persist blocks to DB
    ctx.progress(0.85, "Saving to database")
    _persist_blocks(project, all_blocks, covers)
    counts = _refresh_counts(project)
    project.status = Project.Status.READY
    project.save(update_fields=["status", "detected_mode"])
    ctx.log(f"Extraction complete: {counts['total']} blocks "
            f"({counts['sfx']} SFX)")

    return {"blocks": counts["total"], "mode": project.detected_mode}


class _Keyed:
    """Lightweight wrapper assigning a block key during extraction."""

    __slots__ = ("key", "block")

    def __init__(self, key: str, block):
        self.key = key
        self.block = block


def _persist_blocks(project: Project, all_blocks: dict, covers: set[int]) -> None:
    """Save engine blocks into TextBlock rows."""
    page_rows = {p.page_number: p for p in project.pages.all()}
    items = list(all_blocks.items())
    with transaction.atomic():
        for i, (key, wrapped) in enumerate(items):
            blk = wrapped.block if isinstance(wrapped, _Keyed) else wrapped
            pn = blk.page
            page_row = page_rows.get(pn)
            if page_row is None:
                page_row, _ = Page.objects.get_or_create(project=project, page_number=pn)
            block_type = blk.text_type if blk.text_type in TextBlock.BlockType.values else "dialog"
            TextBlock.objects.create(
                project=project,
                page=page_row,
                key=key,
                original_text=blk.text,
                translation=(blk.translation_fa or "").strip(),
                block_type=block_type,
                x1=blk.x1, y1=blk.y1, x2=blk.x2, y2=blk.y2,
                text_boxes=blk.text_boxes or [],
                orientation=getattr(blk, "orientation", "") or "horizontal",
                order=i,
            )


def _extract_stored_pages(ctx: JobContext) -> dict:
    """Edited collections are authoritative; never recreate pages from the PDF."""
    project = ctx.job.project
    numbers = list(project.pages.order_by("page_number").values_list("page_number", flat=True))
    found = 0
    original_params = dict(ctx.job.params or {})
    try:
        for index, number in enumerate(numbers):
            ctx.progress(index / max(1, len(numbers)), f"Extracting page {number}")
            ctx.job.params = {**original_params, "page_number": number}
            ctx.job.save(update_fields=["params"])
            found += run_reocr(ctx)["found"]
    finally:
        ctx.job.params = original_params
        ctx.job.save(update_fields=["params"])
    project.status = Project.Status.READY if numbers else Project.Status.CREATED
    project.total_pages = len(numbers)
    project.save(update_fields=["status", "total_pages", "updated_at"])
    return {"pages": len(numbers), "blocks": found}


def _refresh_counts(project: Project) -> dict:
    agg = {}
    blocks = project.blocks.all()
    agg["total"] = blocks.count()
    agg["translated"] = blocks.exclude(translation="").count()
    agg["sfx"] = blocks.filter(block_type="sfx").count()
    project.total_blocks = agg["total"]
    project.translated_count = agg["translated"]
    project.save(update_fields=["total_blocks", "translated_count"])
    return agg


# ── Translate ────────────────────────────────────────────────────────────────


def _update_glossary(original: str, translated: str, glossary: dict[str, str]) -> None:
    if not translated.strip() or len(translated.split()) > 8:
        return
    words = re.findall(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\b", original)
    if not words:
        return
    orig_words = original.strip().split()
    trans_words = translated.strip().split()
    if len(orig_words) == 1 and len(trans_words) <= 3:
        name = orig_words[0]
        if name[0].isupper() and len(name) > 1:
            glossary[name] = translated.strip()


def run_translate(ctx: JobContext) -> dict:
    """Auto-translate blocks via configured provider."""
    from comic_translator.translator import create_provider

    project: Project = ctx.job.project
    params = ctx.job.params or {}
    force = bool(params.get("force"))
    block_ids = params.get("block_ids") or None
    config = _get_config(project)

    project.status = Project.Status.TRANSLATING
    project.error_message = ""
    project.save(update_fields=["status", "error_message"])

    provider = create_provider(config.translator)
    provider_override = params.get("provider")
    if provider_override and provider_override != config.translator.provider:
        from dataclasses import replace
        config = replace(config, translator=replace(
            config.translator, provider=str(provider_override)))
        provider = create_provider(config.translator)
        ctx.log(f"Provider override: {provider_override}")
    system_prompt = config.translator.system_prompt
    chunk_size = max(1, config.translator.chunk_size or 50)

    qs = project.blocks.select_related("page").order_by("page__page_number", "order")
    if block_ids:
        qs = qs.filter(id__in=block_ids)
    if not force:
        qs = qs.filter(translation="")

    blocks_list = list(qs)
    if not blocks_list:
        ctx.log("Nothing to translate")
        project.status = Project.Status.READY
        project.save(update_fields=["status"])
        return {"translated": 0}

    # Seed glossary from DB entries
    glossary: dict[str, str] = {
        g.source: g.target for g in project.glossary.all()
    }
    ctx.log(f"Translating {len(blocks_list)} blocks in "
            f"{-(-len(blocks_list) // chunk_size)} chunks "
            f"(provider={config.translator.provider}, glossary={len(glossary)})")

    translations: dict[str, str] = {}
    prev_dialogs: list[str] = []

    def _do_chunk(start: int, end: int) -> None:
        nonlocal glossary
        chunk = blocks_list[start:end]
        batch = {blk.key: blk.original_text for blk in chunk}
        page_numbers = sorted({blk.page.page_number for blk in chunk})
        context_parts = [f"Page {', '.join(map(str, page_numbers))}"]
        if prev_dialogs:
            context_parts.append("Previous dialogs: " + " | ".join(prev_dialogs[-3:]))
        context = "Context: " + ". ".join(context_parts)

        effective_prompt = system_prompt
        if glossary:
            gs = ", ".join(f"{en} → {fa}" for en, fa in sorted(glossary.items()))
            effective_prompt = (f"{system_prompt}\n\n"
                                f"Known name translations (use these consistently): {gs}")

        result = provider.translate_batch(batch, effective_prompt, context=context)
        for blk in chunk:
            fa = (result.get(blk.key) or "").strip()
            if fa:
                blk.translation = fa
                blk.save(update_fields=["translation"])
                translations[blk.key] = fa
                prev_dialogs.append(f"{blk.original_text} → {fa}")
                _update_glossary(blk.original_text, fa, glossary)

    total_chunks = -(-len(blocks_list) // chunk_size)
    done = 0
    failed_chunks = 0
    last_error = ""
    for i in range(0, len(blocks_list), chunk_size):
        end = min(i + chunk_size, len(blocks_list))
        ctx.check_cancelled()
        try:
            _do_chunk(i, end)
        except JobCancelled:
            # Cancellation raised inside a chunk's nested progress/log calls:
            # propagate instead of logging it as a chunk failure.
            raise
        except Exception as e:
            failed_chunks += 1
            last_error = f"{type(e).__name__}: {e}"
            ctx.log(f"Chunk {done + 1}/{total_chunks} FAILED: {last_error[:300]}")
        done += 1
        ctx.progress(0.9 * done / total_chunks,
                     f"Translated chunk {done}/{total_chunks}")

    _refresh_counts(project)

    ok = len(translations)
    if ok == 0:
        project.status = Project.Status.FAILED
        project.error_message = (
            f"Translation produced no results. Last error: {last_error[:400]}"
        )
        project.save(update_fields=["status", "error_message"])
        raise RuntimeError(
            "No blocks were translated. "
            + (f"Last error: {last_error[:300]}. " if last_error else "")
            + "Check Settings → Translator: verify the selected provider's API key"
              " / endpoint — try switching to OpenRouter/Gemini to isolate the problem."
        )

    project.status = Project.Status.READY
    project.save(update_fields=["status"])
    ctx.log(f"Translation complete: {ok}/{len(blocks_list)} blocks"
            + (f" ({failed_chunks} chunks failed)" if failed_chunks else ""))
    return {"translated": ok, "failed_chunks": failed_chunks}


# ── Apply (inpaint + render + export) ───────────────────────────────────────


class _JobProgress:
    """Adapter forwarding engine RenderProgress calls into JobContext."""

    def __init__(self, ctx: JobContext, base: float = 0.1, span: float = 0.8):
        self.ctx = ctx
        self.base = base
        self.span = span
        self._last = 0.0

    def start_phase(self, phase: str, total: int = 0) -> None:
        self.ctx.log(f"Phase: {phase}" + (f" ({total} regions)" if total else ""))

    def update(self, message: str) -> None:
        self._last = min(self._last + 0.01, 0.99)
        self.ctx.progress(self.base + self.span * self._last, message)

    def update_page(self, page_num: int, total: int, message: str) -> None:
        frac = page_num / max(total, 1)
        self.ctx.progress(self.base + self.span * frac, message)
        self._last = frac

    def finish_phase(self) -> None:
        pass

    def finish(self) -> None:
        self.ctx.progress(self.base + self.span, "Render done")

    @property
    def elapsed_str(self) -> str:
        return ""


def run_apply(ctx: JobContext) -> dict:
    """Inpaint original text, draw Persian translations, export files."""
    from comic_translator.pdf import save_pdf, save_webp_zip
    from comic_translator.renderer import render_page_list
    from comic_translator.models import Block as EngineBlock

    project: Project = ctx.job.project
    params = ctx.job.params or {}
    chapter_id = params.get("chapter_id", project.chapter_id) or ""
    formats = params.get("formats") or ["pdf"]

    config = _get_config(project)
    project.chapter_id = chapter_id
    project.status = Project.Status.APPLYING
    project.error_message = ""
    project.save(update_fields=["chapter_id", "status", "error_message"])

    pages = list(project.pages.order_by("page_number"))
    if not pages:
        raise RuntimeError("No pages extracted yet — run extract first")

    # Build engine blocks from DB
    pages_map: dict[int, list[tuple[str, EngineBlock]]] = {}
    translations: dict[str, str] = {}
    for blk in project.blocks.select_related("page").order_by("page__page_number", "order"):
        eb = blk.to_engine_block()
        pages_map.setdefault(blk.page.page_number, []).append((blk.key, eb))
        if blk.translation.strip():
            translations[blk.key] = blk.translation.strip()

    ctx.log(f"Applying {len(translations)} translations on {len(pages)} pages")

    # Reuse rendered previews from earlier Render jobs — Export must not
    # re-clean/re-render work the user already did. Only pages WITHOUT a
    # rendered image go through inpaint + render here. (Chapter stamps come
    # from the render job, which persists the same project.chapter_id.)
    proj_media = _project_media(project)
    done_images: dict[int, Image.Image] = {}
    pending: list[Page] = []
    for p in pages:
        cached = proj_media / "rendered" / f"page-{p.page_number}.jpg"
        if cached.exists():
            done_images[p.page_number] = Image.open(cached).copy()
            continue
        pending.append(p)
    if done_images:
        ctx.log(f"Reusing {len(done_images)} already-rendered page(s); "
                f"processing {len(pending)} remaining")

    # Load cached page images; fall back to PDF rendering
    images: list[Image.Image] = []
    missing = []
    for p in pending:
        img = _load_page_image(project, p.page_number)
        if img is None:
            missing.append(p.page_number)
        images.append(img)
    if missing:
        if not project.pdf_file:
            raise RuntimeError("Page images are missing and this project has no PDF to re-render from")
        from comic_translator.pdf import render_page, resize_to_width, standardize_image
        for idx, (p, img) in enumerate(zip(pending, images)):
            if img is None:
                im = render_page(project.pdf_file.path, p.page_number, config.ocr.dpi)
                im = resize_to_width(im, 1200)
                images[idx] = standardize_image(im, config.ocr.standard_max_side)
        ctx.log(f"Re-rendered {len(missing)} missing page images from PDF")

    if pending:
        # Inpaint all regions that will receive text (shared with clean job)
        _inpaint_pages(
            ctx, project, config, pending, images, pages_map, translations,
            progress=(0.05, 0.40),
        )

        # Render text. render_page_list maps images positionally
        # (page_num = index + 1), so renumber the pending subset to keep its
        # block lookup aligned with the real page numbers.
        sub_map = {i + 1: pages_map[p.page_number]
                   for i, p in enumerate(pending) if p.page_number in pages_map}
        ctx.check_cancelled()
        ctx.progress(0.45, "Rendering text")
        jp = _JobProgress(ctx, base=0.45, span=0.45)
        pending_out, stats = render_page_list(
            images, sub_map, translations, config.font,
            chapter_id=chapter_id, chapter_config=config.chapter_id,
            font_path=None, use_batch_inpaint=True, progress=jp,
            text_color_rules=getattr(config.typography, "text_color", None),
        )
        for p, out in zip(pending, pending_out):
            done_images[p.page_number] = out
    else:
        stats = {"rendered_regions": 0, "elapsed": "0.0s"}
        ctx.progress(0.9, "All pages already rendered — exporting")

    output_images = [done_images[p.page_number] for p in pages]

    # Save rendered previews + exports
    ctx.progress(0.92, "Exporting")
    outputs_dir = _project_media(project) / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    rendered_files: list[dict] = []
    safe_name = re.sub(r"[^\w\-]+", "_", project.name).strip("_") or "output"
    is_webtoon = project.pdf_type == Project.PDFType.MANHWA and len(output_images) > 1
    requested = list(formats)

    if is_webtoon and "zip" in requested:
        # Webtoon mode: reassemble chunks into the single tall strip
        from comic_translator.pdf import concatenate_pages_vertically, save_webp_zip

        combined = concatenate_pages_vertically(output_images)
        zip_path = outputs_dir / f"{safe_name}_webtoon.zip"
        save_webp_zip([combined], str(zip_path), quality=95)
        del combined
        rendered_files.append({
            "name": f"{safe_name}_webtoon.zip (long strip)",
            "url": f"/media/projects/{project.id}/outputs/{zip_path.name}",
        })
    elif "zip" in requested:
        zip_path = outputs_dir / f"{safe_name}_translated.zip"
        save_webp_zip(output_images, str(zip_path), quality=95)
        rendered_files.append({"name": zip_path.name,
                               "url": f"/media/projects/{project.id}/outputs/{zip_path.name}"})
    if "psd" in requested:
        from comic_translator.psd_export import create_page_psd, save_psd_zip
        psd_list = []
        for p, out_img in zip(pages, output_images):
            page_blks = pages_map.get(p.page_number, [])
            psd_list.append(create_page_psd(
                out_img, page_blks, translations, config.font, None,
                chapter_id, config.chapter_id,
            ))
        psd_path = outputs_dir / f"{safe_name}_translated_psd.zip"
        save_psd_zip(psd_list, str(psd_path))
        rendered_files.append({"name": psd_path.name,
                               "url": f"/media/projects/{project.id}/outputs/{psd_path.name}"})
    if "pdf" in requested:
        pdf_path = outputs_dir / f"{safe_name}_translated.pdf"
        save_pdf(output_images, str(pdf_path), config.ocr.dpi)
        rendered_files.insert(0, {"name": pdf_path.name,
                                  "url": f"/media/projects/{project.id}/outputs/{pdf_path.name}"})

    project.status = Project.Status.DONE
    project.save(update_fields=["status"])
    ctx.log(f"Exported {len(rendered_files)} file(s): "
            f"{stats.get('rendered_regions', 0)} regions, {stats.get('elapsed', '')}")
    return {"files": rendered_files, "regions": stats.get("rendered_regions", 0)}


# ── Clean (inpaint only) & Render (text only) ───────────────────────────────


def _inpaint_pages(ctx: JobContext, project: Project, config,
                   pages, images: list[Image.Image],
                   pages_map: dict, translations: dict[str, str],
                   progress: tuple[float, float] = (0.05, 0.90)) -> None:
    """Inpaint translatable regions in-place in `images`, saving cleaned JPGs."""
    p_start, p_end = progress
    inp = config.inpaint
    use_batch = inp.method != "color"

    # Verbose config + backend logging: which backend really got created
    # (the engine silently falls back cv_auto -> opencv -> color on failure).
    ctx.log(f"Inpaint settings: method={inp.method} "
            f"pad_x={inp.padding_x} pad_y={inp.padding_y}")
    if use_batch:
        try:
            from comic_translator.inpaint import _create_backend
            bck = _create_backend(inp.method, device=inp.lama_device)
            backend_name = type(bck).__name__
            ctx.log(f"Inpaint backend: {backend_name} "
                    f"(device={inp.lama_device or 'auto'})")
            if backend_name.lower().removesuffix("backend").replace("_", "") != inp.method.replace("_", ""):
                ctx.log(f"WARNING: backend '{inp.method}' unavailable — "
                        f"fell back to {backend_name}")
        except JobCancelled:
            raise
        except Exception as e:
            ctx.log(f"WARNING: inpaint backend unavailable ({e}) — using color fill")
            use_batch = False

    from comic_translator.renderer import erase_region
    from PIL import ImageDraw

    # Manual freehand marks count as regions to erase too — a page with only
    # marks (no translated blocks) still needs cleaning.
    mask_regions = _mask_regions_by_page(
        project, {p.page_number for p in pages}
    )

    def _page_regions(p) -> list[dict]:
        return [b.region for k, b in pages_map.get(p.page_number, [])
                if translations.get(k, "").strip() and not b.is_sfx]

    todo = [(idx, p, img) for idx, (p, img) in enumerate(zip(pages, images))
            if _page_regions(p) or mask_regions.get(p.page_number)]
    if not todo:
        ctx.log("No translated regions or marks to clean")
        return

    for n, (idx, p, img) in enumerate(todo):
        ctx.check_cancelled()
        regions = _page_regions(p) + mask_regions.get(p.page_number, [])

        def _fmt_region(r) -> str:
            tb = r.get("text_boxes") or []
            first = tb[0][0] if tb and tb[0] else None
            origin = "bbox" if not first else f"poly@{list(first)}"
            return f"({r['x1']},{r['y1']},{r['x2']},{r['y2']})[{origin}]"

        sizes = ", ".join(_fmt_region(r) for r in regions[:6])
        more = f" +{len(regions) - 6} more" if len(regions) > 6 else ""
        ctx.log(f"Page {p.page_number}: inpainting {len(regions)} region(s) [{sizes}{more}]")
        t0 = time.perf_counter()
        try:
            from comic_translator.inpaint import inpaint_batch

            def _cb(msg: str, _pct: float, _pg: int = p.page_number) -> None:
                # Choke point at region granularity: engine fires this per
                # mask/region step, so cancel stops inpainting mid-batch
                # instead of waiting for the whole page.
                ctx.check_cancelled()
                # Engine step messages (mask building, per-component solid-fill
                # vs LaMa decisions, quality fallbacks) → job log.
                ctx.log(f"  ↳ p{_pg}: {msg}")

            new_img = inpaint_batch(
                img, regions,
                pad_x=config.inpaint.padding_x,
                pad_y=config.inpaint.padding_y,
                method=config.inpaint.method,
                opencv_radius=config.inpaint.opencv_radius,
                opencv_method=config.inpaint.opencv_method,
                device=config.inpaint.lama_device,
                pcleaner_profile=config.inpaint.pcleaner_profile,
                pcleaner_cli_path=config.inpaint.pcleaner_cli_path,
                solid_ratio=config.inpaint.cv_auto_solid_ratio,
                color_bucket=config.inpaint.cv_auto_color_bucket,
                mask_pad=config.inpaint.cv_auto_mask_pad,
                progress_callback=_cb,
            )
            images[idx] = new_img
            _save_page_jpg(project, p.page_number, new_img, subdir="cleaned")
            ctx.log(f"Page {p.page_number}: cleaned OK in "
                    f"{time.perf_counter() - t0:.1f}s → cleaned/page-{p.page_number}.jpg")
        except JobCancelled:
            raise
        except Exception as e:
            ctx.log(f"Page {p.page_number}: inpaint FAILED "
                    f"({type(e).__name__}: {e}) — color fill fallback")
            draw = ImageDraw.Draw(images[idx])
            for k, b in pages_map.get(p.page_number, []):
                if translations.get(k, "").strip() and not b.is_sfx:
                    erase_region(draw, b.x1, b.y1, b.x2, b.y2,
                                 image=images[idx], text_boxes=b.text_boxes,
                                 inpaint_config=config.inpaint)
            for mr in mask_regions.get(p.page_number, []):
                erase_region(draw, mr["x1"], mr["y1"], mr["x2"], mr["y2"],
                             image=images[idx], text_boxes=mr["text_boxes"],
                             inpaint_config=config.inpaint)
            _save_page_jpg(project, p.page_number, images[idx], subdir="cleaned")
        ctx.progress(p_start + (p_end - p_start) * (n + 1) / len(todo),
                     f"Cleaned {n + 1}/{len(todo)}")


def preview_text_layout(project: Project, blocks: list[TextBlock]) -> dict:
    """Measure draft blocks without persisting them or running an image job."""
    from urllib.parse import quote
    from comic_translator.renderer import resolve_style, text_layout
    from PIL import ImageDraw

    config = _get_config(project).font
    result = {}
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for block in blocks:
        eb = block.to_engine_block()
        text = block.translation.strip()
        w, h = eb.x2 - eb.x1, eb.y2 - eb.y1
        if not text or eb.is_sfx or w < 10 or h < 10:
            result[str(block.id)] = {"skipped": True}
            continue
        style = resolve_style(
            eb.text_type, config, alignment_override=eb.alignment,
            font_override=eb.font_override, font_size_override=eb.font_size_override,
        )
        layout = text_layout(text, w, h, config, style.font_path,
                             eb.font_type, style.size_factor, style.font_size_max,
                             style.alignment)
        font = layout["font"]
        fp = Path(getattr(font, "path", "") or "").resolve()
        fonts_dir = Path(settings.FONTS_DIR).resolve()
        # Only advertise a font the existing authenticated font route can serve.
        if not fp.is_file() or fp.parent != fonts_dir or not hasattr(font, "getmetrics"):
            result[str(block.id)] = {"unavailable": True}
            continue
        bbox = layout["bbox"]
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        align = layout["align"]
        # The renderer anchors the whole multiline block from its measured
        # bbox; mirror that per line so preview lines land where ink does.
        sx = (w - tw - 4 if align == "right"
              else 4 if align == "left" else max(0, (w - tw) // 2))
        sy = max(0, (h - th) // 2)
        widths = [measure.textlength(line, font=font) for line in layout["lines"]]
        advance = measure.textbbox((0, 0), "A", font=font)[3] + layout["spacing"]
        ascent = font.getmetrics()[0]
        result[str(block.id)] = {
            "font_size": layout["font_size"],
            "rotation": eb.rotation,
            "font_url": f"/api/fonts/{quote(fp.name)}",
            "align": align,
            "lines": [
                {"text": line,
                 "x": sx + (w - 4 - sx if align == "right"
                            else 0 if align == "left" else tw / 2),
                 "y": sy + ascent + index * advance}
                for index, line in enumerate(layout["lines"])
            ],
        }
    return result


def _scoped_targets(project: Project, page_number: int | None):
    """Pages list + block map restricted to one page when requested."""
    qs = project.pages.order_by("page_number")
    if page_number is not None:
        qs = qs.filter(page_number=int(page_number))
    pages = list(qs)
    pages_map: dict[int, list[tuple[str, object]]] = {}
    translations: dict[str, str] = {}
    pnums = {p.page_number for p in pages}
    for blk in project.blocks.select_related("page").order_by(
            "page__page_number", "order"):
        if blk.page.page_number not in pnums:
            continue
        eb = blk.to_engine_block()
        pages_map.setdefault(blk.page.page_number, []).append((blk.key, eb))
        if blk.translation.strip():
            translations[blk.key] = blk.translation.strip()
    return pages, pages_map, translations


def _mask_regions_by_page(project: Project,
                          page_numbers: set[int] | None = None) -> dict[int, list[dict]]:
    """Manual freehand marks → engine-ready region dicts, grouped by page."""
    qs = project.mask_marks.select_related("page")
    if page_numbers is not None:
        qs = qs.filter(page__page_number__in=page_numbers)
    regions: dict[int, list[dict]] = {}
    for mark in qs:
        if len(mark.points) >= 3:
            regions.setdefault(mark.page.page_number, []).append(mark.region)
    return regions


def run_clean(ctx: JobContext) -> dict:
    """Inpaint original text away (no rendering). Params: page_number?"""
    project: Project = ctx.job.project
    params = ctx.job.params or {}
    page_number = params.get("page_number")

    project.status = Project.Status.APPLYING
    project.error_message = ""
    project.save(update_fields=["status", "error_message"])

    config = _get_config(project)
    pages, pages_map, translations = _scoped_targets(project, page_number)
    if not pages:
        raise RuntimeError("No pages to clean — run extract first")

    scope = f"page {page_number}" if page_number else f"{len(pages)} pages"
    total_regions = sum(1 for v in translations.values() if v.strip())
    ctx.log(f"Cleaning (inpainting) {scope}: {total_regions} translated "
            f"region(s), method={config.inpaint.method}")

    images: list[Image.Image] = []
    for p in pages:
        img = _load_page_image(project, p.page_number)
        if img is None:
            if not project.pdf_file:
                raise RuntimeError(f"Page {p.page_number} image is missing and this project has no PDF to re-render from")
            from comic_translator.pdf import render_page
            img = render_page(project.pdf_file.path, p.page_number, config.ocr.dpi)
            ctx.log(f"Page {p.page_number} rendered fresh from PDF")
        images.append(img)

    _inpaint_pages(ctx, project, config, pages, images, pages_map, translations)

    media_root = Path(settings.MEDIA_ROOT)
    cleaned = [
        p.page_number for p in pages
        if (media_root / "projects" / str(project.id) / "cleaned"
            / f"page-{p.page_number}.jpg").exists()
    ]
    # Settle the APPLYING status set at start — jobs that end without a
    # terminal status would leave the project stuck in "busy" forever.
    project.status = Project.Status.READY
    project.save(update_fields=["status"])
    ctx.log(f"Clean done: {cleaned}")
    return {"cleaned": cleaned}


def run_render_text(ctx: JobContext) -> dict:
    """Draw Persian translations onto cleaned (or freshly erased) pages.

    Params: chapter_id?, page_number?
    """
    from comic_translator.pdf import render_page as engine_render_page
    from comic_translator.renderer import erase_region, render_page_list
    from PIL import ImageDraw

    project: Project = ctx.job.project
    params = ctx.job.params or {}
    page_number = params.get("page_number")
    chapter_id = params.get("chapter_id", project.chapter_id) or ""

    project.status = Project.Status.APPLYING
    if chapter_id and not page_number:
        project.chapter_id = chapter_id
    project.error_message = ""
    project.save(update_fields=["chapter_id", "status", "error_message"])

    config = _get_config(project)
    pages, pages_map, translations = _scoped_targets(project, page_number)
    if not pages:
        raise RuntimeError("No pages to render — run extract first")

    scope = f"page {page_number}" if page_number else f"{len(pages)} pages"
    ctx.log(f"Rendering text on {scope} "
            f"({sum(1 for v in translations.values() if v)} regions)")

    ctx.check_cancelled()
    images: list[Image.Image] = []
    media_root = Path(settings.MEDIA_ROOT)
    for p in pages:
        cleaned_path = (media_root / "projects" / str(project.id)
                        / "cleaned" / f"page-{p.page_number}.jpg")
        if cleaned_path.exists():
            images.append(Image.open(cleaned_path).copy())
            continue
        # No cleaned version yet — erase with cheap color fill so the
        # Persian text does not land on top of the original.
        img = _load_page_image(project, p.page_number)
        if img is None:
            if not project.pdf_file:
                raise RuntimeError(f"Page {p.page_number} image is missing and this project has no PDF to re-render from")
            img = engine_render_page(project.pdf_file.path, p.page_number,
                                     config.ocr.dpi)
        draw = ImageDraw.Draw(img)
        for k, b in pages_map.get(p.page_number, []):
            if translations.get(k, "").strip() and not b.is_sfx:
                erase_region(draw, b.x1, b.y1, b.x2, b.y2,
                             image=img, text_boxes=b.text_boxes,
                             inpaint_config=config.inpaint)
        images.append(img)

    jp = _JobProgress(ctx, base=0.15, span=0.75)
    output_images, stats = render_page_list(
        images, {i + 1: pages_map.get(p.page_number, []) for i, p in enumerate(pages)},
        translations, config.font,
        chapter_id=chapter_id, chapter_config=config.chapter_id,
        font_path=None, use_batch_inpaint=True, progress=jp,
        text_color_rules=getattr(config.typography, "text_color", None),
    )

    rendered: list[int] = []
    for p, out_img in zip(pages, output_images):
        _save_page_jpg(project, p.page_number, out_img, subdir="rendered")
        rendered.append(p.page_number)

    ctx.log(f"Render done: pages {rendered}, "
            f"{stats.get('rendered_regions', 0)} regions")
    # Settle the APPLYING status set at start (mirrors run_clean).
    project.status = Project.Status.READY
    project.save(update_fields=["status"])
    return {"rendered": rendered, "regions": stats.get("rendered_regions", 0)}


# ── Re-OCR single page ──────────────────────────────────────────────────────


def run_reocr(ctx: JobContext) -> dict:
    """Re-run OCR for a single page with a quality preset."""
    from dataclasses import replace as dc_replace
    from comic_translator.pdf import render_page
    from comic_translator.ocr_pipeline import detect_page

    project: Project = ctx.job.project
    params = ctx.job.params or {}
    page_number = int(params["page_number"])
    quality = params.get("quality", "normal")
    config = _get_config(project)

    overrides = {}
    if quality == "high":
        overrides = dict(dpi=300, ocr_max_side=4000, ocr_det_limit_side_len=2560,
                         ocr_det_box_thresh=0.2, ocr_det_thresh=0.15)
    elif quality == "ultra":
        overrides = dict(dpi=400, ocr_max_side=4000, ocr_det_limit_side_len=3072,
                         ocr_det_box_thresh=0.15, ocr_det_thresh=0.1,
                         ocr_enable_angle_cls=True)
    if overrides:
        config = dc_replace(config, ocr=dc_replace(config.ocr, **overrides))

    dpi = overrides.get("dpi", config.ocr.dpi)
    ctx.log(f"Re-OCR page {page_number} [{quality}] dpi={dpi}")
    ctx.check_cancelled()
    if project.uses_page_sources:
        from .page_sources import source_image
        img = source_image(project, page_number)
    else:
        img = render_page(project.pdf_file.path, page_number, dpi)
    if not project.uses_page_sources and max(img.size) > config.ocr.standard_max_side:
        scale = config.ocr.standard_max_side / max(img.size)
        img = img.resize((int(img.size[0] * scale), int(img.size[1] * scale)),
                         Image.LANCZOS)

    pr = detect_page(img, config.ocr, page_index=page_number)
    _save_page_jpg(project, page_number, img)
    page_row, _ = Page.objects.update_or_create(
        project=project, page_number=page_number,
        defaults={"width": img.width, "height": img.height},
    )

    old_ids = list(project.blocks.filter(page=page_row).values_list("id", flat=True))
    with transaction.atomic():
        project.blocks.filter(page=page_row).delete()
        created = 0
        for j, blk in enumerate(pr.blocks):
            key = f"p{page_number}_d{j + 1}"
            suffix, base_key = 1, key
            while project.blocks.filter(key=key).exists():
                suffix += 1
                key = f"{base_key}_{suffix}"
            block_type = blk.text_type if blk.text_type in TextBlock.BlockType.values else "dialog"
            TextBlock.objects.create(
                project=project, page=page_row, key=key,
                original_text=blk.text,
                translation=(blk.translation_fa or "").strip(),
                block_type=block_type,
                x1=blk.x1, y1=blk.y1, x2=blk.x2, y2=blk.y2,
                text_boxes=blk.text_boxes or [],
                orientation=getattr(blk, "orientation", "") or "horizontal",
                order=j,
            )
            created += 1

    _refresh_counts(project)
    ctx.log(f"Re-OCR done: removed {len(old_ids)}, found {created} blocks")
    return {"found": created}
