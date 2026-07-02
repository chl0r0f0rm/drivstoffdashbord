import urllib.request
import urllib.error
import json
import sys
import os

TOKEN   = 'sbp_v0_5cc4496c96c13e8b048e203054ee87d6a5b184b7'
PROJECT = 'fnkdbuqsschkvpzeumbz'
URL     = f'https://api.supabase.com/v1/projects/{PROJECT}/database/query'

SCHEMA_SQL = """
create table if not exists price_data (
  id      bigint generated always as identity primary key,
  source  text    not null,
  month   text    not null,
  diesel  numeric,
  hvo     numeric,
  unique  (source, month)
);
alter table price_data enable row level security;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'price_data'
      and policyname = 'public read'
  ) then
    create policy "public read" on price_data for select using (true);
  end if;
end
$$;
create index if not exists price_data_source_month on price_data (source, month);

create table if not exists price_source_sync (
  source     text primary key,
  updated_at timestamptz not null default now()
);
alter table price_source_sync enable row level security;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'price_source_sync'
      and policyname = 'public read sync'
  ) then
    create policy "public read sync" on price_source_sync for select using (true);
  end if;
end
$$;
"""

def run_sql(sql, label):
    payload = json.dumps({'query': sql}).encode('utf-8')
    req = urllib.request.Request(
        URL,
        data=payload,
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Content-Type': 'application/json',
            'User-Agent': 'migration-script/1.0',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode()
            print(f'OK  [{label}]  {body[:120]}')
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'ERR [{label}]  HTTP {e.code}: {body[:300]}')
        return False
    except Exception as exc:
        print(f'ERR [{label}]  {exc}')
        return False


def build_insert_batches(sql_file, batch_size=50):
    """Split the INSERT section of the migration file into batches of rows."""
    with open(sql_file, encoding='utf-8') as f:
        content = f.read()

    sources = ['SE_preem', 'SE_ck', 'DK_ck', 'DK_ck_inkl']
    batches = []

    for source in sources:
        marker_start = f"-- ── Seed: {source}"
        idx_start = content.find(marker_start)
        if idx_start == -1:
            continue
        # find the 'insert into' after this marker
        ins_start = content.find('insert into price_data', idx_start)
        if ins_start == -1:
            continue
        # find end: 'on conflict' clause closes the statement
        ins_end = content.find('on conflict (source, month) do nothing;', ins_start)
        if ins_end == -1:
            continue
        ins_end += len('on conflict (source, month) do nothing;')

        full_insert = content[ins_start:ins_end]

        # extract individual value rows
        values_start = full_insert.find('values') + len('values')
        values_section = full_insert[values_start:full_insert.rfind('\non conflict')]
        # split on '),\n  (' to get rows
        raw_rows = [r.strip().lstrip('(') for r in values_section.split('),\n')]
        raw_rows = [r.rstrip(')').strip() for r in raw_rows]
        raw_rows = [r for r in raw_rows if r]

        # batch them
        for i in range(0, len(raw_rows), batch_size):
            chunk = raw_rows[i:i + batch_size]
            values_sql = ',\n  '.join(f'({r})' for r in chunk)
            batch_sql = (
                f"insert into price_data (source, month, diesel, hvo) values\n  {values_sql}\n"
                "on conflict (source, month) do nothing;"
            )
            batches.append((f'{source} rows {i+1}-{min(i+batch_size, len(raw_rows))}', batch_sql))

    return batches


if __name__ == '__main__':
    sql_file = os.path.join(os.path.dirname(__file__), 'migration.sql')

    print('=== Step 1: Schema + RLS ===')
    ok = run_sql(SCHEMA_SQL, 'schema')
    if not ok:
        print('Schema failed — aborting.')
        sys.exit(1)

    print('\n=== Step 2: Seed data ===')
    batches = build_insert_batches(sql_file, batch_size=50)
    print(f'  {len(batches)} batches to insert')
    failures = 0
    for label, sql in batches:
        if not run_sql(sql, label):
            failures += 1

    if failures:
        print(f'\n{failures} batch(es) failed.')
        sys.exit(1)
    else:
        print('\nAll done — migration complete.')
