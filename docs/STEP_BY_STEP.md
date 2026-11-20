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
```

This pattern is called ELT: Extract, Load, Transform. We pull the data out, load it untouched, then clean it inside the database where every rule is written in SQL and tested. Most modern data teams work this way, whether the warehouse is Snowflake, Databricks, BigQuery or DuckDB.

### Final results

| Measure | Value |
|---|---|
| PDFs collected | 123 (Oct 14, 2022 to Nov 13, 2026) |
| Rows extracted | 5,453 |
| Actual samples (beach actually tested) | 3,229 |
| Unsafe results (>70) | 256 (7.9%) |
| Beaches after merging name spellings | 45 (from 56 printed spellings) |
| dbt models + tests | 7 models, 3 seeds, 20 tests, all passing |

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

There are 20 data tests in total. dbt's built-in tests check that ids are unique, nothing important is null, codes are from the known list, and every beach exists in the dimension. We also wrote some of our own:

- `assert_matches_dpnr_advisory_2026_11_13`: our six unsafe beaches for Nov 13, 2026 must exactly match DPNR's [Beach Advisory press release](https://dpnr.vi.gov/wp-content/uploads/2026/11/Beach-Advisory-11.13.26.pdf) (Coki Point, Vessup Bay, Bluebeard's, New Fort, Chenay Bay and Grapetree).
- `assert_no_unparsed_values`: catches any new code DPNR introduces.
- `assert_every_week_has_rows`: fails if a PDF yields fewer than 40 rows, a sign that extraction broke.

**Run it:**

```bash
cd dbt
dbt build --profiles-dir .
cd ..
```

**What you should see:** `Done. PASS=30 WARN=0 ERROR=0`. The 30 is 7 models, 3 seeds and 20 tests.

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
python run_pipeline.py            # all six steps
python run_pipeline.py --from 3   # skip discovery and download
```

If any step fails, including a failed dbt test, the run stops. Bad data never reaches the dashboard. This is called a quality gate.

---

## Step 8: Schedule it weekly

**File:** `.github/workflows/weekly.yml`

Once the project is on GitHub, GitHub Actions runs `run_pipeline.py` every Saturday at 9:00 AM St. Croix time. It caches the PDFs between runs and commits the refreshed dashboard data. The `workflow_dispatch` line adds a "Run workflow" button for manual runs.

The cron line `0 13 * * 6` means minute 0, hour 13 UTC, any day of the month, any month, Saturday (day 6).

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

**One-line summary:** "I built an automated pipeline that turns the territory's weekly beach-testing PDFs into a tested data warehouse and a public map. It covers four years, 123 reports and 3,229 samples."

**Skills it demonstrates:**
- API discovery
- Resilient PDF extraction
- Idempotent ingestion
- ELT with dbt
- Data quality tests and reconciliation against an official source
- Scheduling
- Communicating results visually

**The story clients remember:** the table extractor failed because of a font bug. We diagnosed it from character coordinates and rebuilt the parser. Our reconciliation test then caught that the official press release had left out a beach.

**Honest limits:**
- Enterococci counts swing a lot from week to week.
- Beaches with fewer than 20 samples have unreliable rates.
- This is an independent analysis, not an official advisory.

---

## Publishing to cruciandataworks.com

When you are ready, copy the `dashboard/` folder into the website as `/projects/beach-water-quality/`, add a project card to the homepage, and upload to Hostinger the same way as before. The page works anywhere static files can be served.
