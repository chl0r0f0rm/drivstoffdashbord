#!/usr/bin/env python3
"""Fetch daily Brent crude spot (USD/bbl) into data/brent_daily.csv.

Primary: FRED series DCOILBRENTEU (EIA Europe Brent Spot FOB), free, no API key.
Fallback: datasets/oil-prices via jsDelivr.
"""
from __future__ import annotations

import csv
import io
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "brent_daily.csv"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
DATAHUB_URL = "https://cdn.jsdelivr.net/gh/datasets/oil-prices@main/data/brent-daily.csv"


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


if __name__ == "__main__":
    main()
