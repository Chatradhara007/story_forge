-- StoryForge database layout.
-- The backend runs this automatically every time it starts, so you normally never run it
-- by hand. Every statement is written so running it again changes nothing.

create extension if not exists vector;

-- One row per book. Everything else belongs to exactly one book, so characters,
-- facts and warnings never mix between books.
create table if not exists projects (
    id serial primary key,
    name text not null,
    created_at timestamptz default now()
);
create unique index if not exists projects_name_idx on projects (lower(name));

-- ---------------------------------------------------------------------------
-- Upgrade: databases created before books existed. Their tables are moved into a
-- book called "My story", keeping all chapters, facts, names and warnings.
-- ---------------------------------------------------------------------------
do $$
begin
    if exists (select 1 from information_schema.tables where table_name = 'chapters')
       and not exists (select 1 from information_schema.columns
                       where table_name = 'chapters' and column_name = 'project_id') then

        insert into projects (name) select 'My story' where not exists (select 1 from projects);

        alter table facts drop constraint if exists facts_chapter_id_fkey;
        alter table contradictions drop constraint if exists contradictions_new_chapter_id_fkey;
        alter table contradictions drop constraint if exists contradictions_conflicting_chapter_id_fkey;

        alter table chapters add column project_id integer;
        update chapters set project_id = (select min(id) from projects);
        alter table chapters alter column project_id set not null;
        alter table chapters add constraint chapters_project_id_fkey
            foreign key (project_id) references projects(id) on delete cascade;
        alter table chapters drop constraint chapters_pkey;
        alter table chapters add primary key (project_id, id);

        alter table entities add column project_id integer;
        update entities set project_id = (select min(id) from projects);
        alter table entities alter column project_id set not null;
        alter table entities add constraint entities_project_id_fkey
            foreign key (project_id) references projects(id) on delete cascade;

        alter table entity_aliases add column project_id integer;
        update entity_aliases a set project_id = e.project_id from entities e where e.id = a.entity_id;
        alter table entity_aliases alter column project_id set not null;
        alter table entity_aliases add constraint entity_aliases_project_id_fkey
            foreign key (project_id) references projects(id) on delete cascade;
        alter table entity_aliases drop constraint if exists entity_aliases_alias_lower_key;
        alter table entity_aliases add constraint entity_aliases_project_alias_key unique (project_id, alias_lower);

        alter table facts add column project_id integer;
        update facts set project_id = (select min(id) from projects);
        alter table facts alter column project_id set not null;
        alter table facts add constraint facts_chapter_fkey
            foreign key (project_id, chapter_id) references chapters(project_id, id) on delete cascade;

        alter table contradictions add column project_id integer;
        update contradictions set project_id = (select min(id) from projects);
        alter table contradictions alter column project_id set not null;
        alter table contradictions add constraint contradictions_new_chapter_fkey
            foreign key (project_id, new_chapter_id) references chapters(project_id, id) on delete cascade;
        alter table contradictions add constraint contradictions_conflicting_chapter_fkey
            foreign key (project_id, conflicting_chapter_id) references chapters(project_id, id) on delete cascade;

        alter table fact_corrections add column if not exists project_id integer;
        update fact_corrections set project_id = (select min(id) from projects) where project_id is null;
    end if;
end $$;

-- One row per chapter. chapter_number is the reading order (1, 2, 3...), so "ch10" is
-- correctly treated as coming after "ch2". Chapter names only need to be unique
-- within a book: two books can both have a "ch1".
create table if not exists chapters (
    project_id integer not null references projects(id) on delete cascade,
    id text not null,                    -- your name for it, e.g. "ch1"
    chapter_number integer not null,     -- reading order
    text text not null,                  -- the original chapter text
    time_note text,                      -- when it's set, e.g. "flashback: twelve years before the fire"
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    primary key (project_id, id)
);
alter table chapters add column if not exists time_note text;

-- One row per real character / place / item / event, no matter how many names
-- it goes by. canonical_name is its "main" name, e.g. "Marcus Vale".
create table if not exists entities (
    id serial primary key,
    project_id integer not null references projects(id) on delete cascade,
    canonical_name text not null,
    entity_type text not null,
    created_at timestamptz default now()
);
create index if not exists entities_project_idx on entities (project_id);

-- Every name an entity has been called: "Marcus", "Marcus Vale", "Captain Vale"...
-- Within one book a name can only point to ONE entity, so once the system has learned
-- a name it links it instantly next time, without asking the AI.
create table if not exists entity_aliases (
    id serial primary key,
    entity_id integer not null references entities(id) on delete cascade,
    project_id integer not null references projects(id) on delete cascade,
    alias text not null,
    alias_lower text not null,
    created_at timestamptz default now(),
    constraint entity_aliases_project_alias_key unique (project_id, alias_lower)
);
create index if not exists entity_aliases_entity_idx on entity_aliases (entity_id);

create table if not exists facts (
    id serial primary key,
    project_id integer not null,
    chapter_id text not null,
    entity_id integer references entities(id) on delete set null,  -- WHO this fact is about
    entity text not null,                                            -- the name as written in the chapter
    entity_type text not null,
    attribute text not null,
    value text not null,
    source_quote text not null,
    confidence float not null,
    embedding vector(2048),
    created_at timestamptz default now(),
    constraint facts_chapter_fkey foreign key (project_id, chapter_id)
        references chapters(project_id, id) on delete cascade
);
create index if not exists facts_entity_idx on facts (lower(entity));
create index if not exists facts_chapter_idx on facts (project_id, chapter_id);
create index if not exists facts_entity_id_idx on facts (entity_id);

-- NOTE: no vector index on purpose. pgvector can only index vectors of up to
-- 2000 dimensions, and our embedding model produces 2048. Searching without an
-- index is perfectly fast for thousands of facts. If this ever gets slow, change
-- the column to halfvec(2048) and add:
--   create index on facts using hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops);

create table if not exists contradictions (
    id serial primary key,
    project_id integer not null,
    entity text not null,
    new_chapter_id text not null,
    new_attribute text not null,
    new_value text not null,
    new_quote text not null,
    conflicting_chapter_id text not null,
    conflicting_value text not null,
    conflicting_quote text not null,
    contradiction_type text not null,
    confidence float not null default 0.5,
    explanation text not null,
    status text not null default 'open',   -- 'open' or 'dismissed' (writer said it's fine)
    created_at timestamptz default now(),
    constraint contradictions_new_chapter_fkey foreign key (project_id, new_chapter_id)
        references chapters(project_id, id) on delete cascade,
    constraint contradictions_conflicting_chapter_fkey foreign key (project_id, conflicting_chapter_id)
        references chapters(project_id, id) on delete cascade
);
alter table contradictions add column if not exists status text not null default 'open';
-- Why the automatic double-check dismissed a warning (empty if it didn't).
alter table contradictions add column if not exists review_note text;
create index if not exists contradictions_project_idx on contradictions (project_id);
create index if not exists contradictions_entity_idx on contradictions (lower(entity));

-- Every manual edit or deletion of a fact is logged here. This is free feedback:
-- it shows where the AI's extraction goes wrong, and can become test data later.
create table if not exists fact_corrections (
    id serial primary key,
    project_id integer,
    fact_id integer not null,
    action text not null,          -- 'edit' or 'delete'
    before jsonb not null,
    after jsonb,
    created_at timestamptz default now()
);
alter table fact_corrections add column if not exists project_id integer;
