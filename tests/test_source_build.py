"""Reproducible, guarded build of the source schemas (source-database spec)."""

import subprocess
import sys
from pathlib import Path

import pytest

from forgelake.sources.db import SchemasExistError, build_source_schemas, connect

pytestmark = pytest.mark.postgres

REPO = Path(__file__).resolve().parents[1]
INIT_SCRIPT = REPO / "scripts" / "init_source_db.py"

EXPECTED_TABLES = {
    ("production", "factory"),
    ("production", "product"),
    ("production", "production_order"),
    ("production", "production_record"),
    ("inventory", "warehouse"),
    ("inventory", "inventory_transaction"),
    ("maintenance", "machine"),
    ("maintenance", "maintenance_record"),
}

_TABLE_OIDS = """
    SELECT n.nspname, c.relname, c.oid
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'r' AND n.nspname IN ('production', 'inventory', 'maintenance')
"""


def _tables(conn):
    rows = conn.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE' "
        "AND table_schema IN ('production', 'inventory', 'maintenance')"
    ).fetchall()
    return set(rows)


def _table_oids(dbname):
    with connect(dbname=dbname) as conn:
        return {(s, t): oid for s, t, oid in conn.execute(_TABLE_OIDS).fetchall()}


def _run_init(*args):
    return subprocess.run(
        [sys.executable, str(INIT_SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )


def test_build_on_empty_database_creates_three_schemas_and_eight_tables(pg_conn, source_schemas):
    pg_conn.execute("DROP SCHEMA production, inventory, maintenance CASCADE")

    build_source_schemas(pg_conn, reset=False)

    app_schemas = {
        r[0]
        for r in pg_conn.execute(
            "SELECT nspname FROM pg_namespace "
            "WHERE nspname NOT LIKE 'pg\\_%' AND nspname NOT IN ('information_schema', 'public')"
        ).fetchall()
    }
    assert app_schemas == {"production", "inventory", "maintenance"}
    assert _tables(pg_conn) == EXPECTED_TABLES


def test_no_master_data_outside_its_owning_schema(db):
    for schema, table in _tables(db):
        if table in ("factory", "product"):
            assert schema == "production"


def test_build_without_reset_refused_and_changes_nothing(db):
    before = {(s, t): oid for s, t, oid in db.execute(_TABLE_OIDS).fetchall()}

    with pytest.raises(SchemasExistError):
        build_source_schemas(db, reset=False)

    after = {(s, t): oid for s, t, oid in db.execute(_TABLE_OIDS).fetchall()}
    assert after == before


def test_build_with_reset_rebuilds(db):
    before = {(s, t): oid for s, t, oid in db.execute(_TABLE_OIDS).fetchall()}

    build_source_schemas(db, reset=True)

    after = {(s, t): oid for s, t, oid in db.execute(_TABLE_OIDS).fetchall()}
    assert set(after) == EXPECTED_TABLES
    assert set(after.values()).isdisjoint(before.values())


def test_init_script_refuses_existing_schemas(source_schemas, pg_test_dbname):
    before = _table_oids(pg_test_dbname)

    result = _run_init("--database", pg_test_dbname)

    assert result.returncode != 0
    assert "--reset" in result.stderr
    assert _table_oids(pg_test_dbname) == before


def test_init_script_with_reset_rebuilds_and_exits_zero(source_schemas, pg_test_dbname):
    before = _table_oids(pg_test_dbname)

    result = _run_init("--reset", "--database", pg_test_dbname)

    assert result.returncode == 0, result.stderr
    after = _table_oids(pg_test_dbname)
    assert set(after) == EXPECTED_TABLES
    assert set(after.values()).isdisjoint(before.values())
