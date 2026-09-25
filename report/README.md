# GoatCounter Report

Python script that fetches GoatCounter stats via the [stats API][api] and generates a self-contained HTML report with embedded charts.

[api]: https://www.goatcounter.com/api.html

## Quickstart

```bash
# One-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run a report (token is auto-loaded from ../.env.sh)
python goatcounter-report.py --period "this month"
```

The script produces a timestamped directory under `reports/`:

```
reports/<timestamp>_<start>_<end>/
  index.html   (self-contained HTML report with embedded charts)
  data.json    (raw metrics, daily breakdown, top events/pages)
  charts/      (PNG chart images, also embedded inline in index.html)
```

## Usage

```bash
# Friendly period names
python goatcounter-report.py --period "today"
python goatcounter-report.py --period "yesterday"
python goatcounter-report.py --period "this week"
python goatcounter-report.py --period "last week"
python goatcounter-report.py --period "this month"
python goatcounter-report.py --period "last month"
python goatcounter-report.py --period "this year"
python goatcounter-report.py --period "last year"

# Explicit date range
python goatcounter-report.py --start 2026-07-01 --end 2026-07-07

# Single date
python goatcounter-report.py --period 2026-07-04

# Custom site (defaults to https://foighne.goatcounter.com/)
python goatcounter-report.py --site mysite --period "this month"
python goatcounter-report.py --site https://example.goatcounter.com/ --period "this month"
```

## Authentication

The script reads `GOATCOUNTER_API_TOKEN` from the environment. It auto-loads `.env.sh` from the project root if present. The `.env.sh` file should contain:

```sh
export GOATCOUNTER_API_TOKEN=your-api-token-here
```

**Precedence:** a value already set in the environment wins over `.env.sh`, and the script prints a warning when the two disagree (e.g. a token exported earlier in the same shell session for another site). If you see unexpected `401`/`404` responses, check that warning first — or run with `env -u GOATCOUNTER_API_TOKEN python goatcounter-report.py ...` to force `.env.sh`.

**Retries:** the API always returns JSON (`401` for a bad/missing key, `403` for insufficient permission). Transient failures — connection errors, `404`/`408`/`425`/`429`, `5xx`, and non-JSON replies such as GoatCounter's HTML error page — are retried up to 3 times with exponential backoff before failing with a readable message instead of a traceback.

## Report contents

The HTML report includes:

- **Top-line metrics** — total visitors, events, new games, wins, win rate
- **Daily visitors chart** — line chart of visitors per day
- **Event distribution** — donut chart of top events (e.g. `new-game`, `game-won`, `auto-complete`, settings changes)
- **Top pages** — horizontal bar chart of most-visited paths
- **Data tables** — event counts, page counts, browser & OS breakdown

## Dependencies

- `requests` — GoatCounter API calls
- `pandas` — data wrangling
- `matplotlib` + `seaborn` — charts

## Notes

- The GoatCounter export API does **not** support date-range filtering — this script uses the stats API (`/api/v0/stats/total`, `/api/v0/stats/hits`, etc.) which does.
- Generated files land in a `reports/` directory at the project root, so everything is grouped together.
- The `top_referrers` section is not available via the stats API without per-path detail calls, so it's omitted from reports.
