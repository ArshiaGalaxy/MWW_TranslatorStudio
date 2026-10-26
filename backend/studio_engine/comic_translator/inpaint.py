"""Text region inpainting with multiple backends.

Backends (auto-detected, best available first):
  - cv_auto: OpenCV inpainting + automatic solid-color normalization
  - color:   Solid background-color fill (fastest, lowest quality)
  - opencv:  OpenCV Navier-Stokes / Telea (always available, no extra deps)
  - pcleaner: Full pipeline via PanelCleaner (text detection + masking + inpainting)

Fallback chain: cv_auto -> opencv -> color

All backends implement the InpainterBackend interface defined in
comic_translator.inpainters.base. This module provides backward-compatible
free functions that delegate to the backend classes.
"""

from __future__ import annotations

import logging

from PIL import Image

logger = logging.getLogger(__name__)


# ── Unified dispatch (backward-compatible API) ────────────────────────────────


def inpaint(
    image: Image.Image,
    x1: int, y1: int, x2: int, y2: int,
    text_boxes: list | None = None,
    pad_x: int = 30,
    pad_y: int = 30,
    method: str = "cv_auto",
    opencv_radius: int = 5,
    opencv_method: str = "ns",
    device: str = "auto",
    pcleaner_profile: str | None = None,
    pcleaner_cli_path: str | None = None,
    solid_ratio: float = 0.85,
    color_bucket: int = 16,
    mask_pad: int = 0,
    progress_callback=None,
    ) -> Image.Image:
    backend = _create_backend(
        method, device=device,
        pcleaner_cli_path=pcleaner_cli_path, pcleaner_profile=pcleaner_profile,
    )
    return backend.inpaint_single(
        image, x1, y1, x2, y2,
        text_boxes=text_boxes,
        pad_x=pad_x,
        pad_y=pad_y,
        opencv_radius=opencv_radius,
        opencv_method=opencv_method,
        device=device,
        pcleaner_profile=pcleaner_profile,
        pcleaner_cli_path=pcleaner_cli_path,
        solid_ratio=solid_ratio,
        color_bucket=color_bucket,
        mask_pad=mask_pad,
        progress_callback=progress_callback,
    )


def inpaint_batch(
    image: Image.Image,
    regions: list[dict],
    pad_x: int = 30,
    pad_y: int = 30,
    method: str = "cv_auto",
    opencv_radius: int = 5,
    opencv_method: str = "ns",
    device: str = "auto",
    pcleaner_profile: str | None = None,
    pcleaner_cli_path: str | None = None,
    solid_ratio: float = 0.85,
    color_bucket: int = 16,
    mask_pad: int = 0,
    progress_callback=None,
    ) -> Image.Image:
    backend = _create_backend(
        method, device=device,
        pcleaner_cli_path=pcleaner_cli_path, pcleaner_profile=pcleaner_profile,
    )
    return backend.inpaint_batch(
        image, regions,
        pad_x=pad_x,
        pad_y=pad_y,
        opencv_radius=opencv_radius,
        opencv_method=opencv_method,
        device=device,
        pcleaner_profile=pcleaner_profile,
        pcleaner_cli_path=pcleaner_cli_path,
        solid_ratio=solid_ratio,
        color_bucket=color_bucket,
        mask_pad=mask_pad,
        progress_callback=progress_callback,
    )


_backend_cache: dict[str, object] = {}

# Fallback chain: if a backend fails to load, try these in order
_FALLBACK: dict[str, list[str]] = {
    "cv_auto": ["opencv", "color"],
    "pcleaner": ["opencv", "color"],
}


def _create_backend(method: str, device: str | None = None,
                    pcleaner_cli_path: str | None = None,
                    pcleaner_profile: str | None = None):
    """Create an inpainting backend — cached, with automatic fallback on load failure."""
    from comic_translator.config import InpaintConfig
    from comic_translator.inpainters import create_inpainter

    # Build cache key from the parameters that affect backend selection
    cache_key = (
        f"{method}:{device or 'auto'}"
        f":{pcleaner_cli_path or ''}:{pcleaner_profile or ''}"
    )
    if cache_key in _backend_cache:
        return _backend_cache[cache_key]

    cfg = InpaintConfig(
        method=method,
        lama_device=device or "auto",
        pcleaner_cli_path=pcleaner_cli_path,
        pcleaner_profile=pcleaner_profile,
    )

    # Try the requested backend, then fallbacks
    candidates = [method] + _FALLBACK.get(method, ["opencv", "color"])
    last_err: Exception | None = None
    for m in candidates:
        try:
            backend = create_inpainter(m, cfg)
            _backend_cache[cache_key] = backend
            if m != method:
                logger.warning("Backend %r unavailable, fell back to %r", method, m)
            return backend
        except Exception as e:
            last_err = e
            logger.warning("Backend %r failed: %s", m, e)
            continue

    raise ValueError(f"All backends failed (tried {candidates}): {last_err}")
