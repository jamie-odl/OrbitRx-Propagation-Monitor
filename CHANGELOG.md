# Changelog

All notable changes to OrbitRx are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow SemVer.

## [Unreleased]

## [5.1.0] - not yet released

### Added
- Live Spots: PSKReporter reception reports drawn as band-coloured arcs and an
  activity heatmap on the interactive map, with a 24 hour replay slider.
- `orbitrx.spots` package, merged from WSPR / FT8 Global Matrix: PSKReporter
  client, SQLite spot cache, analytics, watchlist, spot alerts, rotor headings,
  OmniRig bridge and ADIF export, with their tests.
- Rig control setting: Serial CAT or OmniRig (Windows).
- Manual home location in Settings; IP geolocation is now opt-in.
- About dialog with licence, data credits and a support link.
- MIT LICENSE, NOTICE (data credits), PRIVACY.md, VERSION, this changelog.
- GitHub-hosted CI on Ubuntu and Windows, plus a Windows build artefact.

### Changed
- PSKReporter polling is clamped to a 5 minute minimum.
- Leaflet is bundled with the app instead of loaded from a CDN.
- Space weather has one source (OrbitRx NOAA feed) shared by the spot analytics.
- Structured, rotating log file in `logs/orbitrx.log`; no console prints.
- Update checker points at the current repository.

### Removed
- Tkinter UI and fallback, `_check.py`, `inspect_noaa.py`, `build_exe.py`,
  `START_HERE.txt`, customtkinter dependency.
- Self-hosted CI runner.

### Changed (release UI pass)
- Settings is now a paged dialog (Station, Rig, DX cluster, Live spots, Map,
  Services) instead of one long scrolling form; the QRZ API key is masked by
  default with a show/hide toggle, and lat/lon and interval fields validate
  their ranges instead of accepting free text.
- Rig setup matches Settings terminology exactly ("Serial port", "Rig
  profile", "Baud rate"), is wider, and shows the Test CAT result inline with
  a status icon and the test frequency.
- The history plot's date axis uses `AutoDateLocator`/`ConciseDateFormatter`
  instead of overlapping year-spanning ticks, and Kp (0-9) and solar flux
  (50-300) now have their own labelled axes instead of sharing one scale.
  The date field is a calendar-popup `QDateEdit`.
- Raw/internal values (NOAA source identifiers, ISO timestamps, decimal-hour
  sunrise/sunset) are now formatted for display via a new
  `orbitrx.ui.formatting` module; missing values show "n/a" instead of "--".
- Reworded ambiguous or inconsistent UI copy: map interaction hints, the
  slider labels, the duplicated map-source banner line, and the About
  dialog's "buy me a coffee" line (the link itself, and its TODO placeholder
  constant, are unchanged pending the real page).
- Stats panel uses a scrollable form layout with no horizontal scrollbar;
  alerts moved into their own list with full-text tooltips.
- Input and checkbox borders now meet 3:1 UI contrast against the dark
  background; the app uses a 4-size type scale (caption/body/section/title).
- Static map view now fits the viewport on load, resize and show.
- Generated `assets/orbitrx.ico` and wired it into the window icon, the
  PyInstaller executable, and the Inno Setup installer; the installer now
  sets the publisher, product name and version resource fields. The
  PyInstaller build excludes unused Qt modules (3D, multimedia, charts, etc.)
  to shrink the bundle.

## [5.0.0]
- Qt package refactor and propagation dashboard upgrades.
