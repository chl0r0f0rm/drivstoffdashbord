# Handoff: BAF data pipeline — GitHub → SharePoint → Power BI

**Owner:** Andy (djsmarterchild@gmail.com)
**Last updated:** 2026-07-13
**Status:** GitHub Action writes `baf_data.csv` (repo root). Power Automate + Power BI PQ still to build.

## Purpose

Get BAF price data (scraped by a GitHub Action) into the Power BI dataset **Tender Downstream** without adding new connection types to the dataset. The dataset previously failed to refresh because one Power Query combined three sources (Supabase REST API + SharePoint Excel + forex API), which triggered the Formula.Firewall and an unmanageable credential-mapping situation in the Power BI Service.

**Fix:** land the data as a CSV in SharePoint so the dataset only reads sources it already has working credentials for (SharePoint + forex API). Supabase is removed from the Power BI side entirely.

## Architecture

```
GitHub Action (existing scraper)
  └─ commits baf_data.csv to the repo
       └─ Power Automate flow (daily)
            ├─ HTTP GET raw.githubusercontent.com/<org>/<repo>/main/baf_data.csv
            └─ writes file to SharePoint site
                 └─ Power BI dataset "Tender Downstream" (daily scheduled refresh)
                      └─ BI dashboard
```

## Component 1 — GitHub Action

- **Done in repo:** `.github/workflows/fetch-baf.yml` runs `baf/fetch_baf.py`, merges scrape + `baf/seeds/*.json` into `baf_data.csv` at repo root, and commits. Supabase sync removed.
- Columns (must stay stable — Power Query depends on them):
  `id, company, route, valid_from, valid_to, period_label, price_nok, price_eur, source_url, first_seen_at, updated_at`
- Dates ISO 8601 (`YYYY-MM-DD`), timestamps with timezone, decimal point (not comma).
- If the repo is private, create a fine-grained PAT with read-only Contents access to this repo; store the PAT where the flow owner can rotate it. Note PAT expiry date.

## Component 2 — Power Automate flow

**Name suggestion:** `BAF CSV – GitHub to SharePoint`
**Runs as:** Andy's account. Premium HTTP connector required — currently covered by a "Power Automate For CCI Bots" license (see Risks).

| # | Action | Config |
|---|--------|--------|
| 1 | Recurrence | Daily, ~1 hour before the dataset's scheduled refresh |
| 2 | HTTP | GET `https://raw.githubusercontent.com/<org>/<repo>/main/baf_data.csv`. Private repo: header `Authorization: token <PAT>` |
| 3 | SharePoint – Create file | Site: <this SharePoint site>. Folder: e.g. `/Delte dokumenter/BAF`. File name: `baf_data.csv`. Content: `body('HTTP')` |

If **Create file** fails because the file already exists: add **Get file metadata using path** and use **Update file** (with the file identifier) instead of Create file. Alternatively delete-then-create.

Add a failure notification: configure "Notify me on failure" or add a Teams/mail action on the error branch — a silently dead flow means the dashboard quietly goes stale.

## Component 3 — Power Query (dataset "Tender Downstream")

Replace the old Supabase query pair with a CSV read from SharePoint. Same connector and credential as the existing manual Excel sheet.

**Query `baf_raw`** (single source, no references to other queries):

```
let
    Source = Csv.Document(
        Web.Contents("https://<tenant>.sharepoint.com/sites/<site>/Delte dokumenter/BAF/baf_data.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"valid_from", type date},
        {"valid_to", type date},
        {"price_nok", Int64.Type},
        {"price_eur", type number},
        {"first_seen_at", type datetimezone},
        {"updated_at", type datetimezone}
    })
in
    Typed
```

**Query `baf_data`** (references only other queries — never touches a source directly; this separation is what keeps the Formula.Firewall quiet):

```
let
    Source = baf_raw,
    #"Added 2x20" = Table.AddColumn(Source, "2x20' cont.", each [price_nok] * #"2x20' cont lm", type number),
    #"Added 3x20" = Table.AddColumn(#"Added 2x20", "3x20' cont.", each [price_nok] * #"3x20' modul 25,25", type number),
    #"Added Kapell" = Table.AddColumn(#"Added 3x20", "Vanlig kapell", each [price_nok] * KAP3, type number),
    #"Sorterte rader" = Table.Sort(#"Added Kapell", {{"valid_from", Order.Descending}})
in
    #"Sorterte rader"
```

The multiplier queries (`2x20' cont lm`, `3x20' modul 25,25`, `KAP3`) must each touch only the Excel file — no mixing sources inside a single query, ever.

## Component 4 — Power BI Service

- Dataset credentials needed: SharePoint (OAuth2, existing) + forex API (existing). Nothing new.
- After first publish, verify credentials under Semantic model settings → Datakildelegitimasjon, then run one manual refresh before trusting the schedule.

## Timing chain

GitHub Action commit → flow run (daily, T-1h) → dataset refresh (daily, T) → dashboard. Keep at least 30–60 min buffer between each step.

## Risks / maintenance

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Premium HTTP action runs on "CCI Bots" license, out-of-context | Flow could be flagged/disabled by admins | Long term: ask IT for an Entra app registration (Graph, `Sites.Selected` on this site) and have the GitHub Action upload the file directly — removes Power Automate entirely |
| Flow owned by one personal account | Flow dies if account is disabled | Add a co-owner; document here who |
| PAT expiry (private repo) | HTTP step starts failing | Calendar reminder before expiry; rotate in flow |
| CSV schema drift (Action changes columns) | Refresh fails | Treat the column list above as a contract |
| raw.githubusercontent caching (~5 min) | Marginal staleness | Irrelevant at daily cadence |
| Silent flow failure | Stale dashboard, nobody notices | Failure notification (Component 2) |

## Decisions log (why this design)

- Office Scripts cannot refresh Power Query/external connections when run from Power Automate → cloud "force refresh" of an Excel query is impossible; push data instead.
- No Azure access → Entra app registration (the cleanest option) is pending an IT request; Power Automate is the interim bridge.
- One PQ query mixing Supabase + Excel parameters triggered Formula.Firewall → staging split, then removal of Supabase from PBI entirely.
- Credential/cloud-connection mapping for the Supabase web source in the Service proved unmanageable → consolidate on SharePoint sources.
