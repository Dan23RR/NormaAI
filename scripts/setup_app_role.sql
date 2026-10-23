-- =============================================================================
-- NormaAI - non-superuser application role for REAL Row-Level Security
-- =============================================================================
-- PostgreSQL bypasses RLS for superusers and table OWNERS, so the policies
-- only isolate tenants when the app connects as a dedicated NON-superuser
-- role. The docker-compose.rls.yml overlay repoints the app's DATABASE_URL at
-- that role; this script creates it and grants it the least privilege it
-- needs. Alembic migrations keep running as the `normaai` owner.
--
-- HOW TO USE (one-time, on the live DB, as a SUPERUSER e.g. the `normaai` owner,
-- AFTER `alembic upgrade head` so the grants cover every table):
--   psql "$SUPERUSER_DATABASE_URL" -v app_pw="<strong-password>" -f scripts/setup_app_role.sql
-- then set the app's DATABASE_URL to normaai_app and redeploy.
--
-- !! VALIDATE ON STAGING FIRST !! Run the two-tenant isolation check in
-- docs/DEPLOY_READINESS.md (register two orgs, confirm neither sees the other's
-- rows) before switching production traffic to normaai_app.
--
-- Idempotent: safe to re-run.
--
-- NOTE: the RLS policies themselves are NOT defined here any more. They are
-- owned by Alembic (migration 007_reconcile_schema creates the canonical set
-- and drops the legacy init_db.sql ones), so every database converges on the
-- same policies regardless of how it was born. The historical sections 3-4 of
-- this script, which patched the policy gaps on servers created from
-- init_db.sql, are superseded by `alembic upgrade head`.
-- =============================================================================

-- 1) The role -----------------------------------------------------------------
-- NOTE: psql does NOT interpolate :variables inside a DO $$ ... $$ dollar-quoted
-- block, so the earlier DO-block version failed with "syntax error at :app_pw".
-- Apply the password at the psql level instead (outside any dollar-quote), where
-- :'app_pw' expands to a safely-quoted string literal.
--
-- Create the role only when missing; \gexec runs the generated CREATE statement.
SELECT format(
  'CREATE ROLE normaai_app LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE',
  :'app_pw'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'normaai_app')
\gexec

-- Always SYNC the password + attributes (idempotent). The previous
-- IF-NOT-EXISTS-only guard silently kept the old password on a re-run, so a new
-- APP_DB_PASSWORD in .env no longer matched -> the app got "password
-- authentication failed for user normaai_app". Running this unconditionally
-- always realigns it.
ALTER ROLE normaai_app WITH LOGIN PASSWORD :'app_pw' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

-- 2) Least-privilege grants ---------------------------------------------------
GRANT CONNECT ON DATABASE normaai TO normaai_app;
GRANT USAGE ON SCHEMA public TO normaai_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO normaai_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO normaai_app;
-- future tables/sequences (created by `alembic upgrade`, run as the owner)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO normaai_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO normaai_app;

-- NOTE on register: /auth/register creates the org AND the first user on a
-- no-org session. users/organizations carry no RLS (migration 007 documents
-- why: the login/refresh/me lookups run with no org context), while the
-- handler sets the org context right after flushing the new org so that any
-- tenant-scoped INSERT that follows passes its WITH CHECK under normaai_app.
