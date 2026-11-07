"""Rasterize pinned Natural Earth land data to the packaged dark basemap.

Dataset: third_party/natural_earth/ne_110m_land.geojson
SHA-256 9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9
Source: natural-earth-vector tag v5.1.2, geojson/ne_110m_land.geojson
Terms: third_party/natural_earth/TERMS_OF_USE.txt (public domain statement
copied from naturalearthdata.com). Those terms cover this dataset. They
do not relicense OrbitRx and they do not describe world_map.jpg or the v2
images, which this script refuses to overwrite.

The packaged file is basemap/ne_110m_dark.png. Development and the frozen
onedir both load that file and no other basemap.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
GEOJSON = ROOT / "third_party" / "natural_earth" / "ne_110m_land.geojson"
DATASET_SHA256 = "9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9"
PACKAGED_NAME = "ne_110m_dark.png"
PACKAGED_PATH = ROOT / "basemap" / PACKAGED_NAME
FORBIDDEN = {
    "world_map.jpg",
    "static_basemap_v2.png",
    "static_basemap_v2.webp",
}
OCEAN = (10, 22, 40)
LAND = (28, 42, 58)
WIDTH = 2400
HEIGHT = 1200


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


def png_text() -> PngImagePlugin.PngInfo:
    info = PngImagePlugin.PngInfo()
    info.add_text("Software", "OrbitRx tools/render_natural_earth_candidate.py")
    info.add_text("NaturalEarth-SHA256", DATASET_SHA256)
    info.add_text("NaturalEarth-Source", "natural-earth-vector v5.1.2 geojson/ne_110m_land.geojson")
    info.add_text("Terms", "public domain; see third_party/natural_earth/TERMS_OF_USE.txt")
    return info


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", pnginfo=png_text())


def load_dataset() -> dict:
    raw = GEOJSON.read_bytes()
    import hashlib
    digest = hashlib.sha256(raw).hexdigest()
    if digest != DATASET_SHA256:
        raise SystemExit(f"dataset hash {digest} != {DATASET_SHA256}")
    return json.loads(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=PACKAGED_PATH)
    parser.add_argument("--width", type=int, default=WIDTH)
    parser.add_argument("--height", type=int, default=HEIGHT)
    parser.add_argument(
        "--preview",
        type=Path,
        default=None,
        help="Also write a nearest-neighbour half-size preview.",
    )
    args = parser.parse_args(argv)
    if args.out.name in FORBIDDEN or args.out.resolve() in {
        (ROOT / name).resolve() for name in FORBIDDEN
    }:
        print(f"refusing to overwrite unknown-provenance artwork: {args.out}")
        return 2
    image = render_land(load_dataset(), args.width, args.height)
    save_png(image, args.out)
    print(f"wrote {args.out} ({args.width}x{args.height})")
    if args.preview is not None:
        preview = image.resize((args.width // 2, args.height // 2), Image.Resampling.NEAREST)
        save_png(preview, args.preview)
        print(f"wrote preview {args.preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
