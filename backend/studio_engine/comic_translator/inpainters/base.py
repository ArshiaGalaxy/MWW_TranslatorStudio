"""Abstract base class for inpainting backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from PIL import Image

ProgressCallback = Callable[[str, float], None] | None


class InpainterBackend(ABC):
    """Base class for all inpainting backends.

    Each backend must implement load(), inpaint_single(), and inpaint_batch().
    Backends are responsible for their own model loading, preprocessing, and
    postprocessing. The dispatch layer in inpaint.py delegates to these methods.

    All methods accept an optional ``progress_callback`` parameter with
    signature ``(step: str, progress: float) -> None`` where *progress* is
    0.0–1.0.  Backends that support it should call the callback at each
    meaningful processing step so the caller can display a progress bar.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this backend (e.g. 'lama', 'aotgan')."""
        ...

    @property
    def is_neural(self) -> bool:
        """Whether this backend uses a neural network (affects memory cleanup)."""
        return False

    @abstractmethod
    def load(self, **kwargs) -> None:
        """Load model weights / initialize the backend.

        Called lazily on first use. Must be idempotent.
        """
        ...

    @abstractmethod
    def inpaint_single(
        self,
        image: Image.Image,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        text_boxes: list | None = None,
        pad: int = 30,
        pad_x: int = 30,
        pad_y: int = 30,
        progress_callback: ProgressCallback = None,
        **kwargs,
    ) -> Image.Image:
        """Inpaint a single text region.

        Args:
            image: Full RGB page image.
            x1, y1, x2, y2: Bounding box of the text region.
            text_boxes: Optional list of text-box polygons for precise masking.
            pad: Legacy uniform padding (fallback if pad_x/pad_y not used).
            pad_x: Horizontal padding around the mask.
            pad_y: Vertical padding around the mask.
            progress_callback: Optional ``(step, progress)`` callback.
            **kwargs: Backend-specific parameters (device, opencv_radius, etc.).

        Returns:
            The image with the region inpainted.
        """
        ...

    @abstractmethod
    def inpaint_batch(
        self,
        image: Image.Image,
        regions: list[dict],
        pad: int = 30,
        pad_x: int = 30,
        pad_y: int = 30,
        progress_callback: ProgressCallback = None,
        **kwargs,
    ) -> Image.Image:
        """Inpaint multiple text regions at once.

        Args:
            image: Full RGB page image.
            regions: List of region dicts with keys x1, y1, x2, y2,
                     and optionally text_boxes.
            pad: Legacy uniform padding (fallback if pad_x/pad_y not used).
            pad_x: Horizontal padding around each mask.
            pad_y: Vertical padding around each mask.
            progress_callback: Optional ``(step, progress)`` callback.
            **kwargs: Backend-specific parameters.

        Returns:
            The image with all regions inpainted.
        """
        ...
