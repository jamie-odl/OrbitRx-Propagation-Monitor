# OrbitRx Propagation Monitor

Free desktop HF propagation dashboard for radio amateurs. OrbitRx combines NOAA space
weather, band condition estimates, a live DX cluster and live PSKReporter reception
reports on one map, so you can see what is open and who is hearing whom.

![OrbitRx main window with Live Spots](docs/screenshots/01-main-static.png)

> Status: 5.1.0 in development. Windows is the primary target; Linux and macOS run from source.

## Features

**Space weather and propagation**
- Kp index and forecast, F10.7 solar flux, sunspot number, A-index, solar wind and Bz (NOAA SWPC)
- MUF and LUF estimates, per-band open/closed grid, HamQSL band conditions
- Path MUF to a target station, sunrise and sunset at your location
- NOAA alerts summarised to one line each, with an offline cache when NOAA is unreachable

**Map**
- Greyline, night shading, aurora oval and optional grid, with a 24 hour time-travel slider
- One native map, fully offline: the local basemap drawn directly with Qt (no embedded browser, no tile server, no map API key)
- **Live Spots**: PSKReporter reports as band-coloured arcs, plus an activity heatmap
- **Spot replay**: scrub back through the last 24 hours of cached spots (stored for 7 days)

**Station**
- Live DX cluster with band and continent filters; click a spot to tune your radio
- Rig control by Serial CAT (Kenwood, Icom, Yaesu profiles) or OmniRig on Windows
- Spot alerts (local activity, strong signals, long-distance openings), watchlist, rotor headings, ADIF export
- History chart and CSV/JSON export; minimise to system tray

| Static map | Settings | About |
|---|---|---|
| ![Static map](docs/screenshots/01-main-static.png) | ![Settings](docs/screenshots/03-settings.png) | ![About](docs/screenshots/04-about.png) |

## Install

**Windows:** download `OrbitRxMonitor.exe` (or the installer) from the project's Releases
page once 5.1.0 is published. Releases are unsigned: verify each download against
`SHA256SUMS.txt` (for example `Get-FileHash OrbitRxMonitor.exe -Algorithm SHA256` in
PowerShell) before running it. Windows SmartScreen may warn on first run; choose
"More info" then "Run anyway".

**From source (any OS, Python 3.11 or newer):**

```
pip install -r requirements.txt
python app.py
```

## First run

1. Open **Settings** and enter your home latitude and longitude (or opt in to IP location).
2. Optional: set your callsign for Live Spots, your DX cluster login and a QRZ API key.
3. Turn on the **Live** and **Heat** layer chips under the map to show Live Spots and the heatmap.
4. Choose **Rig control**: Serial CAT or OmniRig, then use **Rig** to test the connection.

## Privacy

No account, no analytics, no telemetry. IP based location is **off by default**.
See [PRIVACY.md](PRIVACY.md) for exactly what is sent where.

## Data sources and credits

NOAA SWPC, HamQSL (N0NBH), PSKReporter (Philip Gladstone, N1DQ), DX cluster nodes,
QRZ.com (optional), and WA7BNM Contest Calendar.
The map image is a local file; see [Map image](#map-image). PSKReporter is
polled no more than once every 5 minutes.
Full credits and licences are in [NOTICE](NOTICE).

## Files OrbitRx writes

| File | Contents |
|------|----------|
| `config.json` | Your settings |
| `logs/orbitrx.log` | Rotating application log (attach this to bug reports) |
| `data/orbitrx_spots.db` | Cached PSKReporter spots for replay (7 days) |
| `propagation_log.csv`, `dx_spots_log.csv` | History |

## Troubleshooting

| Problem | What to do |
|---------|------------|
| Status shows "Offline" | NOAA or PSKReporter is unreachable. OrbitRx keeps showing cached data and retries automatically. |
| No location | Enter home latitude and longitude in Settings, or opt in to IP location. |
| Radio does not tune | Check Rig control, COM port and baud rate in Settings, then use **Rig** then **Test CAT**. For OmniRig, install OmniRig and `pywin32`. |
| Anything else | Check `logs/orbitrx.log`. |

## Development

```
pip install -r requirements.txt
pytest -q                       # set QT_QPA_PLATFORM=offscreen on headless Linux
pyinstaller OrbitRxMonitor.spec --noconfirm
```

CI runs the test suite on GitHub-hosted Ubuntu and Windows runners and builds the
Windows executable and installer as workflow artefacts. See [CHANGELOG.md](CHANGELOG.md).

```
orbitrx/
  config.py, weather.py, propagation.py, dx.py, cat.py, alerts.py, map_renderer.py, storage.py
  spots/   PSKReporter client, spot cache, analytics, watchlist, alerts, rotor, OmniRig, ADIF
  ui/      Qt main window, native map widget, theme, about, rig wizard
tests/     pytest suite
installer/ Inno Setup script
```

## Support

OrbitRx is free. If it helps you make contacts, you can buy me a coffee:
https://buymeacoffee.com/thevenom

## Map image

A source checkout loads `basemap/ne_110m_dark.png` (SHA-256 `552ba27ce43dcb838ed13fe59df8b5305d92d40702f33ceadf038392135db183`). The spec entry is `('basemap/ne_110m_dark.png', '.')`, so the onedir folder has `ne_110m_dark.png` next to the executable, not inside a `basemap` directory. `resolve_map_path` checks both places. It is a deterministic render of Natural Earth 1:110m land, dataset SHA-256 `9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9`. Preview: [docs/basemap_ne_110m_preview.png](docs/basemap_ne_110m_preview.png).

`static_basemap_v2.png` (SHA-256 `3046203ae0ade8be43cf9bd647ced5621ab1ee3cdfc95da5269f931b54ab2f1b`) and `static_basemap_v2.webp` (SHA-256 `2704a5d7c6819859c9d42b2659c23a879658724acd2755ca85ca41b33b252e67`) stay in the tree and are not selected. The 5 Nov 2026 exe packaged `world_map.jpg` instead. That published exe is unchanged. See [docs/MAP_IMAGE.md](docs/MAP_IMAGE.md).

The default station pin remains London (`51.5081`, `-0.1281`). IP geolocation stays off unless the user turns it on. There is no paid map key.

## Licence

MIT, Copyright (C) 2026 thevenom. See [LICENSE](LICENSE). That grant was already on this commit. This documentation does not change it. The basemap files are not named in `LICENSE`.
