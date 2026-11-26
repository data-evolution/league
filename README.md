# League Live Analysis

A local Flask dashboard for League of Legends live games, with lane matchups,
NA ranks, champion stats, estimated team gold, objective participation, and
counter-build suggestions. It polls every two seconds and shows demo data when
no live game is available.

## Run locally

Install Python 3.10+ and run from the repository directory in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src/app.py
```

Open http://127.0.0.1:5000 while League is running. Flask proxies the local
Live Client Data API so the browser does not need to handle its self-signed
HTTPS certificate or cross-origin restrictions.

## Optional NA ranks

Get a developer API key from https://developer.riotgames.com/ and set it in
the same PowerShell terminal before starting Flask:

```powershell
$env:RIOT_API_KEY = 'your-key-here'
.\.venv\Scripts\python.exe src/app.py
```

The key stays on the server. Both teams show Solo/Duo ranks and LP; hover a
portrait or player details for Flex standings. Riot ID lookups use the Americas
Account API and NA1 League API. Results are cached for ten minutes and fetched
in the background. Missing or expired keys, rate limits, and unavailable
accounts are displayed separately from unranked players. Demo players do not
trigger ranked lookups.

Rank diagnostics go to the terminal and `logs/ranks.log`, which rotates at
2 MB with three backups. Rank logs redact API keys. Logs and local environment
files are excluded from Git.

## Configuration

Set environment variables in the terminal before starting Flask; the app does
not load `.env` files automatically.

| Variable | Default | Purpose |
| --- | --- | --- |
| `RIOT_API_KEY` | Unset | Optional NA ranked lookups |
| `LOL_CLIENT_URL` | `https://127.0.0.1:2999/liveclientdata/allgamedata` | Live client endpoint |
| `LOL_CLIENT_VERIFY_TLS` | `false` | Verify the local client's TLS certificate |
| `LOL_HTTP_TIMEOUT` | `4` | Upstream request timeout in seconds |
| `FLASK_HOST` | `127.0.0.1` | Local server address |
| `FLASK_PORT` | `5000` | Local server port |
| `FLASK_DEBUG` | `true` | Flask development debug mode |

Data Dragon provides patch metadata, champion and item icons, and spell details.
Its catalog is cached for ten minutes and uses normal HTTPS verification. These
public endpoints and the Live Client Data API do not require a Riot API key.
Gold and build recommendations are estimates based on the available live data.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## License

Copyright (c) 2026 [Data Evolution](https://data-evolution.net/). Source code is licensed under the
[MIT License](LICENSE). Riot Games names, artwork, and game data remain the
property of their respective owners.
