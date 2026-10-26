"""PSD file export using psd-tools."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from comic_translator.config import FontConfig
from comic_translator.exceptions import ComicTranslatorError
from comic_translator.models import Block
from comic_translator.renderer import (
    _luminance,
    _resolve_text_color,
    _reshape_persian,
    _sample_bg_color,
    _text_width,
    find_font,
    fit_font_size,
    resolve_style,
)
from comic_translator.typography import TextColorRules

logger = logging.getLogger(__name__)


def _render_text_on_transparent(
    text: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    font_config: FontConfig,
    font_path: str | None,
    bg_image: Image.Image,
    font_type: str = "normal",
    stroke_width: int | None = None,
    stroke_color: str | None = None,
    alignment: str = "center",
    size_factor: float = 1.0,
    font_size_max: int | None = None,
    style_text_color: str | None = None,
    original_text_color: str | None = None,
    text_color_rules: TextColorRules | None = None,
    rotation: float = 0.0,
) -> Image.Image | None:
    """Render text onto a transparent RGBA image sized to match the page.

    Returns a RGBA image of the full page size with text painted at the
    correct position, or *None* when the text is empty / box too small.
    """
    if not text.strip():
        return None

    box_w = x2 - x1
    box_h = y2 - y1
    if box_w < 10 or box_h < 10:
        return None

    page_w, page_h = bg_image.size
    shaped = _reshape_persian(text)

    fp = font_path or find_font(font_config, font_type)
    if font_size_max is not None:
        effective_max = max(font_config.size_min, font_size_max)
    else:
        effective_max = max(font_config.size_min, int(font_config.size_max * size_factor))
    font, lines, fs = fit_font_size(shaped, fp, box_w, box_h,
                                    effective_max, font_config.size_min)

    bg_color = _sample_bg_color(bg_image, x1, y1, x2, y2)
    text_color = _resolve_text_color(
        bg_color, text_color_rules, style_text_color, original_text_color
    )

    sw = stroke_width if stroke_width is not None else font_config.stroke_width
    if sw > 0:
        sc = stroke_color if stroke_color is not None else (
            "#FFFFFF" if _luminance(text_color) < 0.5 else "#000000"
        )
    else:
        sc = None

    # Create transparent canvas for the full page
    layer = Image.new("RGBA", (page_w, page_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    spacing = max(8, fs // 3)
    joined = "\n".join(lines)
    bbox = draw.multiline_textbbox((0, 0), joined, font=font, spacing=spacing, align="center")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    if alignment == "rtl":
        sx = x2 - text_w - 4
    elif alignment == "ltr":
        sx = x1 + 4
    else:
        sx = x1 + max(0, (box_w - text_w) // 2)
    sy = y1 + max(0, (box_h - text_h) // 2)

    if sw > 0 and sc:
        draw.multiline_text((sx, sy), joined, fill=text_color, font=font,
                   stroke_width=sw, stroke_fill=sc, spacing=spacing, align="center")
    else:
        draw.multiline_text((sx, sy), joined, fill=text_color, font=font, spacing=spacing, align="center")

    if rotation:
        # Rotate the text layer around the box center so it stays anchored
        # where the box is (PIL rotate is counterclockwise; UI is clockwise).
        cx, cy = x1 + box_w / 2, y1 + box_h / 2
        layer = layer.rotate(-rotation, resample=Image.Resampling.BICUBIC,
                             center=(cx, cy))
        layer = layer.crop((0, 0, page_w, page_h))

    return layer


def _scale_block(blk: Block, scale: float) -> Block:
    """Return a copy of the block with scaled coordinates."""
    scaled_boxes = [
        [
            (int(px * scale), int(py * scale))
            for px, py in ring
        ]
        for ring in blk.text_boxes
    ] if blk.text_boxes else []
    return Block(
        page=blk.page,
        text=blk.text,
        x1=int(blk.x1 * scale),
        y1=int(blk.y1 * scale),
        x2=int(blk.x2 * scale),
        y2=int(blk.y2 * scale),
        translation_fa=blk.translation_fa,
        cover=blk.cover,
        sfx=blk.sfx,
        thinking=blk.thinking,
        text_boxes=scaled_boxes,
        text_type=blk.text_type,
        color=blk.color,
        stroke_color=blk.stroke_color,
        stroke_size=blk.stroke_size,
        alignment=blk.alignment,
        font_override=blk.font_override,
        font_size_override=blk.font_size_override,
        orientation=blk.orientation,
        rotation=blk.rotation,
    )


def _build_layer_from_image(
    psd,
    image: Image.Image,
    name: str,
    top: int = 0,
    left: int = 0,
    opacity: int = 255,
):
    """Build a PSD layer from a PIL Image using low-level API.

    This bypasses `create_pixel_layer()` and `PixelLayer.frompil()` to avoid
    the `has_transparency_data` AttributeError in some Pillow/psd-tools combos.
    """
    from psd_tools.api.layers import PixelLayer
    from psd_tools.constants import ChannelID, Compression
    from psd_tools.psd.layer_and_mask import (
        ChannelData,
        ChannelDataList,
        ChannelInfo,
        LayerRecord,
    )
    image = image.convert("RGBA")
    w, h = image.size

    layer_record = LayerRecord(
        top=top,
        left=left,
        bottom=top + h,
        right=left + w,
        channel_info=[],
    )
    layer_record.name = name
    layer_record.opacity = opacity

    channel_data_list = ChannelDataList()
    compression = Compression.RLE
    depth = 8  # 8-bit per channel

    # === Transparency channel (ChannelID.TRANSPARENCY_MASK = -1) ===
    transparency = ChannelData(compression)
    # Check for alpha channel manually instead of using has_transparency_data
    has_alpha = "A" in image.getbands()
    if has_alpha:
        alpha_idx = image.getbands().index("A")
        image_bytes = image.getchannel(alpha_idx).tobytes()
    else:
        image_bytes = b"\xff" * (w * h)
    transparency.set_data(image_bytes, w, h, depth, version=psd._record.header.version)
    transparency_info = ChannelInfo(
        id=ChannelID.TRANSPARENCY_MASK,
        length=len(transparency.data) + 2,
    )
    layer_record.channel_info.append(transparency_info)
    channel_data_list.append(transparency)

    # === Color channels (R, G, B) ===
    rgb_image = image.convert("RGB")
    for i in range(3):
        ch = ChannelData(compression)
        ch_data = rgb_image.getchannel(i).tobytes()
        ch.set_data(ch_data, w, h, depth, version=psd._record.header.version)
        ch_info = ChannelInfo(id=ChannelID(i), length=len(ch.data) + 2)
        channel_data_list.append(ch)
        layer_record.channel_info.append(ch_info)

    layer = PixelLayer(psd, layer_record, channel_data_list)
    psd._layers.append(layer)
    psd._update_record()
    return layer


def create_page_psd(
    page_image: Image.Image,
    page_blocks: list[tuple[str, Block]],
    translations: dict[str, str],
    font_config: FontConfig,
    font_path: str | None = None,
    chapter_id: str = "",
    chapter_id_config: object | None = None,
    text_color_rules: TextColorRules | None = None,
    original_text_colors: dict[str, str] | None = None,
):
    """Create a layered PSD for a single page.

    Layers (bottom -> top):
        - Background — the translated page image (RGB)
        - One layer per translated text block (RGBA, named by block key)

    Returns a PSDImage instance.
    """
    try:
        from psd_tools import PSDImage
    except ImportError as e:
        raise ComicTranslatorError(
            "psd-tools not installed. Run: pip install psd-tools"
        ) from e

    psd_target_width = 1200

    orig_w, orig_h = page_image.size
    if orig_w != psd_target_width:
        scale = psd_target_width / orig_w
        new_h = int(orig_h * scale)
        page_image = page_image.resize((psd_target_width, new_h), Image.LANCZOS)
        page_blocks = [
            (key, _scale_block(blk, scale)) for key, blk in page_blocks
        ]

    w, h = page_image.size

    # Convert to clean RGB for background
    clean_page = page_image.convert("RGB")

    psd = PSDImage.new(mode="RGB", size=(w, h), depth=8)

    # Background layer
    _build_layer_from_image(psd, clean_page, name="Background", top=0, left=0, opacity=255)

    # Text layers
    for key, blk in page_blocks:
        fa = translations.get(key, "").strip()
        if not fa:
            continue

        style = resolve_style(
            blk.text_type, font_config,
            color_override=blk.color,
            stroke_color_override=blk.stroke_color,
            stroke_size_override=blk.stroke_size,
            alignment_override=blk.alignment,
            font_override=blk.font_override,
            font_size_override=blk.font_size_override,
        )
        text_layer = _render_text_on_transparent(
            fa, blk.x1, blk.y1, blk.x2, blk.y2,
            font_config, style.font_path, clean_page,
            font_type=blk.font_type,
            stroke_width=style.stroke_width,
            stroke_color=style.stroke_color,
            alignment=style.alignment,
            size_factor=style.size_factor,
            font_size_max=style.font_size_max,
            style_text_color=style.text_color,
            original_text_color=original_text_colors.get(key) if original_text_colors else None,
            text_color_rules=text_color_rules,
            rotation=blk.rotation,
        )
        if text_layer is None:
            continue

        _build_layer_from_image(
            psd, text_layer, name=key, top=0, left=0, opacity=255,
        )

    return psd


def save_psd_zip(
    psd_list: list,
    output_path: str | Path,
    naming: str = "page_{idx:03d}.psd",
) -> Path:
    """Save multiple PSDImage objects into a ZIP archive."""
    output_path = Path(output_path)

    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, psd in enumerate(psd_list, start=1):
            buf = io.BytesIO()
            psd.save(buf)
            name = naming.format(idx=idx)
            zf.writestr(name, buf.getvalue())

    return output_path
