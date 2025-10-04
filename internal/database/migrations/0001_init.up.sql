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
