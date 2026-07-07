"""Seed historiske BAF-rader fra JSON-fil til Supabase."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_baf_to_supabase import sync_payload


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "seeds" / "colorline_2026-04.json"
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    payload.pop("source_note", None)
    ok = sync_payload(payload)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
