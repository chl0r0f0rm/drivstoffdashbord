import json
import os
import sys
import urllib.error
import urllib.request

PROJECT = 'fnkdbuqsschkvpzeumbz'
URL = f'https://api.supabase.com/v1/projects/{PROJECT}/database/query'

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


def main() -> int:
    token = os.environ.get('SUPABASE_ACCESS_TOKEN')
    if not token:
        print('Mangler SUPABASE_ACCESS_TOKEN')
        return 1

    body = json.dumps({'query': SQL}).encode('utf-8')
    request = urllib.request.Request(
        URL,
        data=body,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'migration-script/1.0',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print('OK:', response.read().decode()[:200])
            return 0
    except urllib.error.HTTPError as error:
        print(f'ERR {error.code}:', error.read().decode()[:300])
        return 1
    except OSError as error:
        print('ERR:', error)
        return 1


if __name__ == '__main__':
    sys.exit(main())
