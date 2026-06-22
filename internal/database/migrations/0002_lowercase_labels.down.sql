-- Copyright 2026 Canonical Ltd.
-- See LICENSE file for licensing details.

-- This migration normalizes label casing irreversibly: the original casing of
-- existing flavor and job labels is not retained, so there is nothing to roll
-- back to. Fail loudly with a clear reason rather than silently "succeeding" as
-- a no-op (which would leave the data normalized while claiming a rollback) or
-- failing with an opaque file-not-found error.
DO $$
BEGIN
    RAISE EXCEPTION 'migration 0002_lowercase_labels is irreversible: original label casing is not retained and cannot be restored';
END $$;
