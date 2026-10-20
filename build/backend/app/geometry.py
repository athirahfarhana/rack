"""Small shared helpers for validating rack/zone placement - used server-side
as the final source of truth (the frontend also constrains interactively,
but this is what actually gets persisted)."""


def boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def clamp_box_to_bounds(x: int, y: int, w: int, h: int, cols: int, rows: int) -> tuple[int, int, int, int]:
    """Clamp a w x h box so it fits within a cols x rows grid, preserving
    size where possible (shrinking only if the box itself is larger than
    the grid)."""
    w = clamp(w, 1, max(1, cols))
    h = clamp(h, 1, max(1, rows))
    x = clamp(x, 0, max(0, cols - w))
    y = clamp(y, 0, max(0, rows - h))
    return x, y, w, h
