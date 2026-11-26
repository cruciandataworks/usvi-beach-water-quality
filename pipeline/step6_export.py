"""Step 6 - Export: write small JSON files the website dashboard reads.

The dashboard is a static web page (no server, no database), so we pre-compute the
numbers it needs and save them next to it. Re-running this after each weekly load
refreshes the dashboard.

Output: dashboard/data/*.json
"""
import json
from datetime import date, datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse" / "beach.duckdb"
OUT = ROOT / "dashboard" / "data"

QUERIES = {
    "beaches": """
        select beach_id, beach_name, island, latitude, longitude, samples, exceedances,
               exceedance_rate_pct, median_enterococci, max_enterococci,
               last_exceedance_date, latest_date, latest_status, latest_enterococci,
               latest_qualifier, latest_is_exceedance
        from marts.mart_beach_summary order by island, beach_name""",
    "samples": """
        select beach_id, sample_date, sample_status, enterococci_per_100ml as entero,
               enterococci_qualifier as qualifier, turbidity_ntu as turbidity,
               is_exceedance as unsafe
        from marts.fct_beach_samples
        where station = 'main' and sample_status = 'sampled' order by sample_date, beach_id""",
    "weeks": """
        select sample_date, any_value(source_url) as source_url
        from marts.fct_beach_samples group by 1 order by 1""",
    "island_weekly": """
        select sample_date, island, beaches_sampled, beaches_unsafe
        from marts.mart_island_weekly order by sample_date, island""",
    "streaks": """
        select beach_name, island, streak_start, streak_end, consecutive_unsafe_samples
        from marts.mart_exceedance_streaks
        where consecutive_unsafe_samples >= 3
        order by consecutive_unsafe_samples desc, streak_end desc, beach_name""",
}


def default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return float(o)


def export_sargassum(con):
    """sargassum.json - one compact file for the Sargassum section.

    To keep it small, all series share one list of dates. Each island gets lists of
    percentages lined up with those dates, and each beach gets one string with one
    character per date: 0-3 = NOAA level, "." = no NOAA data that day.
    """
    con = con.cursor()  # a separate cursor, so these queries never block the main connection
    have = con.execute("""select count(*) from information_schema.tables
                      where table_schema = 'marts' and table_name = 'mart_sargassum_island_daily'""").fetchone()[0]
    if not have:
        print("sargassum.json skipped (no sargassum models yet)")
        return None
    dates = [r[0] for r in con.execute(
        "select distinct report_date from marts.mart_sargassum_island_daily order by 1").fetchall()]
    if not dates:
        return None
    idx = {d: i for i, d in enumerate(dates)}
    islands = {}
    for isl, d, w, m, h, mx, typ in con.execute("""
            select island, report_date, pct_warning_or_higher, pct_medium_or_higher, pct_high,
                   max_risk_level, typical_risk_level
            from marts.mart_sargassum_island_daily order by island, report_date""").fetchall():
        x = islands.setdefault(isl, {k: [None] * len(dates) for k in ("warning", "medium", "high", "typical")})
        i = idx[d]
        x["warning"][i], x["medium"][i], x["high"][i], x["typical"][i] = float(w), float(m), float(h), typ
    strip = {}
    for bid, d, lvl in con.execute("""select beach_id, report_date, risk_level
                                  from marts.fct_beach_sargassum_daily order by 1, 2""").fetchall():
        strip.setdefault(bid, ["."] * len(dates))[idx[d]] = str(lvl)
    beaches = {}
    for r in con.execute("""select beach_id, nearby_points, nearest_point_km, latest_report_date,
                               latest_risk_level, report_days, days_medium_or_higher,
                               days_medium_or_higher_last_30
                        from marts.mart_beach_sargassum order by beach_id""").fetchall():
        beaches[r[0]] = {"points": r[1], "nearest_km": r[2], "latest_date": r[3], "latest": r[4],
                         "days": r[5], "days_med": r[6], "days_med_30": r[7],
                         "strip": "".join(strip.get(r[0], ["."] * len(dates)))}
    vs = [dict(zip(("level", "samples", "unsafe", "unsafe_pct"), r)) for r in con.execute("""
        select coalesce(max_risk_level_lookback, -1) as level, count(*) as samples,
               count(*) filter (where is_exceedance) as unsafe,
               round(100.0 * count(*) filter (where is_exceedance) / count(*), 1) as unsafe_pct
        from marts.mart_sargassum_vs_samples group by 1 order by 1""").fetchall()]
    total, saved = con.execute("""select count(*), count(*) filter (where status = 'saved')
                              from staging.stg_sargassum_downloads""").fetchone()
    return {
        "meta": {"first_date": dates[0], "last_date": dates[-1], "report_days": len(dates),
                 "files_listed": total, "files_saved": saved, "radius_km": 2, "lookback_days": 7,
                 "source": "https://cwcgom.aoml.noaa.gov/SIR/index.php"},
        "dates": dates, "islands": islands, "beaches": beaches, "vs_bacteria": vs,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)
    changed = False
    for name, sql in QUERIES.items():
        rel = con.sql(sql)
        cols = rel.columns
        rows = [dict(zip(cols, r)) for r in rel.fetchall()]
        text = json.dumps(rows, default=default, separators=(",", ":"))
        path = OUT / f"{name}.json"
        # Sorted queries give identical output for identical data, so we only
        # rewrite a file (and the weekly job only commits) when something changed.
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
            changed = True
        print(f"dashboard/data/{name}.json  {len(rows)} rows")
    sarg = export_sargassum(con)
    if sarg is not None:
        text = json.dumps(sarg, default=default, separators=(",", ":"))
        path = OUT / "sargassum.json"
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
            changed = True
        print(f"dashboard/data/sargassum.json  {sarg['meta']['report_days']} report days")
    meta = con.sql("""select max(sample_date), min(sample_date), count(distinct sample_date),
                      count(*) filter (where sample_status='sampled'),
                      count(*) filter (where is_exceedance)
                      from marts.fct_beach_samples""").fetchall()[0]
    meta_path = OUT / "meta.json"
    old_built = json.loads(meta_path.read_text()).get("built_at") if meta_path.exists() else None
    meta_path.write_text(json.dumps({
        "latest_sample_date": meta[0], "first_sample_date": meta[1], "weeks": meta[2],
        "samples": meta[3], "unsafe": meta[4], "threshold": 70,
        # keep the old timestamp when no data changed
        "built_at": datetime.now().isoformat(timespec="minutes") if changed or not old_built else old_built,
    }, default=default))
    print("dashboard/data/meta.json")


if __name__ == "__main__":
    main()
