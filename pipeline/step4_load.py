"""Step 4 - Load: copy the extracted CSVs into a DuckDB database file.

DuckDB is a database that lives in a single file (warehouse/beach.duckdb) - no server to
install. It speaks normal SQL, so the same models would run on Snowflake or Databricks
with small changes.

We load into a schema called "raw" and change nothing. This is the "L" in ELT
(Extract, Load, Transform): load first, transform later inside the database with dbt.
Every row also gets a loaded_at timestamp so we know when it arrived.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse" / "beach.duckdb"

TABLES = {
    "beach_readings": ROOT / "data" / "interim" / "readings_raw.csv",
    "pdf_manifest": ROOT / "data" / "raw" / "manifest.csv",
    "pdf_downloads": ROOT / "data" / "raw" / "downloads.csv",
    "extract_log": ROOT / "data" / "interim" / "extract_log.csv",
    # Step 2b: NOAA sargassum risk. The daily file is split by month, so we read a
    # whole folder at once with a * wildcard.
    "sargassum_points": ROOT / "data" / "interim" / "sargassum_points.csv",
    "sargassum_daily": ROOT / "data" / "interim" / "sargassum" / "*.csv",
    "sargassum_downloads": ROOT / "data" / "raw" / "sargassum_downloads.csv",
}


def main():
    DB.parent.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute("create schema if not exists raw")
    for table, path in TABLES.items():
        if not list(path.parent.glob(path.name)):
            print(f"raw.{table:16} skipped (no file yet)")
            continue
        # all_varchar: keep everything as text; typing happens in dbt staging models
        con.execute(f"""
            create or replace table raw.{table} as
            select *, current_timestamp as loaded_at
            from read_csv('{path}', header = true, all_varchar = true)
        """)
        n = con.execute(f"select count(*) from raw.{table}").fetchone()[0]
        print(f"raw.{table:16} {n:>6} rows")
    con.close()
    print(f"Database: {DB.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
