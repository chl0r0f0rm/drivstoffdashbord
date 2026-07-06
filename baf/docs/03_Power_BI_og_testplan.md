# 3 — Power BI-kobling + testplan

## Power BI — koble til BAF-tabellen

1. **Power BI Desktop** → **Hent data** → **SharePoint-mappe** (eller **Web**/**SharePoint Online-liste** hvis du foretrekker fil-URL).
   - Lim inn SharePoint-site-URL → naviger til `4. data_BAF.xlsx` → velg tabellen **`BAF`** (ikke arket).
2. I **Power Query**:
   - Sett `valid_from`, `valid_to` til **Dato**, `fetched_at` til **Dato/klokkeslett**.
   - `price_nok` → **Heltall**, `price_eur` → **Desimaltall**.
   - Behold `id` som tekst (nøkkel) — kan skjules i rapporten.
3. **Lukk og bruk** → bygg visualiseringer.
4. **Publiser** til Power BI Service → sett **planlagt oppdatering** (f.eks. daglig 08:00, etter flyten). SharePoint Online + Excel krever **ingen** lokal gateway.

### Forslag til mål (DAX)
```DAX
Siste BAF NOK = 
CALCULATE ( MAX ( BAF[price_nok] ),
    FILTER ( BAF, BAF[valid_from] = MAX ( BAF[valid_from] ) ) )
```
- MoM-endring: sammenlign `price_nok` mot forrige `valid_from` per `route`.
- Kryss-rederi-sammenligning når Fjord Line er lagt til (`company`).

---

## Testplan

| # | Test | Forventet |
|---|------|-----------|
| 1 | Åpne GitHub-JSON-URL i nettleser (API + PAT), eller kjør bare HTTP-steget i PA | HTTP 200, `count: 6`, `errors: []` |
| 2 | Testkjør flyten manuelt (Test → Manually) | Grønn kjøring; de 6 radene oppdateres (samme verdier) |
| 3 | Sjekk `4. data_BAF.xlsx` på SharePoint | Fortsatt 6 rader — **ingen duplikater** |
| 4 | Endre en pris i Excel manuelt, kjør flyten på nytt | Prisen settes tilbake; endringsvarsel-mail til distribusjonslisten |
| 5 | Sett feil URI i HTTP-steget, kjør | Feil-e-post til deg; flyten ender «Failed» |
| 6 | Verifiser i Excel: Oslo–Kiel `price_nok = 123`; Bergen/Stavanger–Hirtshals `price_nok = 165` (116 BAF + 49 ETS) | Stemmer |
| 7 | Power BI → oppdater | Data lastes, datotyper korrekte |

### Verifikasjonspunkt for parserne (allerede testet lokalt)
- Color Line primær-parser (`section.modStructuredinfo`) → 3 rader ✔
- Color Line tekst-fallback (hvis CSS endres) → 3 rader ✔
- Fjord Line BAF+ETS summering → 3 rader, 165/139/53 NOK ✔
- Delvis feil (én kilde nede) → gode rader lagres + feilvarsel ✔
- Alle kilder feiler → 502 → feil-e-post ✔

---

## Feilsøking

| Symptom | Sjekk |
|---------|-------|
| HTTP-steg gir 401/404 | 401 = feil/utløpt PAT i `Authorization`-header. 404 = feil URL/branch, eller `data/baf_latest.json` finnes ikke ennå (kjør GitHub Actions-workflowen) |
| `count: 0` / manglende rader | Sjekk GitHub Actions-kjøringen (rød = parsing feilet, Color Line/Fjord Line endret struktur) |
| Flyt: «table not found» | Tabellnavnet må være `BAF`, og fila må ligge i riktig dokumentbibliotek/sti |
| Fil-velger fryser | Stort bibliotek — naviger mappe-for-mappe eller flytt fila til et mindre bibliotek |
| Dupliserte rader | `id`-kolonnen må være Key Column i «Update a row