# USVI Beach Water Quality Tracker

An automated pipeline that turns the U.S. Virgin Islands Department of Planning and Natural Resources (DPNR) weekly beach-testing PDFs into a tested data warehouse and a public map. It also adds NOAA's daily sargassum risk for the coastline near every beach.

Built by [Crucian Data Works](https://cruciandataworks.com) as portfolio project 01.

## What it does

DPNR tests about 45 beaches each week for enterococci bacteria and posts the results as a PDF. A beach is unsafe for swimming when a sample has more than 70 colonies per 100 mL. This project:

1. Finds every weekly sheet through DPNR's public WordPress media API. There are 123 sheets from Oct 2022 to Nov 2026.
2. Downloads each sheet once, with SHA-256 fingerprints.
   - 2b. Downloads NOAA's daily Sargassum Inundation Risk map (KMZ) and keeps the 2,087 USVI coastline points with their level: low, warning, medium or high.
3. Extracts each table row using PyMuPDF character baselines. Table detection failed on a font-metrics bug.
4. Loads raw text into DuckDB.
5. Cleans, models and tests the data with dbt. The models go through staging, intermediate and marts layers, and there are 40 tests, including reconciliation against DPNR's official press release.
6. Exports JSON for a static dashboard. The whole pipeline runs on GitHub Actions: weekly for DPNR and daily for NOAA sargassum.

## Results

- 3,261 samples
- 262 unsafe results (8.0%)
- 45 beaches across St. Croix, St. Thomas, St. John and Water Island
- 509 days of NOAA sargassum risk (Jul 2025 to Nov 2026), linked to each beach within 2 km

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py
cd dashboard && python -m http.server 8000
```

See [docs/STEP_BY_STEP.md](docs/STEP_BY_STEP.md) for a full walkthrough of every step and decision.

## Stack

Python · requests · PyMuPDF · KML parsing · DuckDB · dbt-core + dbt-duckdb · GitHub Actions · Leaflet · Chart.js

## Data sources and credits

- Beach results: [USVI DPNR](https://dpnr.vi.gov/) weekly Beach Data sheets and Beach Advisory releases (public).
- Sargassum risk: [Daily Sargassum Inundation Risk](https://cwcgom.aoml.noaa.gov/SIR/index.php), NOAA CoastWatch Caribbean & Gulf of America node, using satellite data from the University of South Florida Optical Oceanography Lab. It is experimental and not a forecast: a regional satellite signal, not a beach observation.
- Beach locations: © OpenStreetMap contributors (ODbL), via Nominatim. Ten points are manual approximations, marked in `dbt/seeds/beach_locations.csv`.
- Map tiles: © OpenStreetMap contributors.

This is an independent analysis, not an official health advisory. Always check DPNR's current advisory before swimming.
