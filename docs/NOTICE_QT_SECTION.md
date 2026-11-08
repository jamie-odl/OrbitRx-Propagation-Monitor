# NOTICE_QT_SECTION.md -- corrected NOTICE text (Stage 2 draft, NOT a repo edit)

Standalone draft for the Qt/PySide section of the shipped NOTICE file. Replace the
corresponding section of the real NOTICE with the text below once reviewed; this
file itself does not modify the repository. This revision corrects the Stage 1
draft's reference to "LGPL-3.0 section 6" (LGPL-3.0 has no section 6 of its own;
the relevant GPL-3.0 clause, incorporated via LGPL-3.0 section 4, is section
6(d) for this download-based conveyance -- see docs/QT_SOURCE_OFFER_DRAFT.md "Legal
basis for this offer"). **Nothing here is legal advice.**

```
This product includes PySide6 6.12.0 and PySide6-WebEngine 6.12.0.140.

PySide6-WebEngine 6.12.0.140 packages Qt WebEngine 6.140.0, built from
qtwebengine.git commit d505fc23640d2bd6345e6483eb73daf4e19f5829 (tag
v6.140.0-rc), whose src/3rdparty (Chromium) submodule is pinned to
qtwebengine-chromium.git commit 39352427a3245a19fb395547b3aa38be9d091ec4
(Chromium 140.0.7339.225 plus security backports, including a fix for
CVE-2026-85042).

Qt and PySide6 are available under LGPL-3.0-only (with one GPL/commercial
alternative recorded in the respective qtcoreglobal.h SPDX headers); Chromium
third-party code retains its individual upstream licenses as recorded per
component under chromium/ in the corresponding source archive, supplemented by
third_party/qt/THIRD_PARTY_NOTICES_QtWebEngine-6.140.0.txt (1,026,119 bytes,
sha256 acde5959267a8afbd29c04f776f228ef6d208fa8a632bf356204174de5c460ca), a
vendor-SBOM-derived notices document generated offline by gen_notices.py from
Qt's own SPDX SBOMs for this build (vendor-SBOM inference, not a GN-identity
proof). That file supersedes third_party/qt/chromium_attributions.qdoc and its
regeneration path, REGENERATE_CREDITS.ps1 (the regenerate-credits workflow);
both are superseded and must not be run.

The corresponding source for these libraries is offered under GPL-3.0
section 6(d), as incorporated into LGPL-3.0 section 4 for this Combined
Work: the archives are hosted at the same place the binary is offered, and
will remain available there for as long as the binary continues to be
offered. See docs/QT_SOURCE_OFFER_DRAFT.md (DRAFT -- not yet live) for the
archive list, hashes, and the offer's hosting URL and retention target.

For guidance on replacing or rebuilding these Qt libraries from source, see
REPLACING_QT_LIBRARIES.md.
```

## Notes for the reviewer

- This corrects two things in the prior NOTICE draft:
  1. (per old-offer-draft.md) the named qtwebengine commit `d4735ce2f841ffbe7cbac9ee7fd954f00514825f`
     / chromium `71a2fa55e2e2f5a5d6567aac93bda8775fc7b084` -- confirmed by pass2 and
     independently re-confirmed in the Stage 1 pass to be the wrong commit pair
     for the binary actually shipped (see RESOLUTION.md, pass2-claude-output.txt,
     and CORRESPONDING_SOURCE_MANIFEST.json).
  2. the legal-clause citation -- the Stage 1 draft said "LGPL-3.0 section 6" and
     tied the offer to a three-year written-offer rule. LGPL-3.0 has no section 6;
     that rule is GPL-3.0 section 6(b), which applies to a physical product
     accompanied by a written offer. OrbitRx conveys the binary by download, which
     is GPL-3.0 section 6(d) (incorporated via LGPL-3.0 section 4): source must stay
     available at the hosting location for as long as the binary is offered, with no
     fixed three-year figure in the clause itself. See docs/QT_SOURCE_OFFER_DRAFT.md.
- `REPLACING_QT_LIBRARIES.md` is referenced but not authored in this pass --
  it is assumed to already exist in the repository (packaging docs); this
  draft only points to it. Confirm it exists and covers the 6.140.0 commit
  pair before merging this NOTICE text.
- `third_party/qt/chromium_attributions.qdoc` and its regeneration path,
  `docs/REGENERATE_CREDITS.ps1` (the regenerate-credits workflow), are
  superseded by `third_party/qt/THIRD_PARTY_NOTICES_QtWebEngine-6.140.0.txt`
  and must not be run.
- No legal-clearance claim is made anywhere in this text, and none of it is
  legal advice.
