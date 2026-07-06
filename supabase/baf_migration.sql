-- BAF (Bunker Adjustment Factor) — historikk og gjeldende satser
-- Kjør i Supabase SQL Editor, eller via supabase/create_baf_tables.py

-- Gjeldende sats per strekning og periode (én rad per id)
create table if not exists baf_data (
  id            text primary key,
  company       text        not null,
  route         text        not null,
  valid_from    date        not null,
  valid_to      date        not null,
  period_label  text,
  price_nok     integer     not null,
  price_eur     numeric     not null,
  source_url    text,
  first_seen_at timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

alter table baf_data enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'baf_data' and policyname = 'public read baf_data'
  ) then
    create policy "public read baf_data" on baf_data for select using (true);
  end if;
end
$$;

create index if not exists baf_data_company_route on baf_data (company, route);
create index if not exists baf_data_valid_from on baf_data (valid_from desc);

-- Prishistorikk: ny rad når sats endres (eller ved første innhenting)
create table if not exists baf_price_history (
  id           bigint generated always as identity primary key,
  baf_id       text        not null references baf_data (id) on delete cascade,
  price_nok    integer     not null,
  price_eur    numeric     not null,
  period_label text,
  valid_to     date,
  fetched_at   timestamptz not null
);

alter table baf_price_history enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'baf_price_history' and policyname = 'public read baf_price_history'
  ) then
    create policy "public read baf_price_history" on baf_price_history for select using (true);
  end if;
end
$$;

create index if not exists baf_price_history_baf_id on baf_price_history (baf_id, fetched_at desc);

-- Logg over hver automatiske innhenting (GitHub Actions)
create table if not exists baf_fetch_log (
  id          bigint generated always as identity primary key,
  fetched_at  timestamptz not null default now(),
  row_count   integer     not null default 0,
  error_count integer     not null default 0,
  errors      jsonb       not null default '[]'::jsonb,
  status      text        not null
);

alter table baf_fetch_log enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'baf_fetch_log' and policyname = 'public read baf_fetch_log'
  ) then
    create policy "public read baf_fetch_log" on baf_fetch_log for select using (true);
  end if;
end
$$;

create index if not exists baf_fetch_log_fetched_at on baf_fetch_log (fetched_at desc);
