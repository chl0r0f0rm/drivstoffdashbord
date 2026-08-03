# Innlogging via Cloudflare Worker (PAUSERT)

Auth er midlertidig slått av. Dashbordet er åpent uten innlogging.

Når auth skal på igjen:
1. Bytt `src/worker.js` tilbake til innholdet i `src/worker.auth.js`
2. Sett secrets (`AUTH_SECRET`, `RESEND_API_KEY`, `AUTH_FROM_EMAIL`)
3. Verifiser domene i Resend
4. Sett innloggingsgate i `index.html` / `markedsinnsikt.html` igjen
5. Deploy

## Arkitektur (klar, men pausert)

- `login.html` / `auth.js` — UI og klient-API
- `src/worker.auth.js` — `/api/auth/*` + session-cookie + sidebeskyttelse
- D1 `drivstoff-auth` (`1af983d4-3564-4db5-998c-cff7cc31f05e`) — brukere + engangskoder
- Resend — OTP-e-post (krever verifisert avsenderdomene)

## D1 schema

```bash
# Eller kjør migrations/auth_d1.sql i D1 Console
```
