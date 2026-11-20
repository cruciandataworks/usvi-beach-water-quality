# USVI Beach Water Quality Tracker

An automated pipeline that turns the U.S. Virgin Islands Department of Planning and Natural Resources (DPNR) weekly beach-testing PDFs into a tested data warehouse and a public map.

Built by [Crucian Data Works](https://cruciandataworks.com) as portfolio project 01.

## What it does

DPNR tests about 45 beaches each week for enterococci bacteria and posts the results as a PDF. A beach is unsafe for swimming when a sample has more than 70 colonies per 100 mL. This project:

1. Finds every weekly sheet through DPNR's public WordPress media API. There are 123 sheets from Oct 2022 to Nov 2026.
2. Downloads each sheet once, with SHA-256 fingerprints.
3. Extracts each table row using PyMuPDF character baselines. Table detection failed on a font-metrics bug.
4. Loads raw text into DuckDB.
5. Cleans, models and tests the data with dbt. The models go through staging, intermediate and marts layers, and there are 20 tests, including reconciliation against DPNR's official press release.
6. Exports JSON for a static dashboard. The whole pipeline is scheduled weekly with GitHub Actions.

## Results

- 3,229 samples
- 256 unsafe results (7.9%)
- 45 beaches across St. Croix, St. Thomas, St. John and Water Island

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py
cd dashboard && python -m http.server 8000
```

See [docs/STEP_BY_STEP.md](docs/STEP_BY_STEP.md) for a full walkthrough of every step and decision.

## Stack

Python · requests · PyMuPDF · DuckDB · dbt-core + dbt-duckdb · GitHub Actions · Leaflet · Chart.js

## Data sources and credits

- Beach results: [USVI DPNR](https://dpnr.vi.gov/) weekly Beach Data sheets and Beach Advisory releases (public).
- Beach locations: © OpenStreetMap contributors (ODbL), via Nominatim. Ten points are manual approximations, marked in `dbt/seeds/beach_locations.csv`.
- Map tiles: © OpenStreetMap contributors.

This is an independent analysis, not an official health advisory. Always check DPNR's current advisory before swimming.
