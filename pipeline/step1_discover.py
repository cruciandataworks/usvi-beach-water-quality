"""Step 1 - Discover: find every weekly beach results PDF that DPNR has published.

DPNR's website runs on WordPress. WordPress exposes a public "media library" feed
(the REST API) that lists every uploaded file. Instead of clicking through web pages,
we ask that feed for files whose name contains "Beach-Data".

Output: data/raw/manifest.csv - one row per PDF (file name, upload date, URL, sample date).
"""
import csv
import re
import time
from datetime import date
from pathlib import Path

import requests

API = "https://dpnr.vi.gov/wp-json/wp/v2/media"
HEADERS = {"User-Agent": "CrucianDataWorks-portfolio/1.0 (hello@cruciandataworks.com)"}
OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "manifest.csv"

# File names look like Beach-Data-11.13.26.pdf, Beach-Data-_-9.6.24.pdf, Beach-Data-12.5.25-Revised.pdf
DATE_IN_NAME = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2})")


def sample_date_from_name(name: str):
    """Pull the sampling date (M.D.YY) out of the file name. Returns None if absent."""
    m = DATE_IN_NAME.search(name)
    if not m:
        return None
    month, day, yy = (int(g) for g in m.groups())
    try:
        return date(2000 + yy, month, day)
    except ValueError:
        return None


def fetch_all_pages():
    """The feed returns at most 100 items per page, so we keep asking for the next page."""
    page, items = 1, []
    while True:
        r = requests.get(
            API,
            params={"search": "Beach-Data", "per_page": 100, "page": page,
                    "_fields": "id,date,source_url,mime_type"},
            headers=HEADERS, timeout=60,
        )
        if r.status_code == 400:  # WordPress says "no more pages"
            break
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        items.extend(batch)
        total_pages = int(r.headers.get("X-WP-TotalPages", page))
        print(f"  page {page}/{total_pages}: {len(batch)} files")
        if page >= total_pages:
            break
        page += 1
        time.sleep(1)  # be polite to a government server
    return items


def main():
    print("Asking DPNR's media feed for Beach-Data files...")
    items = fetch_all_pages()
    rows = []
    for it in items:
        url = it["source_url"]
        name = url.rsplit("/", 1)[-1]
        if it.get("mime_type") != "application/pdf" or "beach-data" not in name.lower():
            continue
        rows.append({
            "media_id": it["id"],
            "file_name": name,
            "uploaded_at": it["date"],
            "sample_date": sample_date_from_name(name),
            "url": url,
        })
    rows.sort(key=lambda r: r["uploaded_at"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    missing = sum(1 for r in rows if r["sample_date"] is None)
    print(f"Found {len(rows)} PDFs from {rows[0]['uploaded_at'][:10]} to {rows[-1]['uploaded_at'][:10]}.")
    print(f"{missing} file names had no readable date (we'll handle those in step 3).")
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
