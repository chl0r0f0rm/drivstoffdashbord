"""
Fetch monthly BAF (Bunker Adjustment Factor) from Color Line Cargo.

Source: https://www.colorline-cargo.com/services/baf-adjustments
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

COLORLINE_BAF_URL = "https://www.colorline-cargo.com/services/baf-adjustments"
COMPANY_NAME = "Color Line"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_CSV = DATA_DIR / "colorline_baf.csv"

PERIOD_RE = re.compile(
    r"(\d{1,2})\.\s*[–\-]\s*(\d{1,2})\.(\d{2})\.(\d{4})"
)
PRICE_RE = re.compile(
    r"(\d+)\s*NOK\s*\(\s*€\s*([\d,\.]+)\s*\)",
    re.IGNORECASE,
)

CSV_FIELDS = [
    "company",
    "route",
    "valid_from",
    "valid_to",
    "period_label",
    "price_nok",
    "price_eur",
    "source_url",
    "fetched_at",
]


def parse_period_label(label: str) -> tuple[str, str, str]:
    match = PERIOD_RE.search(label)
    if not match:
        raise ValueError(f"Could not parse BAF period from: {label!r}")
    day_from, day_to, month, year = match.groups()
    valid_from = f"{year}-{month.zfill(2)}-{int(day_from):02d}"
    valid_to = f"{year}-{month.zfill(2)}-{int(day_to):02d}"
    return valid_from, valid_to, label.strip()


def parse_eur_amount(raw: str) -> float:
    normalized = raw.strip().replace(" ", "").replace(",", ".")
    return float(normalized)


def parse_price_text(text: str) -> tuple[int, float]:
    match = PRICE_RE.search(text)
    if not match:
        raise ValueError(f"Could not parse BAF price from: {text!r}")
    nok = int(match.group(1))
    eur = parse_eur_amount(match.group(2))
    return nok, eur


def fetch_colorline_baf_html(session: requests.Session | None = None) -> str:
    client = session or requests.Session()
    response = client.get(
        COLORLINE_BAF_URL,
        timeout=30,
        headers={"User-Agent": "NG-BAF-fetcher/1.0"},
    )
    response.raise_for_status()
    return response.text


def parse_colorline_baf(html: str, fetched_at: datetime | None = None) -> list[dict]:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    soup = BeautifulSoup(html, "lxml")
    sections = soup.select("section.modStructuredinfo")

    rows: list[dict] = []
    for section in sections:
        header = section.select_one(".mod-hd h2, .mod-hd")
        if not header:
            continue
        header_text = header.get_text(" ", strip=True)
        if "BAF Adjustment Fee" not in header_text:
            continue

        valid_from, valid_to, period_label = parse_period_label(header_text)

        for row in section.select("div.row"):
            route_el = row.select_one("div.label")
            price_el = row.select_one("div.text")
            if not route_el or not price_el:
                continue
            route = route_el.get_text(" ", strip=True)
            price_text = price_el.get_text(" ", strip=True)
            if not route or "NOK" not in price_text:
                continue
            price_nok, price_eur = parse_price_text(price_text)
            rows.append({
                "company": COMPANY_NAME,
                "route": route,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "period_label": period_label,
                "price_nok": price_nok,
                "price_eur": price_eur,
                "source_url": COLORLINE_BAF_URL,
                "fetched_at": fetched_at.replace(microsecond=0).isoformat(),
            })

    if not rows:
        raise ValueError("No BAF rows parsed from Color Line page")
    return rows


def fetch_colorline_baf() -> list[dict]:
    html = fetch_colorline_baf_html()
    return parse_colorline_baf(html)


def write_csv(rows: list[dict], path: Path = OUTPUT_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    try:
        rows = fetch_colorline_baf()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    write_csv(rows)
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(rows)} rows to {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
