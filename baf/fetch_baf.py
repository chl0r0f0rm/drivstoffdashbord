"""
GitHub Actions runner: henter BAF fra Color Line + Fjord Line og skriver
en samlet JSON-fil. Synker til Supabase når env er satt.

Output: data/baf_latest.json (repo-rot)
Supabase: baf_data, baf_price_history, baf_fetch_log

Exit-kode 1 hvis 0 rader totalt (gjør at Actions-kjøringen blir rød → varsling).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from baf_parser import fetch_all

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
    for error in errors:
        print(f"  ERROR [{error['company']}]: {error['error']}", file=sys.stderr)

    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"):
        from sync_baf_to_supabase import sync_payload

        if not sync_payload(payload):
            return 1

    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
