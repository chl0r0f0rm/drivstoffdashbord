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

## URL-en Power Automate skal lese

**Hvis repoet er PUBLIC:**
```
https://raw.githubusercontent.com/chl0r0f0rm/drivstoffdashbord/main/data/baf_latest.json
```
(bytt `main` med riktig gren om nødvendig). PA gjør en enkel HTTP GET — ingen autentisering.

**Hvis repoet er PRIVATE:**
Bruk GitHub-API-et med en **fine-grained PAT** (kun `Contents: Read` på dette ene repoet):
- URI: `https://api.github.com/repos/chl0r0f0rm/drivstoffdashbord/contents/data/baf_latest.json?ref=main`
- Header `Authorization`: `Bearer <PAT>`
- Header `Accept`: `application/vnd.github.raw`

> BAF/ETS-satsene er offentlig informasjon (hentet fra åpne nettsider). Er hele repoet privat av
> andre grunner, er enkleste vei å publisere *kun* JSON-en offentlig — f.eks. en egen public repo
> eller en public Gist — så slipper PA å håndtere token. Si fra, så setter jeg det opp.

## Tidsplan og samspill med Power Automate

- Actions kjører **dag 3 kl. 04:00 UTC** (~05:00–06:00 Oslo) — før PA-flyten kl. 07:00, så JSON-en er fersk når PA leser.
- GitHub cron er UTC og hopper ikke for sommertid; 04:00 UTC gir uansett god margin.
- Vil du ha ekstra sikkerhet kan du legge til flere kjøredager (f.eks. `0 4 1-5 * *`).

## Feilhåndtering

- `fetch_baf.py` avslutter med kode 1 hvis 0 rader → Actions-kjøringen blir **rød**. Slå på
  GitHub-varsling for feilede workflows (repo → Settings → Notifications, eller din GitHub-profil).
- Delvis feil (én kilde nede) lagres i `errors[]` i JSON-en, og Power Automate sender deg feilvarsel
  samtidig som den lagrer de gode radene.
