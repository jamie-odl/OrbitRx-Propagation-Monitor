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

## [5.0.0]
- Qt package refactor and propagation dashboard upgrades.
