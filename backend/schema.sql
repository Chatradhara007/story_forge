-- StoryForge database layout.
-- The backend runs this automatically every time it starts, so you normally never run it
-- by hand. Every statement is written so running it again changes nothing.

create extension if not exists vector;

-- One row per chapter you've submitted. chapter_number is the reading order
-- (1, 2, 3...), so "ch10" is correctly treated as coming after "ch2".
create table if not exists chapters (
    id text primary key,                 -- your name for it, e.g. "ch1"
    chapter_number integer not null,     -- reading order
    text text not null,                  -- the original chapter text
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- One row per real character / place / item / event, no matter how many names
-- it goes by. canonical_name is its "main" name, e.g. "Marcus Vale".
create table if not exists entities (
    id serial primary key,
    canonical_name text not null,
    entity_type text not null,
    created_at timestamptz default now()
);

-- Every name an entity has been called: "Marcus", "Marcus Vale", "Captain Vale"...
-- A name can only point to ONE entity (alias_lower is unique), so once the system
-- has learned a name it links it instantly next time, without asking the AI.
create table if not exists entity_aliases (
    id serial primary key,
    entity_id integer not null references entities(id) on delete cascade,
    alias text not null,
    alias_lower text not null unique,
    created_at timestamptz default now()
);

create index if not exists entity_aliases_entity_idx on entity_aliases (entity_id);

create table if not exists facts (
    id serial primary key,
    chapter_id text not null references chapters(id) on delete cascade,
    entity_id integer references entities(id) on delete set null,  -- WHO this fact is about
    entity text not null,                                            -- the name as written in the chapter
    entity_type text not null,
    attribute text not null,
    value text not null,
    source_quote text not null,
    confidence float not null,
    embedding vector(2048),
    created_at timestamptz default now()
);

create index if not exists facts_entity_idx on facts (lower(entity));
create index if not exists facts_chapter_idx on facts (chapter_id);
create index if not exists facts_entity_id_idx on facts (entity_id);

-- NOTE: no vector index on purpose. pgvector can only index vectors of up to
-- 2000 dimensions, and our embedding model produces 2048. Searching without an
-- index is perfectly fast for thousands of facts. If this ever gets slow, change
-- the column to halfvec(2048) and add:
--   create index on facts using hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops);

create table if not exists contradictions (
    id serial primary key,
    entity text not null,
    new_chapter_id text not null references chapters(id) on delete cascade,
    new_attribute text not null,
    new_value text not null,
    new_quote text not null,
    conflicting_chapter_id text not null references chapters(id) on delete cascade,
    conflicting_value text not null,
    conflicting_quote text not null,
    contradiction_type text not null,
    confidence float not null default 0.5,
    explanation text not null,
    status text not null default 'open',   -- 'open' or 'dismissed' (writer said it's fine)
    created_at timestamptz default now()
);

create index if not exists contradictions_entity_idx on contradictions (lower(entity));

-- For databases created before these columns existed.
alter table contradictions add column if not exists status text not null default 'open';

-- Every manual edit or deletion of a fact is logged here. This is free feedback:
-- it shows where the AI's extraction goes wrong, and can become test data later.
create table if not exists fact_corrections (
    id serial primary key,
    fact_id integer not null,
    action text not null,          -- 'edit' or 'delete'
    before jsonb not null,
    after jsonb,
    created_at timestamptz default now()
);
