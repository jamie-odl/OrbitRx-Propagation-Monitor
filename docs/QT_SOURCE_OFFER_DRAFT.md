# DRAFT — not an offer

This text is not published. Nothing in this repository uploads it, and `tools/check_distribution_manifest.py --release` stays closed until the archive below is actually hosted and this paragraph is published with the real URL.

The private candidate is already accompanied by the source. That accompaniment is the LGPL conveyance for the private copy. A public installer still needs the same bytes at a public URL, or shipped in the same public download.

## Archives that are the corresponding source

These hashes were computed on the bytes. Reassemble 40,000,000-byte parts with `cat` in name order. The result must match the hash or the copy is incomplete.

| Archive | Bytes | SHA-256 |
| --- | --- | --- |
| `pyside-setup-everywhere-src-6.12.0.tar.xz` | 18,211,772 | `099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751` |
| `qt-everywhere-src-6.12.0.tar.xz` | 443,394,020 | `98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165` |
| `qtwebengine-6.12-d4735ce.tar.xz` | 3,019,064 | `d5dc0bbbd0d753c8944a537189dc2739f297446016d6af1bc44d5d7fbb886e28` |
| `qtwebengine-chromium-71a2fa55.tar` | 3,819,509,760 | `d258e5a92def26ba37ebea5463c5ea2a0674fded471bf2b6f5ecaf8771fbe865` |
| `chromium_attributions.qdoc` | 707,649 | `b2382a81239e6c100a3f96342909c6c7e7ecec12fb93e6fe91a5aa3bf756c0ec` |

`qt-everywhere-src-6.12.0.tar.xz` is the official single source archive. Its `.tag` is SHA-1 `ef25002ed292b132d1ed3246bfcee1d24a9cd966`. It contains the Qt modules whose DLLs are in the onedir, including Qt State Machine under `qtscxml/src/statemachine` and Qt Labs StyleKit under `qtdeclarative/src/labs/stylekit`. It does not contain Qt WebEngine.

`qtwebengine-6.12-d4735ce.tar.xz` is the `6.12` branch tip `d4735ce2f841ffbe7cbac9ee7fd954f00514825f` (2026-08-25). That commit was still the tip when PySide `v6.12.0` was tagged on 2026-10-08. There is no `v6.12.0` tag on qtwebengine. `.cmake.conf` at that commit still contains `QT_REPO_MODULE_PRERELEASE_VERSION_SEGMENT "alpha1"`. The wheel `PySide6_WebEngine 6.12.0.140` does not embed a git SHA. Its `Qt6WebEngineCore.dll` embeds `Chrome/140.0.7339.225`. `chromium/chrome/VERSION` in submodule `71a2fa55` is `PATCH=225`, which matches that string. The file `CHROMIUM_VERSION` in the WebEngine tree says "Based on Chromium version 140.0.7339.264" and "Patched with security patches up to Chromium version 151.0.7922.108". Those lines are Qt's note. They are not the string in the DLL, and the based-on line does not match `chrome/VERSION` on this branch. The GN log from Actions run 42476475449 is a configure this repository ran. It is not Qt's wheel build. `qtpdf-args-AMD64.gn` is the PDF target from that configure, not QtWebEngineCore.

`qtwebengine-chromium-71a2fa55.tar` is `git archive` of `71a2fa55e2e2f5a5d6567aac93bda8775fc7b084`. The checkout was a depth-1 fetch of that commit with no blob filter. `git ls-tree -r` found zero gitlinks, so there is no further submodule to add. `git cat-file --batch-check` accepted every object reachable from that commit.

The GN arguments printed for `:QtWebEngineCore` during Actions run `42476475449` are `third_party/qt/qtwebengine-core-gn-log.txt`. `is_qtpdf=false` and `is_msvc=true` are in that log. `third_party/qt/qtpdf-args-AMD64.gn` is the PDF module's `args.gn` from the same configure. It is not the WebEngineCore argument list.

PySide6 is pinned to `6.12.0`, which installs PySide6-WebEngine `6.12.0.140`. The separate `qtbase-everywhere-src-6.12.0.tar.xz` already in this directory is the official qtbase module archive and is also contained, as sources, in the everywhere archive.

## Text ready to publish after the upload

Replace `SOURCE_URL` with the URL that actually returns the four archives. Do not publish this paragraph before that URL works.

```
Corresponding source for the Qt and PySide libraries in this OrbitRx onedir
(PySide6 6.12.0, PySide6-WebEngine 6.12.0.140, Qt 6.12.0, qtwebengine
d4735ce2f841ffbe7cbac9ee7fd954f00514825f, qtwebengine-chromium
71a2fa55e2e2f5a5d6567aac93bda8775fc7b084) is at SOURCE_URL.

SHA-256:
099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751  pyside-setup-everywhere-src-6.12.0.tar.xz
98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165  qt-everywhere-src-6.12.0.tar.xz
d5dc0bbbd0d753c8944a537189dc2739f297446016d6af1bc44d5d7fbb886e28  qtwebengine-6.12-d4735ce.tar.xz
d258e5a92def26ba37ebea5463c5ea2a0674fded471bf2b6f5ecaf8771fbe865  qtwebengine-chromium-71a2fa55.tar

The Qt libraries are conveyed under LGPL-3.0-only, one alternative in the
qtcoreglobal.h SPDX line. Chromium code keeps the licences in
chromium_attributions.qdoc. This offer lasts three years from the day the
binary is conveyed, which is the period in LGPL-3.0 section 6. Shipping these
archives next to the installer satisfies that section without a separate offer.
```

## Hosting action

The bytes are already in the agent store under `orbitrx-candidate/corresponding-source/`. Reassemble, check the four hashes, and upload those four files to the existing download host as:

- `https://downloads.thevenom.dev/orbitrx/pyside-setup-everywhere-src-6.12.0.tar.xz`
- `https://downloads.thevenom.dev/orbitrx/qt-everywhere-src-6.12.0.tar.xz`
- `https://downloads.thevenom.dev/orbitrx/qtwebengine-6.12-d4735ce.tar.xz`
- `https://downloads.thevenom.dev/orbitrx/qtwebengine-chromium-71a2fa55.tar`

Then set `SOURCE_URL` to `https://downloads.thevenom.dev/orbitrx/` and publish the paragraph. This repository does not perform that upload. The public 5.1.0 zip is a different, already published file and is not replaced by this draft.
