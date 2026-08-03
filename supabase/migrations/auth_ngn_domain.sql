-- Restrict Supabase Auth signups to @ngn.no only.
-- Run in Supabase SQL Editor (requires privileges on auth schema).

create or replace function public.enforce_ngn_email_domain()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  email_domain text;
begin
  if new.email is null then
    raise exception 'E-post er påkrevd';
  end if;

  email_domain := lower(split_part(new.email, '@', 2));
  if email_domain is distinct from 'ngn.no' then
    raise exception 'Kun @ngn.no-adresser kan registreres';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_enforce_ngn_email_domain on auth.users;

create trigger trg_enforce_ngn_email_domain
  before insert or update of email on auth.users
  for each row
  execute function public.enforce_ngn_email_domain();
