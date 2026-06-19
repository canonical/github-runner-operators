-- Copyright 2026 Canonical Ltd.
-- See LICENSE file for licensing details.

-- Flavor matching became case-insensitive: labels are now normalized to
-- lowercase on insertion. Normalize existing rows so already-stored labels
-- match, and re-run flavor assignment to recover jobs that were left unassigned
-- only because of label casing (e.g. job "X64" vs flavor "x64").

-- Lowercase all flavor labels (small table).
UPDATE flavor AS f
SET labels = (
    SELECT COALESCE(array_agg(lower(x) ORDER BY ord), '{}')
    FROM unnest(f.labels) WITH ORDINALITY AS u(x, ord)
)
WHERE f.labels::text <> lower(f.labels::text);

-- Normalize labels of jobs still needing a runner the same way ingestion does:
-- lowercase and strip GitHub's implicit labels (self-hosted, linux). The old
-- case-sensitive strip left uppercased implicit labels (e.g. "Linux") in the
-- stored array, so lowercasing alone would keep them and matching would still
-- fail. Completed jobs are never re-matched, so their labels are left as
-- historical data.
UPDATE job AS j
SET labels = COALESCE((
    SELECT array_agg(lower(x) ORDER BY ord)
    FROM unnest(j.labels) WITH ORDINALITY AS u(x, ord)
    WHERE lower(x) NOT IN ('self-hosted', 'linux')
), '{}')
WHERE j.completed_at IS NULL;

-- Re-run flavor assignment for unassigned, incomplete jobs that now match a
-- flavor after lowercasing. Mirrors the application's assignment query.
UPDATE job AS j
SET assigned_flavor = (SELECT f.name
                       FROM flavor AS f
                       WHERE f.is_disabled = FALSE
                         AND f.platform = j.platform
                         AND f.labels @> j.labels
                       ORDER BY f.priority DESC, random()
                       LIMIT 1)
WHERE j.assigned_flavor IS NULL AND j.completed_at IS NULL
  AND EXISTS (SELECT 1
              FROM flavor AS f
              WHERE f.is_disabled = FALSE
                AND f.platform = j.platform
                AND f.labels @> j.labels);
