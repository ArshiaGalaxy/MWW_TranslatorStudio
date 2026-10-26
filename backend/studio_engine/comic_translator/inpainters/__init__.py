"""Inpainting backend factory.

Usage:
    from comic_translator.inpainters import create_inpainter, BACKENDS
    painter = create_inpainter("cv_auto", config.inpaint)
    result = painter.inpaint_batch(image, regions)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from comic_translator.inpainters.base import InpainterBackend

if TYPE_CHECKING:
    from comic_translator.config import InpaintConfig

logger = logging.getLogger(__name__)

# Registry of backend names -> lazy import paths
_BACKEND_REGISTRY: dict[str, tuple[str, str]] = {
    "cv_auto": ("comic_translator.inpainters.cv_auto", "CVAutoBackend"),
    "color": ("comic_translator.inpainters.color", "ColorFillBackend"),
    "opencv": ("comic_translator.inpainters.opencv", "OpenCVBackend"),
    "pcleaner": ("comic_translator.inpainters.pcleaner", "PcleanerBackend"),
}

BACKENDS = list(_BACKEND_REGISTRY.keys())


def create_inpainter(method: str, config: InpaintConfig | None = None) -> InpainterBackend:
    """Create an inpainting backend by name.

    Args:
        method: Backend identifier ('cv_auto', 'color', 'opencv', 'pcleaner').
        config: InpaintConfig with backend-specific settings.

    Returns:
        Initialized InpainterBackend instance.

    Raises:
        ValueError: If method is unknown.
    """
    entry = _BACKEND_REGISTRY.get(method)
    if entry is None:
        raise ValueError(
            f"Unknown inpainting method: {method!r}. "
            f"Available: {', '.join(BACKENDS)}"
        )

    module_path, class_name = entry
    try:
        import importlib
        module = importlib.import_module(module_path)
        backend_cls = getattr(module, class_name)
    except (ImportError, AttributeError, OSError) as e:
        raise ValueError(
            f"Failed to load backend {method!r}: {e}"
        ) from e

    backend = backend_cls()

    # Load with config parameters if available
    if config is not None:
        load_kwargs = _extract_load_kwargs(method, config)
        try:
            backend.load(**load_kwargs)
        except Exception as e:
            logger.warning("Failed to load backend %r: %s", method, e)
            raise ValueError(f"Failed to load backend {method!r}: {e}") from e

    return backend


def _extract_load_kwargs(method: str, config: InpaintConfig) -> dict:
    """Extract backend-specific load kwargs from InpaintConfig."""
    base = {}

    if method == "pcleaner":
        base["cli_path"] = getattr(config, "pcleaner_cli_path", None)
        base["pcleaner_profile"] = getattr(config, "pcleaner_profile", None)

    return base


def get_backend_names() -> list[str]:
    """Return list of available backend names."""
    return BACKENDS[:]
