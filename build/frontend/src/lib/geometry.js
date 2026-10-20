/**
 * Shared box-geometry helpers for the digital twin grid map's pointer-based
 * drag/resize. Ported from smart-warehouse-main's lib/geometry.ts so
 * "zones can't overlap" and "stay inside rack bounds" behave identically.
 */

export function boxesOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

export function overlapsAny(candidate, others) {
  return others.some((o) => boxesOverlap(candidate, o));
}

export function clamp(value, lo, hi) {
  return Math.max(lo, Math.min(hi, value));
}

/** Clamp a w x h box so it fits inside a cols x rows grid. */
export function clampBoxToBounds(box, cols, rows) {
  const w = clamp(box.w, 1, Math.max(1, cols));
  const h = clamp(box.h, 1, Math.max(1, rows));
  const x = clamp(box.x, 0, Math.max(0, cols - w));
  const y = clamp(box.y, 0, Math.max(0, rows - h));
  return { x, y, w, h };
}
