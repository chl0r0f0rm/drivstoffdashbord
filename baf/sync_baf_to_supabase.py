"""
DEPRECATED — BAF leser nå fra data/baf_data.csv (se BAF-pipeline-handoff.md).
Beholdes midlertidig for referanse; ikke brukt av GitHub Actions.

Synkroniser BAF-rader til Supabase med historikk.

Leser payload fra fetch_baf.py (eller JSON-fil) og:
  - upserter baf_data (gjeldende sats per strekning/periode)
  - appender baf_price_history ved ny rad eller prisendring
  - logger kjøringen i baf_fetch_log

Krever env:
  SUPABASE_URL
  SUPABASE_SERVICE_KEY
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def _headers(*, prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _price_changed(existing: dict[str, Any], row: dict[str, Any]) -> bool:
    return (
        int(existing["price_nok"]) != int(row["price_nok"])
        or float(existing["price_eur"]) != float(row["price_eur"])
    )


def fetch_existing_rows(row_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not row_ids:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for row_id in row_ids:
        url = f"{SUPABASE_URL}/rest/v1/baf_data"
        response = requests.get(
            url,
            headers=_headers(),
            params={
                "id": f"eq.{row_id}",
                "select": "id,price_nok,price_eur,first_seen_at",
            },
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"Henting av rad {row_id!r} feilet: {response.status_code} {response.text[:200]}")
        rows = response.json()
        if rows:
            result[row_id] = rows[0]
    return result


def upsert_baf_rows(rows: list[dict[str, Any]], now: str) -> tuple[int, list[dict[str, Any]]]:
    existing = fetch_existing_rows([row["id"] for row in rows])
    history_rows: list[dict[str, Any]] = []
    upsert_payload: list[dict[str, Any]] = []

    for row in rows:
        fetched_at = row.get("fetched_at", now)
        data_row = {
            "id": row["id"],
            "company": row["company"],
            "route": row["route"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "period_label": row.get("period_label"),
            "price_nok": row["price_nok"],
            "price_eur": row["price_eur"],
            "source_url": row.get("source_url"),
            "updated_at": now,
        }
        old = existing.get(row["id"])
        if old is None:
            data_row["first_seen_at"] = fetched_at
            history_rows.append(_history_row(row, fetched_at))
        else:
            data_row["first_seen_at"] = old.get("first_seen_at", fetched_at)
            if _price_changed(old, row):
                history_rows.append(_history_row(row, fetched_at))
        upsert_payload.append(data_row)

    if upsert_payload:
        url = f"{SUPABASE_URL}/rest/v1/baf_data?on_conflict=id"
        response = requests.post(
            url,
            json=upsert_payload,
            headers=_headers(prefer="resolution=merge-duplicates"),
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"Upsert baf_data feilet: {response.status_code} {response.text[:200]}")

    if history_rows:
        url = f"{SUPABASE_URL}/rest/v1/baf_price_history"
        response = requests.post(url, json=history_rows, headers=_headers(), timeout=30)
        if not response.ok:
            raise RuntimeError(
                f"Insert baf_price_history feilet: {response.status_code} {response.text[:200]}"
            )

    return len(history_rows), history_rows


def _history_row(row: dict[str, Any], fetched_at: str) -> dict[str, Any]:
    return {
        "baf_id": row["id"],
        "price_nok": row["price_nok"],
        "price_eur": row["price_eur"],
        "period_label": row.get("period_label"),
        "valid_to": row.get("valid_to"),
        "fetched_at": fetched_at,
    }


def insert_fetch_log(row_count: int, errors: list[dict[str, Any]], now: str) -> None:
    if row_count == 0:
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "ok"

    payload = {
        "fetched_at": now,
        "row_count": row_count,
        "error_count": len(errors),
        "errors": errors,
        "status": status,
    }
    url = f"{SUPABASE_URL}/rest/v1/baf_fetch_log"
    response = requests.post(url, json=payload, headers=_headers(), timeout=30)
    if not response.ok:
        raise RuntimeError(f"Insert baf_fetch_log feilet: {response.status_code} {response.text[:200]}")


def sync_payload(payload: dict[str, Any]) -> bool:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("Supabase-sync hoppet over (mangler SUPABASE_URL / SUPABASE_SERVICE_KEY)")
        return True

    rows = payload.get("rows", [])
    errors = payload.get("errors", [])
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    try:
        history_count, _ = upsert_baf_rows(rows, now)
        insert_fetch_log(len(rows), errors, now)
        print(
            f"Supabase: {len(rows)} rad(er) synket, {history_count} historikk-rad(er), "
            f"status={'partial' if errors else 'ok'}"
        )
        return True
    except RuntimeError as error:
        print(f"Supabase-sync feilet: {error}", file=sys.stderr)
        try:
            insert_fetch_log(0, [{"company": "sync", "error": str(error)}], now)
        except RuntimeError:
            pass
        return False


def sync_from_file(path: str) -> bool:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return sync_payload(payload)


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/baf_latest.json"
    if not os.path.exists(path):
        print(f"Fant ikke {path}", file=sys.stderr)
        return 1
    return 0 if sync_from_file(path) else 1


if __name__ == "__main__":
    raise SystemExit(main())
