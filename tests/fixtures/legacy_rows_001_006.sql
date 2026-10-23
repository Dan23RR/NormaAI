-- =============================================================================
-- TEST FIXTURE - DO NOT USE IN PRODUCTION.
--
-- Rows that are valid under the Alembic 001..006 schema but NOT under the ORM
-- shape: NULLs in columns the ORM declares NOT NULL, the legacy column names
-- (alerts.summary, amendments.discovered_at, assessments.created_at), a
-- VARCHAR[] array and a nullable alerts.client_id. The CI "schema" job loads
-- them into a database at revision 006 and then runs `alembic upgrade head`:
-- migration 007 must backfill and rename without losing a row, and
-- `alembic check` must come back clean afterwards.
-- =============================================================================

INSERT INTO organizations (id, name, slug, plan, max_clients, created_at, updated_at)
VALUES ('11111111-1111-1111-1111-111111111111', 'Legacy Org', 'legacy-org', NULL, NULL, NULL, NULL);

INSERT INTO users (id, org_id, email, hashed_password, name, role, is_active, created_at)
VALUES ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111',
        'legacy@example.com', 'x', NULL, NULL, NULL, NULL);

INSERT INTO clients (id, org_id, name, jurisdictions, applicable_frameworks, created_at, updated_at)
VALUES ('33333333-3333-3333-3333-333333333333', '11111111-1111-1111-1111-111111111111',
        'Legacy Client', ARRAY['IT']::varchar[], NULL, NULL, NULL);

INSERT INTO regulations (id, celex, title, framework, is_in_force, created_at, source)
VALUES ('44444444-4444-4444-4444-444444444444', '32022L2464', NULL, NULL, NULL, NULL, NULL);

INSERT INTO amendments (id, original_regulation_id, amending_celex, discovered_at)
VALUES ('55555555-5555-5555-5555-555555555555', '44444444-4444-4444-4444-444444444444',
        '32025L0794', NULL);

INSERT INTO alerts (id, client_id, regulation_id, severity, framework, title, summary,
                    actions_required, is_read, created_at)
VALUES ('66666666-6666-6666-6666-666666666666', '33333333-3333-3333-3333-333333333333',
        '44444444-4444-4444-4444-444444444444', NULL, NULL, NULL, NULL,
        ARRAY['review']::varchar[], NULL, NULL);

INSERT INTO assessments (id, client_id, framework, gaps, recommendations, created_at)
VALUES ('77777777-7777-7777-7777-777777777777', '33333333-3333-3333-3333-333333333333',
        'CSRD', NULL, NULL, NULL);

INSERT INTO conversations (id, client_id, user_id, messages, created_at, updated_at)
VALUES ('88888888-8888-8888-8888-888888888888', '33333333-3333-3333-3333-333333333333',
        '22222222-2222-2222-2222-222222222222', NULL, NULL, NULL);

INSERT INTO crawl_jobs (id, job_type, status, regulations_processed, amendments_found, created_at)
VALUES ('99999999-9999-9999-9999-999999999999', 'full_crawl', NULL, NULL, NULL, NULL);

INSERT INTO citation_verifications (reference, reference_type, verified, is_current, source,
                                    last_checked_at, created_at)
VALUES ('32022L2464', 'celex', NULL, NULL, 'eurlex', NULL, NULL);

INSERT INTO leads (email, org_name, source, status, created_at)
VALUES ('lead@example.com', 'Legacy Lead Org', 'codex_download', 'new', now());

INSERT INTO parent_documents (celex, framework, article_number, full_text, content_hash,
                              created_at, updated_at)
VALUES ('32022L2464', 'CSRD', 'Art. 1', 'Full text', repeat('a', 64), NULL, NULL);
