"""
GitHub Actions runner: henter BAF fra Color Line + Fjord Line og skriver
en samlet JSON-fil som Power Automate leser via HTTP.

Output: data/baf_latest.json (repo-rot), samme skjema som Azure-funksjonen:
    { "count": N, "fetched_at": "...", "errors": [...], "rows": [ {...} ] }

Exit-kode 1 hvis 0 rader totalt (gjør at Actions-kjøringen blir rød → varsling).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from baf_parser import fetch_all

# data/baf_latest.json relativt til repo-rot (scriptet kjøres fra rot i workflowen)
OUTPUT = Path("data/baf_latest.json")


def main() -> int:
    rows, errors = fetch_all()
    payload = {
        "count": len(rows),
        "fetched_at": rows[0]["fetched_at"] if rows else None,
        "errors": errors,
        "rows": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} rows, {len(errors)} error(s) to {OUTPUT}")
    for e in errors:
        print(f"  ERROR [{e['company']}]: {e['error']}", file=sys.stderr)
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
