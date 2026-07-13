"""Merge historiske BAF-rader fra JSON-fil inn i baf_data.csv."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from baf_csv import DEFAULT_CSV_PATH, merge_rows, read_csv, utc_now, write_csv


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "seeds" / "colorline_2026-04.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    if not rows:
        print(f"Ingen rader i {path}", file=sys.stderr)
        return 1

    existing = read_csv(DEFAULT_CSV_PATH)
    merged = merge_rows(existing, rows, updated_at=utc_now())
    count = write_csv(merged, DEFAULT_CSV_PATH)
    print(f"Oppdatert {DEFAULT_CSV_PATH} ({count} rader totalt, +{len(rows)} fra {path.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
