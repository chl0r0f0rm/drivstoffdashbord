# Handoff til Claude Cowork — bygg Power Automate-flyten

**Til:** Claude Cowork  
**Fra:** Drivstoff-index / BAF-prosjekt  
**Oppdatert:** 2026-07-06  
**Status:** GitHub Actions kjører OK. PAT er lagt inn lokalt. **Cowork skal nå bygge PA-flyten.**

---

## Hva du skal gjøre (kort)

Bygg en **Scheduled cloud flow** som:

1. Henter `data/baf_latest.json` fra privat GitHub-repo via HTTP + PAT
2. Parser JSON (ingen HTML, ingen Azure)
3. Upserter 6 rader til Excel-tabell `BAF` på SharePoint
4. Sender e-post ved feil og ved prisendringer

**Steg-for-steg med alle uttrykk:** `baf/docs/02_Power_Automate_bygg.md` — følg den som fasit.

---

## Arkitektur (gjeldende — ikke Azure)

```
GitHub Actions (dag 3, 04:00 UTC)     Power Automate (dag 3, 07:00)        SharePoint              Power BI
────────────────────────────────     ─────────────────────────────        ──────────              ────────
baf/fetch_baf.py                     1. Recurrence
  → data/baf_latest.json  ──HTTP──▶  2. HTTP + PAT → GitHub API
  (6 rader, begge rederier)          3. Parse JSON
                                     4. Upsert per id  ──────────────▶   4. data_BAF.xlsx  ──▶  Dashboard
                                        5. E-post varsler                  tabell BAF
```

- **Parsing skjer i GitHub Actions** (Python). PA gjør **ikke** HTML-scraping.
- **Azure Function er avvist** (ingen admin-tilgang).
- **Repo forblir privat** — fine-grained PAT for lesing.

---

## Hemmeligheter — PAT

**Fil:** `baf/.pa-secrets.local` (finnes, fylt ut av bruker, **ikke i git**)

```
GITHUB_PAT=github_pat_...
```

**Cowork:** Les `GITHUB_PAT` fra filen. Bruk i HTTP-steg:

| Header | Verdi |
|--------|-------|
| `Authorization` | `Bearer ` + verdien fra `GITHUB_PAT` |
| `Accept` | `application/vnd.github.raw` |
| `X-GitHub-Api-Version` | `2022-11-28` |

**Aldri:** committ PAT, logg den i chat, eller eksporter flyt med token synlig.

---

## HTTP-steg (steg 3a)

| Felt | Verdi |
|------|-------|
| **Method** | GET |
| **URI** | `https://api.github.com/repos/chl0r0f0rm/drivstoffdashbord/contents/data/baf_latest.json?ref=main` |

**Parse JSON:** `body('HTTP')` — responsen er rå JSON (ikke base64).

**Forventet ved suksess:** `count: 6`, `errors: []`

---

## Flyt-navn og trigger

- **Navn:** `BAF – månedlig innhenting (Color Line + Fjord Line)`
- **Type:** Scheduled cloud flow
- **Recurrence:** Month, interval 1
- **Time zone:** `W. Europe Standard Time`
- **Start time:** `2026-08-03T07:00:00` (fyrer dag 3 hver måned kl. 07:00)

GitHub Actions oppdaterer JSON **dag 3 kl. 04:00 UTC** (~05:00–06:00 Oslo) — god margin før PA kl. 07:00.

---

## Variabler (steg 2)

| Name | Type | Value |
|------|------|-------|
| `varFailureEmail` | String | `andreas.celiussen@ngn.no` |
| `varUpdateDistro` | String | `andreas.celiussen@ngn.no` *(foreløpig; byttes til distribusjonsliste senere)* |
| `varChanged` | Boolean | `false` |
| `varChangeLog` | String | *(tom)* |

---

## SharePoint / Excel (bekreftet)

| Felt | Verdi |
|------|-------|
| **Site** | Nedstrøm |
| **Mappe** | `Arbeidsrom/Marked/26. Forretningsutvikling/1. Tender Datasett/` |
| **Fil** | `4. data_BAF.xlsx` |
| **Tabell** | `BAF` |

**Cowork må bekrefte full SharePoint-URL** med bruker ved første tilkobling (site-URL for Excel Online-connector).

### Excel-kolonner (10 stk)

| Kolonne | Type | Beskrivelse |
|---------|------|-------------|
| `id` | tekst | Upsert-nøkkel: `company\|route\|valid_from` |
| `company` | tekst | Color Line / Fjord Line |
| `route` | tekst | Strekning |
| `valid_from` | dato | Første dag i perioden |
| `valid_to` | dato | Siste dag i perioden |
| `period_label` | tekst | Rå periode-tekst fra kilde |
| `price_nok` | heltall | NOK per LM |
| `price_eur` | desimal | EUR per LM |
| `source_url` | tekst | Kilde-URL |
| `fetched_at` | datetime | UTC hentetidspunkt |

**Upsert-nøkkel:** `id` (ikke tre separate felt). Eksisterende rad → oppdater pris/periode/fetched_at. Ny rad → legg til alle 10 kolonner.

---

## JSON-kontrakt (fra `data/baf_latest.json`)

```json
{
  "count": 6,
  "fetched_at": "2026-07-06T09:49:27+00:00",
  "errors": [],
  "rows": [
    {
      "id": "Color Line|Oslo – Kiel|2026-07-01",
      "company": "Color Line",
      "route": "Oslo – Kiel",
      "valid_from": "2026-07-01",
      "valid_to": "2026-07-31",
      "period_label": "BAF Adjustment Fee 01.–31.07.2026 (NOK / LM)",
      "price_nok": 123,
      "price_eur": 11.1,
      "source_url": "https://www.colorline-cargo.com/services/baf-adjustments",
      "fetched_at": "2026-07-06T09:49:27+00:00"
    }
  ]
}
```

### Forventede 6 rader (juli 2026, verifisert)

| company | route | price_nok |
|---------|-------|-----------|
| Color Line | Oslo – Kiel | 123 |
| Color Line | Larvik – Hirtshals | 125 |
| Color Line | Kristiansand – Hirtshals | 125 |
| Fjord Line | Bergen/Stavanger–Hirtshals | 165 |
| Fjord Line | Kristiansand–Hirtshals | 139 |
| Fjord Line | Domestic route: Bergen–Stavanger | 53 |

**Fjord Line:** `price_nok`/`price_eur` er **BAF + ETS summert** — ingen ekstra PA-logikk.

**Parse JSON-schema:** se `baf/docs/02_Power_Automate_bygg.md` steg 3b.

---

## Flytstruktur (Scope Try + Catch)

Følg `baf/docs/02_Power_Automate_bygg.md` nøyaktig:

```
Recurrence
→ Initialize variable ×4
→ Scope «Try»
    → HTTP (GitHub API + PAT)
    → Parse JSON
    → Condition: count ≤ 0 → Terminate Failed
    → List rows present in a table (Excel)
    → Apply to each (rows)
        → Filter array på id
        → Condition: rad finnes?
            → Ja: oppdater hvis pris endret, Update a row
            → Nei: Add a row
    → Condition: errors ikke tom → delvis feil-e-post
→ Condition: varChanged → endringsvarsel-e-post
→ Scope «Catch» (run after: failed/skipped/timed out)
    → Feil-e-post til varFailureEmail
```

**Connectorer:** `HTTP` (premium), `Excel Online (Business)`, `Office 365 Outlook`.

---

## E-postvarsler

| Varsel | Når | Til |
|--------|-----|-----|
| Feilvarsel | HTTP-feil, 0 rader, Try-scope feiler | `varFailureEmail` |
| Delvis feil | `errors[]` ikke tom (én kilde nede) | `varFailureEmail` |
| Endringsvarsel | Ny rad eller endret `price_nok` | `varUpdateDistro` |

E-postemner og body-uttrykk: `baf/docs/02_Power_Automate_bygg.md` steg 3f, 4, 5.

---

## Viktig om prissammenligning

- **Color Line:** kun BAF
- **Fjord Line:** BAF + ETS summert i samme kolonne

Tallene er ikke direkte sammenlignbare på tvers av rederi. `period_label` viser hva som ligger bak.

---

## Testplan (kjør etter bygging)

| # | Test | Forventet |
|---|------|-----------|
| 1 | Testkjør flyten manuelt (Test → Manually) | Grønn; HTTP 200; Parse JSON `count: 6` |
| 2 | Sjekk `4. data_BAF.xlsx` | 6 rader, ingen duplikater |
| 3 | Kjør på nytt | Samme 6 rader oppdateres (ikke 12) |
| 4 | Endre `price_nok` manuelt i Excel, kjør igjen | Pris tilbake; endringsvarsel-e-post |
| 5 | Feil URI eller ugyldig PAT | Feil-e-post; flyt Failed |
| 6 | Verifiser Oslo–Kiel = 123, Bergen/Stavanger–Hirtshals = 165 | Stemmer |

Power BI-kobling etterpå: `baf/docs/03_Power_BI_og_testplan.md`

---

## Hva som allerede er ferdig (ikke bygg på nytt)

- [x] Python-fetcher Color Line + Fjord Line (`baf/fetch_baf.py`, `baf/baf_parser.py`)
- [x] GitHub Actions workflow `.github/workflows/fetch-baf.yml` — kjørt med suksess
- [x] `data/baf_latest.json` på `main` med 6 rader
- [x] Fine-grained PAT opprettet og lagt i `baf/.pa-secrets.local`
- [x] Excel-mal `4. data_BAF.xlsx` med tabell `BAF` (10 kolonner)
- [x] Byggeguide med alle PA-uttrykk (`baf/docs/02_Power_Automate_bygg.md`)

## Hva Cowork skal levere

1. **Ferdig Power Automate-flyt** (testet manuelt mot live JSON)
2. **Bekreftelse** at 6 rader ligger i SharePoint uten duplikater
3. **Kort notat** om eventuelle avvik fra guiden (f.eks. connector-navn)

## Åpent / trenger bruker senere

- [ ] Full SharePoint site-URL (bekreft ved Excel-tilkobling)
- [ ] Distribusjonsliste for `varUpdateDistro` (nå: andreas.celiussen@ngn.no)
- [ ] Power BI-rapport + refresh-plan

---

## Referanser

| Fil | Innhold |
|-----|---------|
| `baf/docs/02_Power_Automate_bygg.md` | **Fasit** — alle steg og uttrykk |
| `baf/docs/03_Power_BI_og_testplan.md` | Power BI + testplan |
| `baf/README_github.md` | PAT-oppsett, tidsplan Actions vs PA |
| `data/baf_latest.json` | Live JSON-kontrakt |
| `baf/.pa-secrets.local` | PAT (les, ikke committ) |

**Kilder (hentes av Actions, ikke PA):**
- Color Line: https://www.colorline-cargo.com/services/baf-adjustments
- Fjord Line: https://fjordline.com/nb/p/fjord-line-freight/fraktinformasjon
