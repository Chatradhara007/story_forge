create extension if not exists vector;

create table if not exists facts (
    id serial primary key,
    entity text not null,
    entity_type text not null,
    attribute text not null,
    value text not null,
    source_quote text not null,
    confidence float not null,
    chapter_id text not null,
    embedding vector(2048),
    created_at timestamptz default now()
);

create index if not exists facts_entity_idx on facts (entity);

-- Vector similarity index. Safe to run even with few rows; becomes useful once
-- you have enough facts stored that a sequential scan would be slow.
create index if not exists facts_embedding_idx on facts
    using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create table if not exists contradictions (
    id serial primary key,
    entity text not null,
    new_chapter_id text not null,
    new_attribute text not null,
    new_value text not null,
    new_quote text not null,
    conflicting_chapter_id text not null,
    conflicting_value text not null,
    conflicting_quote text not null,
    contradiction_type text not null,
    explanation text not null,
    created_at timestamptz default now()
);

create index if not exists contradictions_entity_idx on contradictions (entity);
