-- =============================================================================
-- TEST FIXTURE - DO NOT USE IN PRODUCTION.
--
-- Verbatim copy of sections 3) and 4) of scripts/setup_app_role.sql as they
-- were before migration 007 took ownership of the Row-Level Security policies
-- (June 2026). Together with legacy_init_db.sql it reproduces the schema the
-- production server was actually running: init_db.sql + `alembic stamp head`
-- + this policy patch. The CI "schema" job applies both, stamps revision 006
-- and then runs `alembic upgrade head` + `alembic check` to prove that
-- migration 007 reconciles that starting state into the ORM shape.
--
-- The role creation and GRANT sections are omitted: they need a password and
-- are irrelevant to the schema comparison.
-- =============================================================================

-- 3) INSERT-policy gaps -------------------------------------------------------
DROP POLICY IF EXISTS organizations_insert ON organizations;
CREATE POLICY organizations_insert ON organizations FOR INSERT WITH CHECK (true);

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
