# Backup and restore

One script, `scripts/backup.sh`, run by cron every night on the server. What it protects
depends on one thing: whether a restic repository is configured.

- **With restic** (`RESTIC_REPOSITORY` and `RESTIC_PASSWORD_FILE` set): the database, the
  search index and the server's secrets leave the server every night, encrypted.
- **Without restic**: only a dump of the database is kept, unencrypted, on the server's own
  disk. A lost or cancelled server takes it along. This is the state the old server was in
  when it was cancelled in September 2026, and the state a new server is in until step 3 of
  [DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md) is done. The script says so at every run.

State of this document on 2026-11-18: the scripts are written and tested against stand-ins
for Docker, restic and Qdrant (`tests/test_ops_scripts.py`). **No backup has been sent to
a real repository and no restore has been done yet.** Sections 5 and 6 say which figures
are measured and which are not.

## 1. What is backed up, and where

| Data | Where it lives | On the server's disk | Off the server (restic only) |
|---|---|---|---|
| PostgreSQL: every table (accounts, organisations, invites, clients, conversations, assessments, alerts, Codex requests and the rest) | volume `postgres_data` | `pg_dump` in custom format, `/opt/normaai/backups/normaai_<date>_<time>.dump`, readable by root only, checked with `pg_restore --list` | the same dump |
| Qdrant: the corpus and the passages indexed from the documents tenants upload | volume `qdrant_data` | no | one snapshot per collection, taken through Qdrant's snapshot API, named `<collection>.snapshot` |
| `.env`: the server's configuration, with every password and API key | `/opt/normaai/.env` | no | yes |
| `MANIFEST.txt`: date, code revision, schema revision, Qdrant version, points of each collection, size of each file | written at each run | no | yes |

The corpus could be rebuilt from EUR-Lex with `python -m src.pipeline --action seed`, in
hours of CPU with multilingual-e5-large. The passages of tenants' documents could not:
for them the Qdrant snapshot is the only copy.

## 2. What is not covered

- **Anything, without restic.** See the top of this page.
- **What changed since the last run.** The job runs once a day.
- **A failed run while the app is down is not reported.** The script tells the operator
  through the app container (section 4); without it the failure stays in
  `/var/log/normaai-backup.log`, and the external check of
  [uptime.yml](../.github/workflows/uptime.yml) reports the API down instead. A job that
  stops running at all (cron gone, server gone) is noticed only with `BACKUP_HEARTBEAT_URL`.
- **The audit trail.** Audit events are log lines of the app container (logger
  `normaai.audit`), not rows of a table. Docker keeps them until the container is
  recreated, which every deploy does. They are in no backup.
- **Redis** (cache, revoked tokens, login lockout counters): not backed up, by design.
- **The JWT key pair** in `data/`: not backed up, on purpose. A rebuilt server gets a new
  pair from the bootstrap, so every user signs in again and no session that was revoked
  before the loss can come back.
- **The official texts in `data/texts`** (`NORMAAI_TEXT_CACHE`), downloaded by the document
  check: not backed up. They are copies of public texts, downloaded again when needed.
- **The crontab** of the server: not backed up. The bootstrap writes its lines again.
- **Caddy's certificates**: not backed up. Caddy obtains new ones when it starts.
- **Prometheus and Grafana data**: not backed up.
- **Deletion at the storage.** The storage credentials are on the server. Whoever holds
  them can delete the copies: "The restic backup program is not designed to protect
  against attackers deleting files at the storage location"
  ([restic references](https://restic.readthedocs.io/en/stable/100_references.html)).
  Versioning or an object lock on the bucket would cover this; these scripts do not set
  it up.
- **A lost repository password.** Without it no copy can be read (section 3).
- **A search on the restored index.** The restore test loads every collection snapshot
  into a throwaway Qdrant and checks its points (section 6.1), but runs no query: that needs
  the embedding model. A snapshot loads on the same minor version of Qdrant or on the next
  one ([Qdrant documentation](https://qdrant.tech/documentation/snapshots/)); `MANIFEST.txt`
  records the version that made it, and the test uses the image of the running Qdrant.
- **The server backups Hetzner sells are not an off-site copy.** "Backups are bound to a
  single server and will automatically be deleted if you delete the server"
  ([Hetzner FAQ](https://docs.hetzner.com/cloud/servers/backups-snapshots/faq)). They help
  against a mistake on a server that still exists, not against losing the server.
- **The frontend** is on Vercel and its code in GitHub: nothing of it is on the server.

## 3. Encryption, and the one secret to keep elsewhere

restic encrypts on the server, before anything is sent: "All data stored by restic in the
repository is encrypted with AES-256 in counter mode and authenticated using Poly1305-AES"
([restic references](https://restic.readthedocs.io/en/stable/100_references.html)). The
keys are protected by the repository password, the content of `RESTIC_PASSWORD_FILE`: the
same page says the content of the stored files "cannot be accessed without a password for
the repository". The storage provider holds encrypted data only.

**Keep the repository password off the server too**, in a password manager. The copy of
`.env` is inside the encrypted backup, so this password is the one secret that opens
everything else, and "Losing your password means that your data is irrecoverably lost"
([restic documentation](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html)).
The bootstrap never generates it: it asks for a file you created.

**Keep the repository and its keys outside the hosting account.** In September 2026 the whole
hosting account was lost, not only the server: a Storage Box, a bucket or the server's own
backups in that account would have gone with it. So:

- the repository lives at another provider, under a login of its own (an S3-compatible
  bucket or an SFTP account), not in the account that rents the server. `scripts/backup.sh`
  warns at every run when `RESTIC_REPOSITORY` is a Hetzner address (`your-storagebox.de`,
  `your-objectstorage.com`, `hetzner`); a Hetzner account that is not the server's can be
  acknowledged with `BACKUP_SAME_PROVIDER_OK=1` in `/etc/normaai/backup.env`;
- the repository address, its password and the storage key are in the password manager, not
  only in `/etc/normaai/`: the server needs them to write, a rebuild needs them to read;
- the restore drill (section 6.4) opens the repository from another machine with those copies
  alone, so a password that drifted on the server is found before it is needed.

Not encrypted:

- the local dumps in `/opt/normaai/backups/`, on the same disk as the database they copy;
- `backups/offsite/`, the staging directory that holds a plain copy of `.env` and the
  snapshots while a run lasts. The script removes it on every exit, failures included.

The backup settings are in `/etc/normaai/backup.env`, readable by root only, and not in
`.env`: `.env` is handed to the app container, which has no use for the storage
credentials.

## 4. Schedule, retention, and knowing that it ran

- **When**: every night at 02:00, server time. The cron line is
  `0 2 * * * bash /opt/normaai/scripts/backup.sh >> /var/log/normaai-backup.log 2>&1`,
  installed by `bash scripts/backup.sh --install-cron` (the bootstrap runs it). It goes
  through `bash` because a deploy resets file modes to what git holds.
- **Retention: 30 days**, for the local dumps and for the off-site copies alike
  (`BACKUP_RETENTION_DAYS`). Each run deletes what is older than 29 days, so no copy
  reaches 30 days plus a run. Off the server this is
  `restic forget --keep-within 29d --prune`, which counts from the newest snapshot: if
  the nightly job stops, nothing more is deleted.
- **Personal data**: a deleted account or record stays in the copies for up to 30 days.
  The privacy notice of the site says 30 days: change the two together, never one alone.
- **Knowing that it ran**: `backups/last_success` holds the time and the mode (`off-site`
  or `local only`) of the last complete run. With `BACKUP_HEARTBEAT_URL` in
  `/etc/normaai/backup.env`, the script fetches that address after every complete
  off-site run: point it at a service that warns you when the fetch stops coming. Without
  it, the monthly restore test is the check: it fails when the newest copy is older than 36
  hours.
- **Knowing that it failed**: a run that stops (a failed step, or a setting it cannot use)
  sends the reason and the warnings of the run to the operator, through the app container:
  `docker exec -i normaai-app python -m src.ops_alerts backup ...`, which writes a Sentry event
  with `SENTRY_DSN` and emails `OPS_ALERT_EMAIL` with `RESEND_API_KEY` (both in `.env`). No
  secret value is in the message. `BACKUP_ALERTS=0` turns it off; when the app container does
  not answer, the log says that nobody was told.
- **Size**: the two collections of 2026-11-03 gave snapshots of about 400 MB each, mostly
  empty write-ahead-log segments, about 110 MB once compressed
  ([DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md), step 4). What restic uploads after the first
  night has not been measured.
- A run with a Qdrant problem still sends the database, then exits with an error. A run
  that cannot reach the repository exits with an error and keeps the local dump.

## 5. How much can be lost, how long a rebuild takes

**Data loss (RPO).**

- With restic and a nightly job that works: at most the changes since 02:00, that is up
  to 24 hours, plus the minutes a run takes.
- Each night the job fails adds a day, and section 2 says who is told: nobody, by default.
- Without restic: up to 24 hours for a mistake on a server that still exists; everything
  when the server is lost.

**Time to be back (RTO): not measured.** No rebuild from a backup has been done, and the
bootstrap in its present form has not run on a server: the dress rehearsal of 2026-11-09
was on a laptop.
[DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md) estimates 25 to 35 minutes for the bootstrap on
a server with the snapshots at hand. A rebuild adds the download of the copy, the load of
the database and the manual steps of section 6.3, none of them timed.

Plan for one to two hours of work by someone who has the repository password and the
storage credentials at hand, and replace this estimate with the time of the first real
rebuild. Putting back last night's database on a server that still runs (section 6.2)
should take minutes for a database of pilot size; that is not measured either.

## 6. Restore

### 6.1 The restore test

```bash
bash /opt/normaai/scripts/restore_test.sh
```

Cron runs it on the 1st of every month at 05:00 (`bash scripts/backup.sh --install-cron`
writes the line, log in `/var/log/normaai-restore-test.log`) and a failure reaches the
operator like a failed backup (section 4). Run it by hand after the first backup, and write
the outcome in the post-mortem log of [RUNBOOK.md](RUNBOOK.md). It touches neither the running
database nor the running index. It:

1. takes the latest off-site snapshot (or the newest local dump when restic is not
   configured, and says so);
2. fails when that copy is older than 36 hours (`RESTORE_TEST_MAX_AGE_HOURS`);
3. runs `restic check` and verifies that the snapshot holds the Postgres dump, a snapshot
   of at least one Qdrant collection and the copy of `.env`, and that this copy names the
   settings a rebuild needs (`APP_SECRET_KEY`, `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`,
   `LLM_PROVIDER` and its key): names only, no value is printed;
4. loads the dump into a throwaway Postgres container (the image of the running one, no
   network, removed at the end), checks that `alembic_version`, `organizations` and `users`
   exist and prints the row count of every table. Compare the counts with what you expect:
   the script cannot know;
5. loads every Qdrant snapshot of the copy into a throwaway Qdrant container (the image of
   the running one, published on 127.0.0.1 only, without telemetry, removed at the end) and
   checks that each collection has its points again: the number `MANIFEST.txt` recorded at
   backup time, or more than zero for a copy made before the counts were recorded.
   `RESTORE_TEST_QDRANT=0` lists the snapshots without loading them;
6. prints how long each phase took (the copy, Postgres, Qdrant): the measured part of a
   rebuild.

It exits with 0 only when every check passed.

### 6.2 Putting back the database on a server that still runs

For a mistake: rows deleted, a migration gone wrong. Everything written after the dump is
lost. On the server:

```bash
cd /opt/normaai
# The dump to load: a local one from backups/, or the one in the latest off-site copy:
#   set -a; . /etc/normaai/backup.env; set +a
#   restic dump --host normaai --tag normaai latest /opt/normaai/backups/offsite/postgres/normaai.dump > /root/normaai.dump
DUMP=backups/normaai_YYYYMMDD_HHMMSS.dump

docker compose stop app
# What is there now, in case the restore is the mistake (pruned after 30 days like the others).
docker exec normaai-postgres pg_dump -U normaai -d normaai -Fc --no-owner > "backups/normaai_before_restore_$(date +%Y%m%d_%H%M%S).dump"
# Into an empty database, so that nothing of the present one survives next to the dump.
docker exec normaai-postgres dropdb -U normaai --force normaai
docker exec normaai-postgres createdb -U normaai normaai
docker exec -i normaai-postgres pg_restore -U normaai -d normaai --no-owner --exit-on-error < "$DUMP"
# The dump may be older than the code: bring the schema to the code's revision, as the
# owner, in the one-shot migrate service.
docker compose run --rm migrate
# The new database needs the application role's grants again (the script can be re-run).
set -a; . ./.env; set +a
docker compose exec -T postgres \
  psql -U normaai -d normaai -v app_pw="$APP_DB_PASSWORD" < scripts/setup_app_role.sql
docker compose up -d app
docker exec normaai-app curl -fsS http://localhost:8000/readyz
```

The index is not rolled back: passages indexed from uploads after the dump stay in Qdrant.
To put a collection back as well, upload its snapshot ([RUNBOOK.md](RUNBOOK.md) section 3).
These commands have not been run on a server yet; the restore test of 6.1 exercises the
same `pg_restore` into an empty database.

### 6.3 Rebuilding a lost server

You need the repository address, the repository password and the storage credentials,
all from outside the server.

1. A new server and its DNS record: steps 1 and 2 of
   [DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md). The Qdrant snapshots of its step 4 come
   from the backup instead.
2. Take the latest copy, on the new server, as root:

   ```bash
   apt-get update && apt-get install -y restic git
   install -d -m 700 /etc/normaai
   nano /etc/normaai/restic-password      # the repository password, then save
   chmod 600 /etc/normaai/restic-password
   export RESTIC_REPOSITORY='<the repository address>'
   export RESTIC_PASSWORD_FILE=/etc/normaai/restic-password
   export AWS_ACCESS_KEY_ID='<key id>' AWS_SECRET_ACCESS_KEY='<key>'   # S3-compatible storage only
   restic snapshots --host normaai --tag normaai
   restic restore latest --host normaai --tag normaai --target /root/restore
   R="$(dirname "$(find /root/restore -name MANIFEST.txt)")" && cat "$R/MANIFEST.txt"
   ```

3. Put the pieces where the bootstrap looks for them, then run it without its first
   backup: the database is still empty.

   ```bash
   git clone https://github.com/Dan23RR/NormaAI.git /opt/normaai
   install -m 600 "$R/config/env" /opt/normaai/.env
   mkdir -p /opt/normaai-snapshots
   cp "$R"/qdrant/*.snapshot /opt/normaai-snapshots/
   SKIP_FIRST_BACKUP=1 bash /opt/normaai/scripts/bootstrap_hetzner.sh
   ```

   The bootstrap keeps the `.env` it finds (and hands it, with the clone, to the user
   `deploy`), creates a new JWT key pair, loads the collections and, with the `RESTIC_*`
   variables still exported, writes `/etc/normaai/backup.env` and installs the nightly job
   and the monthly restore test. Ignore the invite code it prints: the database you are about
   to load has its own users. Export `DEPLOY_SSH_PUBKEY` too, or install the deploy key
   afterwards (DEPLOY_CHECKLIST.md step 6), and update the `DEPLOY_HOST` and
   `DEPLOY_KNOWN_HOSTS` secrets of GitHub for the new server.
4. Load the database: section 6.2 from `docker compose stop app`, with
   `DUMP="$R/postgres/normaai.dump"`.
5. Back up and test, then remove the plain copy:

   ```bash
   bash /opt/normaai/scripts/backup.sh
   bash /opt/normaai/scripts/restore_test.sh
   rm -rf /root/restore
   ```

6. The final test of [DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md), and the repository
   variables of the uptime check if the address changed.

If 02:00 passes between steps 3 and 4, the nightly job sends a copy of the empty
database, which becomes the newest snapshot: the earlier ones stay, and the files you need
are already in `/root/restore`.

### 6.4 The restore drill, away from the server

The restore test runs on the server, with the keys of the server. The drill answers the
question of September 2026: can the backups be read when the server and its account are gone?
Run it every three months, and after any change of the repository, its password or its
storage key, on a machine that is not the server (a laptop with Docker, or a VM at another
provider), from a clone of the repository, with bash, docker, restic, curl and python3:

```bash
export RESTIC_REPOSITORY='<the repository address, from the password manager>'
export AWS_ACCESS_KEY_ID='<key id>' AWS_SECRET_ACCESS_KEY='<key>'   # S3-compatible storage only
bash scripts/restore_drill.sh
```

It asks for the repository password (not echoed; or `RESTIC_PASSWORD_FILE`, a file you wrote
from the password manager), refuses to run where `/etc/normaai/backup.env` exists (the
production server: a drill there proves nothing), and runs the restore test of 6.1 without the
server's settings and without alerts: restic check, the copy of `.env`, the database and every
collection loaded into throwaway containers, the time of each phase. Nothing stays on the
machine: the password and the copy are in a temporary folder removed at the end.

Then it prints the checklist of what a real rebuild adds (section 6.3): a new server, the DNS
record, the restore of the copy on it, the bootstrap, the database load, the final test. Time
them in the drill (on a throwaway server) or estimate them, and write the date, the times and
the outcome in the post-mortem log of [RUNBOOK.md](RUNBOOK.md): the first real figure for the
RTO of section 5.

## 7. Setting it up, and changing it

Setting up the repository and the password file is step 3 of
[DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md). Afterwards the settings are in
`/etc/normaai/backup.env`, which the bootstrap does not rewrite: edit it by hand.
`bash scripts/backup.sh --help` and `bash scripts/restore_test.sh --help` list every setting;
besides the restic ones: `BACKUP_ALERTS` (0: no failure alert), `BACKUP_SAME_PROVIDER_OK`
(1: the repository is at Hetzner in an account that is not the server's),
`RESTORE_TEST_QDRANT` (0: the test lists the Qdrant snapshots without loading them),
`RESTORE_TEST_MAX_AGE_HOURS`.

`scripts/backup_postgres.sh` is the old name: it runs `scripts/backup.sh`.

## 8. On a development machine

`scripts/backup_postgres.ps1` dumps the local Postgres container into `backups/`, checks
the archive and deletes the dumps older than 30 days. It is for a developer's own data: it
does not use restic and takes no Qdrant snapshot.
