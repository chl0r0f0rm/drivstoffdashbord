# Innlogging (@ngn.no + eget passord + verifikasjonskode)

Dashbordene er beskyttet med Supabase Auth (e-post + passord).

Dette er **ikke** NG SSO. Brukere skal lage et **eget passord kun for denne siden**.

## Oppsett i Supabase Dashboard

1. **Authentication → Providers → Email**
   - Enable Email provider
   - Confirm email: **ON**
   - Minimum password length: 8 (eller høyere)

2. **Authentication → Email Templates → Magic Link**
   - Lim inn malen under (må inneholde `{{ .Token }}`)
   - Dette er malen som brukes for verifikasjonskode ved registrering

3. **Authentication → URL Configuration**
   - Site URL: produksjons-URL for dashbordet (Cloudflare)
   - Redirect URLs: samme origin + `.../login.html`

4. **SQL Editor**
   - Kjør `migrations/auth_ngn_domain.sql`
   - Blokkerer registrering uten `@ngn.no`

## Flyt

### Registrering
1. `@ngn.no`-epost → send verifikasjonskode
2. Bekreft kode
3. Sett eget passord for denne siden
4. Inn i dashbordet

### Innlogging
1. `@ngn.no`-epost + passordet for denne siden

## E-postmal

For registreringskoden brukes **Magic Link**-malen (OTP). Den må inneholde `{{ .Token }}`.

**Subject:**
```text
Verifikasjonskode for NG drivstoffverktøy
```

**Body:**
```html
<h2>Bekreft e-posten din</h2>
<p>Hei,</p>
<p>Du registrerer deg på NG sitt interne drivstoffverktøy (ikke SSO).</p>
<p>Din verifikasjonskode er:</p>
<p style="font-size:24px;font-weight:700;letter-spacing:4px;">{{ .Token }}</p>
<p>Etter at koden er bekreftet, lager du et eget passord bare for denne siden.</p>
<p>Hvis du ikke ba om dette, kan du se bort fra e-posten.</p>
```

## Filer

| Fil | Rolle |
|-----|------|
| `login.html` | Innlogging / registrering / OTP |
| `auth.js` | Auth-logikk + `@ngn.no`-jekk |
| `migrations/auth_ngn_domain.sql` | Server-side domenesperre |
