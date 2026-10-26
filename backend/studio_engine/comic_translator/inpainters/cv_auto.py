"""CV-Auto inpainting backend.

Algorithm (analyze-first):
  1. Create a binary mask covering the text region(s) (with extra padding so
     the fill extends beyond anti-aliased glyph edges).
  2. Analyze the colors of the background band around each component's
     unpadded text bbox (per component so multiple bubbles over different
     backgrounds each get the correct fill).
  3. Decide per component:
     - If a single color covers >= ``solid_ratio`` of the ring (>85%), the
       background is solid: fill the masked area with that exact color using a
       feathered edge blend (OpenCV inpainting is redundant here because the
       ring already tells us the background color).
     - Otherwise (<85%) the background is complex: inpaint the region with
       SimpleLaMa (native 512x512), falling back to a texture push-in fill
       — or OpenCV inpainting for oversized holes — when LaMa is
       unavailable.
"""

from __future__ import annotations

import importlib.util
import logging
import threading

import cv2
import numpy as np
from PIL import Image

from comic_translator.inpainters.base import InpainterBackend
from comic_translator.inpainters.common import (
    build_iopoint_combined_mask,
    build_mask_pil,
    cv2_edge_blend,
    find_connected_components,
)

logger = logging.getLogger(__name__)

# ── SimpleLaMa (optional neural fallback for complex regions) ─────────────────

_lama = None
_lama_failed = False
_lama_lock = threading.Lock()


def _lama_available() -> bool:
    """Cheap availability probe (no model download, no weights load).

    torch is guaranteed importable here (the package pre-imports it before
    PaddleOCR so the Windows DLL load order works out), so only the LaMa
    package itself is checked. Used for the upfront progress line; the model
    itself is only constructed on the first complex region.
    """
    return importlib.util.find_spec("simple_lama_inpainting") is not None


def _get_lama():
    """Load and cache a SimpleLama model on the first complex region.

    Returns None if unavailable. A failed load latches so later components
    do not retry it, and the lock keeps concurrent jobs (one thread per
    project) from constructing the model twice.
    """
    global _lama, _lama_failed
    if _lama is not None:
        return _lama
    if _lama_failed:
        return None
    with _lama_lock:
        if _lama is not None:
            return _lama
        if _lama_failed:
            return None
        try:
            import torch
            from simple_lama_inpainting import SimpleLama

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            logger.info("Loading SimpleLaMa on %s (first complex region)...", device)
            _lama = SimpleLama(device=device)
        except Exception as e:  # noqa: BLE001 - any failure -> graceful fallback
            _lama_failed = True
            logger.warning("SimpleLaMa unavailable; complex regions use push-in fill: %s", e)
            _lama = None
        return _lama


def _hex(color: tuple) -> str:
    """Format an RGB color as a hex string, e.g. '#f0eeff'."""
    return "#" + "".join(f"{max(0, min(255, int(c))):02x}" for c in color[:3])


def _dominant_color(arr: np.ndarray, bucket: int = 16) -> tuple[tuple[int, int, int], float]:
    """Quantize RGB pixels into buckets; return (modal_color, fraction).

    ``modal_color`` is the median color of the most populated bucket so e.g. a
    near-white fill resolves to white (255, 255, 255) instead of (240, 240, 240),
    and the median is robust to a few outlier pixels.
    """
    total = arr.shape[0]
    if total == 0:
        return (255, 255, 255), 0.0
    b = max(1, bucket)
    quantized = (arr // b) * b
    _, inverse, counts = np.unique(
        quantized.reshape(-1, 3), axis=0, return_inverse=True, return_counts=True,
    )
    idx = int(np.argmax(counts))
    modal = arr[inverse == idx]
    median = np.median(modal, axis=0)
    return (
        (int(round(median[0])), int(round(median[1])), int(round(median[2]))),
        float(counts[idx]) / total,
    )


def _border_ring_color(
    img_np: np.ndarray,
    anchor: tuple[int, int, int, int],
    thickness: int,
    bucket: int,
) -> tuple[tuple[int, int, int] | None, float]:
    """Modal color of the background band right around an anchor bbox.

    The band is the ``thickness``-pixel ring outside the ``anchor`` box
    (normally the unpadded text bbox). It lies inside the bubble interior
    around the text, so it is ground truth for the fill color. Returns
    (color, fraction) or (None, 0.0) if no ring pixels exist.
    """
    ax1, ay1, ax2, ay2 = anchor
    H, W = img_np.shape[:2]
    anchor_mask = np.zeros((H, W), np.uint8)
    anchor_mask[max(0, ay1):min(H, ay2 + 1), max(0, ax1):min(W, ax2 + 1)] = 1
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(anchor_mask, kernel, iterations=max(1, thickness))
    ring = (dilated > 0) & (anchor_mask == 0)
    pts = np.argwhere(ring)
    if pts.shape[0] == 0:
        return None, 0.0
    colors = img_np[pts[:, 0], pts[:, 1]]
    return _dominant_color(colors, bucket=bucket)


# Above this hole size (px) the per-pixel push-in fill gets too slow; callers
# switch to ``_cv2_fill`` instead so the text is still removed.
_PUSH_IN_MAX_HOLE = 60_000


def _push_in_fill(img_np: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """Fill a hole by pushing surrounding pixels inward (texture push-in).

    Each iteration copies the color of already-filled neighbors onto the
    boundary of the remaining hole, so halftone/gradient/line-art texture
    flows into the hole without the blur OpenCV produces. Callers must keep
    the hole at or below ``_PUSH_IN_MAX_HOLE`` pixels.
    """
    H, W = img_np.shape[:2]
    out = img_np.astype(np.float32)
    hole = hole.copy()
    filled = ~hole
    kernel = np.ones((3, 3), np.uint8)
    while hole.any():
        dil = cv2.dilate(filled.astype(np.uint8), kernel, iterations=1).astype(bool)
        frontier = hole & dil
        if not frontier.any():
            frontier = hole.copy()
        ys, xs = np.nonzero(frontier)
        for y, x in zip(ys, xs):
            y0, y1 = max(0, y - 1), min(H, y + 2)
            x0, x1 = max(0, x - 1), min(W, x + 2)
            nbr = filled[y0:y1, x0:x1]
            if nbr.any():
                out[y, x] = np.median(out[y0:y1, x0:x1][nbr], axis=0)
        filled[frontier] = True
        hole[frontier] = False
    return np.clip(out, 0, 255).astype(np.uint8)


def _push_in_fallback(sub: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """Push-in fill for a tight crop, feathered at the seam."""
    pushed = _push_in_fill(sub, hole)
    feathered = cv2.GaussianBlur(hole.astype(np.float32), (5, 5), 0)[..., None]
    return np.clip(
        sub.astype(np.float32) * (1.0 - feathered)
        + pushed.astype(np.float32) * feathered,
        0, 255,
    ).astype(np.uint8)


def _cv2_fill(sub: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """OpenCV inpaint fallback for holes too large for the push-in fill.

    Same feathered-seam blend as ``_push_in_fallback`` so the fill does not
    show a hard edge against the surrounding texture.
    """
    mask = hole.astype(np.uint8) * 255
    filled = cv2.inpaint(sub, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
    feathered = cv2.GaussianBlur(hole.astype(np.float32), (5, 5), 0)[..., None]
    return np.clip(
        sub.astype(np.float32) * (1.0 - feathered)
        + filled.astype(np.float32) * feathered,
        0, 255,
    ).astype(np.uint8)


def _lama_inpaint_region(
    img_np: np.ndarray,
    comp_mask_np: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    lama=None,
) -> np.ndarray | None:
    """Inpaint a component with SimpleLaMa at its native 512x512 input size.

    The context crop (bbox + margin) is scaled uniformly to fit 512x512
    (small crops keep native resolution) and mirror-padded to fill the
    frame; LaMa runs and the result is mapped back to the original crop
    size. Returns the filled bbox crop (RGB) or None if LaMa is unavailable
    or the crop is too large for a reasonable run.
    """
    if lama is None:
        return None

    H, W = img_np.shape[:2]
    w = x2 - x1 + 1
    h = y2 - y1 + 1
    margin = max(16, int(round(max(w, h) * 0.2)))
    cx1 = max(0, x1 - margin)
    cy1 = max(0, y1 - margin)
    cx2 = min(W - 1, x2 + margin)
    cy2 = min(H - 1, y2 + margin)
    cw = cx2 - cx1 + 1
    ch = cy2 - cy1 + 1
    if cw * ch > 2_500_000:
        return None  # too large for a fast LaMa run; use fallback

    crop = img_np[cy1:cy2 + 1, cx1:cx2 + 1]
    hole = comp_mask_np[cy1:cy2 + 1, cx1:cx2 + 1] > 0
    if not hole.any():
        return None

    # LaMa was trained at 512x512, but stretching distorts wide regions and
    # upscaling small crops blurs their texture. Scale uniformly to fit
    # (never upscale), then pad the remainder with mirrored content so the
    # model always sees native-resolution texture around the hole.
    target = 512
    scale = min(target / cw, target / ch, 1.0)
    nw = max(1, int(round(cw * scale)))
    nh = max(1, int(round(ch * scale)))
    img_512 = np.array(Image.fromarray(crop).resize((nw, nh), Image.LANCZOS))
    mask_512 = np.array(
        Image.fromarray((hole.astype(np.uint8)) * 255, mode="L")
        .resize((nw, nh), Image.BILINEAR)
    )
    # Re-binarize: downscaled mask strokes get thinned/anti-aliased, and any
    # surviving coverage must stay a hole so LaMa fills all glyph fringes.
    mask_512 = (mask_512 > 0).astype(np.uint8) * 255
    pw, ph = target - nw, target - nh
    if pw or ph:
        # Mirror-pad bottom/right (same convention as the LaMa wrapper).
        img_512 = np.pad(img_512, ((0, ph), (0, pw), (0, 0)), mode="symmetric")
        mask_512 = np.pad(mask_512, ((0, ph), (0, pw)), mode="symmetric")

    try:
        filled = lama(Image.fromarray(img_512), Image.fromarray(mask_512, mode="L"))
        filled_np = np.array(filled.convert("RGB"))[:nh, :nw]
    except Exception as e:  # noqa: BLE001
        logger.warning("SimpleLaMa inference failed: %s", e)
        return None

    if (nw, nh) != (cw, ch):
        filled_np = np.array(
            Image.fromarray(filled_np).resize((cw, ch), Image.LANCZOS)
        )

    return filled_np[y1 - cy1:y2 - cy1 + 1, x1 - cx1:x2 - cx1 + 1].copy()


def _region_bbox(r) -> tuple[int, int, int, int]:
    """Extract (x1, y1, x2, y2) from a region dict or object."""
    try:
        return (r["x1"], r["y1"], r["x2"], r["y2"])
    except (KeyError, TypeError):
        return (r.x1, r.y1, r.x2, r.y2)


def _handle_complex_region(
    img_np: np.ndarray,
    comp_mask_np: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
) -> tuple[np.ndarray, str]:
    """Inpaint a region whose background is complex (< solid_ratio).

    Tries SimpleLaMa first and reports what actually filled the region so
    the job log is truthful. Returns (filled bbox crop (RGB), method used).
    """
    lama = _get_lama()
    lama_crop = (
        _lama_inpaint_region(img_np, comp_mask_np, x1, y1, x2, y2, lama)
        if lama is not None
        else None
    )
    if lama_crop is not None:
        return lama_crop, "SimpleLaMa"

    # Expand the crop with a context margin: a component whose mask fills
    # its own bbox (e.g. a plain rectangular mask) would otherwise leave
    # the fill algorithms with zero source pixels around the hole.
    H, W = img_np.shape[:2]
    margin = max(16, int(round(max(x2 - x1 + 1, y2 - y1 + 1) * 0.2)))
    cx1, cy1 = max(0, x1 - margin), max(0, y1 - margin)
    cx2, cy2 = min(W - 1, x2 + margin), min(H - 1, y2 + margin)
    sub = img_np[cy1:cy2 + 1, cx1:cx2 + 1].copy()
    hole = comp_mask_np[cy1:cy2 + 1, cx1:cx2 + 1] > 0
    bbox = (slice(y1 - cy1, y2 - cy1 + 1), slice(x1 - cx1, x2 - cx1 + 1))
    if not hole.any():
        return sub[bbox].copy(), "no-op (empty mask)"
    if lama is None:
        reason = "SimpleLaMa unavailable"
    else:
        reason = "region too large or LaMa inference failed"
    if hole.sum() > _PUSH_IN_MAX_HOLE:
        # The push-in fill is O(hole) in a Python loop; for oversized holes
        # use OpenCV so the text is actually removed instead of left visible.
        return (
            _cv2_fill(sub, hole)[bbox],
            f"cv2.inpaint (hole too large for push-in; {reason})",
        )
    return _push_in_fallback(sub, hole)[bbox], f"push-in fill ({reason})"


class CVAutoBackend(InpainterBackend):
    """Analyze-first inpainting: solid-color fill or SimpleLaMa per component."""

    @property
    def name(self) -> str:
        return "cv_auto"

    @property
    def is_neural(self) -> bool:
        return False

    def load(self, **kwargs) -> None:
        pass  # OpenCV is always available

    @staticmethod
    def _ring_thickness(w: int, h: int) -> int:
        """Ring thickness proportional to region size, bounded."""
        d = max(w, h)
        return max(2, min(24, int(round(d * 0.03))))

    def _auto_inpaint(
        self, image: Image.Image, mask: Image.Image,
        regions: list | None, solid_ratio: float, color_bucket: int,
        progress_callback=None,
    ) -> Image.Image:
        """Analyze-first inpainting, per connected component.

        The ring is sampled around the original (unpadded) text bbox of each
        component, so it stays inside the bubble interior instead of leaking
        into neighboring backgrounds when the fill mask is heavily padded.
        """
        mask_np = (np.array(mask) > 128).astype(np.uint8)
        if not mask_np.any():
            return image

        out = np.array(image.convert("RGB"))
        H, W = out.shape[:2]
        comps = find_connected_components(mask, min_area=4)
        n = max(1, len(comps))
        # Unpadded text bboxes of the regions, precomputed once for the
        # overlap filter below (regions may be dicts or objects).
        region_boxes = [_region_bbox(r) for r in regions] if regions else []

        if progress_callback:
            # One upfront truth line: is neural inpainting even possible?
            # Import-probe only: actually loading SimpleLaMa (which may need
            # a ~200 MB model download) is deferred to the first complex
            # region so solid-only pages never pay for it.
            lama_ok = _lama_available()
            progress_callback(
                "SimpleLaMa: available"
                if lama_ok
                else "SimpleLaMa: NOT installed — complex regions will use push-in fill",
                0.04,
            )

        for i, (x1, y1, x2, y2) in enumerate(comps):
            # find_connected_components returns slice-style (exclusive) x2/y2;
            # everything below treats bboxes as inclusive.
            x2 = min(x2, W) - 1
            y2 = min(y2, H) - 1
            comp = mask_np[y1:y2 + 1, x1:x2 + 1]
            hole = comp > 0
            if not hole.any():
                continue
            sub = out[y1:y2 + 1, x1:x2 + 1].copy()
            base_pct = 0.05 + 0.9 * (i / n)

            comp_full = np.zeros_like(mask_np)
            comp_full[y1:y2 + 1, x1:x2 + 1] = comp

            if progress_callback:
                progress_callback(f"component {i + 1}/{n}: analyzing colors", base_pct)

            # Anchor the ring to the overlapping unpadded text bbox(es) so it
            # samples true bubble background (ground truth).
            anchor = None
            if region_boxes:
                overlap = [
                    b for b in region_boxes
                    if not (b[2] < x1 or b[0] > x2 or b[3] < y1 or b[1] > y2)
                ]
                if overlap:
                    anchor = (
                        min(b[0] for b in overlap), min(b[1] for b in overlap),
                        max(b[2] for b in overlap), max(b[3] for b in overlap),
                    )
            if anchor is None:
                anchor = (x1, y1, x2, y2)

            thickness = self._ring_thickness(anchor[2] - anchor[0] + 1, anchor[3] - anchor[1] + 1)
            ring_color, ring_frac = _border_ring_color(
                out, anchor, thickness, color_bucket,
            )

            if ring_color is not None and ring_frac >= solid_ratio:
                # > solid_ratio: solid background -> fill with the ring color.
                if progress_callback:
                    progress_callback(
                        f"component {i + 1}/{n}: solid fill — "
                        f"bg ring {_hex(ring_color)} {ring_frac:.0%} >= {solid_ratio:.0%}",
                        base_pct,
                    )
                solid = np.empty_like(sub)
                solid[:] = ring_color
                out[y1:y2 + 1, x1:x2 + 1] = cv2_edge_blend(
                    (comp * 255).astype(np.uint8), solid, sub,
                )
            else:
                # < solid_ratio: complex background — try SimpleLaMa, fall
                # back to push-in fill. The follow-up line reports the
                # algorithm that actually ran.
                if progress_callback:
                    if ring_color is not None:
                        reason = (
                            f"complex bg (ring max {_hex(ring_color)} {ring_frac:.0%}"
                            f" < {solid_ratio:.0%})"
                        )
                    else:
                        reason = "no background ring available"
                    progress_callback(
                        f"component {i + 1}/{n}: {reason}", base_pct,
                    )
                filled, method_used = _handle_complex_region(
                    out, comp_full, x1, y1, x2, y2,
                )
                out[y1:y2 + 1, x1:x2 + 1] = filled
                if progress_callback:
                    progress_callback(
                        f"component {i + 1}/{n}: → {method_used}", base_pct,
                    )

        # `out` is already RGB (PIL order).
        return Image.fromarray(out)

    def inpaint_single(
        self,
        image: Image.Image,
        x1: int, y1: int, x2: int, y2: int,
        text_boxes: list | None = None,
        pad: int = 30, pad_x: int = 30, pad_y: int = 30,
        opencv_method: str = "ns", opencv_radius: int = 5,
        solid_ratio: float = 0.85, color_bucket: int = 16,
        mask_pad: int = 0,
        progress_callback=None,
        **kwargs,
    ) -> Image.Image:
        if progress_callback:
            progress_callback("building mask", 0.03)
        # Step 1: create mask (with extra padding so fringes are covered)
        mask = build_mask_pil(
            image.size, x1, y1, x2, y2, text_boxes, pad_x + mask_pad, pad_y + mask_pad,
        )
        # Steps 2-3: analyze first, then solid fill or SimpleLaMa
        return self._auto_inpaint(
            image, mask,
            [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}],
            solid_ratio, color_bucket, progress_callback=progress_callback,
        )

    def inpaint_batch(
        self,
        image: Image.Image,
        regions: list[dict],
        pad: int = 30, pad_x: int = 30, pad_y: int = 30,
        opencv_method: str = "ns", opencv_radius: int = 5,
        solid_ratio: float = 0.85, color_bucket: int = 16,
        mask_pad: int = 0,
        progress_callback=None,
        **kwargs,
    ) -> Image.Image:
        if progress_callback:
            progress_callback("building mask", 0.03)
        # Step 1: create combined mask. Unlike build_mask_pil, the pad args
        # here widen the context dilation kernel; the region shapes
        # themselves are drawn unpadded.
        mask = build_iopoint_combined_mask(
            image.size, regions, pad_x + mask_pad, pad_y + mask_pad,
        )
        # Steps 2-3: analyze first, then solid fill or SimpleLaMa
        return self._auto_inpaint(
            image, mask, regions, solid_ratio, color_bucket,
            progress_callback=progress_callback,
        )
