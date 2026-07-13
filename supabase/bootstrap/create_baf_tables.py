"""
Opprett BAF-tabeller i Supabase (baf_data, baf_price_history, baf_fetch_log).

Kjør én gang:
  python supabase/bootstrap/create_baf_tables.py

Alternativt: lim inn supabase/migrations/baf_migration.sql i Supabase SQL Editor.
"""

import json
import os
import sys
import urllib.error
import urllib.request

PROJECT = "fnkdbuqsschkvpzeumbz"
API_URL = f"https://api.supabase.com/v1/projects/{PROJECT}/database/query"


def load_sql() -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "migrations", "baf_migration.sql")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def run_sql(sql: str) -> bool:
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        print("Mangler SUPABASE_ACCESS_TOKEN (personal access token fra supabase.com/dashboard/account/tokens)")
        return False

    payload = json.dumps({"query": sql}).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "baf-migration/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            print("OK:", response.read().decode()[:200])
            return True
    except urllib.error.HTTPError as error:
        print(f"ERR HTTP {error.code}:", error.read().decode()[:400])
        return False
    except OSError as error:
        print(f"ERR: {error}")
        return False


if __name__ == "__main__":
    if not run_sql(load_sql()):
        sys.exit(1)
    print("BAF-tabeller opprettet.")
