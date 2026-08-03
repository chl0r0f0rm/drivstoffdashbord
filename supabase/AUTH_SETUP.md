# Innlogging (@ngn.no + eget passord + verifikasjonskode)

Dashbordene er beskyttet med Supabase Auth (e-post + passord).

Dette er **ikke** NG SSO. Brukere skal lage et **eget passord kun for denne siden**.

## Oppsett i Supabase Dashboard

1. **Authentication → Providers → Email**
   - Enable Email provider
   - Confirm email: **ON**
   - Minimum password length: 8 (eller høyere)

2. **Authentication → Email Templates → Confirm signup**
   - Lim inn malen under (må inneholde `{{ .Token }}`)

3. **Authentication → URL Configuration**
   - Site URL: produksjons-URL for dashbordet (Cloudflare)
   - Redirect URLs: samme origin + `.../login.html`

4. **SQL Editor**
   - Kjør `migrations/auth_ngn_domain.sql`
   - Blokkerer registrering uten `@ngn.no`

## E-postmal (Confirm signup)

**Subject:**
```text
Verifikasjonskode for NG drivstoffverktøy
```

**Body:**
```html
<h2>Bekreft kontoen din</h2>
<p>Hei,</p>
<p>Du registrerer deg på NG sitt interne drivstoffverktøy (ikke SSO).</p>
<p>Din verifikasjonskode er:</p>
<p style="font-size:24px;font-weight:700;letter-spacing:4px;">{{ .Token }}</p>
<p>Koden gjelder en kort stund. Hvis du ikke ba om dette, kan du se bort fra e-posten.</p>
```

## Flyt

1. Registrer med `@ngn.no` + eget passord for denne siden
2. Bekreft med 6-sifret kode fra e-post
3. Logg inn senere med samme e-post/passord
4. `index.html` / `markedsinnsikt.html` krever gyldig session

## Filer

| Fil | Rolle |
|-----|------|
| `login.html` | Innlogging / registrering / OTP |
| `auth.js` | Auth-logikk + `@ngn.no`-jekk |
| `migrations/auth_ngn_domain.sql` | Server-side domenesperre |
