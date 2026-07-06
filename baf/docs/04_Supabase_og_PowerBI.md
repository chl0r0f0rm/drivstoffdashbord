# 4 — Supabase + Power BI (uten Excel)

Automatisk pipeline med historikk — erstatter Power Automate + SharePoint Excel.

## Arkitektur

```
GitHub Actions (dag 3, 04:00 UTC)
  → baf/fetch_baf.py (scrape Color Line + Fjord Line)
  → data/baf_latest.json (git-snapshot)
  → Supabase:
       baf_data           — gjeldende sats per strekning/periode
       baf_price_history  — alle prisendringer over tid
       baf_fetch_log      — logg per kjøring

Power BI
  → PostgreSQL-connector mot Supabase
  → planlagt oppdatering i skyen (ingen gateway)
```

## Tabeller

### `baf_data` (gjeldende)
Én rad per `id` = `company|route|valid_from`. Nye måneder gir nye rader — gamle perioder beholdes som historikk.

| Kolonne | Beskrivelse |
|---------|-------------|
| `id` | Primærnøkkel |
| `company`, `route` | Rederi og strekning |
| `valid_from`, `valid_to` | Gyldighetsperiode |
| `price_nok`, `price_eur` | Sats (Fjord Line = BAF+ETS summert) |
| `first_seen_at` | Første gang vi så denne perioden |
| `updated_at` | Sist oppdatert |

### `baf_price_history` (prisendringer)
Ny rad når en sats oppdages første gang, eller når `price_nok`/`price_eur` endres innen samme periode.

### `baf_fetch_log` (kjørelogg)
Én rad per GitHub Actions-kjøring. `status`: `ok` | `partial` | `failed`.

## Engangsoppsett

### 1. Opprett tabeller i Supabase

**Alternativ A — SQL Editor** (enklest):
Lim inn innholdet fra `supabase/baf_migration.sql` i Supabase → SQL Editor → Run.

**Alternativ B — script:**
```bash
set SUPABASE_ACCESS_TOKEN=din_personal_access_token
python supabase/create_baf_tables.py
```

### 2. GitHub secret (allerede i bruk for drivstoff)
Repo → Settings → Secrets → `SUPABASE_SERVICE_KEY` (service_role key).

Workflow `fetch-baf.yml` bruker denne automatisk.

### 3. Test lokalt
```bash
pip install -r baf/requirements.txt
set SUPABASE_URL=https://fnkdbuqsschkvpzeumbz.supabase.co
set SUPABASE_SERVICE_KEY=din_service_role_key
python baf/fetch_baf.py
```

Forvent: 6 rader skrevet + «Supabase: 6 rad(er) synket».

## Power BI

1. **Power BI Desktop** → **Hent data** → **PostgreSQL database**
2. Server: `aws-0-eu-central-1.pooler.supabase.com` (sjekk Connection string i Supabase → Project Settings → Database)
3. Database: `postgres`
4. Velg tabellene `baf_data` og `baf_price_history`
5. Datotyper: `valid_from`/`valid_to` = Dato, `price_eur` = desimal
6. Publiser → sett planlagt oppdatering (f.eks. daglig 08:00)

### Forslag til rapporter

- **Gjeldende satser:** `baf_data` filtrert på `valid_from = MAX(valid_from)` per `route`
- **Prisutvikling:** `baf_price_history` over tid per `baf_id`
- **MoM-sammenligning:** `baf_data` gruppert på `valid_from`
- **Kjørestatus:** `baf_fetch_log` siste rad

## Automatisk kjøring

| Hva | Når |
|-----|-----|
| Scrape + Supabase-sync | Dag 3 kl. 04:00 UTC (GitHub Actions) |
| Manuell kjøring | Actions → *Fetch BAF* → Run workflow |
| Power BI refresh | Etter eget valg (f.eks. daglig) |

## Feilsøking

| Symptom | Løsning |
|---------|---------|
| `relation "baf_data" does not exist` | Kjør `baf_migration.sql` |
| `Upsert baf_data feilet: 401` | Sjekk `SUPABASE_SERVICE_KEY` i GitHub secrets |
| 0 rader, rød workflow | Sjekk `baf_fetch_log` og Actions-logg |
| Power BI tom | Sjekk RLS-policy (public read er satt) og refresh-credentials |
