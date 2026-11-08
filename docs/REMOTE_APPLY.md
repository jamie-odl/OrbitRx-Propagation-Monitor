# REMOTE_APPLY.md -- mechanical edits for a cloud agent with repo + store write access

This sandbox cannot write to the application repo or to the read-only agent
store, so none of the edits below have been applied anywhere. They are exact,
copy-paste replacement text. **Nothing in this file is legal advice or a
legal-clearance claim** -- it only mechanically carries forward the text
already drafted in `docs/QT_SOURCE_OFFER.md`, `docs/NOTICE_QT_SECTION.md`,
and `docs/CORRESPONDING_SOURCE_MANIFEST.json`.

## Order of operations

1. **Regenerate** -- run `docs/REGENERATE_CREDITS.ps1` on a Windows+MSVC
   runner (canonical path: the shipped binary is a Windows/MSVC build, and
   several `extend_gn_target(... CONDITION WIN32 ...)` branches in
   qtwebengine's `src/core/CMakeLists.txt` only fire under a real Windows+MSVC
   CMake configure). `docs/REGENERATE_CREDITS.sh` (Linux) may be run first as
   a mechanism smoke test, but its output is best-effort only and must not be
   the one hosted or hashed into the placeholders below.
2. **Fill placeholders** -- take the `sha256` and byte count the Windows run
   printed for `chromium_attributions.qdoc` and substitute them for every
   `<CREDITS_SHA256>` / `<CREDITS_BYTES>` occurrence below (and in
   `docs/QT_SOURCE_OFFER.md` / `docs/CORRESPONDING_SOURCE_MANIFEST.json`,
   which use the same placeholders).
3. **Re-gate** -- have an independent pass (not the agent that ran the
   regeneration) confirm: the FIDELITY check in step 7 of the `.ps1` run
   printed `PASS` (or, if `NOT CHECKED`, that a production GN-args log was
   obtained and diffed some other way); the new hash differs from the stale
   `b2382a81...` hash; and the byte count is plausible (same order of
   magnitude as the stale file's 707,649 bytes). Record the re-gate result
   before proceeding.
4. **Host** -- upload the three already-verified archives plus the
   newly-regenerated `chromium_attributions.qdoc` to
   `https://downloads.thevenom.dev/orbitrx/`, then apply edits 1-3 below.

Do not reorder these steps -- in particular, do not host or publish before
the re-gate in step 3 passes.

---

## Edit 1 of 3: repo file `docs/QT_SOURCE_OFFER_DRAFT.md`

Replace the entire contents of `docs/QT_SOURCE_OFFER_DRAFT.md` with the
entire contents of `docs/QT_SOURCE_OFFER.md` from this directory, verbatim,
**after** substituting `<CREDITS_SHA256>` with the real value from step 2
above. That file already contains:

- the corrected archive table (three verified archives, Base URL
  `https://downloads.thevenom.dev/orbitrx/`);
- the "Legal basis for this offer" section mapping the offer to GPL-3.0
  section 6(d) (incorporated via LGPL-3.0 section 4), not section 6(b),
  with the three-year/2029-11-08 figure explicitly labeled as an internal
  operational retention target rather than a cited section 6(d) requirement;
- the publishable fenced paragraph with the `<CREDITS_SHA256>` placeholder
  for the `chromium_attributions.qdoc` line;
- the "What this document is NOT" disclaimer block, including "Not legal
  advice."

Do not publish/host-confirm this replacement until the placeholder has been
filled per step 2 and the re-gate in step 3 has passed.

## Edit 2 of 3: repo file `NOTICE` (Qt/PySide section only)

Replace only the Qt/PySide section of the real `NOTICE` file with the fenced
block from `docs/NOTICE_QT_SECTION.md` in this directory, verbatim:

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
component under chromium/ in the corresponding source archive, supplemented
by a separately generated chromium_attributions.qdoc credits document.

The corresponding source for these libraries is offered under GPL-3.0
section 6(d), as incorporated into LGPL-3.0 section 4 for this Combined
Work: the archives are hosted at the same place the binary is offered, and
will remain available there for as long as the binary continues to be
offered. See QT_SOURCE_OFFER.md for the archive list, hashes, and the
offer's hosting URL and retention target.

For guidance on replacing or rebuilding these Qt libraries from source, see
REPLACING_QT_LIBRARIES.md.
```

Confirm `REPLACING_QT_LIBRARIES.md` already exists in the repo and covers the
6.140.0 commit pair before merging this NOTICE text (per
`docs/NOTICE_QT_SECTION.md`'s reviewer notes -- it was not authored in this
pass).

## Edit 3 of 3: agent-store `orbitrx-candidate/corresponding-source/MANIFEST.json`

This sandbox has read-only access to that store path; apply the following
there with write access:

1. Replace the store's `qtwebengine` entry and its
   `retained_source.qtwebengine_chromium` entry with the single
   `qtwebengine-everywhere-src-6.140.0-rc.tar.xz` entry as given in
   `docs/CORRESPONDING_SOURCE_MANIFEST.json`'s `files` array (name, bytes
   `580351144`, sha256 `61257967afd9803a1db6403e86ea25c4efff8fad479bda365a9d81bfd709f621`,
   commit `d505fc23640d2bd6345e6483eb73daf4e19f5829` / chromium
   `39352427a3245a19fb395547b3aa38be9d091ec4`, `no_gitlinks: true`,
   `src_3rdparty_empty: false`).
2. Set `chromium_bytes_included = true` on that entry (and rename/fix any
   equivalently-named field, e.g. `this_tarball_contains_chromium_tree`) --
   the old store entry for `d4735ce` had this `false` because its chromium
   tree was retained in a separate tarball; the new everywhere tarball
   bundles the full chromium tree (296,006 entries under `src/3rdparty/`) in
   the same file, so the field must read `true`.
3. Add the `chromium_attributions.qdoc` entry from
   `docs/CORRESPONDING_SOURCE_MANIFEST.json`, with `status` left as
   `pending-regeneration` and `sha256`/`bytes` left as the `<CREDITS_SHA256>`
   / `<CREDITS_BYTES>` placeholders, until step 2 of the order-of-operations
   above is actually completed -- then overwrite the placeholders with the
   real values and flip `status` to `verified`.
4. Mark the two superseded entries explicitly:
   - `qtwebengine-6.12-d4735ce.tar.xz` (sha256
     `d5dc0bbbd0d753c8944a537189dc2739f297446016d6af1bc44d5d7fbb886e28`) --
     wrong commit (6.12 branch tip, not the tagged v6.140.0-rc the shipped
     binary's own SBOM names).
   - `qtwebengine-chromium-71a2fa55.tar` (sha256
     `d258e5a92def26ba37ebea5463c5ea2a0674fded471bf2b6f5ecaf8771fbe865`) --
     wrong chromium commit, 138 commits behind the actual pin `39352427`.
   Either delete these two entries from the live `files` list or move them
   into a `superseded_files` list as `docs/CORRESPONDING_SOURCE_MANIFEST.json`
   already does. **Do not host either file.**

---

## Placeholder reference

| Placeholder | Filled from | Appears in |
| --- | --- | --- |
| `<CREDITS_SHA256>` | sha256 printed by `docs/REGENERATE_CREDITS.ps1` step 9 | `docs/QT_SOURCE_OFFER.md`, `docs/CORRESPONDING_SOURCE_MANIFEST.json`, store `MANIFEST.json` |
| `<CREDITS_BYTES>` | byte count printed by `docs/REGENERATE_CREDITS.ps1` step 9 | `docs/CORRESPONDING_SOURCE_MANIFEST.json`, store `MANIFEST.json` |

Both placeholders currently appear unfilled in every file listed above --
do not fill one occurrence without filling all of them, and do not host
anything while either placeholder is still present.
