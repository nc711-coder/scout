-- Scout's tables, in their own schema next to Fernwood's data and Relay's inbox.
create schema if not exists scout;

create table if not exists scout.runs (
    id           serial primary key,
    kind         text not null check (kind in ('sample', 'visitor')),
    visitor      text,                                   -- who started it (visitor runs only)
    title        text not null default '',
    status       text not null default 'queued',         -- queued | running | done
    created_at   timestamptz not null default now(),
    finished_at  timestamptz
);

create table if not exists scout.leads (
    id          serial primary key,
    run_id      integer not null references scout.runs on delete cascade,
    position    integer not null,
    name        text not null,
    website     text not null default '',
    city        text not null default '',
    status      text not null default 'queued',          -- queued | running | done | failed
    stage       text not null default '',                -- what it's doing now, shown on the page
    score       integer,
    tier        text,
    opener      text,
    result      jsonb,                                   -- facts, quotes, sources, score breakdown, first line
    error       text,
    updated_at  timestamptz not null default now()
);
create index if not exists leads_run on scout.leads (run_id, position);
