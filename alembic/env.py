"""Alembic environment configuration for async SQLAlchemy."""
import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

# ── Make `src` importable regardless of how alembic is invoked ────────────────
# Without this, `alembic upgrade head` from outside the poetry venv (e.g. from a
# parent conda env shell) fails with `ModuleNotFoundError: No module named 'src'`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


from sqlalchemy import pool  # noqa: E402
from sqlalchemy.ext.asyncio import async_engine_from_config  # noqa: E402

from alembic import context  # noqa: E402
from src.db.models import Base  # noqa: E402


# ── Load .env so DATABASE_URL is available at alembic invocation time ─────────
# Without this, `alembic upgrade head` reads only the placeholder URL
# in alembic.ini (which has fake credentials) instead of the real .env URL.
def _load_dotenv_into_environ() -> None:
    env_path = _REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv_into_environ()


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url with DATABASE_URL from .env / OS environ when present.
# Matches the comment in alembic.ini: "overridden at runtime by alembic/env.py".
_runtime_url = os.environ.get("DATABASE_URL")
if _runtime_url:
    config.set_main_option("sqlalchemy.url", _runtime_url)

# src.db.models declares EVERY table the application uses (including the ones
# only reached through raw SQL, e.g. parent_documents), so this metadata is the
# complete schema that `alembic check` / autogenerate compare against.
target_metadata = Base.metadata

# What `alembic check` compares (CI "schema" job): column types (VARCHAR
# lengths included), nullability, indexes, unique/foreign-key constraints and
# comments. Server defaults are NOT compared: the ORM mostly uses client-side
# defaults and the DB keeps harmless `DEFAULT now()`-style defaults.
_COMPARE_OPTIONS = {"compare_type": True, "compare_server_default": False}


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_COMPARE_OPTIONS,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, **_COMPARE_OPTIONS)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
