# 2 — Bygge Power Automate-flyten

Flyt-navn: **BAF – månedlig innhenting (Color Line + Fjord Line)**. Type: **Scheduled cloud flow**.

Azure-funksjonen returnerer rader fra **begge** rederier i ett kall. Fjord Line-radene har allerede BAF + ETS summert i `price_nok`/`price_eur` — flyten trenger ingen egen logikk for det. Upsert-løkka er lik for begge kilder (nøkkel `id = company|route|valid_from`).

> Jeg kan bygge dette live i nettleseren din når Chrome-utvidelsen er tilkoblet og Azure-funksjonen + SharePoint-stien er klare. Denne guiden er også fasit hvis du vil gjøre det selv — hvert steg med eksakte uttrykk.

**Connectorer som brukes:** `HTTP` (premium — sjekk at lisensen din har den), `Excel Online (Business)`, `Office 365 Outlook`.

---

## Steg 0 — Opprett flyten
Power Automate → **Create** → **Scheduled cloud flow**. Sett hvilken som helst startdato foreløpig; vi justerer triggeren i steg 1.

## Steg 1 — Trigger: Recurrence
- **Frequency:** Month, **Interval:** 1
- **Time zone:** `W. Europe Standard Time`
- **Start time:** `2026-08-03T07:00:00` (fyrer den 3. hver måned kl. 07:00)

> Recurrence fyrer på samme dag-i-måned som starttiden. Vil du ha **3. virkedag** i stedet for kalenderdag 3, la triggeren fyre 1. hver måned og legg til en liten løkke som hopper fram til 3. virkedag — si fra, så legger jeg det inn.

## Steg 2 — Fire variabler (Initialize variable ×4)
| Name | Type | Value |
|------|------|-------|
| `varFailureEmail` | String | `andreas.celiussen@ngn.no` |
| `varUpdateDistro` | String | `andreas.celiussen@ngn.no` *(foreløpig kun deg; bytt til distribusjonsliste senere)* |
| `varChanged` | Boolean | `false` |
| `varChangeLog` | String | *(tom)* |

Dette er det eneste stedet du endrer mottakere. Når distribusjonslisten er klar, bytt `varUpdateDistro` til gruppeadressen — medlemmer styres da i Outlook.

**Excel-fil (bekreftet):** `4. data_BAF.xlsx` på SharePoint-site **Nedstrøm** → `Arbeidsrom/Marked/26. Forretningsutvikling/1. Tender Datasett/`. Tabell: `BAF`. Brukes i alle Excel-steg under.

## Steg 3 — Scope: «Try»
Legg alt under i en **Scope** som du kaller `Try`.

### 3a. HTTP — kall Azure Function
- **Method:** GET
- **URI:** `https://<app>.azurewebsites.net/api/baf?code=<function-key>` (fra deploy-guiden)

Funksjonen svarer 200 ved suksess og 502 ved feil. 502 gjør at dette steget feiler → «Catch» fanger det.

> **Azure ikke deployet ennå:** Vi bygger flyten nå med denne URL-en som **plassholder**. Alt annet (trigger, variabler, Excel-steg, varsler) kan settes opp, men flyten kan ikke test-kjøres før funksjonen er live og URL-en limt inn her.

### 3b. Parse JSON
- **Content:** `body('HTTP')`
- **Schema:**
```json
{
  "type": "object",
  "properties": {
    "count": { "type": "integer" },
    "fetched_at": { "type": ["string", "null"] },
    "errors": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "company": { "type": "string" },
          "error": { "type": "string" }
        }
      }
    },
    "rows": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "company": { "type": "string" },
          "route": { "type": "string" },
          "valid_from": { "type": "string" },
          "valid_to": { "type": "string" },
          "period_label": { "type": "string" },
          "price_nok": { "type": "integer" },
          "price_eur": { "type": "number" },
          "source_url": { "type": "string" },
          "fetched_at": { "type": "string" }
        },
        "required": ["id", "route", "price_nok"]
      }
    }
  }
}
```

### 3c. Condition — «0 rader?» (ekstra sikring)
- Uttrykk venstre: `body('Parse_JSON')?['count']`  **is less or equal to**  `0`
- **If yes:** legg inn **Terminate** → Status `Failed` (trigger «Catch»). **If no:** fortsett.

### 3d. List rows present in a table (Excel Online Business)
Hent alle eksisterende rader én gang (brukes til oppslag i løkka).
- **Location:** SharePoint-site der `4. data_BAF.xlsx` ligger
- **Document Library / File:** `4. data_BAF.xlsx`
- **Table:** `BAF`

### 3e. Apply to each — over `body('Parse_JSON')?['rows']`
Inne i løkka:

**i. Filter array** (finn eksisterende rad med samme id)
- **From:** `body('List_rows_present_in_a_table')?['value']`
- **Condition:** `item()?['id']`  **is equal to**  `items('Apply_to_each')?['id']`

**ii. Condition — «Finnes raden?»**
- `length(body('Filter_array'))`  **is greater than**  `0`

**JA-grenen (oppdater):**
- **Condition «Pris endret?»:** `first(body('Filter_array'))?['price_nok']` **is not equal to** `items('Apply_to_each')?['price_nok']`
  - Ja → **Set variable** `varChanged` = `true`, og **Append to string variable** `varChangeLog`:
    `concat('ENDRET: ', items('Apply_to_each')?['route'], ' ', first(body('Filter_array'))?['price_nok'], ' → ', items('Apply_to_each')?['price_nok'], ' NOK', decodeUriComponent('%0A'))`
- **Update a row** (Excel Online Business):
  - Location/Library/File/Table som i 3d
  - **Key Column:** `id`
  - **Key Value:** `items('Apply_to_each')?['id']`
  - Felt: `valid_to`, `period_label`, `price_nok`, `price_eur`, `fetched_at` = tilsvarende `items('Apply_to_each')?['...']`

**NEI-grenen (ny rad):**
- **Add a row into a table** (Excel Online Business): sett alle 10 kolonner fra `items('Apply_to_each')?['...']` (`id`, `company`, `route`, `valid_from`, `valid_to`, `period_label`, `price_nok`, `price_eur`, `source_url`, `fetched_at`)
- **Set variable** `varChanged` = `true`
- **Append to string variable** `varChangeLog`:
  `concat('NY: ', items('Apply_to_each')?['route'], ' = ', items('Apply_to_each')?['price_nok'], ' NOK (', items('Apply_to_each')?['valid_from'], ')', decodeUriComponent('%0A'))`

### 3f. Delfeil per kilde (Color Line OK, Fjord Line feilet — eller omvendt)
Funksjonen svarer 200 så lenge **minst én** kilde ga rader, men lister feilende kilder i `errors`. HTTP-steget feiler da ikke, så «Catch» trigges ikke — vi må sjekke `errors` eksplisitt så du fortsatt varsles, mens de gode radene lagres.
- **Condition:** `empty(body('Parse_JSON')?['errors'])` **is equal to** `false`
  - **If yes → Send an email (V2):**
    - **To:** `variables('varFailureEmail')`
    - **Subject:** `⚠ BAF – én kilde feilet`
    - **Body:** `concat('Delvis feil i ', workflow()?['run']?['name'], ':', decodeUriComponent('%0A'), string(body('Parse_JSON')?['errors']))`

## Steg 4 — Endringsvarsel (etter «Try»)
**Condition:** `variables('varChanged')` **is equal to** `true`  **AND**  `empty(variables('varUpdateDistro'))` **is equal to** `false`
- **If yes → Send an email (V2)** (Office 365 Outlook):
  - **To:** `variables('varUpdateDistro')`
  - **Subject:** `BAF/ETS oppdatert – Color Line og Fjord Line`
  - **Body:** `concat('Nye/endrede satser hentet ', utcNow(), ':', decodeUriComponent('%0A%0A'), variables('varChangeLog'))`

## Steg 5 — Scope: «Catch» (feilvarsel)
Legg til en **Scope** kalt `Catch` **etter** «Try». Klikk «...» → **Configure run after** → huk av **has failed**, **is skipped**, **has timed out**.

Inne i «Catch»:
- **Send an email (V2):**
  - **To:** `variables('varFailureEmail')`
  - **Subject:** `⚠ BAF-flyt feilet`
  - **Body:**
    `concat('Flyten ', workflow()?['run']?['name'], ' feilet.', decodeUriComponent('%0A'), 'Melding: ', coalesce(body('HTTP')?['error']