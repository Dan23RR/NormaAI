-- =============================================================================
-- NormaAI - non-superuser application role for REAL Row-Level Security
-- =============================================================================
-- PostgreSQL bypasses RLS for superusers and table OWNERS, so the migration-002
-- policies only isolate tenants when the app connects as a dedicated
-- NON-superuser role. Today docker-compose connects the app as `normaai` (the
-- owner) -> RLS is inert. This script creates that role and fills the INSERT
-- policy gaps that block a non-superuser from registering / writing.
--
-- HOW TO USE (one-time, on the live DB, as a SUPERUSER e.g. the `normaai` owner):
--   psql "$SUPERUSER_DATABASE_URL" -v app_pw="<strong-password>" -f scripts/setup_app_role.sql
-- then set the app's DATABASE_URL to normaai_app and redeploy.
--
-- !! VALIDATE ON STAGING FIRST !! Run the two-tenant isolation check in
-- docs/DEPLOY_READINESS.md (register two orgs, confirm neither sees the other's
-- rows) before switching production traffic to normaai_app. A wrong policy here
-- either breaks register or silently leaks across tenants.
--
-- Idempotent: safe to re-run.
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

-- 3) INSERT-policy gaps -------------------------------------------------------
-- Migration 002 added INSERT (WITH CHECK) policies only for users/clients. A
-- non-superuser therefore cannot create an organization (register), or insert
-- alerts/assessments/conversations, under FORCE ROW LEVEL SECURITY. These are
-- no-ops for the current superuser app; they only matter once you switch to
-- normaai_app.

-- organizations: creating a NEW tenant is inherently cross-org; SELECT stays
-- restricted to your own org by the existing organizations_self_only policy.
DROP POLICY IF EXISTS organizations_insert ON organizations;
CREATE POLICY organizations_insert ON organizations FOR INSERT WITH CHECK (true);

-- alerts / assessments / conversations: allow INSERT for rows belonging to the
-- caller's org (mirrors the existing USING isolation via the parent join).
DROP POLICY IF EXISTS alerts_insert ON alerts;
CREATE POLICY alerts_insert ON alerts FOR INSERT WITH CHECK (
  client_id IN (SELECT id FROM clients
                WHERE org_id::text = current_setting('app.current_org_id', true))
);
DROP POLICY IF EXISTS assessments_insert ON assessments;
CREATE POLICY assessments_insert ON assessments FOR INSERT WITH CHECK (
  client_id IN (SELECT id FROM clients
                WHERE org_id::text = current_setting('app.current_org_id', true))
);
DROP POLICY IF EXISTS conversations_insert ON conversations;
CREATE POLICY conversations_insert ON conversations FOR INSERT WITH CHECK (
  user_id IN (SELECT id FROM users
              WHERE org_id::text = current_setting('app.current_org_id', true))
);

-- 4) SELECT/UPDATE/DELETE (USING) policy alignment ----------------------------
-- The bundled scripts/init_db.sql created USING policies for clients/alerts/
-- assessments with the STRICT current_setting('app.current_org_id') (which ERRORS
-- when the GUC is unset, e.g. a no-org session) and created NONE for conversations
-- (RLS-enabled-but-no-policy => a non-superuser sees zero rows and can write but
-- never read back). Re-create them idempotently with the missing_ok form so a
-- no-org session degrades to "no rows" instead of erroring, and so conversations
-- are actually readable by their owner. This mirrors the alembic 002/003 intent
-- for servers whose schema came from init_db.sql (or were `alembic stamp`ed).
-- RLS is intentionally NOT enabled on users/organizations here: the login path
-- looks up a user by email on a no-org session, and an org-scoped policy there
-- would break login. Those tables rely on the application-level org filter.
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS clients_org_policy ON clients;
CREATE POLICY clients_org_policy ON clients
  USING (org_id::text = current_setting('app.current_org_id', true));

DROP POLICY IF EXISTS alerts_org_policy ON alerts;
CREATE POLICY alerts_org_policy ON alerts
  USING (client_id IN (SELECT id FROM clients
                       WHERE org_id::text = current_setting('app.current_org_id', true)));

DROP POLICY IF EXISTS assessments_org_policy ON assessments;
CREATE POLICY assessments_org_policy ON assessments
  USING (client_id IN (SELECT id FROM clients
                       WHERE org_id::text = current_setting('app.current_org_id', true)));

DROP POLICY IF EXISTS conversations_org_policy ON conversations;
CREATE POLICY conversations_org_policy ON conversations
  USING (user_id IN (SELECT id FROM users
                     WHERE org_id::text = current_setting('app.current_org_id', true)));

-- NOTE on register: the /auth/register handler creates the org AND the first
-- user on a no-org session, so users_org_insert (WITH CHECK org_id =
-- current_setting('app.current_org_id')) fails because the context isn't set
-- yet. After switching to normaai_app, set the context inside register right
-- after flushing the new org:
--     await db.execute(text("SELECT set_config('app.current_org_id', :oid, true)"),
--                      {"oid": str(org.id)})
-- (a no-op under the current superuser, required under normaai_app). Verify with
-- the register test on staging.
