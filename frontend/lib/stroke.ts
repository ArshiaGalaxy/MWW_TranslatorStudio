/** Freehand-stroke geometry helpers (image-pixel space, integer coords). */

export type Point = [number, number];

/**
 * Expand a stroke centerline into a closed width-aware polygon outline
 * (left offsets forward + right offsets reversed, with round caps).
 *
 * This is what makes brush size real end-to-end: the cleaner builds its
 * inpaint mask by filling the stored polygon, so a wider polygon erases a
 * wider area — no backend change needed.
 */
export function strokeToPolygon(points: Point[], width: number): Point[] {
  const r = Math.max(1, Math.round(width / 2));
  const n = points.length;
  if (n === 0) return [];
  if (n === 1) {
    const [x, y] = points[0];
    return [
      [x - r, y - r], [x + r, y - r], [x + r, y + r], [x - r, y + r],
    ];
  }
  const left: Point[] = [];
  const right: Point[] = [];
  for (let i = 0; i < n; i++) {
    const p = points[i];
    const a = points[Math.max(0, i - 1)];
    const b = points[Math.min(n - 1, i + 1)];
    let dx = b[0] - a[0];
    let dy = b[1] - a[1];
    const len = Math.hypot(dx, dy);
    if (len === 0) {
      dx = 1;
      dy = 0;
    } else {
      dx /= len;
      dy /= len;
    }
    // Perpendicular (-dy, dx), rounded to integer pixels.
    left.push([Math.round(p[0] - dy * r), Math.round(p[1] + dx * r)]);
    right.push([Math.round(p[0] + dy * r), Math.round(p[1] - dx * r)]);
  }
  // Round caps: fan around each end center.
  const cap = (c: Point, fromAngle: number, toAngle: number): Point[] => {
    const steps = 4;
    const pts: Point[] = [];
    for (let s = 0; s <= steps; s++) {
      const ang = fromAngle + ((toAngle - fromAngle) * s) / steps;
      pts.push([Math.round(c[0] + Math.cos(ang) * r), Math.round(c[1] + Math.sin(ang) * r)]);
    }
    return pts;
  };
  const startDir = Math.atan2(points[1][1] - points[0][1], points[1][0] - points[0][0]);
  const endDir = Math.atan2(
    points[n - 1][1] - points[n - 2][1], points[n - 1][0] - points[n - 2][0],
  );
  // Butt-join the fans into the outline: start fan then left side, end fan
  // then right side back. (Fans share the side endpoints approximately;
  // the clean dilates the mask anyway, so tiny seams don't matter.)
  return [...cap(points[0], startDir + Math.PI / 2, startDir + (Math.PI * 3) / 2), ...left.slice(1, -1), ...cap(points[n - 1], endDir - Math.PI / 2, endDir + Math.PI / 2), ...right.slice(1, -1).reverse()];
}

/**
 * Stride-downsample a point list to at most `max` points, always keeping
 * the first and last points so the stroke keeps its endpoints.
 */
export function downsamplePoints(points: Point[], max: number): Point[] {
  if (points.length <= max) return points;
  const stride = Math.ceil(points.length / max);
  const out = points.filter((_, i) => i % stride === 0);
  const last = points[points.length - 1];
  const tail = out[out.length - 1];
  if (tail[0] !== last[0] || tail[1] !== last[1]) out.push(last);
  return out.slice(0, max);
}
