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

-- Normalize the labels of all incomplete jobs (completed_at IS NULL) the same
-- way ingestion does: lowercase and strip GitHub's implicit labels (self-hosted,
-- linux). Already-assigned jobs are included on purpose -- disabling, deleting or
-- updating a flavor resets its jobs to unassigned and re-runs assignment (see
-- updateAssignedFlavorSql), which re-reads j.labels, so labels left in mixed case
-- would re-introduce the casing mismatch for live jobs. The old case-sensitive
-- strip also left uppercased implicit labels (e.g. "Linux") in the array, which
-- lowercasing alone would keep. Completed jobs are never re-matched, so their
-- labels are kept as historical data.
UPDATE job AS j
SET labels = COALESCE((
    SELECT array_agg(lower(x) ORDER BY ord)
    FROM unnest(j.labels) WITH ORDINALITY AS u(x, ord)
    WHERE lower(x) NOT IN ('self-hosted', 'linux')
), '{}')
WHERE j.completed_at IS NULL
  -- Only touch rows that actually change: those with uppercase characters or a
  -- still-present implicit label. Mirrors the flavor guard above and avoids
  -- locking/WAL for jobs already in canonical form.
  AND (j.labels::text <> lower(j.labels::text)
       OR EXISTS (SELECT 1 FROM unnest(j.labels) AS x WHERE lower(x) IN ('self-hosted', 'linux')));

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
