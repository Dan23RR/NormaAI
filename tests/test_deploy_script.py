"""scripts/deploy.sh, run for real against stand-ins for git and docker.

The deploy cannot be tried on the server from here: each test copies the
script into a temporary checkout with an .env, puts small programs named git,
docker, id and sleep first in PATH (they record their calls and answer from
files the test writes), runs the script with bash, and checks what it decided:
which commit, which image, in which order, what it wrote to .env and how it
exited. Skipped where no POSIX bash is available.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.test_ops_scripts import BASH, _posix

pytestmark = pytest.mark.skipif(BASH is None, reason="no POSIX bash on this machine")

REPO = Path(__file__).resolve().parents[1]
SHA = "0123456789abcdef0123456789abcdef01234567"
OLD_SHA = "fedcba9876543210fedcba9876543210fedcba98"
REPOSITORY = "ghcr.io/dan23rr/normaai"
NEW = f"{REPOSITORY}@sha256:{'a' * 64}"
OLD = f"{REPOSITORY}@sha256:{'b' * 64}"
STALE = f"{REPOSITORY}@sha256:{'c' * 64}"
E5 = "intfloat/multilingual-e5-large"

PRELUDE = r"""
bin="$STUB_BIN"
if command -v cygpath > /dev/null 2>&1; then bin="$(cygpath -u "$bin")"; fi
export PATH="$bin:$PATH"
for tool in git docker id sleep; do
  [ "$(command -v "$tool")" = "$bin/$tool" ] || { echo "stand-in for $tool is not first in PATH" >&2; exit 97; }
done
script="$1"; shift
exec bash "$script" "$@"
"""

STUB = r"""#!/usr/bin/env bash
name="$(basename "$0")"
# One write per call: the deploy runs some stand-ins concurrently.
line="$name"; for arg in "$@"; do line="$line $arg"; done
line="$line | NORMAAI_IMAGE=${NORMAAI_IMAGE:-} GIT_SHA=${GIT_SHA:-} DOCKER_CONFIG=${DOCKER_CONFIG:+set}"
printf '%s\n' "$line" >> "$STUB_STATE/calls.log"
. "$STUB_STATE/behaviour.sh"
"stub_$name" "$@"
"""

BEHAVIOUR = r"""
flag() { [ -e "$STUB_STATE/$1" ]; }

stub_id() { if flag as_root; then echo 0; else echo 1000; fi; }
stub_sleep() { :; }

stub_git() {
  if [ "$1" = "-C" ]; then shift 2; fi
  case "$1" in
    remote) echo "https://github.com/Dan23RR/NormaAI.git" ;;
    fetch) return 0 ;;
    cat-file) if flag commit_missing; then return 1; fi ;;
    merge-base) if flag not_on_main; then return 1; fi ;;
    rev-parse) cat "$STUB_STATE/head" ;;
    reset) echo "${*: -1}" > "$STUB_STATE/head" ;;
    diff) if flag caddyfile_changed; then return 1; fi ;;
  esac
}

stub_docker() {
  case "$1" in
    login) cat > "$STUB_STATE/token_seen"; if flag login_fails; then return 1; fi ;;
    pull) if flag pull_fails; then return 1; fi; echo "${*: -1}" ;;
    image)
      case "$2" in
        inspect)
          case "$*" in
            *org.opencontainers.image.revision*) cat "$STUB_STATE/revision" ;;
            *org.normaai.embedding-model*) cat "$STUB_STATE/model" ;;
          esac ;;
        prune) return 0 ;;
        ls)
          case "$*" in
            *--digests*) printf '%s\n' "$OLD" "$NEW" "$STALE" ;;
            *) printf '%s\n' "normaai-app:local" ;;
          esac ;;
        rm) return 0 ;;
      esac ;;
    compose)
      case "$*" in
        *"run --rm -T migrate"*) if flag migrate_fails; then return 1; fi ;;
        *"up -d --no-deps --no-build app"*) echo "$NORMAAI_IMAGE" >> "$STUB_STATE/app_images" ;;
      esac ;;
    inspect)
      if flag app_unhealthy && [ "$(tail -n 1 "$STUB_STATE/app_images")" != "$(cat "$STUB_STATE/healthy_image")" ]; then
        echo unhealthy
      else
        echo healthy
      fi ;;
    logs) echo "app log line" ;;
  esac
}
"""


class Checkout:
    """A temporary /opt/normaai: the script, an .env, the stand-ins and their state."""

    def __init__(self, root: Path):
        self.app = root / "app"
        self.bin = root / "bin"
        self.state = root / "state"
        for directory in (self.app / "scripts", self.bin, self.state):
            directory.mkdir(parents=True)
        text = (REPO / "scripts" / "deploy.sh").read_text(encoding="utf-8")
        (self.app / "scripts" / "deploy.sh").write_text(text, encoding="utf-8", newline="\n")
        self.env_file = self.app / ".env"
        self.env_file.write_text(
            f"APP_ENV=production\nEMBEDDING_MODEL={E5}\nNORMAAI_IMAGE={OLD}\n", newline="\n"
        )
        for tool in ("git", "docker", "id", "sleep"):
            stub = self.bin / tool
            stub.write_text(STUB, encoding="utf-8", newline="\n")
            stub.chmod(0o755)
        behaviour = BEHAVIOUR.replace("$OLD", OLD).replace("$NEW", NEW).replace("$STALE", STALE)
        (self.state / "behaviour.sh").write_text(behaviour, encoding="utf-8", newline="\n")
        (self.state / "head").write_text(OLD_SHA + "\n", newline="\n")
        (self.state / "app_images").write_text(OLD + "\n", newline="\n")
        (self.state / "healthy_image").write_text(OLD + "\n", newline="\n")
        self.label(SHA[:7], E5)

    def label(self, revision: str, model: str) -> None:
        (self.state / "revision").write_text(revision + "\n", newline="\n")
        (self.state / "model").write_text(model + "\n", newline="\n")

    def flag(self, name: str) -> None:
        (self.state / name).write_text("", newline="\n")

    def run(self, *args: str, stdin: str = "", **extra_env: str) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "STUB_BIN": _posix(self.bin),
            "STUB_STATE": _posix(self.state),
            "TMPDIR": _posix(self.state),
        }
        env.pop("SSH_ORIGINAL_COMMAND", None)
        env.update(extra_env)
        return subprocess.run(
            [BASH, "-c", PRELUDE, "prelude", _posix(self.app / "scripts" / "deploy.sh"), *args],
            env=env,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    def calls(self, tool: str | None = None) -> list[str]:
        log = self.state / "calls.log"
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return [line for line in lines if tool is None or line.startswith(f"{tool} ")]

    def env_image(self) -> str:
        lines = self.env_file.read_text(encoding="utf-8").splitlines()
        return [line for line in lines if line.startswith("NORMAAI_IMAGE=")][-1].split("=", 1)[1]

    def head(self) -> str:
        return (self.state / "head").read_text(encoding="utf-8").strip()


@pytest.fixture
def checkout(tmp_path) -> Checkout:
    return Checkout(tmp_path)


def _command(call: str) -> str:
    return call.split(" | ")[0]


def test_the_script_parses_and_documents_itself(tmp_path):
    text = (REPO / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    copy = tmp_path / "deploy.sh"
    copy.write_text(text, encoding="utf-8", newline="\n")
    result = subprocess.run(
        [BASH, "-n", _posix(copy)], capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, result.stderr
    assert "set -euo pipefail" in text


def test_deploys_the_tested_commit_from_its_image(checkout):
    result = checkout.run(SHA, NEW, "github-actions", stdin="job-token\n")
    assert result.returncode == 0, result.stderr
    assert f"deployed {SHA[:7]} ({NEW})" in result.stdout
    # Exactly that commit, checked against origin/main first.
    git = [_command(call) for call in checkout.calls("git")]
    assert git.index(f"git merge-base --is-ancestor {SHA} origin/main") < git.index(
        f"git reset -q --hard {SHA}"
    )
    assert checkout.head() == SHA
    docker = checkout.calls("docker")
    commands = [_command(call) for call in docker]
    # The token went to a throwaway docker configuration, through stdin.
    login = next(call for call in docker if call.startswith("docker login "))
    assert "--password-stdin" in login and "DOCKER_CONFIG=set" in login
    assert (checkout.state / "token_seen").read_bytes() == b"job-token"
    pull = next(call for call in docker if call.startswith("docker pull "))
    assert "DOCKER_CONFIG=set" in pull and NEW in pull
    # Migrations with the new image while the old app serves, then the app alone.
    migrate = commands.index("docker compose run --rm -T migrate")
    up = commands.index("docker compose up -d --no-deps --no-build app")
    assert migrate < up
    assert f"NORMAAI_IMAGE={NEW}" in docker[migrate] and f"NORMAAI_IMAGE={NEW}" in docker[up]
    assert f"GIT_SHA={SHA[:7]}" in docker[up]
    assert "docker compose up -d --no-deps caddy" in commands
    assert not any("caddy reload" in command for command in commands)
    # .env runs the new image from now on.
    assert checkout.env_image() == NEW
    # Old images go, the previous one stays for a rollback.
    removed = [command for command in commands if command.startswith("docker image rm ")]
    assert removed == [f"docker image rm {STALE}", "docker image rm normaai-app:local"]


def test_the_deploy_key_can_only_deploy(checkout):
    ok = checkout.run(
        "--ssh", stdin="job-token\n", SSH_ORIGINAL_COMMAND=f"deploy {SHA} {NEW} github-actions"
    )
    assert ok.returncode == 0, ok.stderr
    assert checkout.env_image() == NEW


@pytest.mark.parametrize(
    "command",
    [
        "",
        "bash -i",
        f"deploy {SHA}",
        f"deploy {SHA} {NEW} user extra words",
        f"rm -rf / {SHA} {NEW}",
    ],
)
def test_anything_else_sent_with_the_deploy_key_is_refused(checkout, command):
    result = checkout.run("--ssh", SSH_ORIGINAL_COMMAND=command)
    assert result.returncode == 1
    assert "this key may only run: deploy" in result.stderr
    assert checkout.calls() == []


@pytest.mark.parametrize(
    "args",
    [
        ("0123", NEW),  # not a full SHA
        (SHA.upper(), NEW),
        (SHA, f"docker.io/evil/normaai@sha256:{'a' * 64}"),  # another repository
        (SHA, f"{REPOSITORY}:latest"),  # a tag can move: digests only
        (SHA, f"{REPOSITORY}@sha256:{'a' * 63}"),
    ],
)
def test_malformed_input_is_refused_before_anything_moves(checkout, args):
    result = checkout.run(*args)
    assert result.returncode == 1
    # Only the address of origin may be read: no fetch, no checkout, no image.
    assert [_command(call) for call in checkout.calls("git")] in (
        [],
        ["git remote get-url origin"],
    )
    assert checkout.calls("docker") == []
    assert checkout.head() == OLD_SHA
    assert checkout.env_image() == OLD


def test_a_commit_that_is_not_on_main_is_refused(checkout):
    checkout.flag("not_on_main")
    result = checkout.run(SHA, NEW)
    assert result.returncode == 1
    assert "is not on origin/main" in result.stderr
    assert checkout.head() == OLD_SHA
    assert checkout.calls("docker") == []


def test_an_image_of_another_commit_is_refused(checkout):
    checkout.label("1111111", E5)
    result = checkout.run(SHA, NEW)
    assert result.returncode == 1
    assert "built from '1111111', not from 0123456" in result.stderr
    assert not any("compose" in call for call in checkout.calls("docker"))
    assert checkout.env_image() == OLD
    # The compose files go back to the commit whose image still serves.
    assert checkout.head() == OLD_SHA
    assert "checkout back at fedcba9" in result.stdout


def test_an_image_without_the_configured_model_is_refused(checkout):
    checkout.label(SHA[:7], "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
    result = checkout.run(SHA, NEW)
    assert result.returncode == 1
    assert f".env asks for '{E5}'" in result.stderr
    assert not any("compose" in call for call in checkout.calls("docker"))


def test_failed_migrations_leave_the_old_app_serving(checkout):
    checkout.flag("migrate_fails")
    result = checkout.run(SHA, NEW)
    assert result.returncode == 1
    assert "the migrations failed: the old app is still serving" in result.stderr
    commands = [_command(call) for call in checkout.calls("docker")]
    assert "docker compose up -d --no-deps --no-build app" not in commands
    assert checkout.env_image() == OLD


def test_an_unhealthy_app_is_rolled_back_to_the_previous_image(checkout):
    checkout.flag("app_unhealthy")
    result = checkout.run(SHA, NEW)
    assert result.returncode == 1
    assert "did not become healthy" in result.stderr
    assert "back to " + OLD in result.stdout
    images = (checkout.state / "app_images").read_text().split()
    assert images[-2:] == [NEW, OLD]
    # The checkout goes back too, and .env keeps the image that serves.
    assert checkout.head() == OLD_SHA
    assert checkout.env_image() == OLD
    assert "app log line" in result.stderr


def test_the_first_deploy_after_a_local_build_rolls_back_to_it(checkout):
    # An .env from the bootstrap names no image: compose ran normaai-app:local.
    checkout.env_file.write_text(f"EMBEDDING_MODEL={E5}\n", newline="\n")
    (checkout.state / "healthy_image").write_text("normaai-app:local\n", newline="\n")
    checkout.flag("app_unhealthy")
    result = checkout.run(SHA, NEW)
    assert result.returncode == 1
    images = (checkout.state / "app_images").read_text().split()
    assert images[-2:] == [NEW, "normaai-app:local"]
    assert "NORMAAI_IMAGE=" not in checkout.env_file.read_text()


def test_without_an_image_it_builds_here(checkout):
    checkout.label(SHA[:7], E5)
    result = checkout.run(SHA, "build")
    assert result.returncode == 0, result.stderr
    local = f"normaai-app:{SHA[:7]}"
    docker = checkout.calls("docker")
    build = next(call for call in docker if call.startswith("docker compose build app"))
    assert f"NORMAAI_IMAGE={local}" in build and f"GIT_SHA={SHA[:7]}" in build
    assert not any(call.startswith("docker pull ") for call in docker)
    assert checkout.env_image() == local


def test_a_new_caddyfile_is_reloaded(checkout):
    checkout.flag("caddyfile_changed")
    result = checkout.run(SHA, NEW)
    assert result.returncode == 0, result.stderr
    commands = [_command(call) for call in checkout.calls("docker")]
    assert "docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile" in commands


def test_it_refuses_to_run_as_root(checkout):
    checkout.flag("as_root")
    result = checkout.run(SHA, NEW)
    assert result.returncode == 1
    assert "run as the deploy user, not root" in result.stderr
    assert checkout.calls("git") == []


def _compose(name: str) -> dict:
    """A compose file as data; compose's own tags (!override, !reset) read as plain values."""
    yaml = pytest.importorskip("yaml")

    class Loader(yaml.SafeLoader):
        pass

    def plain(loader, _suffix, node):
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
        return loader.construct_scalar(node)

    Loader.add_multi_constructor("!", plain)
    return yaml.load((REPO / name).read_text(encoding="utf-8"), Loader=Loader)


def test_compose_files_run_the_pinned_image_and_keep_the_owner_password_out():
    prod = _compose("docker-compose.prod.yml")
    rls = _compose("docker-compose.rls.yml")
    app = prod["services"]["app"]
    assert app["image"] == "${NORMAAI_IMAGE:-normaai-app:local}"
    # The owner's password is blanked; the app connects as normaai_app.
    assert app["environment"]["POSTGRES_PASSWORD"] == ""
    assert app["environment"]["DATABASE_URL_SYNC"] == ""
    assert rls["services"]["app"]["environment"]["DATABASE_URL"].startswith(
        "postgresql+asyncpg://normaai_app:"
    )
    migrate = prod["services"]["migrate"]
    assert migrate["image"] == app["image"]
    assert migrate["command"] == ["alembic", "upgrade", "head"]
    assert migrate["profiles"] == ["tools"]  # never started by `up`
    assert migrate["environment"]["DATABASE_URL"].startswith("postgresql+asyncpg://normaai:")
    assert "env_file" not in migrate


def test_the_workflow_deploys_only_a_tested_commit_of_main():
    yaml = pytest.importorskip("yaml")
    flow = yaml.safe_load((REPO / ".github/workflows/deploy.yml").read_text(encoding="utf-8"))
    triggers = flow[True]  # YAML 1.1 reads the key `on` as True
    assert "push" not in triggers
    run = triggers["workflow_run"]
    assert run == {"workflows": ["NormaAI CI"], "types": ["completed"], "branches": ["main"]}
    assert "workflow_dispatch" in triggers
    gate = flow["jobs"]["gate"]
    for condition in (
        "github.event.workflow_run.conclusion == 'success'",
        "github.event.workflow_run.event == 'push'",
        "github.event.workflow_run.head_repository.full_name == github.repository",
    ):
        assert condition in gate["if"]
    pick = next(step for step in gate["steps"] if step.get("id") == "pick")
    assert pick["env"]["RUN_SHA"] == "${{ github.event.workflow_run.head_sha }}"
    image = flow["jobs"]["image"]
    checkout = next(step for step in image["steps"] if "checkout" in str(step.get("uses")))
    assert checkout["with"]["ref"] == "${{ needs.gate.outputs.sha }}"
    deploy = flow["jobs"]["deploy"]
    run_step = next(step for step in deploy["steps"] if "deploy.sh" in step.get("name", ""))
    assert "StrictHostKeyChecking=yes" in run_step["run"]
    assert '"deploy $SHA ${IMAGE:-build} $ACTOR"' in run_step["run"]
    # The host key is pinned: never trusted on first use.
    assert "ssh-keyscan" not in yaml.safe_dump(deploy)
    # No root login: the user comes from the secrets, documented as deploy.
    assert "root@" not in (REPO / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
