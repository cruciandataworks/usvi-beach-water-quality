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
