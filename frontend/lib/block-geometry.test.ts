// Geometry self-tests (no test framework in this repo — plain node assert).
// Run: npx tsx lib/block-geometry.test.ts  (from the frontend/ directory)
// Covers resizeRectHandle (axis-aligned) and resizeRotatedHandle (rotated /
// edge handles). Delete-rewrites of these helpers must keep this green.
import assert from "node:assert";
import {
  resizeRectHandle,
  resizeRotatedHandle,
} from "./block-geometry";

let n = 0;
function eq(label: string, actual: unknown, expected: unknown) {
  n++;
  assert.deepStrictEqual(actual, expected, label);
}

const R = { x1: 0, y1: 0, x2: 100, y2: 50 };

// ── resizeRectHandle (axis-aligned) ──────────────────────────────────────
// se drag: pointer right/down extends toward pointer
eq("se extends", resizeRectHandle(0, 0, 100, 50, 1, 1, 120, 70), { x1: 0, y1: 0, x2: 120, y2: 70 });
// nw drag: opposite corner pinned, dragged corner follows pointer
eq("nw shrinks", resizeRectHandle(0, 0, 100, 50, -1, -1, 10, 5), { x1: 10, y1: 5, x2: 100, y2: 50 });
// nw grows: pointer past the opposite side
eq("nw grows", resizeRectHandle(0, 0, 100, 50, -1, -1, -20, -10), { x1: -20, y1: -10, x2: 100, y2: 50 });
// e edge: only x2 moves; y untouched
eq("e edge", resizeRectHandle(0, 0, 100, 50, 1, 0, 130, 999), { x1: 0, y1: 0, x2: 130, y2: 50 });
// w edge: x1 follows pointer, x2 pinned
eq("w edge", resizeRectHandle(0, 0, 100, 50, -1, 0, 15, 999), { x1: 15, y1: 0, x2: 100, y2: 50 });
// s edge: only y2 moves
eq("s edge", resizeRectHandle(0, 0, 100, 50, 0, 1, 999, 60), { x1: 0, y1: 0, x2: 100, y2: 60 });
// min-size guard on every dragged side
eq("min right", resizeRectHandle(0, 0, 100, 50, 1, 1, 5, 70), { x1: 0, y1: 0, x2: 10, y2: 70 });
eq("min left", resizeRectHandle(0, 0, 100, 50, -1, 0, 95, 0), { x1: 90, y1: 0, x2: 100, y2: 50 });
eq("min top", resizeRectHandle(0, 0, 100, 50, 0, -1, 0, 45), { x1: 0, y1: 40, x2: 100, y2: 50 });

// ── resizeRotatedHandle ──────────────────────────────────────────────────
// Parity with the old bottom-right-corner behavior on unrotated boxes.
eq("rotated se = old corner", resizeRotatedHandle({ ...R }, 1, 1, 10, 5), { x1: 0, y1: 0, x2: 110, y2: 55 });
// nw on unrotated box: bottom-right corner pinned exactly
eq("rotated nw pins br", resizeRotatedHandle({ ...R }, -1, -1, 10, 5), { x1: 10, y1: 5, x2: 100, y2: 50 });
// rotated 90°: the box's own axes are screen-vertical/horizontal, so an
// ordinary horizontal drag changes the box's h dimension (parity with the
// old resizeRotatedBlock math).
const R90 = { x1: 0, y1: 0, x2: 100, y2: 50, rotation: 90 };
eq("rot90 se dx changes h", resizeRotatedHandle({ ...R90 }, 1, 1, 10, 0), { x1: 5, y1: 5, x2: 105, y2: 45 });
// e edge on a 90°-rotated box grows width along the box x axis (screen dy)
const e90 = resizeRotatedHandle({ ...R90 }, 1, 0, 0, 10);
eq("rot90 e edge width", e90.x2 - e90.x1, 110);
eq("rot90 e edge height", e90.y2 - e90.y1, 50);
// opposite edge pinned: e edge on unrotated box keeps x1
const eU = resizeRotatedHandle({ ...R }, 1, 0, 25, 7);
eq("e edge pins left", [eU.x1, eU.y1], [0, 0]);
// min size guard, rotated
const nwGrown = resizeRotatedHandle({ ...R }, -1, -1, -400, 400);
eq("min enforced both axes", [nwGrown.x2 - nwGrown.x1, nwGrown.y2 - nwGrown.y1], [100 + 400, 10]);

console.log(`OK: ${n} geometry assertions passed`);
