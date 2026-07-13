# BAF — Bunker Adjustment Factor (Color Line + Fjord Line)

Automatisk innhenting via GitHub Actions → `baf_data.csv` → Power Automate → SharePoint → Power BI.

## Aktive filer

| Fil | Formål |
|-----|--------|
| `baf_parser.py` | Parser for Color Line og Fjord Line |
| `fetch_baf.py` | Kjøres av GitHub Actions — scrape + oppdater CSV |
| `baf_csv.py` | Les/skriv `baf_data.csv` (kolonnekontrakt for Power BI) |
| `seed_rows.py` | Merge historiske rader fra JSON inn i CSV |
| `seeds/` | Historiske BAF JSON-filer (Wayback Machine) |
| `requirements.txt` | Python-avhengigheter |
| `test_baf_parser.py` | Enhetstest for Color Line-parser |

## Dokumentasjon

| Dokument | Innhold |
|----------|---------|
| `../BAF-pipeline-handoff.md` | **Primær** — GitHub → SharePoint → Power BI |
| `docs/02_Power_Automate_bygg.md` | Power Automate (JSON-tilnærming, arkivert) |
| `docs/03_Power_BI_og_testplan.md` | Testplan |
| `docs/archive/` | Utdaterte handoffs |

## Arkitektur

```
GitHub Actions (dag 15 + siste dag i mnd, 04:00 UTC)
  → fetch_baf.py
  → baf_data.csv (repo-roten, git-snapshot)
  → Power Automate (daglig)
  → SharePoint
  → Power BI dataset "Tender Downstream"
```

## CSV-kontrakt

Kolonnene må holdes stabile — Power Query avhenger av dem:

`id, company, route, valid_from, valid_to, period_label, price_nok, price_eur, source_url, first_seen_at, updated_at`

Ved første kjøring uten eksisterende CSV bootstrappes historikk fra `seeds/*.json`. Nye scrapes merges inn på `id`.

## Lokal test

```bash
pip install -r baf/requirements.txt
python baf/fetch_baf.py
python baf/test_baf_parser.py
```

## Seed historikk manuelt

```bash
python baf/seed_rows.py baf/seeds/colorline_2026-04.json
```

Eller via GitHub Actions → **Seed BAF historical data**.
