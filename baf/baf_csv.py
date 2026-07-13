"""Les/skriv baf_data.csv — stabil kolonnekontrakt for Power BI."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CSV_COLUMNS = (
    "id",
    "company",
    "route",
    "valid_from",
    "valid_to",
    "period_label",
    "price_nok",
    "price_eur",
    "source_url",
    "first_seen_at",
    "updated_at",
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV_PATH = REPO_ROOT / "data" / "baf_data.csv"
SEEDS_DIR = Path(__file__).resolve().parent / "seeds"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def row_to_csv_record(row: dict[str, Any], *, first_seen_at: str, updated_at: str) -> dict[str, str]:
    return {
        "id": row["id"],
        "company": row["company"],
        "route": row["route"],
        "valid_from": row["valid_from"],
        "valid_to": row["valid_to"],
        "period_label": row["period_label"],
        "price_nok": str(int(row["price_nok"])),
        "price_eur": str(float(row["price_eur"])),
        "source_url": row["source_url"],
        "first_seen_at": first_seen_at,
        "updated_at": updated_at,
    }


def read_csv(path: Path = DEFAULT_CSV_PATH) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    with path.open(encoding="utf-8", newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle)}


def load_seed_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(SEEDS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(payload.get("rows", []))
    return rows


def merge_rows(
    existing: dict[str, dict[str, str]],
    incoming: list[dict[str, Any]],
    *,
    updated_at: str | None = None,
) -> dict[str, dict[str, str]]:
    stamp = updated_at or utc_now()
    merged = dict(existing)

    for row in incoming:
        row_id = row["id"]
        fetched_at = row.get("fetched_at", stamp)
        previous = merged.get(row_id)
        first_seen_at = previous["first_seen_at"] if previous else fetched_at
        merged[row_id] = row_to_csv_record(
            row,
            first_seen_at=first_seen_at,
            updated_at=stamp,
        )

    return merged


def sorted_records(records: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        records.values(),
        key=lambda item: (item["valid_from"], item["company"], item["route"]),
    )


def write_csv(records: dict[str, dict[str, str]], path: Path = DEFAULT_CSV_PATH) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted_records(records)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
