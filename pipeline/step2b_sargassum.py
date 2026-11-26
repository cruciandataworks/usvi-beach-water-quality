"""Step 2b - Sargassum: save NOAA's daily Sargassum Inundation Risk for USVI coastlines.

NOAA's CoastWatch Caribbean node publishes the Sargassum Inundation Risk (SIR) every day:
https://cwcgom.aoml.noaa.gov/SIR/index.php
For each stretch of coast, it compares satellite floating-algae data (from the University
of South Florida) within 50-100 km with a multi-day baseline and gives a level:

    0 low (blue)   1 warning (yellow)   2 medium (orange)   3 high (red)

Coast with too little satellite data is left out of that day's file (shown black on NOAA's
maps). The product is experimental and is not a forecast.

Each day's map is a KMZ file (a zipped KML, 1.5-5 MB) covering the whole Caribbean and
Gulf. This step keeps only the coastline points around the U.S. Virgin Islands:

    data/interim/sargassum_points.csv          one row per coastline point (fixed list)
    data/interim/sargassum/YYYY-MM.csv         one row per point per day: date, point_id, risk
    data/raw/sargassum_downloads.csv           one row per day: URL, SHA-256, size, points

The coastline points are the same every day, so a day is stored as ~2,600 small rows.
Only days not already saved are downloaded, so a weekly run fetches about 7 files.
"""
import csv
import hashlib
import io
import re
import sys
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://cwcgom.aoml.noaa.gov/SIR"
POINTS = ROOT / "data" / "interim" / "sargassum_points.csv"
DAILY_DIR = ROOT / "data" / "interim" / "sargassum"
LOG = ROOT / "data" / "raw" / "sargassum_downloads.csv"
HEADERS = {"User-Agent": "Crucian Data Works beach tracker (hello@cruciandataworks.com)"}
LOG_COLS = ["report_date", "url", "sha256", "bytes", "usvi_points", "status", "fetched_at_utc"]


def island_of(lon, lat):
    """Which U.S. Virgin Island a coastline point belongs to, or None (PR, BVI, open sea).

    Simple boxes are enough because the islands are far apart. The British Virgin Islands
    sit just north and east of St. John, so those corners are cut out explicitly.
    """
    if 17.60 <= lat <= 17.85 and -64.95 <= lon <= -64.50:
        return "St. Croix"
    if not (18.26 <= lat <= 18.42 and -65.12 <= lon <= -64.655):
        return None
    if lat > 18.375 and lon > -64.79:          # Thatch Cays / Tortola side: BVI
        return None
    if -64.972 <= lon <= -64.944 and 18.298 <= lat <= 18.332:
        return "Water Island"
    if lon > -64.81:
        return "St. John"
    return "St. Thomas"


def report_dates(session):
    """Every report date NOAA lists in its date picker, newest first."""
    r = session.get(f"{BASE}/index.php", timeout=60)
    r.raise_for_status()
    found = sorted(set(re.findall(r"SIR_(\d{8})", r.text)), reverse=True)
    if not found:  # page layout changed: fall back to trying the last ten days
        today = datetime.now(timezone.utc).date()
        found = [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(1, 11)]
    return found


def parse_kmz(blob):
    """Yield (lon, lat, risk) for every coastline vertex inside the USVI boxes."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".kml"))
        kml = z.read(name).decode("utf-8", "replace")
    for risk, coords in re.findall(
        r'<SimpleData name="risk">(-?\d+)</SimpleData>.*?<coordinates>([^<]+)</coordinates>', kml, re.S
    ):
        for p in coords.split():
            lon, lat = (float(v) for v in p.split(",")[:2])
            if island_of(lon, lat):
                yield round(lon, 3), round(lat, 3), int(risk)


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def main():
    session = requests.Session()
    session.headers.update(HEADERS)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    points = {(float(r["longitude"]), float(r["latitude"])): int(r["point_id"]) for r in read_csv(POINTS)}
    log = {r["report_date"]: r for r in read_csv(LOG)}
    done = {d for d, r in log.items() if r["status"] in ("saved", "missing")}

    todo = [d for d in report_dates(session) if d not in done]
    print(f"NOAA lists {len(todo) + len(done & set(log))} reports; {len(todo)} new to fetch")
    new_rows = {}  # month -> rows
    for i, d in enumerate(sorted(todo)):
        url = f"{BASE}/KMZ/sargassum_risk_{d}.kmz"
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        try:
            r = session.get(url, timeout=120)
        except requests.RequestException as e:
            print(f"  {d}: {e.__class__.__name__}, will retry next run")
            continue
        if r.status_code == 404:
            log[d] = dict(report_date=d, url=url, sha256="", bytes=0, usvi_points=0, status="missing", fetched_at_utc=stamp)
            continue
        if r.status_code != 200:
            print(f"  {d}: HTTP {r.status_code}, will retry next run")
            continue
        try:
            seen = {}
            for lon, lat, risk in parse_kmz(r.content):
                pid = points.setdefault((lon, lat), len(points) + 1)
                seen[pid] = max(risk, seen.get(pid, -1))  # a point shared by two lines keeps the higher level
        except (zipfile.BadZipFile, StopIteration, ValueError) as e:
            print(f"  {d}: could not read file ({e}), will retry next run")
            continue
        day = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        new_rows.setdefault(day[:7], []).extend((day, pid, risk) for pid, risk in sorted(seen.items()))
        log[d] = dict(report_date=d, url=url, sha256=hashlib.sha256(r.content).hexdigest(), bytes=len(r.content),
                      usvi_points=len(seen), status="saved", fetched_at_utc=stamp)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(todo)} fetched (latest {d})", flush=True)
        time.sleep(0.3)  # be polite to NOAA's server

    # write the point list (append-only: point ids never change)
    with POINTS.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["point_id", "longitude", "latitude", "island"])
        for (lon, lat), pid in sorted(points.items(), key=lambda kv: kv[1]):
            w.writerow([pid, lon, lat, island_of(lon, lat)])

    # merge the new days into the month files (one file per month keeps git diffs small)
    for month, rows in new_rows.items():
        path = DAILY_DIR / f"{month}.csv"
        old = [(r["report_date"], int(r["point_id"]), int(r["risk"])) for r in read_csv(path)]
        days_new = {r[0] for r in rows}
        merged = sorted([r for r in old if r[0] not in days_new] + rows)
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["report_date", "point_id", "risk"])
            w.writerows(merged)

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_COLS)
        w.writeheader()
        for d in sorted(log):
            w.writerow(log[d])
    saved = sum(1 for r in log.values() if r["status"] == "saved")
    print(f"sargassum: {saved} days saved, {len(points)} USVI coastline points, "
          f"{sum(len(v) for v in new_rows.values())} new rows")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:
        # NOAA's site being down must not stop the beach pipeline; the next run catches up
        print(f"sargassum: NOAA unreachable ({e.__class__.__name__}); keeping saved days")
        sys.exit(0)
