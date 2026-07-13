# Supabase — drivstoffdashbord + BAF

## Produksjon (brukes av GitHub Actions)

| Fil | Formål |
|-----|--------|
| `fetch_prices.py` | Henter drivstoffpriser (SE/NO/DK) → CSV + Supabase |

**Tabeller (drivstoff):** `price_data`, `daily_price_data`, `price_source_sync`  
**Tabeller (BAF):** `baf_data`, `baf_price_history`, `baf_fetch_log`

## Migrasjoner (SQL)

| Fil | Innhold |
|-----|---------|
| `migrations/migration.sql` | Drivstoff-schema + seed-data |
| `migrations/baf_migration.sql` | BAF-tabeller |

Kjør i Supabase SQL Editor, eller bruk bootstrap-scriptene under.

## Bootstrap (engangs, manuell)

| Script | Formål |
|--------|--------|
| `bootstrap/run_migration.py` | Opprett + seed `price_data` |
| `bootstrap/create_daily_table.py` | Opprett `daily_price_data` |
| `bootstrap/create_baf_tables.py` | Opprett BAF-tabeller |
| `bootstrap/run_baf_seed_sql.py` | Kjør historisk BAF-seed fra `migrations/seeds/*.sql` |

Krever `SUPABASE_ACCESS_TOKEN` (personal access token fra supabase.com).

```bash
set SUPABASE_ACCESS_TOKEN=din_token
python supabase/bootstrap/create_baf_tables.py
```

## Viktig

- **Ikke flytt** `fetch_prices.py` uten å oppdatere alle price-workflows.
- Bootstrap-scriptene påvirker **ikke** GitHub Actions automatisk.
