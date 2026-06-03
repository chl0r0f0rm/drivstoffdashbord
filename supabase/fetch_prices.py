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
import sys
from datetime import datetime, timezone
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
MONTH_HEADER_DK = re.compile(r"^(\w+)\s+(20\d{2})\s+ekskl", re.IGNORECASE)


# ── Supabase ──────────────────────────────────────────────────────────────────

def supabase_upsert_source_sync(sources):
    if not sources:
        return
    url = f"{SUPABASE_URL}/rest/v1/price_source_sync"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    now = datetime.now(timezone.utc).isoformat()
    rows = [{"source": source, "updated_at": now} for source in sources]
    resp = requests.post(url, json=rows, headers=headers, timeout=30)
    if resp.ok:
        print(f"  Sync timestamps updated for: {', '.join(sources)}")
    else:
        print(f"  Sync timestamp upsert failed: {resp.status_code} {resp.text[:200]}")


UPSERT_ON_CONFLICT = {
    "price_data": "source,month",
    "daily_price_data": "source,date",
    "price_source_sync": "source",
}


def supabase_upsert(rows, table="price_data"):
    if not rows:
        return True
    on_conflict = UPSERT_ON_CONFLICT.get(table)
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if on_conflict:
        url += f"?on_conflict={on_conflict}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    batch_size = 100
    failed = False
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        resp = requests.post(url, json=chunk, headers=headers, timeout=30)
        if resp.ok:
            print(f"  [{table}] Upserted rows {i + 1}–{i + len(chunk)}")
        else:
            failed = True
            print(f"  [{table}] Upsert failed: {resp.status_code} {resp.text[:200]}")
    return not failed


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
    pending_month = None

    def parse_dk_prices(line):
        numbers = re.findall(r"\d+,\d+", line)
        if len(numbers) < 3:
            return None, None
        def to_float(value):
            return float(value.replace(",", "."))
        diesel = round(to_float(numbers[2]), 4)
        hvo = round(to_float(numbers[5]), 4) if len(numbers) > 5 else None
        return diesel, hvo

    with pdfplumber.open(BytesIO(resp.content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                stripped = line.strip()
                header_match = MONTH_HEADER_DK.match(stripped)
                if header_match:
                    month_key = header_match.group(1).lower()
                    year = header_match.group(2)
                    if month_key in MONTH_MAP_DK:
                        pending_month = f"{year}-{MONTH_MAP_DK[month_key]}"
                    continue

                if not pending_month or not re.search(r"\bsnit\b", stripped, re.IGNORECASE):
                    continue

                try:
                    diesel, hvo = parse_dk_prices(stripped)
                    if diesel:
                        monthly_rows.append({
                            "month": pending_month,
                            "diesel_avg": diesel,
                            "hvo_avg": hvo,
                        })
                except (ValueError, IndexError):
                    pass
                pending_month = None

    print(f"  {len(monthly_rows)} months")
    return monthly_rows


# ── Circle K Norge ───────────────────────────────────────────────────────────

CK_NO_URL = "https://www.circlek.no/bedrift/produkter/drivstoff/priser"

PRODUCT_ALIASES = {
    "diesel":  ["diesel"],
    "hvo":     ["hvo100", "anleggsbio hvo100"],
}

def fetch_ck_no():
    print("\n── Circle K Norge ───────────────────────────────────────────────────")
    try:
        resp = requests.get(CK_NO_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except requests.RequestException as error:
        print(f"  Failed to load page: {error}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    prices = {}
    date_effective = None

    for table in soup.find_all("table"):
        headers_text = " ".join(th.get_text(" ", strip=True).lower() for th in table.find_all("th"))
        if "gjeldende fra" not in headers_text and "pris eks" not in headers_text:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            cell_texts = [c.get_text(" ", strip=True) for c in cells]
            row_text = " ".join(cell_texts).lower()

            # Extract numeric value from a cell (handles "Pris eks. mva.: 14,83" or "14,83")
            def extract_number(text):
                m = re.search(r"(\d+)[,.](\d+)", text)
                return round(float(m.group(1) + "." + m.group(2)), 4) if m else None

            # Extract date from a cell (handles "Gjeldende fra: 2026-06-02" or "2026-06-02")
            def extract_date(text):
                m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
                return m.group(1) if m else None

            # Find which product this row is
            matched_product = None
            for product_key, aliases in PRODUCT_ALIASES.items():
                for alias in aliases:
                    if alias in row_text:
                        matched_product = product_key
                        break
                if matched_product:
                    break

            if not matched_product:
                continue

            # Skip "anleggs" variants (they are a different product tier)
            if "anleggsdiesel" in row_text:
                continue

            # Find price ex. VAT and effective date across all cells
            price_val = None
            row_date = None
            for i, cell_text in enumerate(cell_texts):
                v = extract_number(cell_text)
                d = extract_date(cell_text)
                if d:
                    row_date = d
                # Heuristic: the ex-VAT price is in the cell after "Produkt" column,
                # value is between 10 and 30 NOK/L
                if v and 10 < v < 30 and price_val is None:
                    price_val = v

            if price_val:
                prices[matched_product] = price_val
            if row_date:
                date_effective = row_date

    if not prices.get("diesel"):
        print("  Could not find diesel price on page")
        return []

    fetch_date = date_effective or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = {
        "date":   fetch_date,
        "diesel": prices.get("diesel"),
        "hvo":    prices.get("hvo"),
    }
    print(f"  Diesel: {row['diesel']} NOK/L  HVO: {row['hvo']} NOK/L  (gjeldende fra {fetch_date})")
    return [row]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    monthly_upsert = []
    daily_upsert   = []
    report = []
    synced_sources = []

    preem_monthly, preem_daily = fetch_preem_se()
    if preem_monthly:
        synced_sources.append("SE_preem")
        n = append_csv(
            os.path.join(DATA_DIR, "preem_SE_månedlig.csv"),
            preem_monthly, ["month", "diesel_avg", "hvo_avg"], "month",
        )
        report.append(f"SE_preem: +{n} months (latest: {preem_monthly[-1]['month']})")
        monthly_upsert += [
            {"source": "SE_preem", "month": r["month"], "diesel": r["diesel_avg"], "hvo": r["hvo_avg"]}
            for r in preem_monthly
        ]
    if preem_daily:
        n = append_csv(
            os.path.join(DATA_DIR, "preem_SE_daglig.csv"),
            preem_daily, ["date", "diesel", "hvo"], "date",
        )
        report.append(f"SE_preem daily: +{n} days")
        daily_upsert += [
            {"source": "SE_preem", "date": r["date"], "diesel": r["diesel"], "hvo": r["hvo"]}
            for r in preem_daily
        ]

    ck_se_monthly, ck_se_daily = fetch_ck_se()
    if ck_se_monthly:
        synced_sources.append("SE_ck")
        n = append_csv(
            os.path.join(DATA_DIR, "circklek_SE_månedlig.csv"),
            ck_se_monthly, ["month", "diesel_avg", "hvo_avg"], "month",
        )
        report.append(f"SE_ck: +{n} months (latest: {ck_se_monthly[-1]['month']})")
        monthly_upsert += [
            {"source": "SE_ck", "month": r["month"], "diesel": r["diesel_avg"], "hvo": r["hvo_avg"]}
            for r in ck_se_monthly
        ]
    if ck_se_daily:
        n = append_csv(
            os.path.join(DATA_DIR, "circklek_SE_daglig.csv"),
            ck_se_daily, ["date", "diesel", "hvo"], "date",
        )
        report.append(f"SE_ck daily: +{n} days")
        daily_upsert += [
            {"source": "SE_ck", "date": r["date"], "diesel": r["diesel"], "hvo": r["hvo"]}
            for r in ck_se_daily
        ]

    ck_dk_monthly = fetch_ck_dk()
    if ck_dk_monthly:
        synced_sources.append("DK_ck")
        n = append_csv(
            os.path.join(DATA_DIR, "circklek_DK_månedlig.csv"),
            ck_dk_monthly, ["month", "diesel_avg", "hvo_avg"], "month",
        )
        report.append(f"DK_ck: +{n} months (latest: {ck_dk_monthly[-1]['month']})")
        monthly_upsert += [
            {"source": "DK_ck", "month": r["month"], "diesel": r["diesel_avg"], "hvo": r["hvo_avg"]}
            for r in ck_dk_monthly
        ]

    ck_no_daily = fetch_ck_no()
    if ck_no_daily:
        n = append_csv(
            os.path.join(DATA_DIR, "circklek_NO_daglig.csv"),
            ck_no_daily, ["date", "diesel", "hvo"], "date",
        )
        report.append(f"NO_ck: +{n} rows (date: {ck_no_daily[-1]['date']})")
        daily_upsert += [
            {"source": "NO_ck", "date": r["date"], "diesel": r["diesel"], "hvo": r["hvo"]}
            for r in ck_no_daily
        ]
        # Also update monthly average for price_data
        for r in ck_no_daily:
            month = r["date"][:7]
            monthly_upsert.append({
                "source": "NO_ck", "month": month,
                "diesel": r["diesel"], "hvo": r["hvo"],
            })

    print("\n── Supabase upsert ───────────────────────────────────────────────────")
    upsert_ok = True
    upsert_ok = supabase_upsert(monthly_upsert, table="price_data") and upsert_ok
    upsert_ok = supabase_upsert(daily_upsert,   table="daily_price_data") and upsert_ok
    supabase_upsert_source_sync(synced_sources)

    print("\n── Summary ───────────────────────────────────────────────────────────")
    if report:
        for line in report:
            print(f"  {line}")
    else:
        print("  No new data found.")

    if not upsert_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
