import urllib.request
import urllib.error
import json

TOKEN   = 'sbp_v0_5cc4496c96c13e8b048e203054ee87d6a5b184b7'
PROJECT = 'fnkdbuqsschkvpzeumbz'
URL     = f'https://api.supabase.com/v1/projects/{PROJECT}/database/query'

SQL = """
create table if not exists daily_price_data (
  id     bigint generated always as identity primary key,
  source text    not null,
  date   date    not null,
  diesel numeric,
  hvo    numeric,
  unique (source, date)
);
alter table daily_price_data enable row level security;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'daily_price_data'
      and policyname = 'public read daily'
  ) then
    create policy "public read daily" on daily_price_data for select using (true);
  end if;
end
$$;
create index if not exists daily_price_data_source_date on daily_price_data (source, date);
"""

body = json.dumps({'query': SQL}).encode('utf-8')
req = urllib.request.Request(URL, data=body, headers={
    'Authorization': f'Bearer {TOKEN}',
    'Content-Type': 'application/json',
    'User-Agent': 'migration-script/1.0',
}, method='POST')

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print('OK:', resp.read().decode()[:200])
except urllib.error.HTTPError as e:
    print(f'ERR {e.code}:', e.read().decode()[:300])
except Exception as exc:
    print('ERR:', exc)
