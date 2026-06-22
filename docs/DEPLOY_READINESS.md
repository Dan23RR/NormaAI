# Deploy readiness & re-deploy ("ricaricare") runbook

This repo (`normaai-release`) is the **canonical, complete, hardened** codebase:
all the security/correctness fixes, ~88% backend test coverage, Next.js 16
frontend, and the full deploy infra (`docker-compose.prod.yml`, `Dockerfile`,
`alembic/`, this `docs/`). The internal GTM tooling (`bizdev/`, `marketing/`,
`.planning/`) lives only in the private working copy and is **not needed by the
deployed product**.

> Why this doc exists: the server was deploying an OLDER repo that lacked every
> recent fix. This is the single source of truth to reconcile and re-deploy.

---

## 0. Repo reconciliation (do this once)

The product GitHub repo is one repository (`Dan23RR/NormaAI` ==
`Dan23RR/normaai`, GitHub names are case-insensitive). Two local clones diverged
(`normaai/` = old deployed history, `normaai-release/` = this hardened history,
**no common commits**). Make this repo canonical:

```bash
cd normaai-release
git remote -v                       # confirm origin -> the product repo
git push --force origin main        # ⚠️ overwrites the old divergent history
```

Consequences to accept before the force-push:
- The old history (and the GTM tooling that was only ever on the old remote) is
  replaced on GitHub. Keep a local copy of `normaai/` (it still has bizdev/etc.).
- On the server, the next pull is **not** a fast-forward:
  ```bash
  ssh root@<server> 'cd /opt/normaai && git fetch origin && git reset --hard origin/main'
  ```

---

## 1. Standard deploy

```bash
# on the server, from /opt/normaai
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
curl -fsS http://localhost:8000/health   # expect 200
```

Notes carried over from ADR-006:
- The embedding model is multilingual; if the corpus was seeded with the old
  English model, **re-seed**: `... run --rm api python -m src.pipeline --action seed --recreate` (~40 min; run in tmux).
- `APP_ENV=production` requires real RSA JWT keys + a real `APP_SECRET_KEY`
  (HS256 + `change-me` are fatal by design). They are already on the server `.env`.

---

## 2. 🔴 Enable real multi-tenant isolation (RLS) — the #1 readiness gap

Today the app connects as the Postgres **owner** (`normaai`), so RLS is bypassed
and tenant isolation is application-level only. The code-side groundwork is now
done: `/auth/register` sets `app.current_org_id` after the org flush (PostgreSQL
only), and the two-tenant pool-isolation test (`tests/test_rls_pool_isolation.py`)
now **runs in CI** against a provisioned non-superuser role, so a future
regression fails the build. What remains is the operational switch:

1. Create the non-superuser role + fill the INSERT-policy gaps (one-time, as a
   superuser, on the live DB):
   ```bash
   psql "$SUPERUSER_DATABASE_URL" -v app_pw="'<strong-app-password>'" -f scripts/setup_app_role.sql
   ```
2. **Validate on staging** with a two-tenant check before prod - run the bundled
   harness against the running instance:
   ```bash
   python scripts/validate_rls_two_tenant.py http://localhost:8000
   ```
   It registers org A + org B, creates a client for each, and asserts that
   register + create WORK under the role (INSERT policies + register `set_config`
   correct) AND that neither org sees the other's client by list or by id (no
   IDOR). Exit 0 = PASSED. Also confirm the role itself is non-privileged:
   `psql "$DATABASE_URL" -c "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;"` → `f | f`.
3. Switch the app to the non-superuser role with the RLS overlay (set
   `APP_DB_PASSWORD` in `.env` first; migrations still run as the `normaai`
   owner, the overlay only repoints the long-lived app process):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml \
     -f docker-compose.rls.yml up -d
   ```

Until step 3 is done + verified, a cross-tenant leak is possible — do not put
two real customers on the instance before this.

---

## 3. Other readiness items

- **Fresh-content guarantee (#3)**: `superseded_by` is written only at seed and
  never updated, and the acquisition scheduler is OFF by default
  (`ACQUISITION_SCHEDULER_ENABLED=false`). So the corpus is frozen at last seed
  and abrogated law can be served as current. Until amendment-detection is built,
  either keep the "as-of <seed date>" caveat visible in the UI/PDF, or enable the
  scheduler and accept best-effort refresh.
- **DNS**: point `normaai.org` + `api.normaai.org` (Cloudflare DNS, proxy OFF so
  Vercel/the server can issue TLS). The funnel + backend don't resolve until then.
- **Secrets**: rotate any key that ever sat in a shared `.env` (Resend,
  OpenRouter, etc.). The server `.env` is gitignored in both repos.
- **Claims vs reality (#5)**: README/landing should not promise more than is
  enabled. After steps 1-2 (anti-hallucination prompts fixed) and step 2 (RLS),
  the "verified citations / multi-tenant" claims become true; keep "real-time"
  honest until #3 is built.
- **Brand (#4)**: resolve before broad outreach (see
  `Brand_Risk_Assessment_2026-06-13.md`).

---

## 4. Quick checklist

- [ ] `git push --force origin main` from `normaai-release` (accept §0)
- [ ] server `git reset --hard origin/main`
- [ ] build + `alembic upgrade head` + `up -d` + `/health` 200
- [ ] re-seed corpus if the embedding model changed
- [ ] RLS: run `scripts/setup_app_role.sql`, apply the register note, staging
      two-tenant test, then switch `DATABASE_URL` to `normaai_app`
- [ ] DNS for normaai.org / api.normaai.org
- [ ] rotate shared secrets
- [ ] decide the brand before Wave-2 outreach
