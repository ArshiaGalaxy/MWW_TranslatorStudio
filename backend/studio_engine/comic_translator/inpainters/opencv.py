"""OpenCV Navier-Stokes / Telea inpainting backend."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from comic_translator.inpainters.base import InpainterBackend
from comic_translator.inpainters.common import (
    build_combined_mask,
    build_mask_pil,
    cv2_edge_blend,
    cv2_to_pil,
    pil_to_cv2,
)


def _clahe_enhance(bgr: np.ndarray) -> np.ndarray:
    """Apply CLAHE to the L channel in LAB space for subtle contrast boost."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_ch)
    enhanced_lab = cv2.merge([l_enhanced, a_ch, b_ch])
    return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)


class OpenCVBackend(InpainterBackend):
    """OpenCV inpainting -- always available, no extra deps."""

    @property
    def name(self) -> str:
        return "opencv"

    @property
    def is_neural(self) -> bool:
        return False

    def load(self, **kwargs) -> None:
        pass  # OpenCV is always available

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
        opencv_method: str = "ns",
        opencv_radius: int = 5,
        **kwargs,
    ) -> Image.Image:
        mask = build_mask_pil(image.size, x1, y1, x2, y2, text_boxes, pad_x, pad_y)
        cv_img = pil_to_cv2(image)
        flag = cv2.INPAINT_NS if opencv_method == "ns" else cv2.INPAINT_TELEA
        result = cv2.inpaint(cv_img, np.array(mask), inpaintRadius=opencv_radius, flags=flag)
        result = _clahe_enhance(result)
        return cv2_to_pil(cv2_edge_blend(np.array(mask), result, cv_img))

    def inpaint_batch(
        self,
        image: Image.Image,
        regions: list[dict],
        pad: int = 30,
        pad_x: int = 30,
        pad_y: int = 30,
        opencv_method: str = "ns",
        opencv_radius: int = 5,
        **kwargs,
    ) -> Image.Image:
        mask = build_combined_mask(image.size, regions, pad_x, pad_y)
        mask_np = np.array(mask)
        cv_img = pil_to_cv2(image)
        flag = cv2.INPAINT_NS if opencv_method == "ns" else cv2.INPAINT_TELEA
        result = cv2.inpaint(cv_img, mask_np, inpaintRadius=opencv_radius, flags=flag)
        result = _clahe_enhance(result)
        return cv2_to_pil(cv2_edge_blend(mask_np, result, cv_img))
