#!/usr/bin/env python3
"""
goatcounter-report.py

Fetch GoatCounter stats via the stats API for a date range, compute KPIs,
generate charts (PNG), and write a self-contained HTML report with embedded images.

Usage:
  python3 report/goatcounter-report.py --period "this month"
  python3 report/goatcounter-report.py --site foighne --period "last month"
  python3 report/goatcounter-report.py --start 2026-07-01 --end 2026-07-07

Notes:
  - Calls GoatCounter API v0 stats endpoints per https://www.goatcounter.com/api.html
  - API token is read from the GOATCOUNTER_API_TOKEN environment variable.
    The script auto-loads .env.sh from the project root if present.
  - Produces a timestamped directory under reports/:
      reports/<timestamp>_<start>_<end>/
        index.html   (self-contained HTML report)
        data.json    (raw metrics & breakdown)
        charts/      (PNG chart images)

Defaults:
  - GOAT_SITE defaults to "foighne".
  - Pass --period with friendly periods: today, yesterday, this week, last week,
    this month, last month, this year, last year. --period overrides --start/--end.
  - Also supports explicit single date (YYYY-MM-DD) or explicit range using
    YYYY-MM-DD:YYYY-MM-DD
"""

import os
import sys
import argparse
import requests
import io
import json
import datetime as dt
import pandas as pd
import base64

# Matplotlib + seaborn setup for headless environments
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

sns.set(style="whitegrid", palette="muted", font_scale=1.0)

# Resolve project root (where .env.sh lives) so output paths are always absolute
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# ---------------------------------------------------------------------------
# .env.sh auto-loading
# ---------------------------------------------------------------------------

def load_dotenv_sh():
    """Load environment variables from .env.sh in the project root (if present).
    Only sets vars that aren't already in the environment.
    """
    env_file = os.path.join(PROJECT_ROOT, ".env.sh")
    if not os.path.exists(env_file):
        return
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip 'export ' prefix
            if line.startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def get_api_base(site):
    """Build the API base URL from a site identifier."""
    if site.startswith("http://") or site.startswith("https://"):
        return site.rstrip("/") + "/api/v0"
    return f"https://{site}.goatcounter.com/api/v0"


def api_get(api_base, path, params=None, timeout=60):
    """Make an authenticated GET request to the GoatCounter API.
    Returns the parsed JSON response.
    """
    token = os.getenv("GOATCOUNTER_API_TOKEN")
    if not token:
        raise RuntimeError(
            "GOATCOUNTER_API_TOKEN not set. "
            "Source .env.sh or set the env var before running."
        )
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{api_base}/{path.lstrip('/')}"
    resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    if resp.status_code in (401, 403):
        raise RuntimeError(
            f"Auth error ({resp.status_code}) for {url}. "
            "Check GOATCOUNTER_API_TOKEN."
        )
    resp.raise_for_status()
    return resp.json()


def fetch_stats_data(site, start, end):
    """Fetch all relevant stats from the GoatCounter stats API.

    Returns a dict with keys: total, hits, browsers, systems.
    """
    api_base = get_api_base(site)
    params = {"start": start, "end": end}

    # Total pageviews + events with daily breakdown
    total = api_get(api_base, "stats/total", params)

    # Top hits (paths + events), up to 100
    hits_params = {**params, "limit": 100}
    hits = api_get(api_base, "stats/hits", hits_params)

    # Optional: browser and system stats (best-effort)
    browsers = None
    systems = None
    try:
        browsers = api_get(api_base, "stats/browsers", params)
    except Exception:
        pass
    try:
        systems = api_get(api_base, "stats/systems", params)
    except Exception:
        pass

    return {
        "total": total,
        "hits": hits,
        "browsers": browsers,
        "systems": systems,
    }


# ---------------------------------------------------------------------------
# Period parsing
# ---------------------------------------------------------------------------

def parse_period(period):
    """Return (start_date_str, end_date_str) for friendly English period phrases.

    Accepted phrases (case-insensitive):
      today, yesterday,
      this week, last week,
      this month, last month,
      this year, last year

    Also accepts explicit single date YYYY-MM-DD or explicit range
    YYYY-MM-DD:YYYY-MM-DD.
    """
    if not period:
        return None
    s = period.strip().lower()
    # explicit range
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 2:
            try:
                start = dt.datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
                end = dt.datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
                return (start.isoformat(), end.isoformat())
            except Exception:
                raise ValueError("Invalid explicit range. Use YYYY-MM-DD:YYYY-MM-DD")
    today = dt.date.today()
    if s == "today":
        return (today.isoformat(), today.isoformat())
    if s == "yesterday":
        d = today - dt.timedelta(days=1)
        return (d.isoformat(), d.isoformat())
    if s in ("this week", "current week", "week"):
        start = today - dt.timedelta(days=today.weekday())
        return (start.isoformat(), today.isoformat())
    if s in ("last week", "previous week"):
        start = today - dt.timedelta(days=today.weekday() + 7)
        end = start + dt.timedelta(days=6)
        return (start.isoformat(), end.isoformat())
    if s in ("this month", "month"):
        start = today.replace(day=1)
        return (start.isoformat(), today.isoformat())
    if s in ("last month", "previous month"):
        first_of_this = today.replace(day=1)
        last_month_end = first_of_this - dt.timedelta(days=1)
        start = last_month_end.replace(day=1)
        end = last_month_end
        return (start.isoformat(), end.isoformat())
    if s in ("this year", "year"):
        start = today.replace(month=1, day=1)
        return (start.isoformat(), today.isoformat())
    if s in ("last year", "previous year"):
        start = today.replace(year=today.year - 1, month=1, day=1)
        end = today.replace(year=today.year - 1, month=12, day=31)
        return (start.isoformat(), end.isoformat())
    # try single date
    try:
        single = dt.datetime.strptime(s, "%Y-%m-%d").date()
        return (single.isoformat(), single.isoformat())
    except Exception:
        raise ValueError(f"Unrecognized period: '{period}'")


# ---------------------------------------------------------------------------
# Report building from stats API response
# ---------------------------------------------------------------------------

def build_report(site, start, end, data):
    """Transform raw stats API responses into a structured report dict."""

    total = data["total"]
    hits_list = data["hits"].get("hits", [])

    # Separate pageviews from events
    pages = [h for h in hits_list if not h.get("event")]
    events = [h for h in hits_list if h.get("event")]

    # Daily breakdown from stats/total
    daily = []
    for s in total.get("stats", []):
        daily.append({
            "day": s["day"],
            "visitors": s.get("daily", 0),
        })

    # Map known event names
    new_games = 0
    wins = 0
    top_events = []
    for e in events:
        path = e.get("path", "")
        cnt = e.get("count", 0)
        top_events.append({"event_type": path, "cnt": cnt})
        if "new-game" in path:
            new_games += cnt
        if "game-won" in path:
            wins += cnt

    top_events.sort(key=lambda x: x["cnt"], reverse=True)

    # Top pages (non-event hits)
    top_pages = [{"path": p.get("path", ""), "cnt": p.get("count", 0)} for p in pages]
    top_pages.sort(key=lambda x: x["cnt"], reverse=True)

    # Win rate
    win_rate = (wins / new_games) if new_games else None

    agg = {
        "total_visitors": total.get("total", 0),
        "total_events": total.get("total_events", 0),
        "new_games": new_games,
        "wins": wins,
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
    }

    report = {
        "site": site,
        "period": {"start": start, "end": end},
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "metrics": agg,
        "daily": daily,
        "top_events": top_events,
        "top_pages": top_pages,
        "top_referrers": [],  # Not available via stats API without per-path detail calls
    }

    # Attach optional browser/system stats
    if data.get("browsers"):
        report["browsers"] = data["browsers"].get("stats", [])
    if data.get("systems"):
        report["systems"] = data["systems"].get("stats", [])

    return report


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def short_summary(report):
    m = report["metrics"]
    wr = f"{m.get('win_rate'):.2%}" if m.get("win_rate") is not None else "N/A"
    return (
        f"Period {report['period']['start']} → {report['period']['end']}: "
        f"visitors={m.get('total_visitors')}, "
        f"events={m.get('total_events')}, "
        f"new_games={m.get('new_games')}, "
        f"wins={m.get('wins')}, "
        f"win_rate={wr}"
    )


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


# ---------------------------------------------------------------------------
# Charts + HTML generation
# ---------------------------------------------------------------------------

def generate_charts_and_html(report, out_dir):
    charts_dir = os.path.join(out_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)
    start = report["period"]["start"]
    end = report["period"]["end"]

    # --- Daily visitors chart (line) ---
    daily_df = pd.DataFrame(report["daily"])
    daily_b64 = None
    if not daily_df.empty:
        daily_df["day"] = pd.to_datetime(daily_df["day"])
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(daily_df["day"], daily_df.get("visitors", 0), marker="o", label="Visitors")
        ax.set_title(f"Daily Visitors ({start} → {end})")
        ax.set_xlabel("Day")
        ax.set_ylabel("Visitors")
        ax.legend()
        fig.tight_layout()
        png_path = os.path.join(charts_dir, "daily.png")
        fig.savefig(png_path, dpi=150, bbox_inches="tight")
        daily_b64 = fig_to_base64(fig)

    # --- Top events pie (donut) ---
    tev = pd.DataFrame(report["top_events"])
    events_b64 = None
    if not tev.empty:
        labels = tev["event_type"].astype(str).tolist()
        sizes = [int(x) for x in tev["cnt"].tolist()]
        MAX_SLICES = 8
        if len(sizes) > MAX_SLICES:
            top_labels = labels[:MAX_SLICES]
            top_sizes = sizes[:MAX_SLICES]
            other = sum(sizes[MAX_SLICES:])
            top_labels.append("Other")
            top_sizes.append(other)
            labels, sizes = top_labels, top_sizes
        fig2, ax2 = plt.subplots(figsize=(6, 6))
        wedges, _ = ax2.pie(sizes, startangle=140, wedgeprops=dict(width=0.4))
        ax2.legend(wedges, labels, title="Events", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        ax2.set_title("Top events (distribution)")
        fig2.tight_layout()
        png_path2 = os.path.join(charts_dir, "top-events.png")
        fig2.savefig(png_path2, dpi=150, bbox_inches="tight")
        events_b64 = fig_to_base64(fig2)

    # --- Top pages horizontal bar ---
    tpages = pd.DataFrame(report.get("top_pages", []))
    pages_b64 = None
    if not tpages.empty:
        top10 = tpages.head(10)
        fig3, ax3 = plt.subplots(figsize=(8, max(3, 0.5 * len(top10))))
        ax3.barh(top10["path"].astype(str), top10["cnt"].astype(int))
        ax3.set_title("Top pages")
        ax3.set_xlabel("Visitors")
        ax3.invert_yaxis()
        fig3.tight_layout()
        png_path3 = os.path.join(charts_dir, "top-pages.png")
        fig3.savefig(png_path3, dpi=150, bbox_inches="tight")
        pages_b64 = fig_to_base64(fig3)

    # --- Compose self-contained styled HTML ---
    html = """<html>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>GoatCounter report</title>
<style>
  :root {
    --bg: #f8f9fa;
    --card-bg: #ffffff;
    --text: #212529;
    --muted: #6c757d;
    --border: #dee2e6;
    --accent: #0d6efd;
    --accent-hover: #0b5ed7;
    --radius: 8px;
  }
  *, *::before, *::after { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    margin: 0; padding: 0;
    line-height: 1.6;
  }
  .container { max-width: 960px; margin: 0 auto; padding: 2rem 1.5rem; }
  header {
    background: var(--card-bg);
    border-bottom: 1px solid var(--border);
    padding: 2rem 1.5rem 1.5rem;
    margin-bottom: 2rem;
  }
  header h1 { margin: 0 0 .25rem; font-size: 1.75rem; }
  header p { margin: .25rem 0 0; color: var(--muted); font-size: .9rem; }
  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }
  .metric-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
    text-align: center;
  }
  .metric-card .value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--accent);
    line-height: 1.2;
  }
  .metric-card .label {
    font-size: .8rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .05em;
    margin-top: .25rem;
  }
  .section {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }
  .section h2 {
    margin: 0 0 1rem;
    font-size: 1.25rem;
    border-bottom: 2px solid var(--accent);
    padding-bottom: .5rem;
  }
  .section h3 {
    margin: 1.5rem 0 .75rem;
    font-size: 1.05rem;
  }
  .section img { max-width: 100%; height: auto; border-radius: 4px; }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: .9rem;
  }
  th, td {
    text-align: left;
    padding: .5rem .75rem;
    border-bottom: 1px solid var(--border);
  }
  th { font-weight: 600; color: var(--muted); font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; }
  tr:hover td { background: rgba(13,110,253,.04); }
  td:last-child, th:last-child { text-align: right; font-variant-numeric: tabular-nums; }
  footer {
    text-align: center;
    color: var(--muted);
    font-size: .8rem;
    padding: 1.5rem;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1a1a2e;
      --card-bg: #16213e;
      --text: #e0e0e0;
      --muted: #8892b0;
      --border: #2a2a4a;
      --accent: #64ffda;
      --accent-hover: #45e0be;
    }
    tr:hover td { background: rgba(100,255,218,.06); }
  }
</style>
</head>
<body>
<header>
  <div class="container">
    <h1>GoatCounter report &mdash; """ + report['site'] + """</h1>
    <p>Period: """ + start + """ &#8594; """ + end + """ &middot; Generated: """ + report['generated_at'] + """</p>
  </div>
</header>
<div class="container">
"""
    # Metrics as cards instead of a list
    m = report['metrics']
    wr_str = f"{m.get('win_rate'):.1%}" if m.get('win_rate') is not None else "N/A"
    html += '<div class="metrics-grid">\n'
    html += f'  <div class="metric-card"><div class="value">{m.get("total_visitors",0):,}</div><div class="label">Visitors</div></div>\n'
    html += f'  <div class="metric-card"><div class="value">{m.get("total_events",0):,}</div><div class="label">Events</div></div>\n'
    html += f'  <div class="metric-card"><div class="value">{m.get("new_games",0):,}</div><div class="label">New Games</div></div>\n'
    html += f'  <div class="metric-card"><div class="value">{m.get("wins",0):,}</div><div class="label">Wins</div></div>\n'
    html += f'  <div class="metric-card"><div class="value">{wr_str}</div><div class="label">Win Rate</div></div>\n'
    html += '</div>\n'

    # Charts in sections
    if daily_b64:
        html += '<div class="section">\n<h2>Daily Visitors</h2>\n'
        html += f'<img src="data:image/png;base64,{daily_b64}" alt="daily chart">\n</div>\n'
    if events_b64:
        html += '<div class="section">\n<h2>Event Distribution</h2>\n'
        html += f'<img src="data:image/png;base64,{events_b64}" alt="events pie">\n</div>\n'
    if pages_b64:
        html += '<div class="section">\n<h2>Top Pages</h2>\n'
        html += f'<img src="data:image/png;base64,{pages_b64}" alt="top pages">\n</div>\n'

    # Data tables
    if report.get("top_events"):
        html += '<div class="section">\n<h3>Top Events</h3>\n<table>\n<tr><th>Event</th><th>Count</th></tr>\n'
        for e in report["top_events"]:
            html += f'<tr><td>{e["event_type"]}</td><td>{e["cnt"]:,}</td></tr>\n'
        html += '</table>\n</div>\n'

    if report.get("top_pages"):
        html += '<div class="section">\n<h3>Top Pages</h3>\n<table>\n<tr><th>Path</th><th>Count</th></tr>\n'
        for p in report["top_pages"][:20]:
            html += f'<tr><td>{p["path"]}</td><td>{p["cnt"]:,}</td></tr>\n'
        html += '</table>\n</div>\n'

    # Browsers + Systems side by side
    if report.get("browsers") or report.get("systems"):
        html += '<div class="section">\n<h2>Audience</h2>\n'
        html += '<div style="display:grid; grid-template-columns:1fr 1fr; gap:2rem;">\n'
        if report.get("browsers"):
            html += '<div>\n<h3>Browsers</h3>\n<table>\n<tr><th>Browser</th><th>Count</th></tr>\n'
            for b in report["browsers"]:
                html += f'<tr><td>{b.get("name", b.get("id", "?"))}</td><td>{b["count"]:,}</td></tr>\n'
            html += '</table>\n</div>\n'
        if report.get("systems"):
            html += '<div>\n<h3>Systems</h3>\n<table>\n<tr><th>System</th><th>Count</th></tr>\n'
            for s in report["systems"]:
                html += f'<tr><td>{s.get("name", s.get("id", "?"))}</td><td>{s["count"]:,}</td></tr>\n'
            html += '</table>\n</div>\n'
        html += '</div>\n</div>\n'

    html += '</div>\n<footer>Generated by <code>report/goatcounter-report.py</code></footer>\n</body>\n</html>'

    out_html = os.path.join(out_dir, "index.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "daily_png": daily_b64 is not None,
        "events_png": events_b64 is not None,
        "pages_png": pages_b64 is not None,
        "html_file": out_html,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Auto-load .env.sh before parsing args (so env vars are available)
    load_dotenv_sh()

    parser = argparse.ArgumentParser(
        description="Generate a GoatCounter stats report with charts."
    )
    parser.add_argument(
        "--site",
        help="GoatCounter site code (e.g. foighne) or full URL",
        default=os.getenv("GOAT_SITE", "foighne"),
    )
    parser.add_argument("--start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD")
    parser.add_argument(
        "--period",
        help=(
            "Human-friendly period: today, yesterday, this week, last week, "
            "this month, last month, this year, last year. "
            "Overrides --start/--end."
        ),
    )
    args = parser.parse_args()

    # Determine start/end from --period if given
    if args.period:
        try:
            se = parse_period(args.period)
            if not se:
                raise ValueError("Unable to parse period")
            args.start, args.end = se
        except Exception as e:
            print(f"Error parsing --period: {e}", file=sys.stderr)
            sys.exit(2)

    # Fall back to env vars for start/end
    if not args.start:
        args.start = os.getenv("GOAT_START")
    if not args.end:
        args.end = os.getenv("GOAT_END")

    if not args.start or not args.end:
        print(
            "start and end dates are required. Use --period (e.g. 'this month') "
            "or set --start/--end or GOAT_START/GOAT_END env vars.",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"Fetching stats for {args.site}: {args.start} → {args.end} ...")
    data = fetch_stats_data(args.site, args.start, args.end)

    report = build_report(args.site, args.start, args.end, data)

    # Create timestamped output directory (relative to project root)
    timestamp = dt.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    out_dir = os.path.join(PROJECT_ROOT, "reports", f"{timestamp}_{args.start}_{args.end}")
    os.makedirs(out_dir, exist_ok=True)

    # Save JSON data
    json_path = os.path.join(out_dir, "data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(short_summary(report))

    gen = generate_charts_and_html(report, out_dir)
    print(f"Report saved to: {out_dir}/")
    print(f"  index.html  (self-contained)")
    print(f"  data.json   (raw data)")
    print(f"  charts/     (PNG files)")


if __name__ == "__main__":
    main()
