"""Measure the left/right x of each input field's border on a Settings screenshot
(M1 evidence): finds horizontal top/bottom border runs, pairs them into field rows,
then samples the border colour at each row's mid-height to get its left/right edge.

Usage:
    python tools/measure_field_edges.py <screenshot.png> <out.txt>
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

BORDER_COLOR = (0x6B, 0x80, 0x94)
TOLERANCE = 18
MIN_RUN_FRACTION = 0.3  # a horizontal border line spans at least this much of the width


def _matches(px: tuple[int, ...], tol: int = TOLERANCE) -> bool:
    r, g, b = px[:3]
    return (
        abs(r - BORDER_COLOR[0]) <= tol
        and abs(g - BORDER_COLOR[1]) <= tol
        and abs(b - BORDER_COLOR[2]) <= tol
    )


def find_horizontal_border_rows(img: Image.Image, min_run_frac: float = MIN_RUN_FRACTION) -> list[int]:
    """y-coordinates with a horizontal run of the border colour spanning at least
    min_run_frac of the image width: candidate top/bottom edges of input fields."""
    w, h = img.size
    px = img.load()
    min_run = int(w * min_run_frac)
    rows = []
    for y in range(h):
        run = best = 0
        for x in range(w):
            if _matches(px[x, y]):
                run += 1
                best = max(best, run)
            else:
                run = 0
        if best >= min_run:
            rows.append(y)
    return rows


def group_consecutive(rows: list[int], gap: int = 2) -> list[list[int]]:
    groups: list[list[int]] = []
    cur: list[int] = []
    for y in rows:
        if cur and y - cur[-1] > gap:
            groups.append(cur)
            cur = []
        cur.append(y)
    if cur:
        groups.append(cur)
    return groups


def row_edges_at_mid_height(img: Image.Image, top_y: int, bottom_y: int) -> tuple[int, int] | None:
    w, _ = img.size
    px = img.load()
    mid_y = (top_y + bottom_y) // 2
    # Only the form's field column (right of the page list) counts; a field row has
    # border pixels at both of its vertical edges, so at least two well-separated hits.
    xs = [x for x in range(int(w * 0.45), w) if _matches(px[x, mid_y])]
    if len(xs) < 2 or max(xs) - min(xs) < w * 0.2:
        return None
    return min(xs), max(xs)


def measure_field_edges(path: Path, min_field_height: int = 10) -> list[tuple[int, int, int]]:
    """Returns a list of (top_y, left_x, right_x) for each detected input field row."""
    img = Image.open(path).convert("RGB")
    groups = group_consecutive(find_horizontal_border_rows(img))
    measurements = []
    for top_group, bottom_group in zip(groups, groups[1:]):
        top_y, bottom_y = top_group[-1], bottom_group[0]
        if bottom_y - top_y < min_field_height:
            continue
        edges = row_edges_at_mid_height(img, top_y, bottom_y)
        if edges:
            measurements.append((top_y, edges[0], edges[1]))
    return measurements


def main(argv: list[str]) -> int:
    src = Path(argv[1])
    out = Path(argv[2])
    measurements = measure_field_edges(src)
    lines = [f"row top={top} left={left} right={right}" for top, left, right in measurements]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(measurements)} row measurement(s) from {src} to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
