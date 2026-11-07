# Notices

This file separates two different questions: what licence, if any, covers OrbitRx source on this branch, and which third-party terms apply to components this branch actually names. It does not grant a licence. It is not a SPDX SBOM of either published executable.

## This branch's own code

There is no `LICENSE` file on this branch, and there was none on tag `v5.0.0`. No statement in `README.md`, `START_HERE.txt`, or this file is a grant of rights in the OrbitRx sources or in `world_map.jpg`. Choosing a licence for this branch is a decision for the copyright holder. This change does not make that decision.

The public product page https://thevenom.dev/tools/orbitrx/ says `Licence: MIT` for the 5.1.0 download. The zip itself has no `LICENSE` member. See [RELEASE_CHANNELS.md](RELEASE_CHANNELS.md).

Commit `304db03d99604af20da0b49ee2f3894ab17e2cc9` (the commit whose CI installer is byte-identical to the shipped `OrbitRxMonitor-Setup.exe`) does contain a `LICENSE` file whose first lines are `MIT License` and `Copyright (C) 2026 thevenom`, plus `NOTICE` and `PRIVACY.md`. The matching Actions log shows Inno Setup compressing those files into that installer. That grant stays on that commit. It is not copied here and it does not license this branch. The installer payload was not extracted, so those bytes were not re-read from the exe.

`304db03` `NOTICE` points readers to a README "Map image" note. That commit's `README.md` has no such section. This branch does not invent a licence for `static_basemap_v2.png` or `static_basemap_v2.webp`, which exist only on that commit.

## Third-party code named by this branch

`requirements.txt` and `pyproject.toml` use ranges. The table is PyPI metadata retrieved on 7 November 2026 for the then-current release of each named project. It is not the set frozen into the GitHub `v5.0.0` exe (that job log is gone) and it is not the 5.1.0 build (that run's resolved set is in `RELEASE_CHANNELS.md` and does not include `customtkinter`).

| Project | Role here | PyPI metadata checked | Conflict or limit |
| --- | --- | --- | --- |
| pillow | Runtime images | `license_expression` `MIT-CMU` (Pillow 13.0.0) | Expression is for that PyPI release, not a file vendored here |
| matplotlib | History plots | Classifier `License :: OSI Approved :: Python Software Foundation License`; upstream license text is the Matplotlib licence. Bundled font and test assets have their own terms (including OFL-1.1 and others) inside Matplotlib | Not re-audited inside a built exe |
| PySide6 | Default UI | Project license `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | A onefile exe that bundles Qt has to satisfy the Qt licence that applies. This file does not choose among LGPL and GPL or give compliance steps |
| PySide6-Addons | Optional, commented in `requirements.txt`; needed for the Leaflet widget's Qt WebEngine | Same Qt licence line as PySide6 | Not imported unless that extra is installed |
| pyserial | Optional CAT | Classifier BSD; license field `BSD` (pyserial 3.5) | |
| customtkinter | Optional UI, declared in `requirements.txt` | License field `Creative Commons Zero v1.0 Universal`; classifier `License :: OSI Approved :: MIT License` (customtkinter 6.0.0) | The two PyPI fields disagree. Left unresolved |
| win10toast | Optional toasts | License field `BSD`; classifier `License :: OSI Approved :: MIT License` (win10toast 0.9) | The two PyPI fields disagree. Left unresolved |
| pystray | Optional tray | Classifier LGPLv3; license field `LGPLv3` (pystray 0.19.5) | |
| pytest | Tests | `license_expression` `MIT` | Not shipped in the app |
| pyinstaller | Build tool only | GPLv2-or-later with an exception that allows PyInstaller to build and distribute programs under other terms | The exception is PyInstaller's, not a licence for OrbitRx |

Leaflet 1.9.4 is not vendored on this branch. The optional map loads its CSS and JS from `unpkg.com`. Leaflet 1.9.4 is BSD-2-Clause. That CDN copy was not snapshotted into the repo.

## Map image on this branch

`world_map.jpg` is vendored. SHA-256 `13e99d0a8fe7bc6e0eaac39aaf1358d2613370cc5d89ff1d6e6c989310324695`, 685,828 bytes, JPEG 1600×800. The only JPEG metadata Pillow read is a JFIF APP0 segment. There is no EXIF, comment, or copyright field.

The git blob is the same object on tag `v5.0.0`, on `43a35a8`, and on `304db03` (`2dd61fb1924e5e9353f30d099e7fca31cbf541af`). It was added in commit `d7106d8` (`version 1.01`) with no source URL in that commit.

`generate_map.py` in this tree, if the file is missing, downloads `https://upload.wikimedia.org/wikipedia/commons/f/f2/Large_World_Map_bright.jpg` and resizes to 1600×800. The Commons page for that file says the author is MTBlack and the licence is Creative Commons Attribution-ShareAlike. Byte identity between `world_map.jpg` and a resize of that file was not established, so this file is not labelled as a derivative of it. If it is that derivative, attribution and ShareAlike would be obligations on the image, separate from whatever licence covers the Python sources. That question is unresolved.

The synthetic fallback drawn in `generate_map.py` is only used when the download fails. It is not what is committed.

## Data feeds

These are service terms, not licences on this repository:

- NOAA SWPC JSON products. The 5.1.0 commit's `NOTICE` calls that US Government work public domain. This branch does not add a separate NOAA licence file.
- HamQSL `solarxml.php`, operator credited by the 5.1.0 `NOTICE` as Paul Herrman N0NBH. This branch fetches that URL and does not vendor the feed.
- ipinfo.io, used by this tree's location refresh unless the request fails.
- VE7CC and NC7J, as configured.
- QRZ XML, only when the user sets `qrz_api_key`.
- CARTO basemap tiles and OpenStreetMap data, only if the user selects the Leaflet backend on this tree. The 5.1.0 commit does not use that CARTO URL.

No map account or paid map API key is required or stored for the default raster map.
