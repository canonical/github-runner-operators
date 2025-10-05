DROP TABLE IF EXISTS job;
DROP TABLE IF EXISTS flavor;
DROP TABLE IF EXISTS auth;

DROP INDEX auth_token_idx;
DROP INDEX auth_name_idx;

DROP INDEX flavor_platform_name_idx;
DROP INDEX flavor_platform_labels_gin;
DROP INDEX flavor_platform_priority_pidx;

DROP INDEX job_platform_id_idx;
DROP INDEX job_platform_created_at_idx;
DROP INDEX job_in_progress_platform_created_pidx;
DROP INDEX job_platform_assigned_flavor_idx;
DROP INDEX job_in_progress_by_platform_flavor_pidx;
