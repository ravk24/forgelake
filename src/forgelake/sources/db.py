"""Connections to the PostgreSQL source databases (Production, Inventory, Maintenance).

Settings precedence: keyword argument > FORGELAKE_PG_* environment variable > default.
The password is never handled here: libpq reads it from ~/.pgpass (or PGPASSWORD).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

SOURCE_SCHEMAS = ("production", "inventory", "maintenance")

# Versioned DDL, applied in file-name order (repo root / sql / source).
DDL_DIR = Path(__file__).resolve().parents[3] / "sql" / "source"

DEFAULTS: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "forgelake_source",
    "user": "forgelake",
}

_ENV_VARS = {
    "host": ("FORGELAKE_PG_HOST", str),
    "port": ("FORGELAKE_PG_PORT", int),
    "dbname": ("FORGELAKE_PG_DATABASE", str),
    "user": ("FORGELAKE_PG_USER", str),
}


def resolve_pg_settings(overrides: Mapping[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    """Merge defaults, environment variables and explicit overrides."""
    unknown = set(overrides) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown PostgreSQL setting(s): {', '.join(sorted(unknown))}")

    settings = dict(DEFAULTS)
    for key, (var, cast) in _ENV_VARS.items():
        if var in env:
            settings[key] = cast(env[var])
    settings.update(overrides)
    return settings


def connect(**overrides: Any):
    """Open a psycopg connection to a source database."""
    import psycopg

    return psycopg.connect(**resolve_pg_settings(overrides, os.environ))


class SchemasExistError(RuntimeError):
    """The source schemas already exist and no reset was requested."""


def check_build_allowed(existing: Iterable[str], reset: bool) -> None:
    """Refuse to build over existing source schemas unless a reset was requested."""
    existing = sorted(existing)
    if existing and not reset:
        raise SchemasExistError(
            f"source schema(s) already exist: {', '.join(existing)}. Nothing was changed. "
            "Rerun with --reset to drop and rebuild them (their data is lost)."
        )


def build_source_schemas(conn, reset: bool = False, ddl_dir: Path = DDL_DIR) -> list[Path]:
    """Build the source schemas from the DDL files, all in one transaction.

    With ``reset`` the existing source schemas are dropped first, in the same transaction.
    Raises SchemasExistError (changing nothing) if they exist and ``reset`` is false.
    Returns the DDL files applied.
    """
    from psycopg import sql

    files = sorted(Path(ddl_dir).glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"no DDL files in {ddl_dir}")

    with conn.transaction():
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)", (list(SOURCE_SCHEMAS),)
            ).fetchall()
        }
        check_build_allowed(existing, reset)
        if reset:
            conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.SQL(", ").join(sql.Identifier(s) for s in SOURCE_SCHEMAS)
                )
            )
        for path in files:
            conn.execute(path.read_text(encoding="utf-8"))
    return files
