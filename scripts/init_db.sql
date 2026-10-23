-- =============================================================================
-- NormaAI - PostgreSQL container bootstrap (docker-entrypoint-initdb.d)
-- =============================================================================
-- docker-compose mounts this file at /docker-entrypoint-initdb.d/init.sql, so
-- the postgres image runs it ONCE, as the superuser, when it initialises an
-- EMPTY data directory.
--
-- THE SCHEMA DOES NOT LIVE HERE. Tables, columns, indexes, constraints and the
-- Row-Level Security policies are owned by Alembic: the ORM in
-- src/db/models.py is the single source of truth and
--
--     alembic upgrade head
--
-- creates (or reconciles, migration 007) everything. CI enforces it with
-- `alembic check` against a freshly migrated database.
--
-- History: this file used to create the tables itself. That made `alembic
-- upgrade head` fail with "relation already exists" on every container-born
-- database, the documented workaround (`alembic stamp head`) skipped the
-- migration-only tables (leads, parent_documents, citation_verifications) and
-- the 002 RLS policies, and the three definitions drifted apart. Migration 007
-- brings such databases to the ORM shape. Only what a migration cannot do
-- remains here: extensions need the superuser the init script runs as.
--
-- The non-superuser application role (normaai_app) is created separately by
-- scripts/setup_app_role.sql, which needs a password at runtime.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- uuid_generate_v4(): legacy column defaults
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- trigram text search
