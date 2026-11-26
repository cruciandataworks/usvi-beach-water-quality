"""Run every step in order. This is what the weekly schedule calls.

    python run_pipeline.py            # full run
    python run_pipeline.py --from 3   # start at step 3 (skip discovery + download)
    python run_pipeline.py --from 2b  # refresh only the sargassum reports, then rebuild

Step 2b (NOAA sargassum risk) is "best effort": if NOAA is down the run carries on with
the sargassum days already saved, because the beach results are the main product.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    ("1", "Discover PDFs", [sys.executable, "pipeline/step1_discover.py"]),
    ("2", "Download PDFs", [sys.executable, "pipeline/step2_download.py"]),
    ("2b", "Download NOAA sargassum risk reports", [sys.executable, "pipeline/step2b_sargassum.py"]),
    ("3", "Extract tables", [sys.executable, "pipeline/step3_extract.py"]),
    ("4", "Load DuckDB", [sys.executable, "pipeline/step4_load.py"]),
    ("5", "dbt build (models + tests)", ["dbt", "build", "--profiles-dir", "."]),
    ("6", "Export dashboard data", [sys.executable, "pipeline/step6_export.py"]),
]
ORDER = [n for n, _, _ in STEPS]
OPTIONAL = {"2b"}  # never stops the run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="1", choices=ORDER)
    args = ap.parse_args()
    for n, label, cmd in STEPS:
        if ORDER.index(n) < ORDER.index(args.start):
            continue
        print(f"\n=== Step {n}: {label} ===", flush=True)
        # dbt resolves the DuckDB path relative to where it runs, so run it inside dbt/
        cwd = ROOT / "dbt" if cmd[0] == "dbt" else ROOT
        result = subprocess.run(cmd, cwd=cwd, env=os.environ.copy())
        if result.returncode != 0 and n in OPTIONAL:
            print(f"Step {n} had a problem - continuing with the data already saved.")
        elif result.returncode != 0:
            print(f"Step {n} failed - stopping so bad data never reaches the dashboard.")
            sys.exit(result.returncode)
    print("\nAll steps finished.")


if __name__ == "__main__":
    main()
