"""Enable Row-Level Security policies for multi-tenant data isolation.

Revision ID: 002_rls
Revises: 001_initial
Create Date: 2026-03-01

RLS ensures that each organization can only see its own data.
The app sets `app.current_org_id` on each session via:
    SET LOCAL app.current_org_id = '<org_uuid>';

Tables with RLS:
- users (by org_id)
- clients (by org_id)
- assessments (via clients.org_id)
- alerts (via clients.org_id)
- conversations (via users.org_id)
"""
from alembic import op

revision = "002_rls"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable RLS on tenant-scoped tables
    tables_with_org_id = ["users", "clients"]

    for table in tables_with_org_id:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # Policy: rows visible only when org_id matches session variable
        op.execute(f"""
            CREATE POLICY {table}_org_isolation ON {table}
            USING (org_id::text = current_setting('app.current_org_id', true))
        """)

        # Policy: allow insert only for matching org_id
        op.execute(f"""
            CREATE POLICY {table}_org_insert ON {table}
            FOR INSERT
            WITH CHECK (org_id::text = current_setting('app.current_org_id', true))
        """)

    # Conversations - join through users.org_id
    op.execute("ALTER TABLE conversations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversations FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY conversations_org_isolation ON conversations
        USING (
            user_id IN (
                SELECT id FROM users
                WHERE org_id::text = current_setting('app.current_org_id', true)
            )
        )
    """)

    # Assessments - join through clients.org_id
    op.execute("ALTER TABLE assessments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE assessments FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY assessments_org_isolation ON assessments
        USING (
            client_id IN (
                SELECT id FROM clients
                WHERE org_id::text = current_setting('app.current_org_id', true)
            )
        )
    """)

    # Alerts - join through clients.org_id
    op.execute("ALTER TABLE alerts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE alerts FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY alerts_org_isolation ON alerts
        USING (
            client_id IN (
                SELECT id FROM clients
                WHERE org_id::text = current_setting('app.current_org_id', true)
            )
        )
    """)

    # Organizations - only see your own org
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organizations FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY organizations_self_only ON organizations
        USING (id::text = current_setting('app.current_org_id', true))
    """)

    # Bypass policy for the app superuser role (for admin operations, migrations, etc.)
    # The application DB user should NOT be a superuser in production.
    # Create a dedicated app role if needed:
    #   GRANT normaai_app TO normaai;
    #   ALTER POLICY ... USING (...) TO normaai_app;


def downgrade() -> None:
    tables = ["organizations", "users", "clients", "conversations", "assessments", "alerts"]

    for table in tables:
        # Drop all policies
        op.execute(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_org_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_self_only ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
