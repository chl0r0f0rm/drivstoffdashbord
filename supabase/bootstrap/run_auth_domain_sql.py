import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = "fnkdbuqsschkvpzeumbz"
URL = f"https://api.supabase.com/v1/projects/{PROJECT}/database/query"
SQL_PATH = Path(__file__).resolve().parents[1] / "migrations" / "auth_ngn_domain.sql"


def main() -> int:
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        print("Mangler SUPABASE_ACCESS_TOKEN")
        return 1

    sql = SQL_PATH.read_text(encoding="utf-8")
    body = json.dumps({"query": sql}).encode("utf-8")
    request = urllib.request.Request(
        URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "migration-script/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            print("OK:", response.read().decode()[:300])
            return 0
    except urllib.error.HTTPError as error:
        print(f"ERR {error.code}:", error.read().decode()[:500])
        return 1
    except OSError as error:
        print("ERR:", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
