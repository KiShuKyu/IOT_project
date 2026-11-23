-- Review this against your existing Supabase schema before applying.
create table if not exists public.items (
  id uuid primary key default gen_random_uuid(),
  kind text not null default 'memory',
  title text,
  content text not null,
  details jsonb not null default '{}'::jsonb,
  source text not null default 'audio',
  created_at timestamptz not null default now()
);
create index if not exists items_created_at_idx on public.items(created_at desc);
