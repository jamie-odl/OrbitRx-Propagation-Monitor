# Basemap images on this commit

This note is about `static_basemap_v2.png`, `static_basemap_v2.webp`, and the separate fallback `world_map.jpg` at commit `304db03d99604af20da0b49ee2f3894ab17e2cc9` and the documentation fixes on top of it. It does not add a licence.

## What is in the files

| File | SHA-256 | What the container contains |
| --- | --- | --- |
| `static_basemap_v2.png` | `3046203ae0ade8be43cf9bd647ced5621ab1ee3cdfc95da5269f931b54ab2f1b` | 2400×1200 PNG. Chunks are IHDR, IDAT, IEND only. No `tEXt`, `iTXt`, `zTXt`, or `eXIf`. Pillow read no text or EXIF. 124,783 bytes. |
| `static_basemap_v2.webp` | `2704a5d7c6819859c9d42b2659c23a879658724acd2755ca85ca41b33b252e67` | 2400×1200 lossy VP8. RIFF chunks are `VP8 ` only. No EXIF or XMP. 105,288 bytes. |
| `world_map.jpg` | `13e99d0a8fe7bc6e0eaac39aaf1358d2613370cc5d89ff1d6e6c989310324695` | 1600×800 JPEG. JFIF APP0 only. No copyright field. |

Mean absolute per-channel difference between the PNG and the WebP, after decoding both to RGB, is 5.46 (maximum 50). 26.4% of pixels differ by more than 2. Same dimensions, same picture, lossy WebP. They are one artwork, not two sources.

Git history: both v2 files were added in commit `39d5f1b` and not modified after that, through `304db03`. That commit does not add a generator. No later commit adds one. `generate_map.py` writes `world_map.jpg` only. Its download URL is `https://upload.wikimedia.org/wikipedia/commons/f/f2/Large_World_Map_bright.jpg`. The Commons page for that file says the author is MTBlack and the licence is Creative Commons Attribution-ShareAlike. That download is not a record of how the v2 files were made. The module docstring used to say Natural Earth; the code never downloaded Natural Earth. The docstring is corrected to match the URL.

`orbitrx/paths.py` prefers the PNG, then the WebP, then `world_map.jpg`. `orbitrx/ui/leaflet_map.py` builds the interactive page from bundled Leaflet and `L.imageOverlay` of a `file://` URL. It does not load a slippy-tile template.

## Mask measurement

A plate-carrée raster of Natural Earth 1:110 million land, file `geojson/ne_110m_land.geojson` at natural-earth-vector tag `v5.1.2`, was drawn at 2400×1200 (outer rings filled, holes cleared). Lighter PNG pixels (mean RGB channel greater than 34, between the two luminance modes at about 24 and 43) were treated as land.

- Intersection-over-union with that raster: 0.937.
- Pixels that disagree: 2.21% of the image (63,660 pixels).
- Of those disagreements, 65.5% lie within 2 pixels of the raster boundary.
- Disagreement farther than that is 0.76% of the image.

Interior land (away from that boundary) is not one flat colour: 41 distinct RGB triples, mean about (28, 42, 58). Interior ocean has 15, mean about (10, 22, 40). So the file is a shaded rendering, not a dump of the shapefile.

Natural Earth's terms page (https://www.naturalearthdata.com/about/terms-of-use/, fetched 7 November 2026) says: "All versions of Natural Earth raster + vector map data found on this website are in the public domain. You may use the maps in any manner, including modifying the content and design, electronic dissemination, and offset printing." It also says no permission is needed and crediting is unnecessary.

## What this does not prove

The repository has no script, download URL, or commit message that names the file which was rasterized. Agreement with Natural Earth 1:110m land is strong and the leftover error is mostly on the coastline, which is what a styled raster of those polygons would look like. A different land polygon set with the same simplified coast could score in the same range. 1:50m and 1:10m were not compared. Byte identity with any Natural Earth file was not claimed and does not hold: the committed file is a shaded 2400×1200 image.

`world_map.jpg` was not shown to be that render. A crude land mask on the photographic JPEG, resized to 2400×1200, had IoU about 0.81 against the PNG mask. That comparison used a colour rule, not the polygon raster, and is not an origin finding.

## Not done

Replacing the PNG and WebP with a new raster drawn from Natural Earth polygons would make the public-domain source explicit. It would also change pixels, so it was not done. The images shipped in the 5.1.0 installer inputs stay as they are.

The MIT text in `LICENSE` is unchanged. It licenses "this software and associated documentation files". It does not name these images. This note does not extend that grant to them.
