# Handoff til Cursor — commit BAF-fetcher + kjør workflow

**Repo:** `chl0r0f0rm/drivstoffdashbord` (branch `main`)
**Mål:** Få den nye samlede BAF-fetcheren (Color Line + Fjord Line) inn i repoet, kjøre den én gang, og produsere `data/baf_latest.json` som Power Automate skal lese. Deretter rapportere tilbake URL-en så PA-flyten kan fullføres.

Kontekst: HTML-parsing i Power Automate er skjør, og Azure-deploy er blokkert (ingen admin/Cloud Shell). Derfor gjør GitHub Actions henting+parsing i ekte Python og skriver en JSON-fil; Power Automate leser den via HTTP og upserter til en Excel-tabell på SharePoint for Power BI.

---

## 1. Nye/oppdaterte filer (allerede lagt i arbeidstreet)

```
baf/
├─ baf_parser.py        # NY — parser Color Line (BAF) + Fjord Line (BAF+ETS summert), med tekst-fallback
├─ fetch_baf.py         # NY — kjøres av workflowen → skriver data/baf_latest.json
├─ requirements.txt     # NY — requests, beautifulsoup4, lxml
├─ README_github.md     # NY — forklaring + PA-URL
├─ docs/                # NY — 00_START_HER, 01_Azure (arkiv), 02_Power_Automate_bygg, 03_Power_BI_og_testplan
├─ fetch_colorline_baf.py   # eksisterende (referanse)
├─ test_colorline_baf.py    # eksisterende
└─ HANDOFF_POWER_AUTOMATE.md# eksisterende
.github/workflows/
└─ fetch-baf.yml        # NY — planlagt (dag 3, 04:00 UTC) + manuell; kjører fetch_baf.py, committer JSON
```

`fetch_baf.py` importerer `baf_parser.py` (samme mappe) — **begge må committes**.

## 2. Oppgaver for Cursor

- [ ] **Verifiser lokalt** (valgfritt, men anbefalt):
  ```bash
  pip install -r baf/requirements.txt
  python baf/fetch_baf.py
  cat data/baf_latest.json   # forvent "count": 6, "errors": []
  ```
  6 rader = 3 Color Line + 3 Fjord Line. Fjord Line-radene har BAF+ETS summert i `price_nok`/`price_eur`.

- [ ] **Håndter workflow-overlapp.** Den eksisterende `.github/workflows/fetch-baf-colorline.yml` henter kun Color Line → `data/colorline_baf.csv`. Nye `fetch-baf.yml` henter begge → `data/baf_latest.json` og erstatter den funksjonelt. Velg én:
  - Anbefalt: pensjonér den gamle (slett `fetch-baf-colorline.yml`, eller behold `colorline_baf.csv` hvis dashboardet fortsatt bruker den).
  - Eller behold begge bevisst.

- [ ] **Commit + push:**
  ```bash
  git add baf/baf_parser.py baf/fetch_baf.py baf/requirements.txt baf/README_github.md \
          baf/docs .github/workflows/fetch-baf.yml
  git commit -m "feat(baf): samlet fetcher (Color Line + Fjord Line) -> data/baf_latest.json"
  git push
  ```

- [ ] **Kjør workflowen én gang manuelt:** GitHub → repo → **Actions** → *Fetch BAF (Color Line + Fjord Line)* → **Run workflow**. Bekreft grønn kjøring og at `data/baf_latest.json` ble committet med 6 rader.

## 3. Tilgang for Power Automate (repoet er PRIVAT — valgt: fine-grained PAT)

- [x] **Alternativ A — Fine-grained PAT** (valgt)
- [ ] Alternativ B — Public JSON

**PAT-oppsett:** se `baf/README_github.md` (steg-for-steg).

**PA HTTP:**
```
GET https://api.github.com/repos/chl0r0f0rm/drivstoffdashbord/contents/data/baf_latest.json?ref=main
Authorization: Bearer <PAT>
Accept: application/vnd.github.raw
```

**Status:** GitHub Actions `fetch-baf.yml` kjørt med suksess → `data/baf_latest.json` har 6 rader på `main`.

## 4. Rapportér tilbake (for å fullføre PA-flyten)

Send tilbake:
1. Bekreftelse på at `data/baf_latest.json` finnes og har `"count": 6`.
2. Enten **PAT + API-URL** (valg A) eller **public raw-URL** (valg B).
3. Riktig branch hvis ikke `main`.

Da pekes PA-flytens HTTP-steg dit, og Parse JSON + upsert til SharePoint-Excel (`4. data_BAF.xlsx`, tabell `BAF`) + e-postvarsling fullføres.

## 5. JSON-skjema (kontrakt PA forventer)

```json
{
  "count": 6,
  "fetched_at": "2026-07-06T07:17:31+00:00",
  "errors": [],
  "rows": [
    { "id": "Color Line|Oslo – Kiel|2026-07-01", "company": "Color Line",
      "route": "Oslo – Kiel", "valid_from": "2026-07-01", "valid_to": "2026-07-31",
      "period_label": "BAF Adjustment Fee 01.–31.07.2026 (NOK / LM)",
      "price_nok": 123, "price_eur": 11.1,
      "source_url": "https://www.colorline-cargo.com/services/baf-adjustments",
      "fetched_at": "2026-07-06T07:17:31+00:00" }
  ]
}
```

`id = "<company>|<route>|<valid_from>"` er upsert-nøkkelen mot Excel-tabellen. Ikke endre feltnavn uten å si fra — PA-flyten er bygget mot akkurat disse.
