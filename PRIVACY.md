# Privacy

OrbitRx runs on your computer. It has no account, no analytics and no telemetry,
and the author receives no data from it.

## What leaves your computer

| When | Sent to | What is sent |
|------|---------|--------------|
| Always (space weather) | NOAA SWPC, HamQSL | A normal web request (your IP address, OrbitRx User-Agent) |
| Live Spots on (default) | PSKReporter | Your IP address, and the callsign and mode filter you set (if any). At most once every 5 minutes |
| DX cluster on | The cluster node you pick | Your cluster login callsign |
| QRZ key set (optional) | QRZ.com | Your API key and the callsigns you look up |
| Interactive map selected | No tile server. The page is a local file (`file://` image overlay of the basemap) | Nothing for the basemap. Leaflet is bundled in the app |
| Update check on | GitHub | Your IP address |
| IP location turned on (OFF by default) | ipinfo.io | Your IP address; ipinfo returns an approximate location |

## Location

By default OrbitRx does not look up where you are. Enter your home latitude and
longitude in Settings. If you prefer, tick "Look up my approximate location from my
IP address". That sends your IP address to ipinfo.io each refresh. You can turn it
off at any time and nothing further is sent.

## What is stored locally

`config.json` (your settings, including any QRZ key), `logs/` (rotating app logs),
`data/orbitrx_spots.db` (up to 7 days of cached spots for replay), and CSV/JSON
history files. Delete these files to remove all local data.

## Contact

Questions: open an issue on the project repository.
