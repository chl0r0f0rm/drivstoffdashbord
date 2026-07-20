#!/usr/bin/env python3
"""Fetch daily Brent crude spot (USD/bbl) into data/brent_daily.csv and Supabase.

Primary: FRED series DCOILBRENTEU (EIA Europe Brent Spot FOB), free, no API key.
Fallback: datasets/oil-prices via jsDelivr.

Supabase (optional locally, required in CI):
  SUPABASE_URL, SUPABASE_SERVICE_KEY
  Upserts to daily_price_data with source=BRENT (price in diesel column).
"""
from __future__ import annotations

import csv
import io
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "brent_daily.csv"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
DATAHUB_URL = "https://cdn.jsdelivr.net/gh/datasets/oil-prices@main/data/brent-daily.csv"
BRENT_SOURCE = "BRENT"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def download(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "NG-Drivstoff-Index/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def normalize(text: str) -> list[tuple[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV missing header")

    fields = [name.strip() for name in reader.fieldnames]
    lower = {name.lower(): name for name in fields}

    date_key = lower.get("observation_date") or lower.get("date")
    price_key = lower.get("dcoilbrenteu") or lower.get("price") or lower.get("value")
    if not date_key or not price_key:
        raise ValueError(f"Unexpected columns: {fields}")

    rows: list[tuple[str, str]] = []
    for row in reader:
        date = (row.get(date_key) or "").strip()
        price = (row.get(price_key) or "").strip()
        if not date or not price or price.upper() == ".":
            continue
        rows.append((date, price))
    return rows


def supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }


def supabase_upsert_brent(rows: list[tuple[str, str]]) -> bool:
    if not rows:
        return True
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("  Supabase skip (SUPABASE_URL/SUPABASE_SERVICE_KEY not set)")
        return True

    url = f"{SUPABASE_URL}/rest/v1/daily_price_data?on_conflict=source,date"
    upsert_rows = [
        {"source": BRENT_SOURCE, "date": date, "diesel": float(price), "hvo": None}
        for date, price in rows
    ]
    batch_size = 100
    failed = False
    for index in range(0, len(upsert_rows), batch_size):
        chunk = upsert_rows[index:index + batch_size]
        response = requests.post(url, json=chunk, headers=supabase_headers(), timeout=60)
        if response.ok:
            print(f"  [daily_price_data] Upserted rows {index + 1}–{index + len(chunk)}")
        else:
            failed = True
            print(f"  [daily_price_data] Upsert failed: {response.status_code} {response.text[:200]}")
    return not failed


def supabase_upsert_source_sync() -> bool:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return True

    url = f"{SUPABASE_URL}/rest/v1/price_source_sync?on_conflict=source"
    now = datetime.now(timezone.utc).isoformat()
    response = requests.post(
        url,
        json=[{"source": BRENT_SOURCE, "updated_at": now}],
        headers=supabase_headers(),
        timeout=30,
    )
    if response.ok:
        print(f"  Sync timestamp updated for: {BRENT_SOURCE}")
        return True
    print(f"  Sync timestamp upsert failed: {response.status_code} {response.text[:200]}")
    return False


def main() -> None:
    errors: list[str] = []
    rows: list[tuple[str, str]] | None = None
    source = ""
    for url in (FRED_URL, DATAHUB_URL):
        try:
            rows = normalize(download(url))
            source = url
            break
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    if rows is None:
        raise SystemExit("Brent fetch failed:\n" + "\n".join(errors))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "price"])
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUT.relative_to(ROOT)} from {source}")

    upsert_ok = supabase_upsert_brent(rows)
    sync_ok = supabase_upsert_source_sync()
    if SUPABASE_URL and SUPABASE_SERVICE_KEY and (not upsert_ok or not sync_ok):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
