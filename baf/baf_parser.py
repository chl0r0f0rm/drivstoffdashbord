"""
BAF-parser for ferjefrakt — Color Line og Fjord Line.

Color Line: kun BAF (kilde til sannhet = fetch_colorline_baf.py fra repoet).
Fjord Line: BAF + ETS summeres til ett tall (price_nok / price_eur), etter ønske.

Alle parsere har en tekst-basert fallback slik at små strukturendringer på
nettsidene ikke stopper innhentingen.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

USER_AGENT = "NG-BAF-fetcher/1.0"

# ---------------------------------------------------------------- Color Line
COLORLINE_URL = "https://www.colorline-cargo.com/services/baf-adjustments"
COLORLINE_COMPANY = "Color Line"

CL_PERIOD_RE = re.compile(r"(\d{1,2})\.\s*[–\-]\s*(\d{1,2})\.(\d{2})\.(\d{4})")
CL_PRICE_RE = re.compile(r"(\d+)\s*NOK\s*\(\s*€\s*([\d,\.]+)\s*\)", re.IGNORECASE)

# ---------------------------------------------------------------- Fjord Line
FJORD_URL = "https://fjordline.com/nb/p/fjord-line-freight/fraktinformasjon"
FJORD_COMPANY = "Fjord Line"

# "01.07.-31.07.26"  ->  day.month.-day.month.yy
FJ_PERIOD_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.\s*[–\-]\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})")
# "116 NOK (10,7 €/80 DKK)"  -> NOK, deretter euro FØR €-tegnet
FJ_PRICE_RE = re.compile(r"(\d+)\s*NOK\s*\(\s*([\d,\.]+)\s*€", re.IGNORECASE)


# --------------------------------------------------------------- fellesnytte
def _eur(raw: str) -> float:
    return float(raw.strip().replace(" ", "").replace(",", "."))


def _year(yy: str) -> int:
    y = int(yy)
    return y + 2000 if y < 100 else y


def fetch_html(url: str, session: requests.Session | None = None) -> str:
    client = session or requests.Session()
    resp = client.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.text


def _row(company, route, valid_from, valid_to, period_label,
         price_nok, price_eur, source_url, fetched_at):
    return {
        "id": f"{company}|{route}|{valid_from}",
        "company": company,
        "route": route,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "period_label": period_label,
        "price_nok": price_nok,
        "price_eur": price_eur,
        "source_url": source_url,
        "fetched_at": fetched_at.replace(microsecond=0).isoformat(),
    }


# =============================================================== Color Line
def _cl_period(label: str):
    m = CL_PERIOD_RE.search(label)
    if not m:
        raise ValueError(f"Color Line: kunne ikke tolke periode fra {label!r}")
    d_from, d_to, month, year = m.groups()
    return (f"{year}-{month.zfill(2)}-{int(d_from):02d}",
            f"{year}-{month.zfill(2)}-{int(d_to):02d}", label.strip())


def _cl_price(text: str):
    m = CL_PRICE_RE.search(text)
    if not m:
        raise ValueError(f"Color Line: kunne ikke tolke pris fra {text!r}")
    return int(m.group(1)), _eur(m.group(2))


def _cl_structured(html: str, fetched_at: datetime) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    for section in soup.select("section.modStructuredinfo"):
        header = section.select_one(".mod-hd h2, .mod-hd")
        if not header:
            continue
        htext = header.get_text(" ", strip=True)
        if "BAF Adjustment Fee" not in htext:
            continue
        valid_from, valid_to, label = _cl_period(htext)
        for row in section.select("div.row"):
            r_el, p_el = row.select_one("div.label"), row.select_one("div.text")
            if not r_el or not p_el:
                continue
            route = r_el.get_text(" ", strip=True)
            ptext = p_el.get_text(" ", strip=True)
            if not route or "NOK" not in ptext:
                continue
            nok, eur = _cl_price(ptext)
            rows.append(_row(COLORLINE_COMPANY, route, valid_from, valid_to,
                             label, nok, eur, COLORLINE_URL, fetched_at))
    return rows


def _cl_fallback(html: str, fetched_at: datetime) -> list[dict]:
    lines = [l.strip() for l in BeautifulSoup(html, "lxml").get_text("\n").split("\n") if l.strip()]
    header = next((l for l in lines if "BAF Adjustment Fee" in l and CL_PERIOD_RE.search(l)), None)
    if not header:
        return []
    valid_from, valid_to, label = _cl_period(header)
    rows: list[dict] = []
    for i, ln in enumerate(lines):
        m = CL_PRICE_RE.search(ln)
        if not m:
            continue
        route = lines[i - 1].strip() if i > 0 else ""
        if not route or "NOK" in route:
            continue
        rows.append(_row(COLORLINE_COMPANY, route, valid_from, valid_to,
                         label, int(m.group(1)), _eur(m.group(2)), COLORLINE_URL, fetched_at))
    return rows


def parse_colorline(html: str, fetched_at: datetime | None = None) -> list[dict]:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    rows = _cl_structured(html, fetched_at) or _cl_fallback(html, fetched_at)
    if not rows:
        raise ValueError("Color Line: ingen rader parset (struktur kan ha endret seg)")
    return rows


def fetch_colorline() -> list[dict]:
    return parse_colorline(fetch_html(COLORLINE_URL))


# =============================================================== Fjord Line
def parse_fjordline(html: str, fetched_at: datetime | None = None) -> list[dict]:
    """BAF og ETS summeres per strekning til ett tall."""
    fetched_at = fetched_at or datetime.now(timezone.utc)
    lines = [l.strip() for l in BeautifulSoup(html, "lxml").get_text("\n").split("\n") if l.strip()]

    section = None
    period = None
    prev = ""
    baf: dict[str, tuple[int, float]] = {}
    ets: dict[str, tuple[int, float]] = {}

    for ln in lines:
        low = ln.lower()
        if "baf adjustment" in low:
            section = "BAF"
            m = FJ_PERIOD_RE.search(ln)
            if m:
                period = m
            prev = ln
            continue
        if "ets surcharge" in low:
            section = "ETS"
            m = FJ_PERIOD_RE.search(ln)
            if m and not period:
                period = m
            prev = ln
            continue
        pm = FJ_PRICE_RE.search(ln)
        if pm and section:
            route = prev.rstrip(":").strip()
            if route and "NOK" not in route:
                data = (int(pm.group(1)), _eur(pm.group(2)))
                (baf if section == "BAF" else ets)[route] = data
        prev = ln

    if not period or not baf:
        raise ValueError("Fjord Line: fant ikke BAF-periode eller -rader (struktur kan ha endret seg)")

    d_from, m_from, d_to, m_to, yy = period.groups()
    year = _year(yy)
    valid_from = f"{year}-{int(m_from):02d}-{int(d_from):02d}"
    valid_to = f"{year}-{int(m_to):02d}-{int(d_to):02d}"
    period_label = (f"BAF+ETS {int(d_from):02d}.{int(m_from):02d}.-"
                    f"{int(d_to):02d}.{int(m_to):02d}.{str(year)[2:]} (per metre)")

    rows: list[dict] = []
    for route, (b_nok, b_eur) in baf.items():
        e_nok, e_eur = ets.get(route, (0, 0.0))
        rows.append(_row(FJORD_COMPANY, route, valid_from, valid_to, period_label,
                         b_nok + e_nok, round(b_eur + e_eur, 2), FJORD_URL, fetched_at))
    return rows


def fetch_fjordline() -> list[dict]:
    return parse_fjordline(fetch_html(FJORD_URL))


# =============================================================== samlet
CARRIERS = [
    ("Color Line", fetch_colorline),
    ("Fjord Line", fetch_fjordline),
]


def fetch_all() -> tuple[list[dict], list[dict]]:
    """Returnerer (rows, errors). Én kildes feil stopper ikke de andre."""
    rows: list[dict] = []
    errors: list[dict] = []
    for name, fn in CARRIERS:
        try:
            rows.extend(fn())
        except Exception as err:  # noqa: BLE001
            errors.append({"company": name, "error": str(err)})
    return rows, errors
