# Qt corresponding source (published)

The corresponding source for the Qt and PySide6 libraries in OrbitRx is
published at `https://downloads.thevenom.dev/orbitrx/`. On 13 November 2026 that
location returned HTTP 200 for all three archives below. For 5.2.0, the offer
itself is the Qt paragraph in `NOTICE`, which ships in the download; this
document records the archives, their hashes and the clause mapping behind that
offer. **Nothing in this document is legal advice or a legal-clearance claim.**

This document replaces the earlier draft text of this file.
`docs/QT_SOURCE_OFFER_DRAFT.md` is superseded by it and is kept only as history.

## Archives that are the corresponding source

Base URL: `https://downloads.thevenom.dev/orbitrx/`

Filenames are immutable and embed the exact commit or version they correspond to,
so a republished archive can never silently shadow an older one at the same name.

### 5.2.0

5.2.0 ships Qt6Core, Qt6Gui, Qt6Widgets, Qt6Network and Qt6Svg (qtbase, qtsvg,
plus the qtimageformats plugins) with PySide6 and Shiboken6, and no Qt
WebEngine. Its corresponding source is these two archives (the offer in NOTICE):

| Archive (hosted filename) | Bytes | SHA-256 | Source commit / version |
| --- | --- | --- | --- |
| `pyside-setup-everywhere-src-6.12.0.tar.xz` | 18,211,772 | `099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751` | PySide6 6.12.0 (PySide6, Shiboken6) |
| `qt-everywhere-src-6.12.0.tar.xz` | 443,394,020 | `98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165` | Qt 6.12.0 (qtbase, qtsvg, qtimageformats among its modules) |

### 5.1.0 (WebEngine era) only

5.1.0 is covered by the same two archives above plus this one:

| Archive (hosted filename) | Bytes | SHA-256 | Source commit / version |
| --- | --- | --- | --- |
| `qtwebengine-everywhere-src-6.140.0-rc.tar.xz` | 580,351,144 | `61257967afd9803a1db6403e86ea25c4efff8fad479bda365a9d81bfd709f621` | qtwebengine `d505fc23640d2bd6345e6483eb73daf4e19f5829` (tag v6.140.0-rc) + chromium `39352427a3245a19fb395547b3aa38be9d091ec4`, bundled as one official full-tree tarball. Covers the WebEngine-era 5.1.0 binary only; 5.2.0 ships no Qt WebEngine. |

The hosted qtwebengine file is the upstream filename, unchanged bytes, fetched from
`download.qt.io/development_releases/qtwebengine/6.140.0-rc/qtwebengine-everywhere-src-6.140.0-rc.tar.xz`
-- it replaces the two separate archives
(`qtwebengine-6.12-d4735ce.tar.xz` + `qtwebengine-chromium-71a2fa55.tar`) named in the
old draft, which pinned the wrong commits.

All three archives stay hosted, unchanged, for as long as copies of 5.1.0 are
offered, and the two 5.2.0 archives for as long as 5.2.0 is offered.

### Open item (5.1.0 only, not part of 5.2.0)

`chromium_attributions.qdoc` is an open 5.1.0-only item. It is not part of the
5.2.0 offer, because 5.2.0 ships no Chromium-derived code. The retained copy
(sha256 `b2382a81239e6c100a3f96342909c6c7e7ecec12fb93e6fe91a5aa3bf756c0ec`) was generated
against chromium `71a2fa55`, not `39352427`, and license-attribution inputs changed
between those two commits (see docs/CORRESPONDING_SOURCE_MANIFEST.json). It is not
hosted (HTTP 404), and `<CREDITS_SHA256>` in the 5.1.0 text below stays a placeholder
until it is regenerated against the actual shipped commit.

## Legal basis for this offer (not legal advice)

This section maps the offer below to specific license clauses so a reviewer can
check the mapping. It is **not** a legal-clearance claim and is **not legal advice**.

- LGPL-3.0-only is not a standalone license text; its own preamble states it
  "incorporates the terms and conditions of version 3 of the GNU General Public
  License, supplemented by the additional permissions listed below." Qt's
  libraries are under LGPL-3.0-only (with a GPL/commercial alternative recorded
  in the `qtcoreglobal.h` SPDX line), so the obligations for conveying a binary
  that links against them run through **GPL-3.0 section 6**, as modified by
  **LGPL-3.0 section 4** for "Combined Works."
- LGPL-3.0 section 4(d) requires that a Combined Work be accompanied by the
  Minimal Corresponding Source for the library, conveyed under terms that
  satisfy GPL-3.0 section 6. Section 4(e) additionally requires Installation
  Information (relinking/reinstallation information) when the Combined Work is
  conveyed in or with a "User Product" under circumstances where GPL-3.0
  section 6 would require Installation Information for that product.
- GPL-3.0 section 6 lists five alternative ways to convey object code together
  with source. Two are relevant here:
  - **6(b)**: accompanying a *physical product* with a *written offer*, valid
    for at least three years (and for as long as spare parts/customer support
    are offered for that product model), to provide the Corresponding Source.
  - **6(d)**: conveying the object code "by offering access from a designated
    place" -- which includes a download server -- and "offer[ing] equivalent
    access to the Corresponding Source in the same way through the same place
    at no further charge." Under 6(d) you remain "obligated to ensure that
    [the Corresponding Source] is available for as long as needed to satisfy
    these requirements" -- GPL-3.0 does not write a fixed three-year duration
    into 6(d) itself; that duration is specific to the 6(b) written-offer
    alternative.
- OrbitRx is distributed as a downloadable installer/onedir, not as a physical
  product accompanied by a written offer letter. **Section 6(d) is therefore
  the applicable clause, not 6(b).** The obligation is to keep the
  Corresponding Source hosted at (or clearly pointed to from) the same place
  the binary is offered, for as long as the binary continues to be offered.
- The "no earlier than 2029-11-08" date in the 5.1.0 offer text below is
  **not** a cited GPL-3.0 section 6(d) requirement. It is an internal,
  conservative *operational retention target* -- a floor below which these
  archives will not be taken down -- chosen to be at least as protective as
  section 6(b)'s three-year minimum, even though 6(b) is not the clause in
  effect here. If OrbitRx were ever to ship a physical medium accompanied by
  its own written 6(b) offer, that offer's three-year clock would apply
  separately, in addition to the 6(d) hosting obligation described here, not
  instead of it.

## 5.1.0 offer text (WebEngine era)

This is the offer text prepared for the WebEngine-era 5.1.0 line. It is not the
5.2.0 offer, which is the Qt paragraph in NOTICE. Its `<CREDITS_SHA256>` line is
the open 5.1.0-only item above.

```
Corresponding source for the Qt and PySide libraries in this OrbitRx onedir
(PySide6 6.12.0, PySide6-WebEngine 6.12.0.140 = Qt WebEngine 6.140.0 at commit
d505fc23640d2bd6345e6483eb73daf4e19f5829 (tag v6.140.0-rc), chromium submodule
commit 39352427a3245a19fb395547b3aa38be9d091ec4, Qt 6.12.0) is at
https://downloads.thevenom.dev/orbitrx/ .

SHA-256:
099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751  pyside-setup-everywhere-src-6.12.0.tar.xz
98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165  qt-everywhere-src-6.12.0.tar.xz
61257967afd9803a1db6403e86ea25c4efff8fad479bda365a9d81bfd709f621  qtwebengine-everywhere-src-6.140.0-rc.tar.xz
<CREDITS_SHA256>  chromium_attributions.qdoc

The Qt libraries are conveyed under LGPL-3.0-only, one alternative in the
qtcoreglobal.h SPDX line. Chromium code keeps its third-party licenses inside
the qtwebengine-everywhere-src archive itself (chromium/ tree, LICENSE and
README.chromium files per component), supplemented by the chromium_attributions.qdoc
credits document regenerated against commit 39352427a3245a19fb395547b3aa38be9d091ec4
and hosted alongside the archives above.

This offer is made under GPL-3.0 section 6(d), as incorporated into LGPL-3.0
section 4 for this Combined Work: the object code is conveyed by offering
access from this download location, so the Corresponding Source above is
hosted at the same location and will stay available for as long as the
corresponding binary continues to be offered. As a conservative operational
retention target -- not itself a section 6(d) requirement, and not a section
6(b) written offer -- these archives will not be taken down before
2029-11-08 (three years from the date of this writing), a target extended by
a further three years from each later conveyance of the binary.
```

## What this document is NOT

- Not a legal-clearance claim of any kind. It states dates, filenames, hashes
  and license-clause mappings only.
- Not legal advice. Anyone relying on the offer for compliance purposes
  should have the clause mapping above independently reviewed.
- Not a statement that `chromium_attributions.qdoc` has been regenerated:
  it is not hosted (HTTP 404) and `<CREDITS_SHA256>` above is a placeholder.
