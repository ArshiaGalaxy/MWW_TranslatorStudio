"""Configuration loading with env-var overrides and validation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from comic_translator.exceptions import ConfigError
from comic_translator.typography import (
    DEFAULT_TYPOGRAPHY_RULES,
    TypographyConfig,
    TypographyRules,
    build_typography_rules,
)

_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONFIG = _PROJECT_DIR / "config.json"


def _env(key: str, default: Any = None) -> Any:
    """Env override that only applies when the variable is non-empty — an
    exported-but-empty var (OPENROUTER_API_KEY="") must not wipe a valid
    config-file value."""
    val = os.environ.get(key)
    return val if val else default


def _as_bool(raw: Any, default: bool) -> bool:
    """Strict boolean coercion: JSON booleans pass through; the strings
    "true"/"false" (any case) are honored so a user typo like "False" no
    longer silently evaluates as True."""
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str):
        low = raw.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
    raise ConfigError(
        f"Invalid boolean value: {raw!r} (use true/false)"
    )


@dataclass(frozen=True)
class OCRConfig:
    dpi: int = 200
    confidence_min: float = 0.5
    dbscan_eps: float = 2.5
    pdf_type: str = "manga"
    ocr_version: str = "PP-OCRv6"
    ocr_max_side: int = 3000
    standard_max_side: int = 3000
    max_chunk_height: int = 2400
    cross_page_height: int = 600
    enable_cross_page_merge: bool = True
    duplicate_iou_threshold: float = 0.5
    long_strip_aspect_ratio_threshold: float = 1.5
    size_consistency_threshold: float = 0.15
    boundary_region_height: int = 200
    boundary_dialogue_min_height: int = 20
    manhwa_concat_width: int = 1200
    manhwa_concat_overlap: int = 500
    angle_merge_threshold: float = 0.0
    ocr_det_limit_side_len: int = 1920
    ocr_det_unclip_ratio: float = 2.5
    ocr_det_box_thresh: float = 0.3
    ocr_det_thresh: float = 0.2
    ocr_enable_angle_cls: bool = True
    # Recognition confidence floor — separate knob from the DETECTION
    # threshold; seeding rec from det accepted garbage OCR strings.
    text_rec_score_thresh: float = 0.5


@dataclass(frozen=True)
class FontConfig:
    path_normal: str | None = None
    path_sfx: str | None = None
    path_thinking: str | None = None
    size_max: int = 60
    size_min: int = 15
    stroke_width: int = 1
    tall_render_chunk_size: int = 3


@dataclass(frozen=True)
class ChapterIDConfig:
    color: str = "#8E44AD"
    stroke_color: str = "#2C0B3E"
    stroke_width: int = 2
    size: int = 0


@dataclass(frozen=True)
class InpaintConfig:
    method: str = "cv_auto"
    opencv_radius: int = 5
    opencv_method: str = "ns"
    cv_auto_solid_ratio: float = 0.85
    cv_auto_color_bucket: int = 16
    cv_auto_mask_pad: int = 20
    lama_device: str = "auto"
    padding_x: int = 30
    padding_y: int = 30
    pcleaner_profile: str | None = None
    pcleaner_cli_path: str | None = None


@dataclass(frozen=True)
class TranslatorConfig:
    provider: str = "openrouter"
    temperature: float = 0.2
    chunk_size: int = 12
    system_prompt: str = ""
    user_prompt: str = "Translate this JSON:\n\n{dialogs}\n\nReturn JSON only."
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-20b:free"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    custom_base_url: str = ""
    custom_api_key: str = ""
    custom_model: str = ""


@dataclass(frozen=True)
class AppConfig:
    ocr: OCRConfig = field(default_factory=OCRConfig)
    font: FontConfig = field(default_factory=FontConfig)
    chapter_id: ChapterIDConfig = field(default_factory=ChapterIDConfig)
    inpaint: InpaintConfig = field(default_factory=InpaintConfig)
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)
    typography: TypographyRules = field(
        default_factory=lambda: DEFAULT_TYPOGRAPHY_RULES
    )


def _build_config(raw: dict[str, Any]) -> AppConfig:
    ocr_raw = raw.get("ocr", {})
    font_raw = raw.get("font", {})
    ch_raw = raw.get("chapter_id", {})
    inp_raw = raw.get("inpaint", {})
    t_raw = raw.get("translator", {})
    typo_raw = raw.get("typography", {})

    or_cfg = t_raw.get("openrouter", {})
    gem_cfg = t_raw.get("gemini", {})
    custom_cfg = t_raw.get("custom", {})

    font_config = FontConfig(
        path_normal=font_raw.get("path_normal"),
        path_sfx=font_raw.get("path_sfx"),
        path_thinking=font_raw.get("path_thinking"),
        size_max=int(font_raw.get("size_max", 60)),
        size_min=int(font_raw.get("size_min", 15)),
        stroke_width=int(font_raw.get("stroke_width", 1)),
        tall_render_chunk_size=int(font_raw.get("tall_render_chunk_size", 3)),
    )

    typography_config = TypographyConfig(
        # The "typography" section only exposes the text-color matching knobs
        # the render pipeline actually consumes; the "font" section is the
        # single source of truth for font sizes.
        match_original_text_color=_as_bool(typo_raw.get("match_original_text_color"), True),
        text_color_contrast_min=float(typo_raw.get("text_color_contrast_min", 3.0)),
        ink_color_distance_threshold=float(typo_raw.get("ink_color_distance_threshold", 90.0)),
        ink_quantization_step=int(typo_raw.get("ink_quantization_step", 16)),
    )

    typography = build_typography_rules(typography_config)

    return AppConfig(
        ocr=OCRConfig(
            dpi=int(_env("OCR_DPI", ocr_raw.get("dpi", 200))),
            confidence_min=float(ocr_raw.get("confidence_min", 0.5)),
            dbscan_eps=float(ocr_raw.get("dbscan_eps", 2.5)),
            pdf_type=ocr_raw.get("pdf_type", "manga"),
            ocr_version=ocr_raw.get("ocr_version", "PP-OCRv6"),
            ocr_max_side=int(ocr_raw.get("ocr_max_side", 3000)),
            standard_max_side=int(ocr_raw.get("standard_max_side", 3000)),
            max_chunk_height=int(ocr_raw.get("max_chunk_height", 2400)),
            cross_page_height=int(ocr_raw.get("cross_page_height", 600)),
            enable_cross_page_merge=_as_bool(ocr_raw.get("enable_cross_page_merge"), True),
            duplicate_iou_threshold=float(ocr_raw.get("duplicate_iou_threshold", 0.5)),
            long_strip_aspect_ratio_threshold=float(
                ocr_raw.get("long_strip_aspect_ratio_threshold", 1.5)
            ),
            size_consistency_threshold=float(
                ocr_raw.get("size_consistency_threshold", 0.15)
            ),
            boundary_region_height=int(ocr_raw.get("boundary_region_height", 200)),
            boundary_dialogue_min_height=int(
                ocr_raw.get("boundary_dialogue_min_height", 20)
            ),
            manhwa_concat_width=int(ocr_raw.get("manhwa_concat_width", 1200)),
            manhwa_concat_overlap=int(ocr_raw.get("manhwa_concat_overlap", 500)),
            angle_merge_threshold=float(ocr_raw.get("angle_merge_threshold", 0.0)),
            ocr_det_limit_side_len=int(ocr_raw.get("ocr_det_limit_side_len", 1920)),
            ocr_det_unclip_ratio=float(ocr_raw.get("ocr_det_unclip_ratio", 2.5)),
            ocr_det_box_thresh=float(ocr_raw.get("ocr_det_box_thresh", 0.3)),
            ocr_det_thresh=float(ocr_raw.get("ocr_det_thresh", 0.2)),
            ocr_enable_angle_cls=_as_bool(ocr_raw.get("ocr_enable_angle_cls"), True),
            text_rec_score_thresh=float(ocr_raw.get("text_rec_score_thresh", 0.5)),
        ),
        font=font_config,
        chapter_id=ChapterIDConfig(
            color=ch_raw.get("color", "#8E44AD"),
            stroke_color=ch_raw.get("stroke_color", "#2C0B3E"),
            stroke_width=int(ch_raw.get("stroke_width", 2)),
            size=int(ch_raw.get("size", 0)),
        ),
        inpaint=InpaintConfig(
            method=_env("INPAINT_METHOD", inp_raw.get("method", "cv_auto")),
            opencv_radius=int(inp_raw.get("opencv_radius", 5)),
            opencv_method=inp_raw.get("opencv_method", "ns"),
            cv_auto_solid_ratio=float(inp_raw.get("cv_auto_solid_ratio", 0.85)),
            cv_auto_color_bucket=int(inp_raw.get("cv_auto_color_bucket", 16)),
            cv_auto_mask_pad=int(inp_raw.get("cv_auto_mask_pad", 20)),
            lama_device=inp_raw.get("lama_device", "auto"),
            padding_x=int(inp_raw.get("padding_x", 30)),
            padding_y=int(inp_raw.get("padding_y", 30)),
            pcleaner_profile=inp_raw.get("pcleaner_profile") or None,
            pcleaner_cli_path=inp_raw.get("pcleaner_cli_path") or None,
        ),
        translator=TranslatorConfig(
            provider=_env("TRANSLATOR_PROVIDER", t_raw.get("provider", "openrouter")),
            temperature=float(t_raw.get("temperature", 0.2)),
            chunk_size=int(t_raw.get("chunk_size", 12)),
            system_prompt=t_raw.get("system_prompt", ""),
            user_prompt=t_raw.get(
                "user_prompt", "Translate this JSON:\n\n{dialogs}\n\nReturn JSON only."
            ),
            openrouter_api_key=_env("OPENROUTER_API_KEY", or_cfg.get("api_key", "")),
            openrouter_model=or_cfg.get("model", "openai/gpt-oss-20b:free"),
            gemini_api_key=_env("GEMINI_API_KEY", gem_cfg.get("api_key", "")),
            gemini_model=gem_cfg.get("model", "gemini-2.0-flash"),
            custom_base_url=_env("CUSTOM_BASE_URL", custom_cfg.get("base_url", "")),
            custom_api_key=_env("CUSTOM_API_KEY", custom_cfg.get("api_key", "")),
            custom_model=custom_cfg.get("model", ""),
        ),
        typography=typography,
    )


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load config from JSON file with env-var overrides."""
    load_dotenv()

    path = Path(config_path) if config_path else _DEFAULT_CONFIG
    if not path.exists():
        return AppConfig()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {path}: {e}") from e
    except Exception as e:
        raise ConfigError(f"Failed to read config file {path}: {e}") from e

    return _build_config(raw)
