"""One-time helper - find map coordinates for each beach.

DPNR's PDFs don't include locations, so we look each beach up in OpenStreetMap's free
search service (Nominatim). Its rules: at most 1 request per second and an identifying
User-Agent. Results are saved to dbt/seeds/beach_locations.csv with a "geocode_source"
column so anyone can see which points came from OSM and which were checked by hand.

Run once, then review the CSV by eye - geocoders sometimes pick the wrong "Cane Bay".
OpenStreetMap data (c) OpenStreetMap contributors, ODbL.
"""
import csv
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BEACHES = ROOT / "dbt" / "seeds" / "beaches.csv"
OUT = ROOT / "dbt" / "seeds" / "beach_locations.csv"
HEADERS = {"User-Agent": "CrucianDataWorks-portfolio/1.0 (hello@cruciandataworks.com)"}

# rough boxes so a hit on the wrong island is rejected (lon_min, lat_min, lon_max, lat_max)
ISLAND_BOX = {
    "St. Croix": (-64.95, 17.65, -64.55, 17.80),
    "St. Thomas": (-65.10, 18.27, -64.82, 18.40),
    "Water Island": (-64.97, 18.30, -64.93, 18.33),
    "St. John": (-64.82, 18.29, -64.65, 18.38),
}


def search(q):
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": q, "format": "json", "limit": 5},
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(1.1)
    return r.json()


def main():
    rows = []
    for b in csv.DictReader(BEACHES.open()):
        box = ISLAND_BOX[b["island"]]
        base = b["beach_name"].split(" (")[0].replace("'", "")
        hit = None
        for q in (f"{b['beach_name']}, {b['island']}", f"{base}, {b['island']}", f"{base}, US Virgin Islands"):
            for h in search(q):
                lon, lat = float(h["lon"]), float(h["lat"])
                if box[0] <= lon <= box[2] and box[1] <= lat <= box[3]:
                    hit = (lat, lon, h["display_name"][:80])
                    break
            if hit:
                break
        print(f"{b['beach_name']:32} {hit[:2] if hit else 'NOT FOUND'}")
        rows.append({"beach_id": b["beach_id"],
                     "latitude": round(hit[0], 5) if hit else "",
                     "longitude": round(hit[1], 5) if hit else "",
                     "geocode_source": "OpenStreetMap Nominatim" if hit else "",
                     "osm_match": hit[2] if hit else ""})
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
