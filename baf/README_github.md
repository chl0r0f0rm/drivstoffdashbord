# GitHub Actions-fetcher for BAF

GitHub Actions henter BAF fra Color Line + Fjord Line (ekte Python, robust parsing), skriver
`data/baf_latest.json`, og Power Automate leser den filen via HTTP. Ingen Azure, ingen admin,
ingenting lokalt — Actions kjører i GitHubs sky.

## Filer her

```
github-actions/
├─ baf/
│  ├─ fetch_baf.py        # kjøres av workflowen → skriver data/baf_latest.json
│  ├─ baf_parser.py       # parser for Color Line (BAF) + Fjord Line (BAF+ETS summert)
│  └─ requirements.txt
└─ .github/workflows/
   └─ fetch-baf.yml        # planlagt (dag 3, 04:00 UTC) + manuell kjøring
```

## Slik legger du det inn i repoet `chl0r0f0rm/drivstoffdashbord`

Legg filene på disse stiene i repo-rota (samme `baf/`-mappe som referansekoden allerede bruker):

- `baf/fetch_baf.py`
- `baf/baf_parser.py`   *(kan erstatte/utfylle eksisterende `fetch_colorline_baf.py`)*
- `baf/requirements.txt`
- `.github/workflows/fetch-baf.yml`

Deretter:

```bash
git add baf/fetch_baf.py baf/baf_parser.py baf/requirements.txt .github/workflows/fetch-baf.yml
git commit -m "feat(baf): samlet fetcher (Color Line + Fjord Line) -> data/baf_latest.json"
git push
```

Første kjøring: **Actions**-fanen i repoet → *Fetch BAF (Color Line + Fjord Line)* → **Run workflow**.
Den lager `data/baf_latest.json` og committer den. Forvent 6 rader (3 + 3) for inneværende måned.

## URL-en Power Automate skal lese (valgt: privat repo + fine-grained PAT)

GitHub Actions har kjørt med suksess. `data/baf_latest.json` ligger på `main` med 6 rader.

### 1. Opprett fine-grained PAT (én gang)

1. Gå til [github.com/settings/tokens?type=beta](https://github.com/settings/tokens?type=beta) → **Generate new token**
2. **Token name:** `power-automate-baf-read`
3. **Expiration:** 90 dager (eller «No expiration» etter org-policy)
4. **Repository access:** **Only select repositories** → `chl0r0f0rm/drivstoffdashbord`
5. **Permissions → Repository permissions:**
   - **Contents:** Read-only
6. Generer og **kopier token** (vises bare én gang). Lagre i passordmanager.

> Ikke committ PAT til repo eller chat. **For agent som bygger PA-flyt:** legg PAT i `baf/.pa-secrets.local` (se `.pa-secrets.local.example`). Agenten leser derfra og setter HTTP-header `Authorization: Bearer <PAT>`.

### 2. HTTP-steg i Power Automate

| Felt | Verdi |
|------|-------|
| **Method** | GET |
| **URI** | `https://api.github.com/repos/chl0r0f0rm/drivstoffdashbord/contents/data/baf_latest.json?ref=main` |

**Headers:**

| Header | Verdi |
|--------|-------|
| `Authorization` | `Bearer <din-PAT>` |
| `Accept` | `application/vnd.github.raw` |
| `X-GitHub-Api-Version` | `2022-11-28` |

Med `Accept: application/vnd.github.raw` returnerer API-et JSON-innholdet direkte (ikke base64-wrapper). **Parse JSON** bruker `body('HTTP')` som vanlig.

### 3. Test før du kobler Excel

Kjør flyten manuelt etter HTTP-steget. Forvent i Parse JSON:
- `count`: 6
- `errors`: []
- `rows`: 6 objekter med `id`, `company`, `route`, `price_nok`, osv.

### Alternativ (ikke valgt): public raw-URL

Hvis repoet blir public senere:
```
https://raw.githubusercontent.com/chl0r0f0rm/drivstoffdashbord/main/data/baf_latest.json
```
Ingen autentisering nødvendig.

## Tidsplan og samspill med Power Automate

- Actions kjører **dag 3 kl. 04:00 UTC** (~05:00–06:00 Oslo) — før PA-flyten kl. 07:00, så JSON-en er fersk når PA leser.
- GitHub cron er UTC og hopper ikke for sommertid; 04:00 UTC gir uansett god margin.
- Vil du ha ekstra sikkerhet kan du legge til flere kjøredager (f.eks. `0 4 1-5 * *`).

## Feilhåndtering

- `fetch_baf.py` avslutter med kode 1 hvis 0 rader → Actions-kjøringen blir **rød**. Slå på
  GitHub-varsling for feilede workflows (repo → Settings → Notifications, eller din GitHub-profil).
- Delvis feil (én kilde nede) lagres i `errors[]` i JSON-en, og Power Automate sender deg feilvarsel
  samtidig som den lagrer de gode radene.
