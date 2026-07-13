"""
BAF-parser for ferjefrakt — Color Line og Fjord Line.

Color Line: kun BAF. Fjord Line: BAF + ETS summeres til ett tall (price_nok / price_eur).

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

FJ_PERIOD_DASH_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.\s*[–\-]\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})")
FJ_PERIOD_TIL_RE = re.compile(
    r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s+til\s+(\d{1,2})\.(\d{1,2})\.(\d{2,4})",
    re.IGNORECASE,
)
# "116 NOK (10,7 €/80 DKK)"  -> NOK, deretter euro FØR €-tegnet
FJ_PRICE_RE = re.compile(r"(\d+)\s*NOK\s*\(\s*([\d,\.]+)\s*€", re.IGNORECASE)


# --------------------------------------------------------------- fellesnytte
def _eur(raw: str) -> float:
    return float(raw.strip().replace(" ", "").replace(",", "."))


def _year(yy: str) -> int:
    y = int(yy)
    return y + 2000 if y < 100 else y


FJORD_ROUTE_ORDER = (
    "Bergen/Stavanger–Hirtshals",
    "Kristiansand–Hirtshals",
    "Domestic route: Bergen–Stavanger",
)


def _match_fj_period(line: str) -> re.Match[str] | None:
    match = FJ_PERIOD_DASH_RE.search(line)
    if match:
        return match
    return FJ_PERIOD_TIL_RE.search(line)


def _fj_period_bounds(match: re.Match[str]) -> tuple[str, str, str]:
    groups = match.groups()
    if len(groups) == 5:
        day_from, month_from, day_to, month_to, year_part = groups
    else:
        day_from, month_from, year_part, day_to, month_to, _year_end = groups
    year = _year(year_part)
    valid_from = f"{year}-{int(month_from):02d}-{int(day_from):02d}"
    valid_to = f"{year}-{int(month_to):02d}-{int(day_to):02d}"
    period_label = (
        f"BAF+ETS {int(day_from):02d}.{int(month_from):02d}.-"
        f"{int(day_to):02d}.{int(month_to):02d}.{str(year)[2:]} (per metre)"
    )
    return valid_from, valid_to, period_label


def _fj_route_name(raw_route: str, section: str, index: int) -> str:
    cleaned = raw_route.rstrip(":").strip()
    low = cleaned.lower()
    if cleaned and "nok" not in low and "adjustment" not in low and "surcharge" not in low:
        return cleaned
    if index < len(FJORD_ROUTE_ORDER):
        return FJORD_ROUTE_ORDER[index]
    return cleaned


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
    baf_index = 0
    ets_index = 0

    for ln in lines:
        low = ln.lower()
        if "baf adjustment" in low:
            section = "BAF"
            baf_index = 0
            match = _match_fj_period(ln)
            if match:
                period = match
            prev = ln
            continue
        if "ets surcharge" in low:
            section = "ETS"
            ets_index = 0
            match = _match_fj_period(ln)
            if match and not period:
                period = match
            prev = ln
            continue
        pm = FJ_PRICE_RE.search(ln)
        if pm and section:
            index = baf_index if section == "BAF" else ets_index
            route = _fj_route_name(prev, section, index)
            if route:
                data = (int(pm.group(1)), _eur(pm.group(2)))
                if section == "BAF":
                    baf[route] = data
                    baf_index += 1
                else:
                    ets[route] = data
                    ets_index += 1
        prev = ln

    if not period or not baf:
        raise ValueError("Fjord Line: fant ikke BAF-periode eller -rader (struktur kan ha endret seg)")

    valid_from, valid_to, period_label = _fj_period_bounds(period)

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
