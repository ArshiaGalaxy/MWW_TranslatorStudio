"""Solid-color fill inpainting backend."""

from __future__ import annotations

from PIL import Image, ImageDraw

from comic_translator.inpainters.base import InpainterBackend


class ColorFillBackend(InpainterBackend):
    """Fast solid-color fill -- no neural network, always available."""

    @property
    def name(self) -> str:
        return "color"

    @property
    def is_neural(self) -> bool:
        return False

    def load(self, **kwargs) -> None:
        pass  # No model to load

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
        **kwargs,
    ) -> Image.Image:
        from comic_translator.renderer import _sample_bg_color, _sample_interior_color, _invalidate_np_cache

        interior = _sample_interior_color(image, x1, y1, x2, y2)
        bg_hex = _sample_bg_color(image, x1, y1, x2, y2)
        r, g, b = 255, 255, 255

        if interior:
            import random
            box_w = x2 - x1
            box_h = y2 - y1
            if box_w > 0 and box_h > 0:
                uniform_count = 0
                test_points = 50
                for _ in range(test_points):
                    test_x = random.randint(x1, x2 - 1)
                    test_y = random.randint(y1, y2 - 1)
                    test_pixel = image.getpixel((test_x, test_y))
                    if len(test_pixel) == 3:
                        pixel_r, pixel_g, pixel_b = test_pixel
                    elif len(test_pixel) == 4:
                        pixel_r, pixel_g, pixel_b, _ = test_pixel
                    else:
                        pixel_r, pixel_g, pixel_b = test_pixel
                    is_white = (
                        abs(pixel_r - 255) <= 5 and
                        abs(pixel_g - 255) <= 5 and
                        abs(pixel_b - 255) <= 5
                    )
                    if is_white:
                        uniform_count += 1
                if uniform_count >= int(test_points * 0.9):
                    fill = (255, 255, 255, 255) if image.mode == "RGBA" else (255, 255, 255)
                else:
                    if bg_hex and bg_hex.startswith("#"):
                        r, g, b = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
                    fill = (r, g, b, 255) if image.mode == "RGBA" else (r, g, b)
            else:
                if bg_hex and bg_hex.startswith("#"):
                    r, g, b = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
                fill = (r, g, b, 255) if image.mode == "RGBA" else (r, g, b)
        elif bg_hex and bg_hex.startswith("#"):
            r, g, b = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
            fill = (r, g, b, 255) if image.mode == "RGBA" else (r, g, b)
        else:
            fill = (255, 255, 255, 255) if image.mode == "RGBA" else (255, 255, 255)

        draw = ImageDraw.Draw(image)
        rx1, ry1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        rx2, ry2 = min(image.width, x2 + pad_x), min(image.height, y2 + pad_y)

        # Fill the dilated rectangle first to clean the area
        draw.rectangle([rx1, ry1, rx2, ry2], fill=fill)

        # Then draw text boxes on top (more precise)
        if text_boxes:
            for pts in text_boxes:
                draw.polygon(pts, fill=fill)

        _invalidate_np_cache(image)
        return image

    def inpaint_batch(
        self,
        image: Image.Image,
        regions: list[dict],
        pad: int = 30,
        pad_x: int = 30,
        pad_y: int = 30,
        **kwargs,
    ) -> Image.Image:
        from comic_translator.renderer import _sample_bg_color, _sample_interior_color, _invalidate_np_cache

        draw = ImageDraw.Draw(image)
        for region in regions:
            x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]
            interior = _sample_interior_color(image, x1, y1, x2, y2)
            bg_hex = _sample_bg_color(image, x1, y1, x2, y2)
            fill_hex = interior if interior else bg_hex
            if fill_hex and fill_hex.startswith("#"):
                r, g, b = int(fill_hex[1:3], 16), int(fill_hex[3:5], 16), int(fill_hex[5:7], 16)
            else:
                r, g, b = 255, 255, 255
            fill = (r, g, b, 255) if image.mode == "RGBA" else (r, g, b)
            rx1, ry1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
            rx2, ry2 = min(image.width, x2 + pad_x), min(image.height, y2 + pad_y)
            # Fill the dilated rectangle first to clean the area
            draw.rectangle([rx1, ry1, rx2, ry2], fill=fill)

            # Then draw text boxes on top (more precise)
            text_boxes = region.get("text_boxes", [])
            if text_boxes:
                for pts in text_boxes:
                    draw.polygon(pts, fill=fill)
        _invalidate_np_cache(image)
        return image
