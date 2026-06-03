"""
Weekly price data fetcher.
Fetches XLS/PDF files from Preem SE, Circle K SE, and Circle K DK,
appends new rows to CSV files in data/, and upserts to Supabase.

Required env vars:
  SUPABASE_URL          https://fnkdbuqsschkvpzeumbz.supabase.co
  SUPABASE_SERVICE_KEY  service_role key (bypasses RLS)
"""

import csv
import os
import re
from datetime import datetime
from io import BytesIO

import requests
import xlrd
from bs4 import BeautifulSoup

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

MONTH_MAP_DK = {
    "januar": "01", "februar": "02", "marts": "03", "april": "04",
    "maj": "05", "juni": "06", "juli": "07", "august": "08",
    "september": "09", "oktober": "10", "november": "11", "december": "12",
}


# ── Supabase ──────────────────────────────────────────────────────────────────

def supabase_upsert(rows):
    if not rows:
        return
    url = f"{SUPABASE_URL}/rest/v1/price_data"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        resp = requests.post(url, json=chunk, headers=headers, timeout=30)
        if resp.ok:
            print(f"  Upserted rows {i + 1}–{i + len(chunk)}")
        else:
            print(f"  Upsert failed: {resp.status_code} {resp.text[:200]}")


# ── CSV helpers ───────────────────────────────────────────────────────────────

def read_existing_keys(filepath, key_column):
    if not os.path.exists(filepath):
        return set()
    with open(filepath, "r", encoding="utf-8") as f:
        return {row[key_column] for row in csv.DictReader(f)}


def append_csv(filepath, new_rows, fieldnames, key_column):
    existing = read_existing_keys(filepath, key_column)
    rows_to_add = [r for r in new_rows if r[key_column] not in existing]
    if not rows_to_add:
        return 0
    write_header = not os.path.exists(filepath)
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(rows_to_add)
    return len(rows_to_add)


# ── Excel date helper ─────────────────────────────────────────────────────────

def excel_serial_to_date(serial):
    try:
        if not isinstance(serial, (int, float)) or serial < 30000:
            return None
        return xlrd.xldate.xldate_as_datetime(serial, 0).date()
    except Exception:
        return None


def safe_float(value):
    try:
        result = float(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def monthly_avg(values):
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 4)


# ── Preem SE ──────────────────────────────────────────────────────────────────

def fetch_preem_se():
    print("\n── Preem SE ─────────────────────────────────────────────────────────")
    try:
        page = requests.get("https://www.preem.se/foretag/listpriser/", timeout=30)
        page.raise_for_status()
    except requests.RequestException as error:
        print(f"  Failed to load Preem page: {error}")
        return [], []

    soup = BeautifulSoup(page.text, "html.parser")
    xls_links = [
        a["href"] for a in soup.find_all("a", href=True)
        if ".xls" in a["href"].lower()
    ]
    if not xls_links:
        print("  No XLS link found on Preem page")
        return [], []

    xls_url = xls_links[0]
    if not xls_url.startswith("http"):
        xls_url = "https://www.preem.se" + xls_url
    print(f"  XLS: {xls_url}")

    try:
        resp = requests.get(xls_url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as error:
        print(f"  Download failed: {error}")
        return [], []

    wb = xlrd.open_workbook(file_contents=resp.content)
    target_sheets = [s for s in wb.sheet_names() if s.strip() in ("2025", "2026")]

    # month -> {diesel_vals, hvo_vals, genomsnitt_diesel, genomsnitt_hvo}
    monthly_data = {}
    daily_rows = []

    for sheet_name in target_sheets:
        ws = wb.sheet_by_name(sheet_name)
        for row_idx in range(2, ws.nrows):
            row = ws.row_values(row_idx)
            if not row or not row[0]:
                continue
            label = str(row[0])

            if re.search(r"genomsnitt|snitt", label, re.IGNORECASE):
                diesel = safe_float(row[3] if len(row) > 3 else None)
                hvo = safe_float(row[5] if len(row) > 5 else None)
                # find month from most recent daily row above
                for back_idx in range(row_idx - 1, max(0, row_idx - 35), -1):
                    date = excel_serial_to_date(ws.row_values(back_idx)[0])
                    if date:
                        month = f"{date.year}-{date.month:02d}"
                        if diesel:
                            monthly_data.setdefault(month, {})
                            monthly_data[month]["genomsnitt_diesel"] = diesel
                            monthly_data[month]["genomsnitt_hvo"] = hvo
                        break
                continue

            date = excel_serial_to_date(row[0])
            if not date:
                continue

            diesel = safe_float(row[3] if len(row) > 3 else None)
            hvo = safe_float(row[5] if len(row) > 5 else None)
            if not diesel:
                continue

            month = f"{date.year}-{date.month:02d}"
            bucket = monthly_data.setdefault(month, {"diesel_vals": [], "hvo_vals": []})
            if "diesel_vals" in bucket:
                bucket["diesel_vals"].append(diesel)
                if hvo:
                    bucket["hvo_vals"].append(hvo)

            daily_rows.append({
                "date": str(date),
                "diesel": round(diesel, 4),
                "hvo": round(hvo, 4) if hvo else None,
            })

    monthly_rows = []
    for month, data in sorted(monthly_data.items()):
        if "genomsnitt_diesel" in data:
            diesel_avg = data["genomsnitt_diesel"]
            hvo_avg = data.get("genomsnitt_hvo")
        else:
            diesel_avg = monthly_avg(data.get("diesel_vals", []))
            hvo_avg = monthly_avg(data.get("hvo_vals", []))
        if diesel_avg:
            monthly_rows.append({
                "month": month,
                "diesel_avg": diesel_avg,
                "hvo_avg": hvo_avg,
            })

    print(f"  {len(monthly_rows)} months, {len(daily_rows)} daily rows")
    return monthly_rows, daily_rows


# ── Circle K SE ───────────────────────────────────────────────────────────────

def fetch_ck_se():
    print("\n── Circle K SE ──────────────────────────────────────────────────────")
    now = datetime.now()
    candidates = []
    for delta in range(4):
        month = now.month - delta
        year = now.year
        if month <= 0:
            month += 12
            year -= 1
        candidates.append(
            f"https://www.circlek.se/media-assets/uploads/{year}-{month:02d}/Prishistorik_B2B.xls"
        )

    xls_url = None
    for url in candidates:
        try:
            r = requests.head(url, timeout=15)
            if r.ok:
                xls_url = url
                break
        except requests.RequestException:
            continue

    if not xls_url:
        print("  No Circle K SE XLS found (tried last 4 months)")
        return [], []
    print(f"  XLS: {xls_url}")

    try:
        resp = requests.get(xls_url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as error:
        print(f"  Download failed: {error}")
        return [], []

    wb = xlrd.open_workbook(file_contents=resp.content)
    target_sheets = [s for s in wb.sheet_names() if s.strip() in ("2025", "2026")]

    monthly_data = {}
    daily_rows = []
    current_month = None

    for sheet_name in target_sheets:
        ws = wb.sheet_by_name(sheet_name)
        for row_idx in range(3, ws.nrows):
            row = ws.row_values(row_idx)
            if not row or row[0] is None:
                continue
            label = str(row[0])

            if re.match(r"^Genomsnitt\s+", label, re.IGNORECASE):
                if current_month:
                    diesel_ore = safe_float(row[5] if len(row) > 5 else None)
                    hvo_ore = safe_float(row[11] if len(row) > 11 else None)
                    diesel_sek = round(diesel_ore / 100, 4) if diesel_ore else None
                    hvo_sek = round(hvo_ore / 100, 4) if hvo_ore else None
                    if diesel_sek:
                        monthly_data[current_month] = {
                            "diesel_avg": diesel_sek,
                            "hvo_avg": hvo_sek,
                        }
                continue

            date = excel_serial_to_date(row[0])
            if not date:
                continue

            diesel_ore = safe_float(row[5] if len(row) > 5 else None)
            hvo_ore = safe_float(row[11] if len(row) > 11 else None)
            if not diesel_ore:
                continue

            current_month = f"{date.year}-{date.month:02d}"
            daily_rows.append({
                "date": str(date),
                "diesel": round(diesel_ore / 100, 4),
                "hvo": round(hvo_ore / 100, 4) if hvo_ore else None,
            })

    monthly_rows = [
        {"month": m, "diesel_avg": v["diesel_avg"], "hvo_avg": v["hvo_avg"]}
        for m, v in sorted(monthly_data.items())
    ]
    print(f"  {len(monthly_rows)} months, {len(daily_rows)} daily rows")
    return monthly_rows, daily_rows


# ── Circle K DK ───────────────────────────────────────────────────────────────

def fetch_ck_dk():
    print("\n── Circle K DK ──────────────────────────────────────────────────────")
    try:
        import pdfplumber
    except ImportError:
        print("  pdfplumber not installed — skipping DK")
        return []

    try:
        page = requests.get(
            "https://www.circlek.dk/erhverv/braendstof/historiskepriser", timeout=30
        )
        page.raise_for_status()
    except requests.RequestException as error:
        print(f"  Failed to load Circle K DK page: {error}")
        return []

    soup = BeautifulSoup(page.text, "html.parser")
    pdf_url = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if ".pdf" in href.lower() and "ekskl" in text and "moms" in text and "afgifter" not in text:
            pdf_url = href
            break

    if not pdf_url:
        print("  No matching PDF found on Circle K DK page")
        return []

    if not pdf_url.startswith("http"):
        pdf_url = "https://www.circlek.dk" + pdf_url
    print(f"  PDF: {pdf_url}")

    try:
        resp = requests.get(pdf_url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as error:
        print(f"  PDF download failed: {error}")
        return []

    monthly_rows = []
    current_year = None

    with pdfplumber.open(BytesIO(resp.content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                year_match = re.search(r"\b(20\d{2})\b", line)
                if year_match and len(line.strip()) < 10:
                    current_year = year_match.group(1)

                if "snit" not in line.lower():
                    continue

                month_num = None
                for part in line.split():
                    key = part.lower().rstrip(":")
                    if key in MONTH_MAP_DK:
                        month_num = MONTH_MAP_DK[key]
                        break

                numbers = re.findall(r"\d+,\d+", line)
                if len(numbers) >= 3 and month_num and current_year:
                    try:
                        def to_float(s):
                            return float(s.replace(",", "."))
                        diesel = round(to_float(numbers[2]), 4)
                        hvo = round(to_float(numbers[5]), 4) if len(numbers) > 5 else None
                        monthly_rows.append({
                            "month": f"{current_year}-{month_num}",
                            "diesel_avg": diesel,
                            "hvo_avg": hvo,
                        })
                    except (ValueError, IndexError):
                        pass

    print(f"  {len(monthly_rows)} months")
    return monthly_rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    upsert_rows = []
    report = []

    preem_monthly, preem_daily = fetch_preem_se()
    if preem_monthly:
        n = append_csv(
            os.path.join(DATA_DIR, "preem_SE_månedlig.csv"),
            preem_monthly, ["month", "diesel_avg", "hvo_avg"], "month",
        )
        report.append(f"SE_preem: +{n} months (latest: {preem_monthly[-1]['month']})")
        upsert_rows += [
            {"source": "SE_preem", "month": r["month"], "diesel": r["diesel_avg"], "hvo": r["hvo_avg"]}
            for r in preem_monthly
        ]
    if preem_daily:
        append_csv(
            os.path.join(DATA_DIR, "preem_SE_daglig.csv"),
            preem_daily, ["date", "diesel", "hvo"], "date",
        )

    ck_se_monthly, ck_se_daily = fetch_ck_se()
    if ck_se_monthly:
        n = append_csv(
            os.path.join(DATA_DIR, "circklek_SE_månedlig.csv"),
            ck_se_monthly, ["month", "diesel_avg", "hvo_avg"], "month",
        )
        report.append(f"SE_ck: +{n} months (latest: {ck_se_monthly[-1]['month']})")
        upsert_rows += [
            {"source": "SE_ck", "month": r["month"], "diesel": r["diesel_avg"], "hvo": r["hvo_avg"]}
            for r in ck_se_monthly
        ]
    if ck_se_daily:
        append_csv(
            os.path.join(DATA_DIR, "circklek_SE_daglig.csv"),
            ck_se_daily, ["date", "diesel", "hvo"], "date",
        )

    ck_dk_monthly = fetch_ck_dk()
    if ck_dk_monthly:
        n = append_csv(
            os.path.join(DATA_DIR, "circklek_DK_månedlig.csv"),
            ck_dk_monthly, ["month", "diesel_avg", "hvo_avg"], "month",
        )
        report.append(f"DK_ck: +{n} months (latest: {ck_dk_monthly[-1]['month']})")
        upsert_rows += [
            {"source": "DK_ck", "month": r["month"], "diesel": r["diesel_avg"], "hvo": r["hvo_avg"]}
            for r in ck_dk_monthly
        ]

    print("\n── Supabase upsert ───────────────────────────────────────────────────")
    supabase_upsert(upsert_rows)

    print("\n── Summary ───────────────────────────────────────────────────────────")
    if report:
        for line in report:
            print(f"  {line}")
    else:
        print("  No new data found.")


if __name__ == "__main__":
    main()
