# Ukentlig oppdatering avgifter

Sjekk om det har kommet nye midlertidige eller permanente dieselavgiftsendringer i **Norge, Sverige og Danmark** som påvirker pumpepris, og oppdater dashbordets avgiftstabell ved behov.

## Oppgave

1. Les eksisterende `TAX_CHANGES` i `index.html` (søk etter `const TAX_CHANGES`).
2. Søk på nettet etter nye/endrede tiltak siden forrige sjekk (bruk dagens dato; typisk siste 7–14 dager, men fang også varslede endringer fremover).
3. Prioriter offisielle kilder:
   - **NO:** Skatteetaten (veibruksavgift / CO₂-avgift), Regjeringen.no, Lovdata/Stortinget
   - **SE:** regeringen.se, Riksdagen (energiskatt / drivmedelsskatt), Skatteverket
   - **DK:** Skatteministeriet, Retsinformation (dieselafgift / energiafgift)
4. Vurder bare endringer som påvirker **diesel ved pumpe** (ikke jordbruksdiesel, eieravgift alene, osv. med mindre det er direkte relevant).

## Oppdatering

Hvis noe er nytt eller endret:

- Oppdater `TAX_CHANGES` i `index.html` med korrekte felt:
  - `country`: `NO` | `SE` | `DK`
  - `start` / `end`: ISO-dato (`YYYY-MM-DD`); `end: null` hvis åpen/pågående
  - `periodLabel`, `measure`, `effect`, `kind`
- Behold filtrering via årsslider (`taxChangeOverlapsYearRange`) — ikke endre logikken unødvendig.
- Commit kun hvis brukeren ber om det.

Hvis ingenting nytt:

- Si kort «Ingen nye relevante avgiftsendringer» og list kort hva som ble sjekket (land + hovedkilde).

## Svarformat

1. **Verdict** — nytt / ikke nytt
2. **Funn** — korte punkter per land (periode + tiltak + anslått pumpeeffekt)
3. **Endringer i kode** — hva som ble oppdatert i `TAX_CHANGES` (eller «ingen»)
4. **Kilder** — lenker
