#!/usr/bin/env python3
"""
goatcounter-report.py

Fetch GoatCounter export for a date range, compute KPIs, generate charts (PNG),
and write a self-contained HTML report with embedded images.

Usage:
  GOATCOUNTER_API_TOKEN=... python3 report/goatcounter-report.py --period "this month"
  python3 report/goatcounter-report.py --site foighne --period "last month"
  python3 report/goatcounter-report.py --start 2026-07-01 --end 2026-07-07

Notes:
  - Calls GoatCounter API v0 export endpoint (preferred) per https://www.goatcounter.com/api.html
  - If the export needs HTTP Basic auth, set GOAT_USER and GOAT_PASS or pass --user/--pass.
  - Produces:
      - report-<start>-<end>.json
      - report-<start>-<end>.html (self-contained)
      - charts/ (PNG files)

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
import re
import datetime as dt
import time
import gzip
import duckdb
import pandas as pd
import base64

# Matplotlib + seaborn setup for headless environments
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

sns.set(style="whitegrid", palette="muted", font_scale=1.0)


def fetch_export(site, start, end, user=None, passwd=None, timeout=60):
    """
    Use GoatCounter API v0 to create an export, wait for it to finish,
    download the gzipped CSV, convert to JSON-lines, and return that text.

    Auth:
      - Preferred: set GOATCOUNTER_API_TOKEN to your API key (Bearer).
      - Fallback: HTTP Basic auth with empty username and key as password (user arg blank, passwd set).
    """
    token = os.getenv("GOATCOUNTER_API_TOKEN")
    # Build API base. Accept either 'foighne' or a full host 'https://...' or 'foighne.goatcounter.com'
    if site.startswith("http://") or site.startswith("https://"):
        host = site.rstrip("/")
        api_base = f"{host}/api/v0"
    else:
        # regular hosted site at site.goatcounter.com
        api_base = f"https://{site}.goatcounter.com/api/v0"

    headers = {"Content-Type": "application/json"}
    auth = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif user is not None and passwd is not None:
        auth = (user, passwd)

    # Start export (POST /api/v0/export)
    create_url = f"{api_base}/export"
    payload = {"start": start, "end": end}
    try:
        resp = requests.post(create_url, headers=headers, json=payload, auth=auth, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to start export: {e}")
    # If unauthorized, give clear message
    if resp.status_code in (401, 403):
        raise RuntimeError(f"Export creation failed: {resp.status_code} {resp.text.strip()[:300]}. Check GOATCOUNTER_API_TOKEN and permissions.")
    resp.raise_for_status()

    data = resp.json()
    export_id = data.get("id")
    if not export_id:
        raise RuntimeError(f"Export creation returned unexpected response: {data}")

    # Poll export status GET /api/v0/export/{id} until finished_at is non-null or error
    status_url = f"{api_base}/export/{export_id}"
    finished = False
    poll_start = time.time()
    while True:
        try:
            sresp = requests.get(status_url, headers=headers, auth=auth, timeout=timeout)
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to poll export status: {e}")
        if sresp.status_code in (401, 403):
            raise RuntimeError(f"Export status check unauthorized: {sresp.status_code} {sresp.text.strip()[:300]}")
        sresp.raise_for_status()
        status_data = sresp.json()
        if status_data.get("finished_at"):
            finished = True
            break
        # If API returned an error field, surface it
        if status_data.get("error") or status_data.get("errors"):
            raise RuntimeError(f"Export failed: {status_data.get('error') or status_data.get('errors')}")
        # rate-limit friendly: sleep 1s
        time.sleep(1)
        # safety timeout (5 minutes)
        if time.time() - poll_start > 300:
            raise RuntimeError("Timed out waiting for GoatCounter export to finish (5m)")

    # Download the export: GET /api/v0/export/{id}/download
    dl_url = f"{api_base}/export/{export_id}/download"
    try:
        dresp = requests.get(dl_url, headers=headers, auth=auth, timeout=120)
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to download export: {e}")
    if dresp.status_code in (401, 403):
        raise RuntimeError(f"Export download unauthorized: {dresp.status_code} {dresp.text.strip()[:300]}")
    if dresp.status_code == 404:
        raise RuntimeError("Export download not found (404).")
    dresp.raise_for_status()

    # Response is typically gzipped CSV. Try to decompress; if not gzipped, treat as plain CSV bytes.
    content = dresp.content
    try:
        csv_bytes = gzip.decompress(content)
    except (OSError, EOFError):
        csv_bytes = content

    # Load CSV into a DataFrame and convert to JSON-lines (so existing code using read_json(lines=True) works)
    try:
        csv_buf = io.BytesIO(csv_bytes)
        df = pd.read_csv(csv_buf)
    except Exception as e:
        text = None
        try:
            text = csv_bytes.decode("utf-8", errors="replace")
        except Exception:
            text = str(csv_bytes[:1000])
        raise RuntimeError(f"Failed to parse CSV export into DataFrame: {e}\nSample:\n{text[:1000]}")

    # Convert to JSON lines and return string
    jsonl = df.to_json(orient="records", lines=True, date_format="iso")
    return jsonl


def parse_period(period):
    """Return (start_date_str, end_date_str) for friendly English period phrases.

    Accepted phrases (case-insensitive):
      today, yesterday,
      this week, last week,
      this month, last month,
      this year, last year

    Accepts explicit single date YYYY-MM-DD or explicit range YYYY-MM-DD:YYYY-MM-DD.
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


def detect_ts_col(df):
    for candidate in ("time", "timestamp", "ts", "created_at", "date"):
        if candidate in df.columns:
            return candidate
    for c in df.columns:
        if "time" in c.lower() or "date" in c.lower():
            return c
    raise RuntimeError("No timestamp column found in export; adjust mapping.")


def detect_visitor_col(df):
    for candidate in ("visitor", "visitor_id", "vid", "client", "ip", "id"):
        if candidate in df.columns:
            return candidate
    return None


def detect_path_col(df):
    for candidate in ("path", "url", "page", "p"):
        if candidate in df.columns:
            return candidate
    return None


def extract_event_from_path(path):
    if not isinstance(path, str):
        return None
    m = re.search(r"[?&](?:e|event)=([^&/]+)", path)
    if m:
        return m.group(1)
    m = re.search(r"/(?:e|event|track)/([^/?#]+)", path)
    if m:
        return m.group(1)
    return None


def normalize_df(df):
    ts_col = detect_ts_col(df)
    visitor_col = detect_visitor_col(df)
    path_col = detect_path_col(df)

    df = df.copy()
    df.rename(columns={ts_col: "event_time"}, inplace=True)
    if visitor_col:
        df.rename(columns={visitor_col: "visitor_id"}, inplace=True)
    if path_col:
        df.rename(columns={path_col: "path"}, inplace=True)

    df["event_time"] = pd.to_datetime(df["event_time"], utc=True, errors="coerce")

    if "event" in df.columns:
        df["event_type"] = df["event"].astype(str)
    else:
        df["event_type"] = df.get("path", "").apply(extract_event_from_path)

    df["event_type"] = df["event_type"].fillna("pageview")

    if "visitor_id" not in df.columns:
        df["visitor_id"] = (df.get("ua", "") + df.get("user_agent", "") + df.get("referrer", "")).astype(str)
        if df["visitor_id"].eq("").all():
            df["visitor_id"] = df.index.astype(str)

    if "ua" in df.columns:
        df.rename(columns={"ua": "user_agent"}, inplace=True)
    if "ref" in df.columns and "referrer" not in df.columns:
        df.rename(columns={"ref": "referrer"}, inplace=True)

    keep = ["event_time", "event_type", "visitor_id", "path", "referrer", "user_agent"]
    present = [c for c in keep if c in df.columns]
    out = df[present].copy()
    return out


def run_queries(df, start, end):
    con = duckdb.connect(database=":memory:")
    con.register("events", df)
    daily_sql = f"""
    SELECT DATE(event_time) AS day,
           COUNT(DISTINCT visitor_id) AS dau,
           SUM(CASE WHEN event_type='new-game' THEN 1 ELSE 0 END) AS new_games,
           SUM(CASE WHEN event_type='game-won' THEN 1 ELSE 0 END) AS wins,
           CASE WHEN SUM(CASE WHEN event_type='new-game' THEN 1 ELSE 0 END)=0 THEN NULL
                ELSE (SUM(CASE WHEN event_type='game-won' THEN 1 ELSE 0 END))*1.0 / SUM(CASE WHEN event_type='new-game' THEN 1 ELSE 0 END)
           END AS win_rate
    FROM events
    WHERE event_time >= TIMESTAMP '{start}' AND event_time < TIMESTAMP '{end}' + INTERVAL '1 day'
    GROUP BY day
    ORDER BY day
    """
    daily = con.execute(daily_sql).fetchdf()
    agg_sql = f"""
    SELECT COUNT(DISTINCT visitor_id) AS unique_users,
           SUM(CASE WHEN event_type='new-game' THEN 1 ELSE 0 END) AS new_games,
           SUM(CASE WHEN event_type='game-won' THEN 1 ELSE 0 END) AS wins,
           CASE WHEN SUM(CASE WHEN event_type='new-game' THEN 1 ELSE 0 END)=0 THEN NULL
                ELSE (SUM(CASE WHEN event_type='game-won' THEN 1 ELSE 0 END))*1.0 / SUM(CASE WHEN event_type='new-game' THEN 1 ELSE 0 END)
           END AS win_rate
    FROM events
    WHERE event_time >= TIMESTAMP '{start}' AND event_time < TIMESTAMP '{end}' + INTERVAL '1 day'
    """
    agg = con.execute(agg_sql).fetchdf().to_dict(orient="records")[0]
    refs_sql = f"""
    SELECT COALESCE(referrer,'(direct)') AS referrer, COUNT(*) AS cnt
    FROM events
    WHERE event_time >= TIMESTAMP '{start}' AND event_time < TIMESTAMP '{end}' + INTERVAL '1 day'
    GROUP BY referrer
    ORDER BY cnt DESC
    LIMIT 10
    """
    refs = con.execute(refs_sql).fetchdf().to_dict(orient="records")
    top_events_sql = f"""
    SELECT event_type, COUNT(*) AS cnt
    FROM events
    WHERE event_time >= TIMESTAMP '{start}' AND event_time < TIMESTAMP '{end}' + INTERVAL '1 day'
    GROUP BY event_type
    ORDER BY cnt DESC
    LIMIT 20
    """
    top_events = con.execute(top_events_sql).fetchdf().to_dict(orient="records")
    return {"daily": daily.to_dict(orient="records"), "aggregate": agg, "top_referrers": refs, "top_events": top_events}


def make_report(site, start, end, df):
    results = run_queries(df, start, end)
    report = {
        "site": site,
        "period": {"start": start, "end": end},
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "metrics": results["aggregate"],
        "daily": results["daily"],
        "top_referrers": results["top_referrers"],
        "top_events": results["top_events"]
    }
    return report


def short_summary(report):
    m = report["metrics"]
    s = f"Period {report['period']['start']} → {report['period']['end']}: users={m.get('unique_users')}, new_games={m.get('new_games')}, wins={m.get('wins')}, win_rate={m.get('win_rate')}"
    return s


# Chart helpers
def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def generate_charts_and_html(report, out_prefix):
    os.makedirs("charts", exist_ok=True)
    start = report["period"]["start"]
    end = report["period"]["end"]

    # Daily series chart (line)
    daily_df = pd.DataFrame(report["daily"])
    if daily_df.empty:
        daily_b64 = None
    else:
        daily_df["day"] = pd.to_datetime(daily_df["day"])
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(daily_df["day"], daily_df.get("dau", 0), marker="o", label="DAU")
        ax.plot(daily_df["day"], daily_df.get("new_games", 0), marker="o", label="New games")
        ax.set_title(f"Daily DAU & New Games ({start} → {end})")
        ax.set_xlabel("Day")
        ax.set_ylabel("Count")
        ax.legend()
        fig.tight_layout()
        png_path = f"charts/daily-{start}-{end}.png"
        fig.savefig(png_path, dpi=150, bbox_inches="tight")
        daily_b64 = fig_to_base64(fig)

    # Top events pie (donut)
    tev = pd.DataFrame(report["top_events"])
    if tev.empty:
        events_b64 = None
    else:
        labels = tev["event_type"].astype(str).tolist()
        sizes = tev["cnt"].tolist()
        N = 8
        if len(sizes) > N:
            top_labels = labels[:N]
            top_sizes = sizes[:N]
            other = sum(sizes[N:])
            top_labels.append("Other")
            top_sizes.append(other)
            labels, sizes = top_labels, top_sizes
        fig2, ax2 = plt.subplots(figsize=(6, 6))
        wedges, texts = ax2.pie(sizes, startangle=140, wedgeprops=dict(width=0.4))
        ax2.legend(wedges, labels, title="Events", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        ax2.set_title("Top events (distribution)")
        fig2.tight_layout()
        png_path2 = f"charts/top-events-{start}-{end}.png"
        fig2.savefig(png_path2, dpi=150, bbox_inches="tight")
        events_b64 = fig_to_base64(fig2)

    # Top referrers horizontal bar
    tref = pd.DataFrame(report["top_referrers"])
    if tref.empty:
        refs_b64 = None
    else:
        fig3, ax3 = plt.subplots(figsize=(8, max(3, 0.5 * len(tref))))
        ax3.barh(tref["referrer"].astype(str), tref["cnt"])
        ax3.set_title("Top referrers")
        ax3.set_xlabel("Hits")
        ax3.invert_yaxis()
        fig3.tight_layout()
        png_path3 = f"charts/top-referrers-{start}-{end}.png"
        fig3.savefig(png_path3, dpi=150, bbox_inches="tight")
        refs_b64 = fig_to_base64(fig3)

    # Compose HTML (self-contained)
    html_parts = []
    html_parts.append(f"<h1>GoatCounter report for {report['site']}</h1>")
    html_parts.append(f"<p>Period: {start} → {end}</p>")
    html_parts.append(f"<p>Generated at: {report['generated_at']}</p>")
    # Metrics summary table
    metrics = report["metrics"]
    html_parts.append("<h2>Top-line metrics</h2>")
    html_parts.append("<ul>")
    html_parts.append(f"<li>Unique users: {metrics.get('unique_users')}</li>")
    html_parts.append(f"<li>New games: {metrics.get('new_games')}</li>")
    html_parts.append(f"<li>Wins: {metrics.get('wins')}</li>")
    html_parts.append(f"<li>Win rate: {metrics.get('win_rate')}</li>")
    html_parts.append("</ul>")

    if daily_b64:
        html_parts.append("<h2>Daily</h2>")
        html_parts.append(f'<img src="data:image/png;base64,{daily_b64}" alt="daily chart" style="max-width:100%"/>')

    if events_b64:
        html_parts.append("<h2>Event distribution</h2>")
        html_parts.append(f'<img src="data:image/png;base64,{events_b64}" alt="events pie" style="max-width:100%"/>')

    if refs_b64:
        html_parts.append("<h2>Top referrers</h2>")
        html_parts.append(f'<img src="data:image/png;base64,{refs_b64}" alt="referrers" style="max-width:100%"/>')

    if len(report.get("top_events", [])) > 0:
        html_parts.append("<h3>Top events (counts)</h3>")
        html_parts.append("<table border='1' cellpadding='4'><tr><th>event</th><th>count</th></tr>")
        for e in report["top_events"]:
            html_parts.append(f"<tr><td>{e['event_type']}</td><td>{e['cnt']}</td></tr>")
        html_parts.append("</table>")

    if len(report.get("top_referrers", [])) > 0:
        html_parts.append("<h3>Top referrers (counts)</h3>")
        html_parts.append("<table border='1' cellpadding='4'><tr><th>referrer</th><th>count</th></tr>")
        for r in report["top_referrers"]:
            html_parts.append(f"<tr><td>{r['referrer']}</td><td>{r['cnt']}</td></tr>")
        html_parts.append("</table>")

    html = "<html><head><meta charset='utf-8'><title>GoatCounter report</title></head><body>"
    html += "\n".join(html_parts)
    html += "</body></html>"

    out_html = f"{out_prefix}.html"
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)

    return {"daily_png": daily_b64 is not None, "events_png": events_b64 is not None, "refs_png": refs_b64 is not None, "html_file": out_html}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", help="GoatCounter site (e.g. foighne)", default=os.getenv("GOAT_SITE", "foighne"))
    parser.add_argument("--start", help="Start date YYYY-MM-DD", default=os.getenv("GOAT_START"))
    parser.add_argument("--end", help="End date YYYY-MM-DD", default=os.getenv("GOAT_END"))
    parser.add_argument("--period", help="Human period (today, this month, last month, this year, last year, etc). Overrides start/end if set.")
    parser.add_argument("--user", help="GoatCounter basic auth user (optional)", default=os.getenv("GOAT_USER"))
    parser.add_argument("--pass", dest="passwd", help="GoatCounter basic auth pass (optional)", default=os.getenv("GOAT_PASS"))
    args = parser.parse_args()

    # Determine start/end from --period if given
    if args.period:
        try:
            se = parse_period(args.period)
            if not se:
                raise ValueError("Unable to parse period")
            args.start, args.end = se
        except Exception as e:
            print("Error parsing --period:", e, file=sys.stderr)
            sys.exit(2)

    if not args.start or not args.end:
        print("site, start, and end are required (env GOAT_SITE, GOAT_START, GOAT_END are supported), or pass --period.", file=sys.stderr)
        sys.exit(2)

    raw = fetch_export(args.site, args.start, args.end, args.user, args.passwd)
    try:
        df = pd.read_json(io.StringIO(raw), lines=True)
    except Exception as e:
        print("Failed to parse export JSON; inspect raw output.", file=sys.stderr)
        raise

    dfn = normalize_df(df)
    report = make_report(args.site, args.start, args.end, dfn)
    out_name = f"report-{args.start}-{args.end}.json"
    with open(out_name, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(short_summary(report))
    html_out_prefix = f"report-{args.start}-{args.end}"
    gen = generate_charts_and_html(report, html_out_prefix)
    print(f"Generated HTML report: {gen['html_file']}")
    print(f"Saved PNGs to charts/ (if present)")


if __name__ == "__main__":
    main()
