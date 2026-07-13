"""Kjør historisk BAF-seed SQL via Supabase Management API."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = "fnkdbuqsschkvpzeumbz"
API_URL = f"https://api.supabase.com/v1/projects/{PROJECT}/database/query"
SEEDS_DIR = Path(__file__).resolve().parent.parent / "migrations" / "seeds"


def run_sql(sql: str, token: str) -> None:
    payload = json.dumps({"query": sql}).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "baf-seed/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode()
        if body.strip():
            print(body[:400])


def main() -> int:
    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    if not token:
        print("Mangler SUPABASE_ACCESS_TOKEN", file=sys.stderr)
        return 1

    if len(sys.argv) < 2:
        print(f"Bruk: python {Path(__file__).name} <sql-fil>", file=sys.stderr)
        print(f"Eksempel: python {Path(__file__).name} {SEEDS_DIR / 'colorline_2025-12.sql'}", file=sys.stderr)
        return 1

    sql_path = Path(sys.argv[1])
    sql = sql_path.read_text(encoding="utf-8")
    cleaned_lines = [
        line for line in sql.splitlines() if not line.strip().startswith("--")
    ]
    statements = [part.strip() for part in "\n".join(cleaned_lines).split(";") if part.strip()]
    for index, statement in enumerate(statements, start=1):
        print(f"Kjører statement {index}/{len(statements)} ...")
        try:
            run_sql(statement, token)
        except urllib.error.HTTPError as error:
            print(f"HTTP {error.code}: {error.read().decode()[:400]}", file=sys.stderr)
            return 1
        except OSError as error:
            print(f"Feil: {error}", file=sys.stderr)
            return 1

    print(f"BAF seed fullført: {sql_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
