"""Rasterize a Natural Earth land file to a candidate PNG.

The candidate is not the packaged basemap. This script refuses to write
world_map.jpg or either static_basemap_v2 file. Default output is under
candidates/, which is gitignored.

The land file third_party/natural_earth/ne_110m_land.geojson is
natural-earth-vector tag v5.1.2. Its terms are in TERMS_OF_USE.txt next
to it. Those terms are Natural Earth's, for that dataset. They are not
a finding that the JPEG or the v2 images were made from it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
GEOJSON = ROOT / "third_party" / "natural_earth" / "ne_110m_land.geojson"
FORBIDDEN = {
    "world_map.jpg",
    "static_basemap_v2.png",
    "static_basemap_v2.webp",
}
OCEAN = (10, 22, 40)
LAND = (28, 42, 58)


def _rings(geometry: dict):
    kind = geometry["type"]
    coords = geometry["coordinates"]
    if kind == "Polygon":
        yield coords
    elif kind == "MultiPolygon":
        for polygon in coords:
            yield polygon


def render_land(geojson: dict, width: int, height: int, land=LAND, ocean=OCEAN) -> Image.Image:
    """Plate-carrée fill. No antialiasing, so the pixels depend only on the polygons."""
    image = Image.new("RGB", (width, height), ocean)
    draw = ImageDraw.Draw(image)

    def project(lon: float, lat: float) -> tuple[float, float]:
        return ((lon + 180.0) / 360.0 * width, (90.0 - lat) / 180.0 * height)

    for feature in geojson["features"]:
        for polygon in _rings(feature["geometry"]):
            draw.polygon([project(lon, lat) for lon, lat in polygon[0]], fill=land)
            for hole in polygon[1:]:
                draw.polygon([project(lon, lat) for lon, lat in hole], fill=ocean)
    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "candidates" / "ne_110m_candidate.png",
    )
    parser.add_argument("--width", type=int, default=2400)
    parser.add_argument("--height", type=int, default=1200)
    args = parser.parse_args(argv)
    if args.out.name in FORBIDDEN:
        print(f"refusing to overwrite packaged or v2 artwork: {args.out.name}")
        return 2
    geojson = json.loads(GEOJSON.read_text(encoding="utf-8"))
    image = render_land(geojson, args.width, args.height)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.out, format="PNG")
    print(f"wrote candidate {args.out} ({args.width}x{args.height}); not the packaged basemap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
