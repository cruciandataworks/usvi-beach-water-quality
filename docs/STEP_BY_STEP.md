# USVI Beach Water Quality Tracker: Step-by-Step Guide

This guide walks through the project in the order it was built, so you can re-run every command, understand why each choice was made, and explain it in a client conversation or interview as your own work.

Each step uses the same format:

- **Goal**: what the step produces.
- **Why**: the reasoning behind it.
- **Run it**: the exact command.
- **What you should see**: so you know it worked.
- **Check your understanding**: questions you should be able to answer afterward.

---

## The big picture

The U.S. Virgin Islands Department of Planning and Natural Resources (DPNR) tests about 45 beaches for enterococci bacteria. It posts the results each week as a PDF on [dpnr.vi.gov](https://dpnr.vi.gov/). Every sheet says a beach is unsafe for swimming when a sample has more than 70 colonies per 100 mL.

PDFs are made for people to read, not for analysis. Nobody can easily answer "which beach fails most often?" or "is this getting worse?" This project turns four years of those PDFs into a tested database and a public dashboard.

```
DPNR website ──► 1 Discover ──► 2 Download ──► 3 Extract ──► 4 Load ──► 5 Transform + test ──► 6 Export ──► Dashboard
 (WordPress)      manifest.csv    PDFs on disk    rows (text)    DuckDB      dbt models            JSON files    web page
                                                                   ▲
NOAA SIR maps ──────────────► 2b Sargassum ───────────────────────┘
 (daily KMZ)                   USVI points + daily levels
```

The second feed, NOAA's daily sargassum risk map, joins in at the load step. Step 2b explains it.

This pattern is called ELT: Extract, Load, Transform. We pull the data out, load it untouched, then clean it inside the database where every rule is written in SQL and tested. Most modern data teams work this way, whether the warehouse is Snowflake, Databricks, BigQuery or DuckDB.

### Final results

| Measure | Value |
|---|---|
| PDFs collected | 124 (Oct 14, 2022 to Nov 20, 2026) |
| Rows extracted | 5,498 |
| Actual samples (beach actually tested) | 3,261 |
| Unsafe results (>70) | 262 (8.0%) |
| Beaches after merging name spellings | 45 (from 56 printed spellings) |
| NOAA sargassum report days | 509 (Jul 1, 2025 to Nov 24, 2026) |
| USVI coastline points NOAA scores | 2,087 |
| dbt models + tests | 15 models, 3 seeds, 40 tests, all passing |

---

## Step 0: Set up your machine

**Goal:** get a working Python environment with the tools installed.

**Why:** a virtual environment (`.venv`) keeps this project's libraries separate from everything else on your computer, so another project can never break this one.

**Run it** (Mac/Linux terminal; on Windows use `.venv\Scripts\activate`):

```bash
cd usvi-beach-water-quality
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**What you should see:** `pip` installs requests, pymupdf, duckdb, dbt-core and dbt-duckdb. Check it worked with `dbt --version`.

### What each tool does

| Tool | Job in this project |
|---|---|
| `requests` | Downloads web pages and files |
| `pymupdf` | Reads text and character positions out of PDFs |
| `duckdb` | A database in a single file. No server needed. |
| `dbt` | Runs SQL models in the right order and tests the results |

### Project layout

```
usvi-beach-water-quality/
├── run_pipeline.py          # runs steps 1-6 in order
├── pipeline/                # one Python file per step
├── data/raw/                # manifest + downloaded PDFs (PDFs not in git)
├── data/interim/            # extracted rows as CSV
├── warehouse/beach.duckdb   # the database (rebuilt each run)
├── dbt/                     # SQL models, tests, reference tables (seeds)
├── dashboard/               # the web page + its JSON data
└── .github/workflows/       # the weekly schedule
```

---

## Step 1: Discover every PDF

**File:** `pipeline/step1_discover.py`

**Goal:** a list (manifest) of every Beach-Data PDF DPNR has ever posted, with its URL and date.

**Why:** the obvious approach is to open DPNR's web pages and copy links by hand, but that is slow, misses older files, and breaks when the site changes. DPNR's site runs on WordPress, and every WordPress site has a public "media library" feed called the REST API. Asking it for files named "Beach-Data" returns a clean list in JSON.

Try it yourself in a browser:

```
https://dpnr.vi.gov/wp-json/wp/v2/media?search=Beach-Data&per_page=5&_fields=date,source_url
```

**Key concept, pagination:** the feed returns at most 100 items per request. The response header `X-WP-TotalPages` says how many pages exist, so the script keeps asking for `page=2`, `page=3` and so on until it has them all.

**Run it:**

```bash
python pipeline/step1_discover.py
```

**What you should see:**

```
  page 1/2: 100 files
  page 2/2: 23 files
Found 123 PDFs from 2022-11-28 to 2026-11-13.
```

Open `data/raw/manifest.csv`. Each row has `media_id`, `file_name`, `uploaded_at`, `sample_date` (read from the file name, like `11.13.26`) and `url`.

**Check your understanding**
- Why is an API better than copying links from web pages?
- File names vary (`Beach-Data-_-9.6.24.pdf`, `Beach-Data-12.5.25-Revised.pdf`). How does the script still find the date? (Answer: the regular expression `(\d{1,2})\.(\d{1,2})\.(\d{2})` finds the M.D.YY pattern wherever it appears.)

---

## Step 2: Download the PDFs

**File:** `pipeline/step2_download.py`

**Goal:** a local copy of every PDF, plus a log with a fingerprint for each.

**Why:** two habits professional pipelines have:

1. **Idempotent.** Running it twice gives the same result and doesn't download twice. If a file is already on disk, it is skipped. The weekly run therefore fetches only the one new PDF.
2. **Fingerprints (SHA-256 hashes).** A hash is a short code calculated from a file's contents. If DPNR quietly replaces a PDF, the hash changes and you can prove it.

Each file is saved as `{media_id}_{file_name}`, so two uploads with the same name can never overwrite each other.

**Run it:**

```bash
python pipeline/step2_download.py
```

**What you should see:** `123 PDFs on disk (123 new this run, 0 failed).` Run it again and it says `0 new this run`. That is idempotency in action.

**Check your understanding**
- What would happen without the `if not target.exists()` check?
- Why wait half a second between downloads? (Being polite to a small government server.)

---

## Step 2b: Add NOAA's daily sargassum risk

**File:** `pipeline/step2b_sargassum.py`

**Goal:** for every day NOAA has published, the sargassum risk level at every scored stretch of USVI coastline, saved as small CSV files the warehouse can join to the beaches.

**The source.** NOAA's CoastWatch Caribbean & Gulf of America node publishes a [Daily Sargassum Inundation Risk](https://cwcgom.aoml.noaa.gov/SIR/index.php) map (SIR). For each coastal pixel it looks at satellite floating-algae data from the University of South Florida within 50 to 100 km, compares it with a multi-day baseline, and assigns a level: 0 low (blue), 1 warning (yellow), 2 medium (orange) or 3 high (red). Coast with too little satellite data is painted black. NOAA is clear that it is an experimental product and not a forecast. [NOAA AOML's explainer](https://www.aoml.noaa.gov/tracking-sargassum/) describes how it is made.

**Why this source and not another.** We looked at three options:

- The CARICOOS sargassum biomass dataset turned out to cover San Cristóbal in Puerto Rico, not the Virgin Islands.
- USF's [Sargassum Watch](https://optics.marine.usf.edu/projects/saws.html) bulletins are monthly and regional, too coarse for a beach map.
- NOAA's SIR scores individual stretches of coast every day and publishes a downloadable file for each day. That is the one we used.

**How the step works.**

1. Read NOAA's SIR page and collect every report date listed in its date picker (570 dates, May 1, 2025 to Nov 24, 2026, when this was built).
2. For each date not already saved, download `sargassum_risk_YYYYMMDD.kmz`. A KMZ is a zipped KML file, the format Google Earth uses. Each one covers the whole Caribbean and Gulf, 1.5 to 5 MB.
3. Read the KML text and keep only coastline points inside simple boxes around St. Croix, St. Thomas, St. John and Water Island. The British Virgin Islands sit just northeast of St. John, so that corner is cut out. We checked the result by plotting the kept points: they trace each island's outline, plus Buck Island off St. Croix and the cays around St. Thomas.
4. Write three files:
   - `data/interim/sargassum_points.csv`: the 2,087 coastline points, each with an id and an island (1,004 St. Thomas, 530 St. Croix, 503 St. John, 50 Water Island).
   - `data/interim/sargassum/YYYY-MM.csv`: one row per day per point (date, point id, level), split by month so no single file gets large.
   - `data/raw/sargassum_downloads.csv`: the audit trail, with one row per date showing the URL, SHA-256 fingerprint, size, number of USVI points and whether NOAA had the file.

**Two things we found.**

- NOAA lists reports from May 1, 2025, but the map files for May and June 2025 return "not found". Only the PDF versions exist for those days. The step records those 61 days as `missing` so it doesn't keep retrying them. The usable record starts July 1, 2025: 509 days.
- The coastline points are exactly the same every day. So we store each point's position once and keep only the id and level per day. That is the same idea as a dimension table plus a fact table.

**Never fatal.** The beach results are the main product, so step 2b is marked optional in `run_pipeline.py`. If NOAA is down, the run carries on with the days already saved and picks up the gap next time.

**Run it:**

```bash
python pipeline/step2b_sargassum.py
```

**What you should see:** the first run takes about 40 minutes and ends with `sargassum: 509 days saved, 2087 USVI coastline points, 1062175 new rows`. Run it again and you'll see `0 new to fetch`. Later runs fetch only the new day.

**How it flows through the warehouse (step 5).**

| Model | What it holds |
|---|---|
| `stg_sargassum_points`, `stg_sargassum_daily`, `stg_sargassum_downloads` | Typed copies. `risk_label` spells out low, warning, medium or high. |
| `int_beach_sargassum_points` | For each beach, the NOAA points within 2 km of its map pin, on the same island. Distance uses the haversine formula, which gives straight-line distance on a sphere. |
| `fct_beach_sargassum_daily` | One row per beach per day: the highest level among its nearby points. No row means no data. We never guess. |
| `mart_sargassum_island_daily` | Per island per day: the share of coastline at warning or higher, medium or higher, and high, plus the most common level. |
| `mart_beach_sargassum` | Per beach: number of nearby points, latest level, and days at medium or higher (all time and in the last 30 days). |
| `mart_sargassum_vs_samples` | Each DPNR sample since July 2025, with the highest nearby level in the 7 days up to the sampling day. |

The 2 km radius and the 7-day look-back are variables in `dbt_project.yml` (`sargassum_radius_km`, `sargassum_lookback_days`). You can change them in one place. New tests check that levels are 0 to 3, that (date, point) pairs are unique, that every daily row points to a known coastline point, and that every beach has nearby points. The last one is a warning, not a failure. Every one of the 45 beaches has at least 10 nearby points.

**What the comparison shows.** Of 1,645 samples since July 1, 2025, the share above 70 was:

- 8.4% when the nearby level was low (203 samples)
- 2.9% at warning (35 samples)
- 11.8% at medium (451 samples)
- 7.4% at high (956 samples)

There is no steady rise with sargassum level. That is an honest result worth showing, not hiding. Bacteria spikes in the USVI track rain runoff and sewage more than seaweed, and sargassum was at medium or high for most of the period anyway, so there are few low days to compare against.

**Check your understanding**
- Why store point positions once instead of on every daily row? (The same 2,087 positions would repeat 509 times.)
- Why take the highest level near a beach, not the average? (A single red stretch next to a beach matters more to a swimmer than a calm coast 2 km away.)
- Why is a comparison table not proof of cause? (Other things, like rain and season, move both numbers.)

---

## Step 3: Extract the table rows

**File:** `pipeline/step3_extract.py`

**Goal:** one CSV row per beach per PDF, with the four printed columns copied exactly as text: Beach Name, Island, Enterococci, Turbidity.

**Rule:** extraction copies and does not clean. "<10" stays "<10". Cleaning happens in step 5, where every rule is visible and tested. If a number ever looks wrong, you can trace it straight back to the PDF.

### The problem we hit, and how we solved it

This is the most interesting part of the project and worth telling clients about.

**Attempt 1: table detection (pdfplumber).** Libraries can detect a table's grid lines and return cells. It mostly worked, but some rows were scrambled. Hull Bay's "52" landed in Coki Point's cell, and the footer sentence appeared as a beach name.

**Diagnosis.** We rendered a page as an image and printed each word's coordinates. One font in these PDFs (Cambria, regular weight) reports a wrong height for its letters, so the library believed the numbers sat about 20 points higher than they really do. The text didn't line up with the grid.

**Attempt 2: character baselines (PyMuPDF).** Every character has a reliable *baseline*, the invisible line letters sit on. The new method is:

1. Find the header words (Island, #/100ml, Turbidity) and note the horizontal center of each column.
2. Assign every piece of text to the column whose center is closest.
3. Treat each line in the Beach Name column as a new row, unless nothing else is on that line. In that case it is a wrapped name, like "Augusta)" continuing "New Fort (Ft. Louise".
4. Attach each island, bacteria and turbidity value to the row with the nearest baseline.
5. Stop at the footer ("In accordance with...") but keep the last row even when the footer starts on the same line.

**Run it:**

```bash
python pipeline/step3_extract.py
```

**What you should see:** `Extracted 5453 beach rows from 123 PDFs.` and one PDF flagged in `data/interim/extract_log.csv`. That PDF (`12.6.24-Copy-1`) has no printed date, which step 5 handles.

**Sanity check you can run:** every PDF should have 44 or 45 rows (Prosperity Beach was added in October 2025):

```bash
python -c "import pandas as pd; print(pd.read_csv('data/interim/extract_log.csv').rows.value_counts())"
```

**Check your understanding**
- Why not clean "<10" into a number during extraction?
- What is a baseline, and why was it more reliable than the box around each word?

---

## Step 4: Load into DuckDB

**File:** `pipeline/step4_load.py`

**Goal:** the CSVs copied into a database file, `warehouse/beach.duckdb`, in a schema called `raw`.

**Why:** this is the "L" in ELT. Every column is loaded as text (`all_varchar = true`) and nothing is changed. Converting types early is a common source of silent data loss: "<10" can't become a number, so a careless load would turn it into a blank. We also add `loaded_at` so each row records when it arrived.

**Run it:**

```bash
python pipeline/step4_load.py
```

**What you should see:**

```
raw.beach_readings     5453 rows
raw.pdf_manifest        123 rows
```

After step 2b was added, three more tables load the same way: `raw.sargassum_points` (2,087 rows), `raw.sargassum_daily` (about 1.06 million rows, read from the whole `data/interim/sargassum/` folder at once using a `*.csv` wildcard) and `raw.sargassum_downloads` (one row per NOAA date). If those files don't exist yet, the step skips them instead of failing.

**Explore it yourself.** DuckDB has a command-line shell, or use Python:

```bash
python -c "import duckdb; print(duckdb.connect('warehouse/beach.duckdb').sql('select enterococci_raw, count(*) from raw.beach_readings group by 1 order by 2 desc limit 10'))"
```

This query is how we found all the codes DPNR uses: `<10`, `NS`, `*`, `SI`, and plain numbers.

---

## Step 5: Transform and test with dbt

**Folder:** `dbt/`

**Goal:** clean, documented, tested tables that answer real questions.

**Why dbt:** each model is just a SQL `select` statement in a file. dbt works out the order to run them (from the `ref()` links between files), builds them, and runs tests. The same skills carry over directly to Snowflake and Databricks, which is what clients pay for.

### The layers

| Layer | Model | What it does |
|---|---|---|
| Seeds (reference CSVs) | `beaches`, `beach_aliases`, `beach_locations` | The official list of 45 beaches, every spelling DPNR has used, and map coordinates |
| Staging | `stg_beach_readings` | Types and decodes. Turns `<10` into value 10 plus a "below reporting limit" flag. Decodes `NS`, `*`, `SI`. Picks the right date. |
| Intermediate | `int_readings_resolved` | Maps spellings to one `beach_id`. Keeps DPNR's latest PDF when a week was re-posted. |
| Marts | `fct_beach_samples` | One row per beach per week, with `is_exceedance` (>70) |
| | `dim_beach` | One row per beach with location |
| | `mart_beach_summary` | Track record per beach |
| | `mart_island_weekly` | Unsafe counts per island per week |
| | `mart_exceedance_streaks` | Consecutive unsafe weeks |

### Decisions written into the SQL

1. **Below the reporting limit.** "<10" means the lab detected less than 10, so it is never counted as unsafe.
2. **Stale dates.** Normally the date printed on a sheet is the sampling day, 1–3 days before the file name date. Five sheets reused the previous week's printed date while holding new results (we checked: only 7–9 of about 44 values matched the earlier sheet). So when the printed date is more than 4 days older than the file name date, the file name wins. The column `sample_date_source` records which date was used.
3. **Typing slips.** "1..57" becomes 1.57, "2 .04" becomes 2.04, and "050" becomes 0.50.
4. **Spelling variants.** "Cramers Park" and "Cramer's Park", "Halfpenny Beach" and "Ha'penny Beach", "Shoy's" and "Shoy's Beach", and others all map to one beach through `seeds/beach_aliases.csv`. To fix a new spelling, add one line to that file. No code change is needed.
5. **Princess A and C.** On a few weeks in late 2024, DPNR sampled Princess (Condo Row) at two stations, A and C. They are kept as separate `station` values, and the summaries use the main station.

### Pattern worth knowing: "gaps and islands"

`mart_exceedance_streaks` finds runs of consecutive unsafe weeks with a classic SQL trick. Number all of a beach's samples 1, 2, 3, and so on. Separately, number only the unsafe ones 1, 2, 3, and so on. Within a streak both numbers rise together, so their difference stays constant. Grouping by that difference gives one row per streak.

### Tests

There are 40 data tests in total (20 for the beach results, 20 for the sargassum feed). dbt's built-in tests check that ids are unique, nothing important is null, codes are from the known list, and every beach exists in the dimension. We also wrote some of our own:

- `assert_matches_dpnr_advisory_2026_11_13`: our six unsafe beaches for Nov 13, 2026 must exactly match DPNR's [Beach Advisory press release](https://dpnr.vi.gov/wp-content/uploads/2026/11/Beach-Advisory-11.13.26.pdf) (Coki Point, Vessup Bay, Bluebeard's, New Fort, Chenay Bay and Grapetree).
- `assert_no_unparsed_values`: catches any new code DPNR introduces.
- `assert_every_week_has_rows`: fails if a PDF yields fewer than 40 rows, a sign that extraction broke.

**Run it:**

```bash
cd dbt
dbt build --profiles-dir .
cd ..
```

**What you should see:** `Done. PASS=58 WARN=0 ERROR=0`. The 58 is 15 models (6 views, 9 tables), 3 seeds and 40 tests. Before the sargassum feed it was 30: 7 models, 3 seeds and 20 tests.

**A finding from reconciliation.** The press release says 31 beaches were analyzed. The data sheet has 32 results. The difference is Sprat Hall: its sheet shows 20 colonies (safe), but the press release left it off the safe list. The test caught a gap in the source itself. That is a strong story to tell clients about why automated checks matter.

**Check your understanding**
- Why do staging models have no business rules beyond decoding?
- How would you change the threshold from 70 to 104 (the older single-sample standard)? (Answer: change `exceedance_threshold` in `dbt_project.yml`. Every model uses that one variable.)

---

## Step 6: Export for the dashboard

**File:** `pipeline/step6_export.py`

**Goal:** small JSON files in `dashboard/data/` that the web page reads.

**Why:** the dashboard is a static page with no server and no database, so it can be hosted anywhere, including Hostinger. We pre-calculate what it needs. When the pipeline reruns, the page updates automatically.

**Run it:**

```bash
python pipeline/step6_export.py
```

**View the dashboard locally:**

```bash
cd dashboard
python -m http.server 8000
# open http://localhost:8000
```

---

## Step 7: Run everything with one command

**File:** `run_pipeline.py`

```bash
python run_pipeline.py            # every step
python run_pipeline.py --from 3   # skip discovery and the two downloads
python run_pipeline.py --from 2b  # refresh only the sargassum days, then rebuild
```

Steps are labeled 1, 2, 2b, 3, 4, 5, 6. Step 2b is "optional". If it fails, the run prints a note and carries on.

If any step fails, including a failed dbt test, the run stops. Bad data never reaches the dashboard. This is called a quality gate.

---

## Step 8: Schedule it weekly

**File:** `.github/workflows/weekly.yml`

Once the project is on GitHub, GitHub Actions runs `run_pipeline.py` every Saturday at 9:00 AM St. Croix time. It caches the PDFs between runs and commits the refreshed dashboard data. The `workflow_dispatch` line adds a "Run workflow" button for manual runs.

The cron line `0 13 * * 6` means minute 0, hour 13 UTC, any day of the month, any month, Saturday (day 6).

A second line, `30 15 * * *`, runs the same pipeline every day at 11:30 AM St. Croix time, so the sargassum section picks up NOAA's new map each day. On days with no new DPNR sheet, discovery finds nothing new. Only the sargassum files change, and only changed files are committed and uploaded. The commit step now also saves `data/raw/sargassum_downloads.csv`.

The last step uploads the `dashboard/` folder to your Hostinger site over FTP, so the published page updates on its own. It stays switched off until you add three repository secrets in GitHub (Settings > Secrets and variables > Actions > New repository secret):

| Secret | Where to find it in Hostinger hPanel |
|---|---|
| `FTP_SERVER` | Files > FTP Accounts: the FTP IP or hostname |
| `FTP_USERNAME` | Same page: the FTP username |
| `FTP_PASSWORD` | The password for that FTP account |

By default, files go to `/public_html/projects/beach-water-quality/`. To change that, add a repository variable (not a secret) named `FTP_SERVER_DIR`. Secrets are encrypted and hidden in the logs, so the password never appears in the code.

To check it works: open the Actions tab, choose "Weekly beach data refresh", click "Run workflow", and watch each step turn green. If a dbt test fails, the run stops before the upload, so the website keeps last week's good data.

**Failure alerts.** If any step fails, the last step opens a GitHub issue titled "Weekly beach refresh failed", labeled `refresh-failure` and assigned to the repository admin. GitHub then emails the assignee. If the issue is already open, later failures add a comment instead of opening duplicates. Close it once the cause is fixed. To test it, click "Run workflow" and tick "Fail on purpose to test the failure alert".

---

## Beach locations (one-time helper)

**File:** `pipeline/helper_geocode.py`

DPNR doesn't publish coordinates. The helper looks each beach up in OpenStreetMap's free search service (one request per second, as its rules require). It rejects any match outside that island's bounding box.

OpenStreetMap found 35 of 45 beaches. Ten could not be found and were placed by hand; they are marked `manual_approximate` in `dbt/seeds/beach_locations.csv`:

- Dorsch
- Prosperity
- Davis Bay
- Columbus Landing
- Teague Bay
- Ha'penny
- New Fort
- Lindbergh Bay
- Sapphire
- Lindqvist

Two of the ten (Lindbergh Bay and Sapphire) did get OpenStreetMap matches, but in the wrong place, so they were overridden. **Action for you:** check those ten points against your own local knowledge and correct any that are off. You know these beaches better than any geocoder.

---

## Talking about this project

**One-line summary:** "I built an automated pipeline that turns the territory's weekly beach-testing PDFs into a tested data warehouse and a public map. It covers four years, 124 reports and 3,261 samples, plus 509 days of NOAA satellite sargassum risk linked to every beach."

**Skills it demonstrates:**
- API discovery
- Resilient PDF extraction
- Idempotent ingestion
- ELT with dbt
- Data quality tests and reconciliation against an official source
- Joining a second, spatial data source (satellite KML) to point locations
- Scheduling
- Communicating results visually

**The story clients remember:** the table extractor failed because of a font bug. We diagnosed it from character coordinates and rebuilt the parser. Our reconciliation test then caught that the official press release had left out a beach. A second story: when we joined satellite sargassum risk to the bacteria results, there was no clear link, and the dashboard says so plainly instead of implying one.

**Honest limits:**
- Enterococci counts swing a lot from week to week.
- Beaches with fewer than 20 samples have unreliable rates.
- This is an independent analysis, not an official advisory.

---

## Publishing to cruciandataworks.com

When you are ready, copy the `dashboard/` folder into the website as `/projects/beach-water-quality/`, add a project card to the homepage, and upload to Hostinger the same way as before. The page works anywhere static files can be served.
