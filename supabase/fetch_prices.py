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
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from collections import defaultdict

import requests
from bs4 import BeautifulSoup

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

MONTH_MAP_DK = {
    "januar": "01", "februar": "02", "marts": "03", "april": "04",
    "maj": "05", "juni": "06", "juli": "07", "august": "08",
    "september": "09", "oktober": "10", "november": "11", "december": "12",
}
MONTH_HEADER_DK = re.compile(
    r"^(\w+)\s+(20\d{2})\s+(?:ekskl|inkl)",
    re.IGNORECASE,
)
DK_MIN_MONTH = "2022-01"
DK_MIN_DATE = "2022-01-01"


# ── Supabase ──────────────────────────────────────────────────────────────────

def compute_monthly_from_daily(sources):
    """Fetches all daily_price_data rows for given sources, returns monthly averages."""
    if not sources:
        return []
    source_filter = ",".join(f"source.eq.{s}" for s in sources)
    url = (
        f"{SUPABASE_URL}/rest/v1/daily_price_data"
        f"?select=source,date,diesel,hvo"
        f"&or=({source_filter})"
        f"&order=date.asc"
        f"&limit=10000"
    )
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    if not resp.ok:
        print(f"  compute_monthly_from_daily: fetch failed {resp.status_code}")
        return []
    rows = resp.json()
    monthly = defaultdict(lambda: {"diesel": [], "hvo": []})
    for row in rows:
        month = row["date"][:7]
        key = (row["source"], month)
        if row.get("diesel") is not None:
            monthly[key]["diesel"].append(float(row["diesel"]))
        if row.get("hvo") is not None:
            monthly[key]["hvo"].append(float(row["hvo"]))
    result = []
    for (source, month), vals in sorted(monthly.items()):
        diesel_avg = round(sum(vals["diesel"]) / len(vals["diesel"]), 4) if vals["diesel"] else None
        hvo_avg    = round(sum(vals["hvo"])    / len(vals["hvo"]),    4) if vals["hvo"]    else None
        result.append({"source": source, "month": month, "diesel": diesel_avg, "hvo": hvo_avg})
    print(f"  compute_monthly_from_daily: {len(result)} month-rows from {len(rows)} daily rows")
    return result


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


def merge_csv_rows(filepath, new_rows, fieldnames, key_column):
    merged = {}
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as file_handle:
            for row in csv.DictReader(file_handle):
                merged[row[key_column]] = row
    for row in new_rows:
        merged[row[key_column]] = row
    with open(filepath, "w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(merged.keys()):
            writer.writerow(merged[key])
    return len(new_rows)


def write_csv_full(filepath, rows, fieldnames, key_column):
    with open(filepath, "w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: item[key_column]):
            writer.writerow(row)
    return len(rows)


def supabase_delete_before(source, table, date_column, before_value):
    if not SUPABASE_SERVICE_KEY:
        print(f"  Skip delete (no service key): {table} {source} < {before_value}")
        return True
    url = (
        f"{SUPABASE_URL}/rest/v1/{table}"
        f"?source=eq.{source}&{date_column}=lt.{before_value}"
    )
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    resp = requests.delete(url, headers=headers, timeout=30)
    if resp.ok:
        print(f"  Deleted {table} rows for {source} before {before_value}")
    else:
        print(f"  Delete failed ({table} {source}): {resp.status_code} {resp.text[:200]}")
    return resp.ok


def gap_fill_daily_rows(latest_row, existing_dates):
    """Fill missing calendar days from last stored date through today with current price."""
    today = date.fromisoformat(latest_row["date"])
    if existing_dates:
        last_stored = max(date.fromisoformat(d) for d in existing_dates)
        start = last_stored + timedelta(days=1)
    else:
        start = today
    if start > today:
        return []
    filled = []
    current = start
    while current <= today:
        filled.append({
            "date": str(current),
            "diesel": latest_row["diesel"],
            "hvo": latest_row.get("hvo"),
        })
        current += timedelta(days=1)
    return filled


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
        import xlrd
    except ImportError:
        print("  xlrd not installed — skipping Preem SE")
        return [], []
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
    try:
        import xlrd
    except ImportError:
        print("  xlrd not installed — skipping Circle K SE")
        return [], []
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

CK_DK_HIST_URL = "https://www.circlek.dk/erhverv/braendstof/historiskepriser"

STATION_PRICE_PATTERN = re.compile(r"\d+,\d+")


def _find_dk_pdf_url(soup, vat_type):
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        text = anchor.get_text(strip=True).lower()
        if ".pdf" not in href.lower():
            continue
        if "afgifter" in text:
            continue
        if vat_type == "ekskl" and "ekskl" in text and "moms" in text:
            return href if href.startswith("http") else f"https://www.circlek.dk{href}"
        if vat_type == "inkl" and "inkl" in text and "moms" in text:
            return href if href.startswith("http") else f"https://www.circlek.dk{href}"
    return None


def _extract_dk_month_from_page(text):
    for line in text.split("\n"):
        header_match = MONTH_HEADER_DK.match(line.strip())
        if not header_match:
            continue
        month_key = header_match.group(1).lower()
        year = header_match.group(2)
        if month_key in MONTH_MAP_DK:
            return f"{year}-{MONTH_MAP_DK[month_key]}"
    return None


def _parse_dk_station_prices(line):
    numbers = STATION_PRICE_PATTERN.findall(line)
    if len(numbers) < 6:
        return None, None
    diesel = round(float(numbers[2].replace(",", ".")), 4)
    hvo = round(float(numbers[5].replace(",", ".")), 4)
    return diesel, hvo


def _parse_ck_dk_pdf(pdf_bytes, min_month=DK_MIN_MONTH):
    try:
        import pdfplumber
    except ImportError:
        print("  pdfplumber not installed — skipping DK PDF")
        return [], []

    monthly_rows = []
    daily_rows = []
    current_month = None

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            page_month = _extract_dk_month_from_page(text)
            if page_month:
                current_month = page_month

            if not current_month or current_month < min_month:
                continue

            year, month = current_month.split("-")
            for line in text.split("\n"):
                stripped = line.strip()
                if re.search(r"\bsnit\b", stripped, re.IGNORECASE):
                    diesel, hvo = _parse_dk_station_prices(stripped)
                    if diesel:
                        monthly_rows.append({
                            "month": current_month,
                            "diesel_avg": diesel,
                            "hvo_avg": hvo,
                        })
                    continue

                day_match = re.match(r"^(\d{1,2})\s", stripped)
                if not day_match:
                    continue
                diesel, hvo = _parse_dk_station_prices(stripped)
                if not diesel:
                    continue
                day = int(day_match.group(1))
                try:
                    date_value = date(int(year), int(month), day).isoformat()
                except ValueError:
                    continue
                if date_value < DK_MIN_DATE:
                    continue
                daily_rows.append({
                    "date": date_value,
                    "diesel": diesel,
                    "hvo": hvo,
                })

    monthly_by_month = {row["month"]: row for row in monthly_rows}
    daily_by_date = {row["date"]: row for row in daily_rows}
    monthly_rows = [monthly_by_month[key] for key in sorted(monthly_by_month)]
    daily_rows = [daily_by_date[key] for key in sorted(daily_by_date)]
    return monthly_rows, daily_rows


def fetch_ck_dk():
    print("\n── Circle K DK ──────────────────────────────────────────────────────")
    try:
        page_resp = requests.get(
            CK_DK_HIST_URL,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        page_resp.raise_for_status()
    except requests.RequestException as error:
        print(f"  Failed to load Circle K DK page: {error}")
        return {}

    soup = BeautifulSoup(page_resp.text, "html.parser")
    results = {}

    for vat_type, source_key in (("ekskl", "DK_ck"), ("inkl", "DK_ck_inkl")):
        pdf_url = _find_dk_pdf_url(soup, vat_type)
        if not pdf_url:
            print(f"  No {vat_type} moms PDF found")
            continue

        print(f"  {source_key} PDF: {pdf_url}")
        try:
            resp = requests.get(pdf_url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except requests.RequestException as error:
            print(f"  PDF download failed ({source_key}): {error}")
            continue

        monthly_rows, daily_rows = _parse_ck_dk_pdf(resp.content)
        print(
            f"  {source_key}: {len(monthly_rows)} months, {len(daily_rows)} daily rows"
            + (f" ({daily_rows[0]['date']} – {daily_rows[-1]['date']})" if daily_rows else "")
        )
        results[source_key] = {"monthly": monthly_rows, "daily": daily_rows}

    return results


# ── Circle K SE (daglig listpris) ────────────────────────────────────────────

CK_SE_DAILY_URL = "https://www.circlek.se/foretag/drivmedel/priser"

SE_DAILY_PRODUCT_MAP = {
    "miles diesel": "diesel",
    "hvo100":       "hvo",
}


def fetch_ck_se_daily():
    print("\n── Circle K SE (daglig listpris) ────────────────────────────────────")
    try:
        resp = requests.get(
            CK_SE_DAILY_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"}
        )
        resp.raise_for_status()
    except requests.RequestException as error:
        print(f"  Failed to load page: {error}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    prices = {}

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            cell_texts = [c.get_text(" ", strip=True) for c in cells]
            row_text = " ".join(cell_texts).lower()

            matched_product = None
            for product_key, product_name in SE_DAILY_PRODUCT_MAP.items():
                if product_key in row_text:
                    matched_product = product_name
                    break

            if not matched_product:
                continue

            for cell_text in cell_texts:
                m = re.search(r"(\d+)[,.](\d+)", cell_text)
                if m:
                    val = float(m.group(1) + "." + m.group(2))
                    if 15 < val < 35:  # SEK/L range for diesel/HVO
                        prices[matched_product] = round(val, 4)
                        break

    if not prices.get("diesel"):
        print("  Could not find diesel price on Circle K SE page")
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = {"date": today, "diesel": prices.get("diesel"), "hvo": prices.get("hvo")}
    print(f"  Diesel: {row['diesel']} SEK/L  HVO: {row.get('hvo')} SEK/L  (lagres som {today})")
    return [row]


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

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = {
        "date":   today,
        "diesel": prices.get("diesel"),
        "hvo":    prices.get("hvo"),
    }
    print(f"  Diesel: {row['diesel']} NOK/L  HVO: {row['hvo']} NOK/L  (gjeldende fra {date_effective or '?'}, lagres som {today})")
    return [row]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # FETCH_MODE=weekly  → Preem SE, Circle K SE (monthly XLS/Excel sources)
    # FETCH_MODE=daily   → Circle K DK, Circle K NO (daily-updated sources)
    # FETCH_MODE=all     → everything (default)
    mode = os.environ.get("FETCH_MODE", "all").lower()
    run_weekly = mode in ("weekly", "all")
    run_daily  = mode in ("daily",  "all")
    print(f"FETCH_MODE={mode}  (weekly={run_weekly}, daily={run_daily})")

    os.makedirs(DATA_DIR, exist_ok=True)

    monthly_upsert = []
    daily_upsert   = []
    report = []
    synced_sources = []

    if run_weekly:
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
        # SE_preem daily rows from XLS are synthetic — not stored in daily_price_data

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
            report.append(f"SE_ck daily (XLS): +{n} days")
            daily_upsert += [
                {"source": "SE_ck", "date": r["date"], "diesel": r["diesel"], "hvo": r["hvo"]}
                for r in ck_se_daily
            ]

    if run_daily:
        dk_results = fetch_ck_dk()
        for source_key, suffix in (("DK_ck", ""), ("DK_ck_inkl", "_inkl")):
            dk_data = dk_results.get(source_key, {})
            ck_dk_monthly = dk_data.get("monthly", [])
            ck_dk_daily = dk_data.get("daily", [])
            if not ck_dk_monthly and not ck_dk_daily:
                continue

            synced_sources.append(source_key)
            supabase_delete_before(source_key, "price_data", "month", DK_MIN_MONTH)
            supabase_delete_before(source_key, "daily_price_data", "date", DK_MIN_DATE)

            if ck_dk_monthly:
                monthly_path = os.path.join(DATA_DIR, f"circklek_DK_månedlig{suffix}.csv")
                write_csv_full(monthly_path, ck_dk_monthly, ["month", "diesel_avg", "hvo_avg"], "month")
                report.append(
                    f"{source_key}: {len(ck_dk_monthly)} months (latest: {ck_dk_monthly[-1]['month']})"
                )
                monthly_upsert += [
                    {"source": source_key, "month": r["month"], "diesel": r["diesel_avg"], "hvo": r["hvo_avg"]}
                    for r in ck_dk_monthly
                ]

            if ck_dk_daily:
                daily_path = os.path.join(DATA_DIR, f"circklek_DK_daglig{suffix}.csv")
                write_csv_full(daily_path, ck_dk_daily, ["date", "diesel", "hvo"], "date")
                report.append(
                    f"{source_key} daily: {len(ck_dk_daily)} rows (through {ck_dk_daily[-1]['date']})"
                )
                daily_upsert += [
                    {"source": source_key, "date": r["date"], "diesel": r["diesel"], "hvo": r["hvo"]}
                    for r in ck_dk_daily
                ]

    ck_se_live = fetch_ck_se_daily() if run_daily else []
    if ck_se_live:
        se_live_csv = os.path.join(DATA_DIR, "circklek_SE_daglig.csv")
        ck_se_live = gap_fill_daily_rows(
            ck_se_live[0], read_existing_keys(se_live_csv, "date")
        )
    if ck_se_live:
        if "SE_ck" not in synced_sources:
            synced_sources.append("SE_ck")
        n = append_csv(se_live_csv, ck_se_live, ["date", "diesel", "hvo"], "date")
        report.append(f"SE_ck daily live: +{n} rows (through {ck_se_live[-1]['date']})")
        daily_upsert += [
            {"source": "SE_ck", "date": r["date"], "diesel": r["diesel"], "hvo": r["hvo"]}
            for r in ck_se_live
        ]

    ck_no_daily = fetch_ck_no() if run_daily else []
    if ck_no_daily:
        no_csv = os.path.join(DATA_DIR, "circklek_NO_daglig.csv")
        ck_no_daily = gap_fill_daily_rows(
            ck_no_daily[0], read_existing_keys(no_csv, "date")
        )
    if ck_no_daily:
        synced_sources.append("NO_ck")
        n = append_csv(no_csv, ck_no_daily, ["date", "diesel", "hvo"], "date")
        report.append(f"NO_ck: +{n} rows (through {ck_no_daily[-1]['date']})")
        daily_upsert += [
            {"source": "NO_ck", "date": r["date"], "diesel": r["diesel"], "hvo": r["hvo"]}
            for r in ck_no_daily
        ]

    print("\n── Supabase upsert ───────────────────────────────────────────────────")
    upsert_ok = True
    upsert_ok = supabase_upsert(monthly_upsert, table="price_data") and upsert_ok
    upsert_ok = supabase_upsert(daily_upsert,   table="daily_price_data") and upsert_ok

    # Compute true monthly averages from all accumulated daily data for web-scraped sources
    daily_sources = [s for s in ("NO_ck",) if s in synced_sources]
    if daily_sources:
        print("\n── Monthly averages from daily data ──────────────────────────────────")
        monthly_from_daily = compute_monthly_from_daily(daily_sources)
        if monthly_from_daily:
            upsert_ok = supabase_upsert(monthly_from_daily, table="price_data") and upsert_ok
            report.append(f"Monthly averages recomputed: {', '.join(daily_sources)}")
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
