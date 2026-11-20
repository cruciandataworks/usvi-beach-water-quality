"""Step 3 - Extract: turn each PDF table into plain rows of text.

Rule of thumb: in this step we copy what the PDF says, exactly as text, and nothing more.
Cleaning ("<10" -> 10, "TNTC" -> too many to count) happens later in dbt (step 5),
where every rule is written down and tested. Keeping raw text means we can always
re-check a number against the original PDF.

Why we read character positions instead of "the table":
  Our first attempt used pdfplumber's table finder. It mixed up neighbouring rows
  (e.g. Hull Bay's "52" ended up in Coki Point's cell) because one of the fonts in these
  PDFs reports a wrong box height, and the printed text doesn't sit inside its grid cell.
  The fix: every character has a reliable "baseline" (the line letters sit on) and an x
  position. So we
    1. find the header words to learn where each column starts (x positions),
    2. treat every bold-ish text line in the Beach Name column as the start of a row,
       unless nothing else is on that line (then it's a wrapped name, e.g. "Augusta)"),
    3. attach each Island / Enterococci / Turbidity piece to the row whose baseline
       is closest.

Output: data/interim/readings_raw.csv (one row per beach per PDF)
        data/interim/extract_log.csv  (one row per PDF: how many rows, any problems)
"""
import csv
import re
from datetime import date, datetime
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "raw" / "pdfs"
MANIFEST = ROOT / "data" / "raw" / "manifest.csv"
OUT = ROOT / "data" / "interim" / "readings_raw.csv"
LOG = ROOT / "data" / "interim" / "extract_log.csv"

HEADER_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")  # e.g. 8/15/25 or 4/17/2024
SAME_LINE = 3.0  # points; pieces whose baselines differ by less than this are on one line


def parse_date(text: str):
    m = HEADER_DATE.search(text)
    if not m:
        return None
    mo, d, y = (int(g) for g in m.groups())
    y = y + 2000 if y < 100 else y
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def page_lines(page):
    """Return text pieces as (x_start, baseline, text), split into runs of characters."""
    pieces = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                run, run_x, run_y, last_x1 = "", None, None, None
                for ch in span["chars"]:
                    x0, y = ch["origin"]
                    # a big horizontal jump means a new column inside the same span
                    if run and last_x1 is not None and x0 - last_x1 > 12:
                        pieces.append((run_x, run_y, run, last_x1))
                        run, run_x = "", None
                    if run_x is None:
                        run_x, run_y = x0, y
                    run += ch["c"]
                    last_x1 = ch["bbox"][2]
                if run:
                    pieces.append((run_x, run_y, run, last_x1))
    # (x_start, baseline, text, x_end)
    return [(x, y, re.sub(r"\s+", " ", t).strip(), x1) for x, y, t, x1 in pieces if t.strip()]


def column_centers(pieces):
    """Learn where each column sits from the header words.

    Values in a column are centred under the header, but not always exactly, so instead of
    hard cut-offs we assign every piece of text to the column whose header centre is
    closest to the piece's own centre."""
    def centre(*words):
        hits = [(x + x1) / 2 for x, y, t, x1 in pieces if t.lower().startswith(words)]
        return min(hits) if hits else None
    island, turb = centre("island"), centre("turbidity")
    entero = centre("#/100", "enterococci")
    names = [(x, x1) for x, y, t, x1 in pieces if t.lower().startswith("beach name")]
    if None in (island, entero, turb) or not names:
        raise ValueError("header not found")
    header_y = max(y for x, y, t, x1 in pieces
                   if t.lower().startswith(("(ntu", "enterococci", "turbidity", "#/100")))
    # beach names are left-aligned and long, so use a point left of the header centre
    beach = (names[0][0] + names[0][1]) / 2 - 20
    return {"beach": beach, "island": island, "enterococci": entero, "turbidity": turb}, header_y


ISLANDS = ("St. Croix", "St. Thomas", "St. John", "Water Island")
FOOTER_WORDS = ("in accordance", "accordance", "bacterial", "colonies", "*key", "key:",
                "is found", "more than 70", "with the vi")


def parse_pdf(path: Path):
    rows, notes, sampled = [], [], None
    doc = pymupdf.open(path)
    for page_no, page in enumerate(doc, start=1):
        pieces = page_lines(page)
        if sampled is None:
            top = " ".join(p[2] for p in sorted(pieces, key=lambda p: p[1])[:5])
            sampled = parse_date(top)
        try:
            centres, header_y = column_centers(pieces)
        except ValueError:
            notes.append(f"p{page_no}: no table header")
            continue
        footer = [y for x, y, t, x1 in pieces if t.lower().startswith(FOOTER_WORDS)]
        bottom = min([y for y in footer if y > header_y] or [10_000])
        # keep the last table row even when the footer sentence starts on the same line
        body = [(x, y, t, x1) for x, y, t, x1 in pieces
                if header_y + 2 < y < bottom + 1
                and t != "In" and not t.lower().startswith(FOOTER_WORDS)]

        def col(x, x1):
            mid = (x + x1) / 2
            return min(centres, key=lambda c: abs(centres[c] - mid))

        names = sorted([(y, x, t) for x, y, t, x1 in body if col(x, x1) == "beach"])
        others = [(y, col(x, x1), t) for x, y, t, x1 in body if col(x, x1) != "beach"]
        # merge name pieces on the same baseline ("Magens B" + "ay")
        lines = []
        for y, x, t in names:
            if lines and abs(lines[-1][0] - y) < SAME_LINE:
                lines[-1][1].append(t)
            else:
                lines.append([y, [t]])
        anchors = []  # rows: [baseline, name_parts, {col: [texts]}]
        for y, parts in lines:
            has_values = any(abs(oy - y) < SAME_LINE for oy, c, t in others)
            if not has_values and anchors and y - anchors[-1][0] < 16:
                anchors[-1][1].extend(parts)  # wrapped beach name
            else:
                anchors.append([y, parts, {}])
        for oy, c, t in others:
            if not anchors:
                break
            row = min(anchors, key=lambda a: abs(a[0] - oy))
            row[2].setdefault(c, []).append(t)
        for y, parts, vals in anchors:
            name = " ".join(parts)
            # one PDF glued the island onto the name ("Coki Point St. Thomas") - split it off
            for isl in ISLANDS:
                if name.endswith(" " + isl) or name.startswith(isl + " "):
                    name = name.replace(isl, "").strip()
                    vals.setdefault("island", []).append(isl)
            rec = {"page": page_no, "beach_name_raw": name}
            for c in ("island", "enterococci", "turbidity"):
                v = vals.get(c, [])
                if len(v) > 1:
                    notes.append(f"p{page_no}: {rec['beach_name_raw']} has {len(v)} {c} values {v}")
                rec[f"{c}_raw"] = " ".join(v)
            rows.append(rec)
    return sampled, rows, notes


def main():
    manifest = {r["media_id"]: r for r in csv.DictReader(MANIFEST.open())}
    out_rows, log_rows = [], []
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        media_id = pdf_path.name.split("_", 1)[0]
        meta = manifest.get(media_id, {})
        try:
            sampled, rows, notes = parse_pdf(pdf_path)
        except Exception as e:  # a corrupt PDF shouldn't stop the whole run
            log_rows.append({"local_file": pdf_path.name, "header_date": "", "rows": 0,
                             "notes": f"ERROR {e}"})
            continue
        name_date = meta.get("sample_date") or ""
        for i, r in enumerate(rows, start=1):
            out_rows.append({
                "media_id": media_id,
                "source_file": pdf_path.name,
                "source_url": meta.get("url", ""),
                "uploaded_at": meta.get("uploaded_at", ""),
                "header_date": sampled.isoformat() if sampled else "",
                "filename_date": name_date,
                "row_number": i,
                **r,
            })
        log_rows.append({"local_file": pdf_path.name,
                         "header_date": sampled.isoformat() if sampled else "",
                         "rows": len(rows), "notes": " | ".join(notes)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["local_file", "header_date", "rows", "notes"])
        w.writeheader()
        w.writerows(log_rows)
    problems = [l for l in log_rows if l["notes"] or not l["header_date"]]
    print(f"Extracted {len(out_rows)} beach rows from {len(log_rows)} PDFs "
          f"({datetime.now():%Y-%m-%d %H:%M}).")
    print(f"{len(problems)} PDFs need a look - see {LOG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
