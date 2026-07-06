# 1 — Deploye Azure Function

Funksjonen henter og parser BAF, og returnerer JSON til Power Automate. Koden ligger ferdig i `azure-function-baf/`.

## Hva den gjør

- **Endpoint:** `GET/POST https://<app-navn>.azurewebsites.net/api/baf?code=<function-key>`
- Henter **begge** rederier i ett kall: Color Line (BAF) og Fjord Line (BAF+ETS summert). Forventet 6 rader for juli 2026 (3 + 3).
- **Suksess (HTTP 200):**
  ```json
  { "count": 6, "fetched_at": "2026-07-06T07:17:31+00:00", "errors": [],
    "rows": [
      { "id": "Color Line|Oslo – Kiel|2026-07-01", "company": "Color Line",
        "route": "Oslo – Kiel", "valid_from": "2026-07-01", "valid_to": "2026-07-31",
        "period_label": "BAF Adjustment Fee 01.–31.07.2026 (NOK / LM)",
        "price_nok": 123, "price_eur": 11.1,
        "source_url": "https://www.colorline-cargo.com/services/baf-adjustments",
        "fetched_at": "2026-07-06T07:17:31+00:00" },
      { "id": "Fjord Line|Bergen/Stavanger–Hirtshals|2026-07-01", "company": "Fjord Line",
        "route": "Bergen/Stavanger–Hirtshals", "valid_from": "2026-07-01", "valid_to": "2026-07-31",
        "period_label": "BAF+ETS 01.07.-31.07.26 (per metre)",
        "price_nok": 165, "price_eur": 15.2,
        "source_url": "https://fjordline.com/nb/p/fjord-line-freight/fraktinformasjon",
        "fetched_at": "2026-07-06T07:17:31+00:00" }
    ] }
  ```
- **Delvis feil (HTTP 200):** minst én kilde OK, men `errors` er ikke tom, f.eks. `"errors": [{"company":"Fjord Line","error":"..."}]`. Flyten lagrer de gode radene **og** sender deg feilvarsel.
- **Full feil (HTTP 502):** `{ "error": "<melding>", "count": 0, "rows": [], "errors": [...] }` — ingen rader fra noen kilde.

## Forutsetninger

- Azure-abonnement med rett til å opprette **Function App** (Consumption/Flex, Linux, Python 3.11).
- Én av delene under. **Alternativ A (portal)** krever ingen installasjon. **Alternativ B (CLI)** er raskest hvis du har verktøyene.

---

## Alternativ A — Deploy via VS Code (anbefalt, ingen CLI)

1. Installer **VS Code** + utvidelsen **Azure Functions** (+ **Azure Account**), og **Azure Functions Core Tools** + **Python 3.11**.
2. Åpne mappen `azure-function-baf` i VS Code. Full sti:
   `...\1. Tender Datasett\BAF\azure-function-baf` (åpne akkurat denne mappen, ikke foreldermappen — `function_app.py` og `host.json` må ligge i rota av det du åpner).
3. Logg inn i Azure (ikon i venstremeny → Sign in).
4. Trykk **F1** → `Azure Functions: Create Function App in Azure (Advanced)`:
   - Navn: `ngn-baf-func` (må være globalt unikt)
   - Runtime: **Python 3.11**
   - OS: **Linux**, Plan: **Consumption**
   - Region: **North Europe** eller **West Europe**
5. Trykk **F1** → `Azure Functions: Deploy to Function App` → velg app-en du lagde.
6. Etter deploy: i Azure-panelet, høyreklikk funksjonen `baf` → **Copy Function Url** (inkluderer `?code=...`). **Ta vare på denne — Power Automate trenger den.**

---

## Alternativ B — Deploy via Azure CLI + Functions Core Tools (valgt)

**Krever:** [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) + [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local) + Python 3.11.

> **Navn må være globalt unike.** `APP`-navnet (Function App) og `STORAGE`-navnet må være ledige i hele Azure. Bytt suffiks