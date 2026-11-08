# Verified corresponding source offer

The three archives and the notices text below are hosted at a public URL. The hashes in the table were re-verified against a public HTTPS GET to that host on 2026-11-08 (~19:35 GMT, UTC+0); see `RECEIPT_public_get.txt`-style evidence recorded in `packaging/distribution_manifest.json`. That verification establishes hosting and byte identity. It is not a statement of legal clearance: packaging Qt under the LGPL-3.0-only alternative and hosting corresponding source do not by themselves resolve every open item tracked in `docs/DISTRIBUTION.md`.

## Archives that are the corresponding source

| Archive | Bytes | SHA-256 | URL |
| --- | --- | --- | --- |
| `pyside-setup-everywhere-src-6.12.0.tar.xz` | 18,211,772 | `099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751` | `https://downloads.thevenom.dev/orbitrx/pyside-setup-everywhere-src-6.12.0.tar.xz` |
| `qt-everywhere-src-6.12.0.tar.xz` | 443,394,020 | `98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165` | `https://downloads.thevenom.dev/orbitrx/qt-everywhere-src-6.12.0.tar.xz` |
| `qtwebengine-everywhere-src-6.140.0-rc.tar.xz` | 580,351,144 | `61257967afd9803a1db6403e86ea25c4efff8fad479bda365a9d81bfd709f621` | `https://downloads.thevenom.dev/orbitrx/qtwebengine-everywhere-src-6.140.0-rc.tar.xz` |
| `THIRD_PARTY_NOTICES_QtWebEngine-6.140.0.txt` | 1,026,119 | `acde5959267a8afbd29c04f776f228ef6d208fa8a632bf356204174de5c460ca` | `https://downloads.thevenom.dev/orbitrx/THIRD_PARTY_NOTICES_QtWebEngine-6.140.0.txt` |

`qt-everywhere-src-6.12.0.tar.xz` is the official single source archive. Its `.tag` is SHA-1 `ef25002ed292b132d1ed3246bfcee1d24a9cd966`. It contains the Qt modules whose DLLs are in the onedir, including Qt State Machine under `qtscxml/src/statemachine` and Qt Labs StyleKit under `qtdeclarative/src/labs/stylekit`. It does not contain Qt WebEngine.

## Provenance for the WebEngine archive

`qtwebengine-everywhere-src-6.140.0-rc.tar.xz` is the official Qt tarball served from `download.qt.io/development_releases/qtwebengine/6.140.0-rc/`, matching the official `.meta4` metalink for that file. It is qtwebengine commit `d505fc23640d2bd6345e6483eb73daf4e19f5829` (tag `v6.140.0-rc`), whose `src/3rdparty` is the qtwebengine-chromium submodule at `39352427a3245a19fb395547b3aa38be9d091ec4`.

The shipped `Qt6WebEngineCore.dll` is proven to be the same build as Qt's own `qtsdkrepository` 6.12.0 package: the PDB GUID, PDB age, and PE timestamp are identical between the two; the only byte differences are the PE checksum and the Authenticode signature. That ties the shipped binary to this commit pair, not to the superseded pins below.

`THIRD_PARTY_NOTICES_QtWebEngine-6.140.0.txt` is the vendor-SBOM-derived notices document for that same commit pair, generated offline by `gen_notices.py` from Qt's own SPDX SBOMs. It is vendor-SBOM inference, not a GN-identity proof.

## Superseded

`qtwebengine-6.12-d4735ce.tar.xz` (qtwebengine commit `d4735ce2f841ffbe7cbac9ee7fd954f00514825f`, chromium submodule `71a2fa55e2e2f5a5d6567aac93bda8775fc7b084`, claimed chromium version base `140.0.7339.264`, security patches through `151.0.7922.108`) and `qtwebengine-chromium-71a2fa55.tar` are superseded. `d4735ce` was the 6.12 branch tip, not the tagged `v6.140.0-rc` (`d505fc23`) that the shipped binary's DLL identity and its own vendor SBOM name. Neither file is current source for the shipped build and neither must be presented as such.

## Text ready to publish

```
Corresponding source for the Qt and PySide libraries in this OrbitRx onedir
(PySide6 6.12.0, PySide6-WebEngine 6.12.0.140, Qt 6.12.0, qtwebengine
d505fc23640d2bd6345e6483eb73daf4e19f5829, qtwebengine-chromium
39352427a3245a19fb395547b3aa38be9d091ec4) is at
https://downloads.thevenom.dev/orbitrx/.

SHA-256:
099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751  pyside-setup-everywhere-src-6.12.0.tar.xz
98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165  qt-everywhere-src-6.12.0.tar.xz
61257967afd9803a1db6403e86ea25c4efff8fad479bda365a9d81bfd709f621  qtwebengine-everywhere-src-6.140.0-rc.tar.xz
acde5959267a8afbd29c04f776f228ef6d208fa8a632bf356204174de5c460ca  THIRD_PARTY_NOTICES_QtWebEngine-6.140.0.txt

The Qt libraries are conveyed under LGPL-3.0-only, one alternative in the
qtcoreglobal.h SPDX line. Chromium code keeps its third-party licenses
inside the corresponding source archive itself (chromium/ tree, LICENSE and
README.chromium per component), supplemented by
third_party/qt/THIRD_PARTY_NOTICES_QtWebEngine-6.140.0.txt (1,026,119 bytes,
sha256 acde5959267a8afbd29c04f776f228ef6d208fa8a632bf356204174de5c460ca), a
vendor-SBOM-derived notices file generated offline by gen_notices.py from
Qt's own SPDX SBOMs for this build (vendor-SBOM inference, not a
GN-identity proof). It supersedes the former gn-generated
chromium_attributions.qdoc and that file's regeneration path,
REGENERATE_CREDITS.ps1 (the regenerate-credits workflow); both are
superseded and must not be run. This offer is made under GPL-3.0 section
6(d), as incorporated into LGPL-3.0 section 4 for this Combined Work: the
object code is conveyed by offering access from a download location, so the
Corresponding Source above is hosted at that same location and stays
available for as long as the binary continues to be offered. That is not
the physical-product written-offer clause in GPL-3.0 section 6(b), which
carries its own fixed three-year minimum; no such fixed figure applies
under 6(d) itself.
```

## Hosting verification (2026-11-08)

A public HTTPS GET against each URL above returned HTTP/2 200, with `content-length` and a SHA-256 of the response body matching the table, taken 2026-11-08 ~19:35 GMT (UTC+0). That GET verifies hosting and byte identity; it does not itself constitute legal clearance -- see `docs/DISTRIBUTION.md` for the remaining open items, including the still-open release blocker `final-public-candidate-gate-pending`. The public 5.1.0 zip is a different, already published file and is not replaced by this offer.
