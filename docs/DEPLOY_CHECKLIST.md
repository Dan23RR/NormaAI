# Production deploy checklist (backend)

Bring `api.normaai.org` back in under an hour: a server, one DNS record, the corpus as Qdrant
snapshots, the bootstrap script, the GitHub deploy secrets, one Vercel variable, a final test.
`scripts/bootstrap_hetzner.sh` does the server work; [RUNBOOK.md](RUNBOOK.md) covers what comes after.
This checklist replaces the older manual guides: [DEPLOY_HETZNER.md](DEPLOY_HETZNER.md) still
describes a 4 GB server and mpnet, and the `up -d` of [DEPLOY_READINESS.md](DEPLOY_READINESS.md)
§1 starts the app without the RLS overlay, which production refuses.

| Step | Where | Time |
|---|---|---|
| 1. Model and server | Hetzner console | 5 min |
| 2. DNS record | Cloudflare | 2 min, plus up to 5 for the old TTL |
| 3. Corpus snapshots | laptop | 5 min, plus the upload |
| 4. Bootstrap | server (SSH) | 25-35 min |
| 5. Deploy secrets | GitHub | 5 min |
| 6. API address | Vercel | 5 min |
| 7. Final test | laptop | 5 min |

Before you start: an API key for the answering model (Gemini or Anthropic), an SSH key pair on
the laptop (`ssh-keygen -t ed25519`), and Docker Desktop running for step 3. The bootstrap is
downloaded from `main`, so deploy from a `main` that contains this checklist.

## 1. Model and server

The bootstrap asks which search model the API serves (step 4). Both collections travel in the
snapshots of step 3, so either choice works without re-embedding, and switching later is a
change of `.env` (RUNBOOK §3). In the container the two models need about the same memory.

| | e5, recommended | mpnet, the alternative |
|---|---|---|
| Model | `intfloat/multilingual-e5-large` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`, the code default |
| Golden v2 end to end (2026-10-27, Haiku 5.5) | 89 / 101 | 81 / 101 |
| AI Act Art. 50 for the chatbot question without an article number | found | not among the first 30 candidates |
| Collection | `eu_regulations_e5` | `eu_regulations` |
| Model in the image | 2.1 GB | 1.1 GB |
| App container, 1 worker | 1.6 GiB | 1.8 GiB |
| App container, 2 workers | 3.2 GiB | 3.7 GiB |
| Server | 8 GB recommended; 4 GB holds 1 worker | 8 GB recommended; 4 GB holds 1 worker |

Golden v2 and retrieval figures: docs/MODELS.md, sections 2.1 and 2.2 (a few questions change
from run to run). Memory: `docker stats` of the app container in the production image, read-only
root, after the model warm-up, in the local dress rehearsal of 2026-11-09; Postgres, Qdrant with
both collections, Redis and Caddy added 0.25 GiB. Each uvicorn worker holds its own copy of the
model. The bootstrap writes `WEB_CONCURRENCY=1` and `APP_MEMORY_LIMIT=4G`; for 2 workers set
`WEB_CONCURRENCY=2` and `APP_MEMORY_LIMIT=6G` in `.env` on an 8 GB server. On 4 GB one worker
fits, with little room for long answers, the image builds of the deploys, the monitoring stack
or the reranker later (0.6 GB more per worker, docs/MODELS.md); the bootstrap asks for
`ALLOW_LOW_MEMORY=1` below 8 GB.

Prices from hetzner.com on 2026-11-03, per month, excluding VAT, IPv4 included:

| Type | vCPU | RAM | Disk | EUR/month | Note |
|---|---|---|---|---|---|
| CX33 | 4 shared | 8 GB | 80 GB | 8.99 | Cheapest recommended size. Cost-optimized line: reported not orderable since September 2026 |
| CPX32 | 4 shared | 8 GB | 160 GB | 35.99 | Regular performance, when CX33 cannot be ordered |
| CCX13 | 2 dedicated | 8 GB | 80 GB | 43.49 | Dedicated vCPUs |
| CX43 | 8 shared | 16 GB | 160 GB | 16.49 | Room for 2 workers, the reranker or the monitoring stack |
| CX23 | 2 shared | 4 GB | 40 GB | 5.99 | 1 worker only, little headroom; same availability as CX33 |
| CPX22 | 2 shared | 4 GB | 80 GB | 19.99 | 1 worker only, little headroom |

Availability changes: the console shows which types can be created. In the Hetzner console,
Create Server:

- Location Nuremberg or Falkenstein (data in Germany); Helsinki is the other EU option.
- Image Ubuntu 24.04. Your SSH public key, no root password.
- Firewall: inbound TCP 22, 80 and 443 only (the bootstrap also enables `ufw` with these).
- Backups (20% of the server price) are worth it: the nightly Postgres dumps stay on the disk.

Write down the server's IPv4.

## 2. DNS record

Cloudflare, zone `normaai.org`, DNS, Records: edit the `api` record of type A.

- Content: the server's IPv4. Proxy status: **DNS only** (grey cloud): Caddy obtains the Let's
  Encrypt certificate itself and the orange proxy would get in the way. TTL: Auto.
- No AAAA record is needed.

Do it before anything else, and leave no other A or AAAA record for `api`: a record that points to
an address you do not hold lets whoever holds it obtain a certificate for the name. Check from the
laptop, whose resolver answers 127.0.0.1 for this name:

```powershell
curl.exe -s -H "accept: application/dns-json" "https://cloudflare-dns.com/dns-query?name=api.normaai.org&type=A"
```

## 3. Corpus snapshots

The server does not re-embed the corpus: with e5 that takes hours of CPU. It restores two Qdrant
snapshots taken on the laptop, where the volume `normaai_localtest_qdrant_data` holds both
collections in the Qdrant 1.20 format (5,852 points each, corpus of 2026-10-24):

- `eu_regulations_e5`: multilingual-e5-large, the one the API searches;
- `eu_regulations`: mpnet, kept as the fallback model.

Snapshots are taken from a copy of the volume, so Qdrant never runs on the original. In
PowerShell, from an empty folder:

```powershell
docker volume create normaai_snapshot_src
docker run --rm -v normaai_localtest_qdrant_data:/from:ro -v normaai_snapshot_src:/to redis:7-alpine sh -c "cp -a /from/. /to/"
docker run -d --name normaai-snapshot-src -p 127.0.0.1:16335:6333 -v normaai_snapshot_src:/qdrant/storage qdrant/qdrant:v1.20.0
while (-not (curl.exe -fs http://127.0.0.1:16335/readyz)) { Start-Sleep 1 }
New-Item -ItemType Directory -Force snapshots | Out-Null
foreach ($c in "eu_regulations_e5", "eu_regulations") {
    $name = (curl.exe -fsS -X POST "http://127.0.0.1:16335/collections/$c/snapshots?wait=true" | ConvertFrom-Json).result.name
    curl.exe -fsS -o "snapshots\$c.snapshot" "http://127.0.0.1:16335/collections/$c/snapshots/$name"
}
Get-FileHash snapshots\*.snapshot
tar.exe -czf normaai-snapshots.tgz -C snapshots eu_regulations_e5.snapshot eu_regulations.snapshot
docker rm -f normaai-snapshot-src; docker volume rm normaai_snapshot_src
```

Each snapshot is about 400 MB, mostly empty WAL segments: the archive is about 110 MB. The
block above took 5 minutes on the laptop (2026-11-03). Send it:

```powershell
ssh root@<IP> "mkdir -p /opt/normaai-snapshots"
scp normaai-snapshots.tgz root@<IP>:/opt/normaai-snapshots/
ssh root@<IP> "cd /opt/normaai-snapshots && tar -xzf normaai-snapshots.tgz && rm normaai-snapshots.tgz && sha256sum *.snapshot"
```

The hashes must match `Get-FileHash`. The file names must stay `<collection>.snapshot`. Keep
the snapshots: they are also the Qdrant backup (RUNBOOK §3).

## 4. Bootstrap

```bash
ssh root@<IP>
curl -fsSL https://raw.githubusercontent.com/Dan23RR/NormaAI/main/scripts/bootstrap_hetzner.sh -o bootstrap.sh
bash bootstrap.sh
```

It asks for the answering provider (`gemini` or `anthropic`), its API key (not echoed), an
optional Resend key, the first administrator's email and the search model (`e5` or `mpnet`,
step 1). Then, with every step numbered:

| Step | What | Time |
|---|---|---|
| 1-2 | Docker, swap, security updates, firewall; clone into `/opt/normaai` | 3-5 min |
| 3 | `.env` with fresh secrets (permissions 600), the model settings, `COMPOSE_FILE` | seconds |
| 4 | Image build: about 0.6 GB of Python packages and the model from Hugging Face (2.1 GB for e5, 1.1 GB for mpnet); JWT keys | 10-15 min on a server; 85 min on the laptop at 1-2 MB/s |
| 5-6 | Postgres, Qdrant, Redis, migrations, the non-superuser role `normaai_app` | 2 min |
| 7 | Restore of the two snapshots; `CORPUS_AS_OF` from the collection | 2-4 min |
| 8 | App and Caddy with the RLS overlay: the app listens once the model is loaded (31-90 s with e5), then Caddy starts and gets the Let's Encrypt certificate | 2-3 min |
| 9 | Nightly backup cron, health checks, the administrator's invite code | seconds |

The invite code is printed once: keep it for step 7. A failed step can be fixed and the script run
again: it keeps `.env`, the keys and the data, and skips the restore of collections that already
have points.

Then copy the server's secrets off it, into a password manager, never into the repo:

```powershell
scp root@<IP>:/opt/normaai/.env normaai-prod.env
scp root@<IP>:/opt/normaai/data/jwt_private.pem normaai-prod-jwt_private.pem
```

With `anthropic` the API answers with `claude-sonnet-5-5`, the default of `src/config.py`; the
six-month plan uses Haiku 5.5 as the default. To change it, set `ANTHROPIC_MODEL` in
`/opt/normaai/.env` and run `docker compose up -d app`.

## 5. GitHub: automatic deploys

`.github/workflows/deploy.yml` deploys every push to `main` over SSH and waits until
`https://api.normaai.org/health` reports the new commit. Without its secrets it skips with a
notice. Create a key pair used only by GitHub, on the laptop (press Enter at the passphrase
prompts: GitHub cannot type one):

```powershell
ssh-keygen -t ed25519 -f normaai_deploy -C github-actions-deploy
scp normaai_deploy.pub root@<IP>:/tmp/
ssh root@<IP> "cat /tmp/normaai_deploy.pub >> /root/.ssh/authorized_keys && rm /tmp/normaai_deploy.pub"
ssh-keyscan -p 22 <IP>
```

Repository, Settings, Secrets and variables, Actions, New repository secret:

| Secret | Value | |
|---|---|---|
| `DEPLOY_HOST` | the server's IPv4 | required |
| `DEPLOY_USER` | `root`, or a user that can run docker in `/opt/normaai` | required |
| `DEPLOY_SSH_KEY` | the whole content of `normaai_deploy` (the private key) | required |
| `DEPLOY_KNOWN_HOSTS` | the `ssh-keyscan` output | recommended: without it the host key is trusted on first use |
| `DEPLOY_PORT` | only if SSH is not on 22 | optional |

The job runs in the GitHub environment `production`, which GitHub creates on the first run. Test
it: Actions, Deploy, Run workflow on `main`. Then delete `normaai_deploy` from the laptop.

## 6. Vercel

Project settings:

- Environment Variables: `NEXT_PUBLIC_API_BASE_URL` = `https://api.normaai.org` for
  Production. Delete `NEXT_PUBLIC_API_URL` if it is still there: the frontend ignores it since v2
  and it points at the old server.
- Build and Deployment, Node.js Version: 22.x, as in the CI.
- Deployments, the latest production deployment, Redeploy: `NEXT_PUBLIC_*` variables are read
  when the site is built, so the login page stays disabled until this redeploy.

Preview deployments reach the API only if their origin is in `CORS_ORIGINS` (server `.env`).

## 7. Final test

From the repository on the laptop, with the SHA that `/health` must report (the short SHA of
`main`):

```powershell
git fetch origin
pwsh scripts/verify_live_site.ps1 -BaseUrl https://normaai.org -ApiVersion (git rev-parse --short=7 origin/main)
```

Every check must pass: the site, `/health`, `/readyz` (Qdrant, model key and corpus up), the
corpus in `/api/v1/stats`, CORS from normaai.org, and the site's CSP naming the API. (Run
against a local `next start`, the `/codex` check fails: Vercel does that redirect, from
`vercel.json`.) Then
register at https://normaai.org/login with the invite code, ask a question in Chiedi, and check
that the answer quotes a verified passage.

## Known limits

- **PDF uploads index nothing.** `POST /api/v1/documents/upload` with a PDF answers 200, "Document
  processed", with `chunks_indexed: 0`. The PDF goes to docling, which needs its layout models from
  Hugging Face; the image does not have them and the runtime is offline with a read-only root, so
  docling fails ("Cannot find an appropriate cached snapshot folder") and the log says "No PDF
  processor available". The user sees no error. HTML uploads and the corpus are not affected.
  Seen in the dress rehearsal with the Codex PDF; not fixed.

## If something fails

| Symptom | Likely cause | Fix |
|---|---|---|
| Caddy has no certificate, browser warns | DNS not on the new IP yet, orange proxy, port 80 closed | Step 2, Hetzner firewall; `docker compose logs caddy` |
| Bootstrap stops at step 8, app unhealthy | Configuration | `docker logs --tail 100 normaai-app`, RUNBOOK §2 |
| `/readyz` says `corpus: down` | Collection empty or missing | Step 3 and `RESTORE=1 bash bootstrap.sh`, or the curl restore in RUNBOOK §3 |
| `/readyz` says `llm: down` | No key for the provider | Key in `/opt/normaai/.env`, then `docker compose up -d app` |
| Login page says accounts are suspended | Vercel built without `NEXT_PUBLIC_API_BASE_URL` | Step 6, redeploy |
| CORS error in the browser console | Site origin missing from `CORS_ORIGINS` | Server `.env`, then `docker compose up -d app` |
| Deploy job: `Permission denied (publickey)` | Wrong key or user | Step 5 |
