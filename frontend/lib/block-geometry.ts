type Rectangle = { x1: number; y1: number; x2: number; y2: number; rotation?: number };

type Sign = -1 | 0 | 1;

/**
 * Axis-aligned resize: sides marked by sx/sy (+1 = e/s, -1 = w/n, 0 = edge
 * stays) follow the pointer; opposite sides stay pinned. Enforces min size
 * on every dragged side.
 */
export function resizeRectHandle(
  x1: number, y1: number, x2: number, y2: number,
  sx: Sign, sy: Sign, px: number, py: number, min = 10,
) {
  let nx1 = x1, ny1 = y1, nx2 = x2, ny2 = y2;
  if (sx === 1) nx2 = Math.max(x1 + min, px);
  if (sx === -1) nx1 = Math.min(x2 - min, px);
  if (sy === 1) ny2 = Math.max(y1 + min, py);
  if (sy === -1) ny1 = Math.min(y2 - min, py);
  return { x1: nx1, y1: ny1, x2: nx2, y2: ny2 };
}

/**
 * Resizing a rotated box by any corner (`sx`,`sy` ∈ {−1,1}) or edge (one
 * sign is 0). (dx,dy) is the pointer delta in image axes, projected onto
 * the box's own axes: dW = cos·dx + sin·dy, dH = −sin·dx + cos·dy. Each
 * dimension grows toward the drag on the dragged side (opposite side/edge
 * pinned via the center shift along the box axes); min size is enforced,
 * and the actual (possibly clamped) deltas move the center so the pinned
 * edge remains fixed even when clamping kicks in.
 */
export function resizeRotatedHandle(box: Rectangle, sx: Sign, sy: Sign, dx: number, dy: number, minSize = 10) {
  const angle = (box.rotation ?? 0) * Math.PI / 180;
  const cos = Math.cos(angle), sin = Math.sin(angle);
  const oldW = box.x2 - box.x1, oldH = box.y2 - box.y1;
  const dW = cos * dx + sin * dy;
  const dH = -sin * dx + cos * dy;
  const w = Math.max(minSize, oldW + sx * dW);
  const h = Math.max(minSize, oldH + sy * dH);
  const cw = w - oldW, ch = h - oldH;
  const cx = (box.x1 + box.x2) / 2 + sx * (cw / 2) * cos + sy * (ch / 2) * (-sin);
  const cy = (box.y1 + box.y2) / 2 + sx * (cw / 2) * sin + sy * (ch / 2) * cos;
  const x1 = Math.max(0, Math.round(cx - w / 2));
  const y1 = Math.max(0, Math.round(cy - h / 2));
  return { x1, y1, x2: x1 + Math.round(w), y2: y1 + Math.round(h) };
}
