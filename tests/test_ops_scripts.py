"""scripts/backup.sh and scripts/restore_test.sh, run for real against stand-ins.

The scripts cannot be tried on a server from here, so each test copies them into
a temporary "server" (an app directory with .env and the JWT keys) and runs them
with bash, with `docker`, `restic`, `curl` and `crontab` replaced by small
programs that record how they were called and answer as the real ones would.
What is checked is what the scripts decide and do: which commands, in which
order, with which arguments, what they leave on disk and how they exit.

Skipped where no POSIX bash is available (on Windows the one shipped with Git is
used; the WSL launcher is not).
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = ("backup.sh", "backup_postgres.sh", "restore_test.sh", "bootstrap_hetzner.sh")


def _find_bash() -> str | None:
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    if git:
        for root in Path(git).resolve().parents[:3]:
            candidate = root / "bin" / "bash.exe"
            if candidate.exists() and (root / "usr" / "bin").is_dir():
                return str(candidate)
    return None


BASH = _find_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="no POSIX bash on this machine")

# Puts the stand-ins first in PATH and refuses to go on if a real tool would run.
PRELUDE = r"""
bin="$STUB_BIN"
if command -v cygpath > /dev/null 2>&1; then bin="$(cygpath -u "$bin")"; fi
export PATH="$bin:$PATH"
for tool in docker restic curl crontab python3; do
  [ "$(command -v "$tool")" = "$bin/$tool" ] || { echo "stand-in for $tool is not first in PATH" >&2; exit 97; }
done
script="$1"; shift
exec bash "$script" "$@"
"""

STUB = r"""#!/usr/bin/env bash
# Stand-in for a real command: records the call, then answers from behaviour.sh.
name="$(basename "$0")"
{ printf '%s' "$name"; for arg in "$@"; do printf ' %s' "$arg"; done; printf '\n'; } >> "$STUB_STATE/calls.log"
. "$STUB_STATE/behaviour.sh"
"stub_$name" "$@"
"""

BEHAVIOUR = r"""
flag() { [ -e "$STUB_STATE/$1" ]; }
fake_dump() { head -c 8192 /dev/zero | tr '\0' 'D'; }

stub_docker() {
  case "$1" in
    inspect)
      case "$*" in
        *State.Running*) if flag postgres_down; then echo false; else echo true; fi ;;
        *Config.Image*) echo "postgres:16-alpine" ;;
      esac ;;
    exec)
      case "$*" in
        *"pg_restore --list"*) cat > /dev/null ;;
        *pg_restore*) cat > "$STUB_STATE/restored.dump"; if flag pg_restore_fails; then return 1; fi ;;
        *pg_dump*) if flag pg_dump_fails; then echo "pg_dump: error" >&2; return 1; fi; fake_dump ;;
        *pg_isready*) return 0 ;;
        *"CREATE ROLE"*) return 0 ;;
        *"to_regclass('public.users')"*) if flag users_table_missing; then echo f; else echo t; fi ;;
        *to_regclass*) echo t ;;
        *"version_num FROM alembic_version"*) echo "008_invites" ;;
        *information_schema.tables*) printf '%s\n' alembic_version leads organizations users ;;
        *"count(*) FROM public."*) echo 3 ;;
      esac ;;
    run) echo "0123456789ab" ;;
    rm) return 0 ;;
  esac
}

stub_curl() {
  local method=GET out="" url="" arg
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -X) method="$2"; shift ;;
      -o) out="$2"; shift ;;
      --max-time | --retry) shift ;;
      http*) url="$1" ;;
    esac
    shift
  done
  case "$method $url" in
    "GET http://127.0.0.1:6333/collections")
      if flag qdrant_down; then echo "curl: (7) Failed to connect" >&2; return 7; fi
      echo '{"result":{"collections":[{"name":"eu_regulations"},{"name":"eu_regulations_e5"}]},"status":"ok"}' ;;
    "POST http://127.0.0.1:6333/collections/"*"/snapshots?wait=true")
      arg="${url#http://127.0.0.1:6333/collections/}"; arg="${arg%%/*}"
      echo "{\"result\":{\"name\":\"$arg-1111-2026-11-11-02-00-05.snapshot\",\"size\":$(cat "$STUB_STATE/announced_size")}}" ;;
    "DELETE http://127.0.0.1:6333/collections/"*) echo '{"result":true}' ;;
    "GET http://127.0.0.1:6333/collections/"*"/snapshots/"*) head -c 2048 /dev/zero > "$out" ;;
    "GET http://127.0.0.1:6333/") echo '{"title":"qdrant - vector search engine","version":"1.20.0"}' ;;
    "GET https://heartbeat.example/"*) return 0 ;;
    *) echo "unexpected request: $method $url" >&2; return 22 ;;
  esac
}

stub_restic() {
  case "$1" in
    cat) flag restic_repository ;;
    init) : > "$STUB_STATE/restic_repository" ;;
    backup)
      if flag restic_backup_fails; then echo "Fatal: unable to save snapshot" >&2; return 1; fi
      local path="${*: -1}"
      (cd "$path" && find . -type f | sort) > "$STUB_STATE/backed_up.txt"
      cp "$path/MANIFEST.txt" "$STUB_STATE/manifest.txt" ;;
    forget) if flag restic_forget_fails; then return 1; fi ;;
    snapshots) printf '[{"time":"%s","short_id":"abcd1234","paths":["/opt/normaai/backups/offsite"]}]\n' "$(cat "$STUB_STATE/snapshot_time")" ;;
    check) if flag restic_check_fails; then return 1; fi ;;
    ls) cat "$STUB_STATE/snapshot_listing" ;;
    dump) fake_dump ;;
    version) echo "restic 0.16.4 compiled with go1.22 on linux/amd64" ;;
  esac
}

stub_crontab() {
  if [ "$1" = "-l" ]; then
    [ -s "$STUB_STATE/crontab" ] || { echo "no crontab for root" >&2; return 1; }
    cat "$STUB_STATE/crontab"
  else
    # Like the real crontab: the whole input first, then the new table. Writing
    # as it reads would empty the table under a `crontab -l | ... | crontab -`
    # pipeline still reading it.
    cat > "$STUB_STATE/crontab.new" && mv "$STUB_STATE/crontab.new" "$STUB_STATE/crontab"
  fi
}

# The real interpreter. On Windows it ends its lines with CR LF: the scripts run
# on Linux, so the stand-in hands them what python3 prints there.
stub_python3() { set -o pipefail; "$STUB_PYTHON" "$@" | tr -d '\r'; }
"""

LISTING = """snapshot abcd1234 of [/opt/normaai/backups/offsite] at 2026-11-11 02:00:05 +0000 UTC):
/opt/normaai/backups/offsite/MANIFEST.txt
/opt/normaai/backups/offsite/config/env
/opt/normaai/backups/offsite/postgres/normaai.dump
/opt/normaai/backups/offsite/qdrant/eu_regulations.snapshot
/opt/normaai/backups/offsite/qdrant/eu_regulations_e5.snapshot
"""


def _posix(path: Path) -> str:
    return str(path).replace("\\", "/")


class Server:
    """A temporary server: the app directory, the stand-ins and their state."""

    def __init__(self, root: Path):
        self.app = root / "app"
        self.bin = root / "bin"
        self.state = root / "state"
        self.env_file = root / "etc" / "backup.env"
        self.password_file = root / "etc" / "restic-password"
        for directory in (self.app / "scripts", self.app / "data", self.bin, self.state):
            directory.mkdir(parents=True)
        self.env_file.parent.mkdir()
        for name in SCRIPTS:
            text = (REPO / "scripts" / name).read_text(encoding="utf-8")
            (self.app / "scripts" / name).write_text(text, encoding="utf-8", newline="\n")
        (self.app / ".env").write_text("APP_SECRET_KEY=secret-of-the-server\n", newline="\n")
        (self.app / "data" / "jwt_private.pem").write_text("private\n", newline="\n")
        (self.app / "data" / "jwt_public.pem").write_text("public\n", newline="\n")
        for tool in ("docker", "restic", "curl", "crontab", "python3"):
            stub = self.bin / tool
            stub.write_text(STUB, encoding="utf-8", newline="\n")
            stub.chmod(0o755)
        (self.state / "behaviour.sh").write_text(BEHAVIOUR, encoding="utf-8", newline="\n")
        (self.state / "announced_size").write_text("2048", newline="\n")
        (self.state / "snapshot_listing").write_text(LISTING, newline="\n")
        self.snapshot_age(3)

    # ── arranging ──
    def flag(self, name: str) -> None:
        (self.state / name).write_text("", newline="\n")

    def snapshot_age(self, hours: float) -> None:
        moment = time.gmtime(time.time() - hours * 3600)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S", moment) + ".123456789Z"
        (self.state / "snapshot_time").write_text(stamp, newline="\n")

    def configure_restic(self, **extra: str) -> None:
        self.password_file.write_text("the-repository-password\n", newline="\n")
        lines = [
            "RESTIC_REPOSITORY=s3:https://storage.example/bucket/normaai",
            f"RESTIC_PASSWORD_FILE={_posix(self.password_file)}",
        ]
        lines += [f"{name}={value}" for name, value in extra.items()]
        self.env_file.write_text("\n".join(lines) + "\n", newline="\n")

    def local_dump(self, name: str, age_days: float = 0) -> Path:
        backups = self.app / "backups"
        backups.mkdir(exist_ok=True)
        dump = backups / name
        dump.write_bytes(b"D" * 8192)
        moment = time.time() - age_days * 86400
        os.utime(dump, (moment, moment))
        return dump

    # ── acting ──
    def run(self, script: str, *args: str) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "STUB_BIN": _posix(self.bin),
            "STUB_STATE": _posix(self.state),
            "STUB_PYTHON": _posix(Path(sys.executable)),
            "BACKUP_ENV_FILE": _posix(self.env_file),
        }
        for name in ("RESTIC_REPOSITORY", "RESTIC_PASSWORD_FILE", "BACKUP_HEARTBEAT_URL"):
            env.pop(name, None)
        return subprocess.run(
            [BASH, "-c", PRELUDE, "prelude", _posix(self.app / "scripts" / script), *args],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    # ── observing ──
    def calls(self, tool: str | None = None) -> list[str]:
        log = self.state / "calls.log"
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        wanted = [line for line in lines if not line.startswith("python3 ")]
        return [line for line in wanted if tool is None or line.startswith(f"{tool} ")]

    def backed_up(self) -> list[str]:
        return (self.state / "backed_up.txt").read_text(encoding="utf-8").split()

    def dumps(self) -> list[str]:
        return sorted(path.name for path in (self.app / "backups").glob("normaai_*.dump*"))

    def crontab(self) -> list[str]:
        return (self.state / "crontab").read_text(encoding="utf-8").splitlines()


@pytest.fixture
def server(tmp_path) -> Server:
    return Server(tmp_path)


# ─── Syntax ──────────────────────────────────────────────────────


@pytest.mark.parametrize("name", SCRIPTS)
def test_shell_script_parses(name, tmp_path):
    # As git stores it (LF): a Windows checkout may hold CRLF, which bash rejects.
    text = (REPO / "scripts" / name).read_text(encoding="utf-8")
    copy = tmp_path / name
    copy.write_text(text, encoding="utf-8", newline="\n")
    result = subprocess.run(
        [BASH, "-n", _posix(copy)], capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, result.stderr
    assert "set -euo pipefail" in text


# ─── backup.sh without restic: today's behaviour, and a clear warning ────────


def test_backup_without_restic_keeps_a_local_dump_and_warns(server):
    result = server.run("backup.sh")
    assert result.returncode == 0, result.stderr
    assert len(server.dumps()) == 1
    assert "off-site backup is NOT configured" in result.stderr
    assert "The Qdrant index and .env are NOT backed up" in result.stderr
    assert "done (local only)" in result.stdout
    # Nothing but the Postgres dump and its check: no restic, no Qdrant, no heartbeat.
    assert server.calls("restic") == []
    assert server.calls("curl") == []
    assert [call.split()[1] for call in server.calls("docker")] == ["inspect", "exec", "exec"]
    assert (server.app / "backups" / "last_success").read_text().strip().endswith("local only")


def test_the_old_script_name_still_runs_the_backup(server):
    result = server.run("backup_postgres.sh")
    assert result.returncode == 0, result.stderr
    assert len(server.dumps()) == 1
    assert "done (local only)" in result.stdout


def test_backup_fails_when_pg_dump_fails(server):
    server.configure_restic()
    server.flag("pg_dump_fails")
    result = server.run("backup.sh")
    assert result.returncode == 1
    assert "pg_dump failed" in result.stderr
    assert server.dumps() == []  # no partial file left behind
    assert server.calls("restic") == []


def test_backup_fails_when_postgres_is_not_running(server):
    server.flag("postgres_down")
    result = server.run("backup.sh")
    assert result.returncode == 1
    assert "is not running" in result.stderr


def test_backup_rejects_an_unknown_argument(server):
    result = server.run("backup.sh", "--everything")
    assert result.returncode == 1
    assert "unknown argument" in result.stderr
    assert server.calls() == []


# ─── backup.sh with restic ───────────────────────────────────────────────────


def test_offsite_backup_sends_database_index_and_secrets(server):
    server.configure_restic(BACKUP_HEARTBEAT_URL="https://heartbeat.example/ping")
    result = server.run("backup.sh")
    assert result.returncode == 0, result.stderr

    assert server.backed_up() == [
        "./MANIFEST.txt",
        "./config/env",
        "./postgres/normaai.dump",
        "./qdrant/eu_regulations.snapshot",
        "./qdrant/eu_regulations_e5.snapshot",
    ]
    stage = _posix(server.app / "backups" / "offsite")
    restic = server.calls("restic")
    assert restic[0] == "restic cat config"
    assert restic[1] == "restic init"  # first run: the repository did not exist
    assert restic[2].startswith("restic backup --host normaai --tag normaai ")
    assert restic[2].replace("\\", "/").lower().endswith("/app/backups/offsite")
    assert restic[3] == (
        "restic forget --host normaai --tag normaai --group-by host --keep-within 29d --prune"
    )
    assert len(restic) == 4
    # The plain copy of the secrets and the snapshots do not stay on the disk.
    assert not Path(stage).exists()
    # Qdrant's own copy of each snapshot is deleted after the download.
    deleted = [call for call in server.calls("curl") if " -X DELETE " in call]
    assert len(deleted) == 2
    assert all("/snapshots/eu_regulations" in call for call in deleted)
    assert server.calls("curl")[-1].endswith("https://heartbeat.example/ping")
    manifest = (server.state / "manifest.txt").read_text(encoding="utf-8")
    assert "alembic: 008_invites" in manifest
    assert "qdrant: 1.20.0" in manifest
    assert "./postgres/normaai.dump" in manifest
    assert "secret-of-the-server" not in manifest
    # The JWT keys stay on the server: a rebuilt one gets a new pair.
    assert not any("jwt" in path for path in server.backed_up())
    assert "done (off-site)" in result.stdout
    assert "NOT configured" not in result.stderr
    # The local dump is kept as well.
    assert len(server.dumps()) == 1


def test_second_offsite_run_does_not_create_the_repository_again(server):
    server.configure_restic()
    assert server.run("backup.sh").returncode == 0
    assert server.run("backup.sh").returncode == 0
    assert server.calls("restic").count("restic init") == 1


def test_retention_drives_both_the_offsite_and_the_local_copies(server):
    server.configure_restic(BACKUP_RETENTION_DAYS="10")
    old = server.local_dump("normaai_20260101_020000.dump", age_days=9.5)
    recent = server.local_dump("normaai_20261105_020000.dump", age_days=8.5)
    result = server.run("backup.sh")
    assert result.returncode == 0, result.stderr
    assert any(call.endswith("--keep-within 9d --prune") for call in server.calls("restic"))
    assert not old.exists()
    assert recent.exists()
    pruned = [line for line in result.stdout.splitlines() if line.startswith("[backup] pruned ")]
    assert len(pruned) == 1
    assert pruned[0].endswith(old.name)


def test_default_retention_never_keeps_a_local_dump_past_thirty_days(server):
    past = server.local_dump("normaai_20261010_020000.dump", age_days=29.2)
    kept = server.local_dump("normaai_20261013_020000.dump", age_days=28.5)
    assert server.run("backup.sh").returncode == 0
    assert not past.exists()
    assert kept.exists()


@pytest.mark.parametrize("value", ["soon", "1", "0", "-3"])
def test_backup_rejects_a_retention_it_cannot_apply(server, value):
    server.configure_restic(BACKUP_RETENTION_DAYS=value)
    result = server.run("backup.sh")
    assert result.returncode == 1
    assert "BACKUP_RETENTION_DAYS" in result.stderr
    assert server.calls() == []


def test_qdrant_down_still_sends_the_database_but_fails_the_run(server):
    server.configure_restic(BACKUP_HEARTBEAT_URL="https://heartbeat.example/ping")
    server.flag("qdrant_down")
    result = server.run("backup.sh")
    assert result.returncode == 1
    assert "holds no complete Qdrant index" in result.stderr
    assert "./postgres/normaai.dump" in server.backed_up()
    assert "./config/env" in server.backed_up()
    assert not any("qdrant" in path for path in server.backed_up())
    assert not any("heartbeat" in call for call in server.calls("curl"))
    assert not (server.app / "backups" / "last_success").exists()


def test_a_truncated_qdrant_snapshot_is_not_sent(server):
    server.configure_restic()
    (server.state / "announced_size").write_text("4096", newline="\n")
    result = server.run("backup.sh")
    assert result.returncode == 1
    assert "downloaded 2048 bytes, Qdrant announced 4096" in result.stderr
    assert not any("qdrant" in path for path in server.backed_up())


def test_restic_failure_fails_the_run_and_leaves_no_secret_behind(server):
    server.configure_restic(BACKUP_HEARTBEAT_URL="https://heartbeat.example/ping")
    server.flag("restic_backup_fails")
    result = server.run("backup.sh")
    assert result.returncode == 1
    assert "nothing was sent off the server" in result.stderr
    assert not (server.app / "backups" / "offsite").exists()
    assert not any("heartbeat" in call for call in server.calls("curl"))
    assert not any(call.startswith("restic forget") for call in server.calls("restic"))


def test_restic_forget_failure_fails_the_run(server):
    server.configure_restic()
    server.flag("restic_forget_fails")
    result = server.run("backup.sh")
    assert result.returncode == 1
    assert "past the retention were not removed" in result.stderr


def test_half_a_restic_configuration_is_an_error(server):
    server.env_file.write_text("RESTIC_REPOSITORY=s3:https://storage.example/b\n", newline="\n")
    result = server.run("backup.sh")
    assert result.returncode == 1
    assert "set both RESTIC_REPOSITORY and RESTIC_PASSWORD_FILE" in result.stderr
    assert len(server.dumps()) == 1  # the local dump was still taken
    assert server.calls("restic") == []


def test_missing_password_file_is_an_error(server):
    server.configure_restic()
    server.password_file.unlink()
    result = server.run("backup.sh")
    assert result.returncode == 1
    assert "is missing or empty" in result.stderr
    assert not any(call.startswith("restic backup") for call in server.calls("restic"))
    assert not (server.app / "backups" / "offsite").exists()


# ─── The cron line ───────────────────────────────────────────────────────────

OLD_LINE = "0 2 * * * /opt/normaai/scripts/backup_postgres.sh >> /var/log/normaai-backup.log 2>&1"
OTHER_JOB = "5 4 * * * /usr/bin/true"


@pytest.mark.parametrize(
    ("before", "others"),
    [
        ([], []),  # a new server: root has no crontab
        ([OLD_LINE], []),  # only the old line
        ([OTHER_JOB, OLD_LINE], [OTHER_JOB]),  # another job is kept
    ],
)
def test_install_cron_leaves_exactly_one_backup_line(server, before, others):
    if before:
        (server.state / "crontab").write_text("\n".join(before) + "\n", newline="\n")
    for _ in range(2):  # twice: installing again changes nothing
        result = server.run("backup.sh", "--install-cron")
        assert result.returncode == 0, result.stderr
    lines = server.crontab()
    backup_lines = [line for line in lines if "backup" in line]
    assert len(backup_lines) == 1
    # Through bash: the script has no execute bit after a deploy's git reset.
    assert backup_lines[0].startswith("0 2 * * * bash ")
    assert backup_lines[0].endswith("/app/scripts/backup.sh >> /var/log/normaai-backup.log 2>&1")
    assert [line for line in lines if "backup" not in line] == others


def _app_cron_block() -> str:
    """The lines of step 9 of the bootstrap that install the application's jobs."""
    text = (REPO / "scripts" / "bootstrap_hetzner.sh").read_text(encoding="utf-8")
    start = text.index('JOBS_LOG="')
    end = text.index('if [ "${SKIP_FIRST_BACKUP', start)
    return text[start:end].replace("\r\n", "\n")


def test_bootstrap_installs_the_application_jobs_once(server):
    # The block runs as it is in the bootstrap, after the backup's own line.
    block = server.app / "scripts" / "app_cron.sh"
    block.write_text("set -euo pipefail\n" + _app_cron_block(), encoding="utf-8", newline="\n")
    (server.state / "crontab").write_text(OTHER_JOB + "\n", newline="\n")
    assert server.run("backup.sh", "--install-cron").returncode == 0
    for _ in range(2):  # twice: running the bootstrap again changes nothing
        result = server.run("app_cron.sh")
        assert result.returncode == 0, result.stderr
    assert server.run("backup.sh", "--install-cron").returncode == 0
    lines = server.crontab()
    jobs = [line for line in lines if "src.pipeline" in line]
    # Brief section 6.4: nightly freshness, weekly re-check, inside the app container.
    assert jobs == [
        "30 3 * * * docker exec normaai-app python -m src.pipeline --action check-freshness"
        " >> /var/log/normaai-jobs.log 2>&1",
        "0 4 * * 1 docker exec normaai-app python -m src.pipeline --action recheck-documents"
        " >> /var/log/normaai-jobs.log 2>&1",
    ]
    assert OTHER_JOB in lines
    assert len([line for line in lines if "scripts/backup.sh" in line]) == 1


def test_the_app_container_caches_official_texts_on_its_writable_mount():
    yaml = pytest.importorskip("yaml")
    app = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"][
        "app"
    ]
    assert app["read_only"] is True
    assert "./data:/app/data" in app["volumes"]
    cache = app["environment"]["NORMAAI_TEXT_CACHE"]
    assert cache.startswith("/app/data/")
    # The bootstrap creates the folder before handing data/ to the app's user.
    assert "mkdir -p data/texts" in (REPO / "scripts" / "bootstrap_hetzner.sh").read_text(
        encoding="utf-8"
    )


# ─── restore_test.sh ─────────────────────────────────────────────────────────


def test_restore_test_passes_on_a_complete_recent_backup(server):
    server.configure_restic()
    result = server.run("restore_test.sh")
    assert result.returncode == 0, result.stderr
    assert "PASSED" in result.stdout
    assert "the latest off-site snapshot is 3 hours old" in result.stdout
    assert "schema revision (alembic): 008_invites" in result.stdout
    for table in ("alembic_version", "leads", "organizations", "users"):
        assert any(line.split()[-2:] == [table, "3"] for line in result.stdout.splitlines())
    assert "eu_regulations_e5.snapshot" in result.stdout
    # The dump taken from the snapshot is what pg_restore received.
    assert (server.state / "restored.dump").stat().st_size == 8192
    docker = server.calls("docker")
    run = next(call for call in docker if call.startswith("docker run "))
    assert "--network none" in run
    assert "normaai-restore-test-" in run
    assert run.endswith(" postgres:16-alpine")
    assert any("pg_restore" in c and "--exit-on-error" in c and "--no-owner" in c for c in docker)
    # The throwaway container is removed, with its volume.
    assert docker[-1].startswith("docker rm -f -v normaai-restore-test-")
    restic = server.calls("restic")
    assert "restic check" in restic
    assert restic[-1].startswith("restic dump --host normaai --tag normaai latest ")
    assert restic[-1].endswith("/postgres/normaai.dump")


def test_restore_test_fails_when_the_nightly_job_has_stopped(server):
    server.configure_restic()
    server.snapshot_age(50)
    result = server.run("restore_test.sh")
    assert result.returncode == 1
    assert "50 hours old, more than 36: the nightly backup has stopped" in result.stderr
    assert "PASSED" not in result.stdout
    assert server.calls("docker")[-1].startswith("docker rm -f -v ")


def test_restore_test_fails_when_the_index_is_not_in_the_backup(server):
    server.configure_restic()
    listing = "\n".join(line for line in LISTING.splitlines() if "/qdrant/" not in line)
    (server.state / "snapshot_listing").write_text(listing + "\n", newline="\n")
    result = server.run("restore_test.sh")
    assert result.returncode == 1
    assert "holds no Qdrant snapshot" in result.stderr


def test_restore_test_fails_when_the_configuration_is_not_in_the_backup(server):
    server.configure_restic()
    listing = "\n".join(line for line in LISTING.splitlines() if "/config/env" not in line)
    (server.state / "snapshot_listing").write_text(listing + "\n", newline="\n")
    result = server.run("restore_test.sh")
    assert result.returncode == 1
    assert "holds no copy of .env" in result.stderr


def test_restore_test_fails_when_the_dump_is_not_in_the_backup(server):
    server.configure_restic()
    listing = "\n".join(line for line in LISTING.splitlines() if "/postgres/" not in line)
    (server.state / "snapshot_listing").write_text(listing + "\n", newline="\n")
    result = server.run("restore_test.sh")
    assert result.returncode == 1
    assert "holds no Postgres dump" in result.stderr
    assert not any(call.startswith("docker run") for call in server.calls("docker"))


def test_restore_test_fails_when_the_dump_does_not_load(server):
    server.configure_restic()
    server.flag("pg_restore_fails")
    result = server.run("restore_test.sh")
    assert result.returncode == 1
    assert "the dump does not load" in result.stderr
    assert server.calls("docker")[-1].startswith("docker rm -f -v ")


def test_restore_test_fails_when_a_core_table_is_missing(server):
    server.configure_restic()
    server.flag("users_table_missing")
    result = server.run("restore_test.sh")
    assert result.returncode == 1
    assert "the table users is missing" in result.stderr


def test_restore_test_fails_when_the_repository_is_damaged(server):
    server.configure_restic()
    server.flag("restic_check_fails")
    result = server.run("restore_test.sh")
    assert result.returncode == 1
    assert "restic check reports errors" in result.stderr


def test_restore_test_without_restic_uses_the_newest_local_dump(server):
    server.local_dump("normaai_20261101_020000.dump", age_days=10)
    server.local_dump("normaai_20261111_020000.dump", age_days=0.1)
    result = server.run("restore_test.sh")
    assert result.returncode == 0, result.stderr
    assert "testing the newest LOCAL dump" in result.stderr
    assert "normaai_20261111_020000.dump" in result.stdout
    assert "PASSED" in result.stdout
    assert server.calls("restic") == []


def test_restore_test_without_any_backup_fails(server):
    result = server.run("restore_test.sh")
    assert result.returncode == 1
    assert "run scripts/backup.sh first" in result.stderr
    assert not any(call.startswith("docker run") for call in server.calls("docker"))
