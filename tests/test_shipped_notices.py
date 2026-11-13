"""Notices, basemap record, and zip wrapper on the shipped 5.1.0 line.

The MIT grant file is pinned by hash so this work cannot rewrite it.
The full historical zip check runs only when ORBITRX_SETUP_EXE points
at the installer; CI does not have that file.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from orbitrx.config import DEFAULT_CONFIG

ROOT = Path(__file__).resolve().parents[1]
NOTICE = (ROOT / "NOTICE").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
PRIVACY = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
MAP_DOC = (ROOT / "docs" / "MAP_IMAGE.md").read_text(encoding="utf-8")
DEPS = (ROOT / "docs" / "DEPENDENCY_LICENCES.md").read_text(encoding="utf-8")
ZIP_DOC = (ROOT / "docs" / "SETUP_ZIP.md").read_text(encoding="utf-8")

MIT_GRANT_SHA256 = "19da41191a556cbe12cfd4a51839e86c7345204ac73834771b41a07b8ed524b6"
PNG_SHA256 = "3046203ae0ade8be43cf9bd647ced5621ab1ee3cdfc95da5269f931b54ab2f1b"
WEBP_SHA256 = "2704a5d7c6819859c9d42b2659c23a879658724acd2755ca85ca41b33b252e67"


def test_existing_mit_grant_is_not_rewritten():
    licence = (ROOT / "LICENSE").read_bytes()
    assert hashlib.sha256(licence).hexdigest() == MIT_GRANT_SHA256
    assert licence.startswith(b"MIT License\n")
    assert b"Copyright (C) 2026 thevenom" in licence


def test_london_default_and_offline_map_stay():
    assert DEFAULT_CONFIG["home_lat"] == 51.5081
    assert DEFAULT_CONFIG["home_lon"] == -0.1281
    assert DEFAULT_CONFIG["ip_geolocation_enabled"] is False
    assert DEFAULT_CONFIG["map_backend"] == "static"
    assert DEFAULT_CONFIG["qrz_api_key"] == ""
    assert "mapbox" not in NOTICE.lower()
    assert not (ROOT / "orbitrx" / "ui" / "leaflet_map.py").exists()


def test_broken_osm_notice_is_corrected_and_map_section_exists():
    assert "Foundation tile servers" not in NOTICE
    assert 'README "Map image"' in NOTICE
    assert "docs/MAP_IMAGE.md" in NOTICE
    assert "## Map image" in README
    assert PNG_SHA256 in README
    assert PNG_SHA256 in MAP_DOC
    assert WEBP_SHA256 in MAP_DOC
    assert "0.937" in MAP_DOC
    assert "public domain" in MAP_DOC
    assert "does not extend that grant" in MAP_DOC
    assert "OpenStreetMap tile servers" not in PRIVACY
    # F11: no Leaflet/WebEngine claim — the map is native-only now.
    assert "Leaflet" not in PRIVACY
    assert "No tile server" in PRIVACY
    about = (ROOT / "orbitrx" / "ui" / "about.py").read_text(encoding="utf-8")
    assert "OpenStreetMap credits" not in about
    assert "application source is under the MIT License" in about
    assert "does not cover Qt" in about
    qt = (ROOT / "orbitrx" / "ui" / "qt_app.py").read_text(encoding="utf-8")
    assert "Interactive map · OpenStreetMap" not in qt
    assert "Map · offline basemap" in qt


def test_dependency_lines_follow_upstream_files():
    assert "PSF-based" not in NOTICE
    assert "pywin32 (PSF)" not in NOTICE
    assert "BSD-3-Clause" in NOTICE
    assert "LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only" in NOTICE
    assert "customtkinter is not a dependency" in NOTICE
    assert "76d491638b" in DEPS
    assert "win32/License.txt" in DEPS
    assert "not the PSF licence text" in DEPS
    assert "customtkinter" not in (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()


def test_basemap_digests_match_the_files():
    assert hashlib.sha256((ROOT / "static_basemap_v2.png").read_bytes()).hexdigest() == PNG_SHA256
    assert hashlib.sha256((ROOT / "static_basemap_v2.webp").read_bytes()).hexdigest() == WEBP_SHA256


def test_zip_wrapper_is_split_into_historical_and_future():
    from tools.pack_setup_zip import (
        HISTORICAL_DOS_DATE,
        HISTORICAL_DOS_TIME,
        HISTORICAL_ZIP_SHA256,
        future_zip,
        historical_observed_zip,
    )

    assert HISTORICAL_ZIP_SHA256 in ZIP_DOC
    assert "not a command found in git" in ZIP_DOC
    sample = b"not-the-installer"
    historical = historical_observed_zip(sample)
    future = future_zip(sample, datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
    assert historical != future
    assert HISTORICAL_DOS_TIME == 20601
    assert HISTORICAL_DOS_DATE == 23909
    assert hashlib.sha256(historical).hexdigest() != HISTORICAL_ZIP_SHA256


def test_default_zip_name_uses_the_version_file():
    from tools.pack_setup_zip import default_zip_name

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert default_zip_name(version) == "OrbitRx-Setup-5.2.0.zip"


def test_setup_zip_doc_names_the_live_5_1_0_digest_not_the_superseded_one():
    """The live 5.1.0 zip (since 9 Nov 2026) is d6a3aebf...; bb8f087e... is the
    superseded 5 Nov installer-only archive and must not be presented as the
    current published checksum."""
    from tools.pack_setup_zip import HISTORICAL_ZIP_SHA256, LIVE_ZIP_SHA256

    assert LIVE_ZIP_SHA256 == "d6a3aebf3c79389949ce3ca4abe2b865fe6d1ce4346aa409ba610b053c609c6f"
    assert LIVE_ZIP_SHA256 != HISTORICAL_ZIP_SHA256
    live_section = ZIP_DOC.split("## Superseded 5 November 2026 archive")[0]
    assert f"{LIVE_ZIP_SHA256}  OrbitRx-Setup-5.1.0.zip" in live_section
    assert "434,814,502 bytes" in live_section
    assert f"{HISTORICAL_ZIP_SHA256}  OrbitRx-Setup-5.1.0.zip" not in live_section
    assert "superseded" in live_section
    assert "## Superseded 5 November 2026 archive" in ZIP_DOC


def test_historical_wrapper_matches_published_zip_when_installer_present():
    exe = os.environ.get("ORBITRX_SETUP_EXE")
    if not exe:
        return
    from tools.pack_setup_zip import HISTORICAL_EXE_SHA256, HISTORICAL_ZIP_SHA256, historical_observed_zip

    data = Path(exe).read_bytes()
    assert hashlib.sha256(data).hexdigest() == HISTORICAL_EXE_SHA256
    assert hashlib.sha256(historical_observed_zip(data)).hexdigest() == HISTORICAL_ZIP_SHA256


def test_qt_replacement_notice_points_to_shipped_internal_doc():
    assert "_internal/REPLACING_QT_LIBRARIES.md" in NOTICE
    assert "See\n    docs/REPLACING_QT_LIBRARIES.md" not in NOTICE
    assert "See docs/REPLACING_QT_LIBRARIES.md" not in NOTICE


def test_notice_qt_paragraph_names_the_actual_ship_set_not_the_false_plain_sentence():
    """F1 (2026-11-12): "Only the plain Qt libraries (Widgets, Core, Gui) are
    linked and shipped" was false -- Network and Svg ship too, and the wheel
    also carries (but this build drops) Pdf, Virtual Keyboard, Quick/Qml and
    OpenGL. The paragraph must name what is actually shipped instead.

    M5: a mutant that drops Qt6Network/Qt6Svg from the shipped-libraries
    sentence must be caught even though those two names also occur later in
    the source-offer text -- so this extracts that sentence by its anchor
    phrases instead of searching NOTICE as a whole."""
    from tools.ship_set import REQUIRED_QT_DLLS

    assert "Only the plain Qt libraries (Widgets, Core, Gui)" not in NOTICE
    anchor_start = "actually linked and shipped are"
    anchor_end = "together with"
    assert anchor_start in NOTICE, "shipped-libraries anchor phrase is missing from NOTICE"
    after_start = NOTICE.split(anchor_start, 1)[1]
    assert anchor_end in after_start, "shipped-libraries anchor end phrase is missing from NOTICE"
    sentence = after_start.split(anchor_end, 1)[0]
    normalised = " ".join(sentence.split()).replace(" and ", ", ")
    named = {part.strip().rstrip(",") for part in normalised.split(",")} - {""}
    assert named == {dll.removesuffix(".dll") for dll in REQUIRED_QT_DLLS}

    for plugin_category in ("platforms", "imageformats", "iconengines", "styles", "tls", "networkinformation"):
        assert plugin_category in NOTICE
    for not_shipped in ("Qt PDF", "Qt Virtual Keyboard", "Qt Quick/Qml", "Qt OpenGL"):
        assert not_shipped in NOTICE
    assert "Qt WebEngine" in NOTICE and "Qt WebChannel" in NOTICE
    assert "No Chromium-derived code is\n    shipped by this build." in NOTICE
    assert "opengl32sw.dll" in NOTICE
    assert "Mesa llvmpipe" in NOTICE
    assert "ship-set filter and is not shipped" in NOTICE
    assert "PySide6 and Shiboken6" in NOTICE


def test_notice_and_packaged_replacing_doc_agree_on_the_same_offer():
    replacing = (ROOT / "docs" / "REPLACING_QT_LIBRARIES.md").read_text(encoding="utf-8")
    assert "not an offer" not in replacing
    assert "QT_SOURCE_OFFER_DRAFT.md" not in replacing
    pyside_sha = "099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751"
    qt_sha = "98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165"
    for sha in (pyside_sha, qt_sha):
        assert sha in NOTICE
        assert sha in replacing
    assert "https://downloads.thevenom.dev/orbitrx/pyside-setup-everywhere-src-6.12.0.tar.xz" in replacing
    assert "https://downloads.thevenom.dev/orbitrx/qt-everywhere-src-6.12.0.tar.xz" in replacing
    for dll in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll", "Qt6Svg.dll"):
        assert dll in replacing


def test_notice_makes_one_consistent_statement_about_the_source_offer():
    """NOTICE must not simultaneously deny and make the Corresponding Source
    offer. It names LGPL-3.0-only as the conveyance route and then offers
    Corresponding Source under GPL-3.0 6(d)/LGPL-3.0 4 -- it must never also
    say the offer was not published."""
    replacing = (ROOT / "docs" / "REPLACING_QT_LIBRARIES.md").read_text(encoding="utf-8")
    for doc in (NOTICE, replacing):
        assert "not a published source offer" not in doc
        assert "not an offer" not in doc
    assert "is offered under GPL-3.0 section 6(d)" in NOTICE
    assert "This offer is made under GPL-3.0 section 6(d)" in replacing


def test_notice_names_openssl_3_and_its_licence_text():
    assert "OpenSSL 3" in NOTICE
    assert "Apache License 2.0" in NOTICE or "Apache-2.0" in NOTICE
    for dll in ("libcrypto-3.dll", "libssl-3.dll", "libcrypto-3-x64.dll", "libssl-3-x64.dll"):
        assert dll in NOTICE
    assert "third_party/openssl/LICENSE.txt" in NOTICE


def test_spec_datas_include_the_openssl_licence_text():
    spec = (ROOT / "OrbitRxMonitor.spec").read_text(encoding="utf-8")
    assert "('third_party/openssl/LICENSE.txt', 'third_party/openssl')" in spec


def test_openssl_licence_text_is_the_apache_2_0_header():
    path = ROOT / "third_party" / "openssl" / "LICENSE.txt"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Apache License" in text
    assert "Version 2.0" in text


def test_no_tracked_file_references_the_404_qtwebengine_rename():
    """The never-uploaded rename of the hosted qtwebengine archive returns
    HTTP 404 at downloads.thevenom.dev; the hosted file keeps its upstream
    name, qtwebengine-everywhere-src-6.140.0-rc.tar.xz (see
    docs/QT_SOURCE_OFFER_DRAFT.md). The renamed string is assembled at
    runtime so this test itself does not trip its own check."""
    import subprocess

    this_file = Path(__file__).relative_to(ROOT).as_posix()
    renamed = "qtwebengine-everywhere-src-6.140.0-rc-" + "d505fc23640d-39352427a324.tar.xz"
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    offenders = []
    for rel in tracked:
        if rel == this_file:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if renamed in text:
            offenders.append(rel)
    assert offenders == []
