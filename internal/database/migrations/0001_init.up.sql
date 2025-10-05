CREATE TABLE auth
(
    pk    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    token TEXT NOT NULL UNIQUE
);

CREATE TABLE flavor
(
    pk               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    platform         TEXT    NOT NULL,
    name             TEXT    NOT NULL UNIQUE,
    labels           TEXT[]  NOT NULL DEFAULT '{}',
    priority         INT     NOT NULL DEFAULT 0,
    is_disabled      BOOLEAN NOT NULL DEFAULT FALSE,
    minimum_pressure INT     NOT NULL DEFAULT 0,
    UNIQUE (platform, name),
    CHECK (platform <> '' AND name <> '' AND name <> '-')
);

CREATE TABLE job
(
    pk              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    platform        TEXT        NOT NULL,
    id              TEXT        NOT NULL,
    labels          TEXT[]      NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    raw             JSONB       NOT NULL DEFAULT '{}',
    assigned_flavor TEXT REFERENCES flavor (name),
    UNIQUE (platform, id),
    CHECK (platform <> '' AND id <> '')
);

CREATE EXTENSION IF NOT EXISTS btree_gin;

CREATE INDEX auth_token_idx ON auth (token);
CREATE INDEX auth_name_idx ON auth (name);

CREATE INDEX flavor_platform_name_idx ON flavor (platform, name);
CREATE INDEX flavor_platform_labels_gin ON flavor USING gin(platform, labels);
CREATE INDEX flavor_platform_priority_pidx ON flavor (platform, priority DESC) WHERE NOT is_disabled;

CREATE INDEX job_platform_id_idx ON job (platform, id);
CREATE INDEX job_platform_created_at_idx ON job (platform, created_at);
CREATE INDEX job_in_progress_platform_created_pidx ON job (platform, created_at) WHERE completed_at IS NULL;
CREATE INDEX job_platform_assigned_flavor_idx ON job (platform, assigned_flavor);
CREATE INDEX job_in_progress_by_platform_flavor_pidx ON job (platform, assigned_flavor) WHERE completed_at IS NULL;
