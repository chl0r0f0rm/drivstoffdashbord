"""
GitHub Actions runner: henter BAF fra Color Line + Fjord Line og oppdaterer
data/baf_data.csv.

Exit-kode 1 hvis 0 rader totalt (gjør at Actions-kjøringen blir rød → varsling).
"""

from __future__ import annotations

import sys
from pathlib import Path

from baf_csv import DEFAULT_CSV_PATH, load_seed_rows, merge_rows, read_csv, utc_now, write_csv
from baf_parser import fetch_all

OUTPUT = DEFAULT_CSV_PATH


def main() -> int:
    scraped_rows, errors = fetch_all()
    existing = read_csv(OUTPUT)
    if not existing:
        existing = merge_rows({}, load_seed_rows(), updated_at=utc_now())

    merged = merge_rows(existing, scraped_rows)
    row_count = write_csv(merged, OUTPUT)
    print(f"Wrote {row_count} row(s) to {OUTPUT} ({len(scraped_rows)} from scrape)")
    for error in errors:
        print(f"  ERROR [{error['company']}]: {error['error']}", file=sys.stderr)

    return 0 if row_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
