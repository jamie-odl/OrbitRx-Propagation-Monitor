# Basemap images on this commit

This note does not add a licence and does not say the shipped app loads the v2 images.

## What the frozen build loads

`OrbitRxMonitor.spec` datas, `installer/OrbitRxMonitor.iss`, the Inno log for Actions run `42004653668` (it compresses `world_map.jpg` and does not name either v2 file), and the resulting exe archive all contain `world_map.jpg` only. `orbitrx/paths.py` still searches the v2 PNG, then the WebP, then the JPEG, and uses the first file that exists. Inside that frozen exe the v2 files are absent, so the app displays the JPEG. A source checkout that still has the PNG uses the PNG. Those are different files.

## Commons file versus the committed JPEG

`generate_map.py` can download `https://upload.wikimedia.org/wikipedia/commons/f/f2/Large_World_Map_bright.jpg`. The Commons imageinfo API on 7 November 2026 reports that original as SHA-1 `959a972de3f4faa78af35b486cf2e4921b3505be`, 78,654,642 bytes, 21600×10800, MIME image/jpeg. `extmetadata` names the licence `CC BY-SA 4.0` and the artist MTBlack. The committed `world_map.jpg` is SHA-256 `13e99d0a8fe7bc6e0eaac39aaf1358d2613370cc5d89ff1d6e6c989310324695`, 685,828 bytes, 1600×800, with no copyright field. Different pixel size means it is not that original file. No resize of the original was hashed against the committed JPEG, so this note does not say the JPEG is a derivative of that Commons file.

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

## Optional candidate, not the default

`tools/render_natural_earth_candidate.py` rasterizes `third_party/natural_earth/ne_110m_land.geojson` (SHA-256 `9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9`, natural-earth-vector tag `v5.1.2`). The terms copied from https://www.naturalearthdata.com/about/terms-of-use/ are in `third_party/natural_earth/TERMS_OF_USE.txt`. The script refuses to write `world_map.jpg` or either v2 file. It is not called by the app or by the spec. Running it does not change the packaged artwork.

## Not done

Replacing the PNG, the WebP, or the JPEG with that candidate would change pixels. That was not done. The images in git are unchanged.

The MIT text in `LICENSE` is unchanged. It licenses "this software and associated documentation files". It does not name these images. This note does not extend that grant to them.
