"""Least-privilege access to the PostgreSQL test database (source-database spec)."""

import pytest

pytestmark = pytest.mark.postgres


def test_connected_role_is_not_superuser(pg_conn):
    rolsuper = pg_conn.execute(
        "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
    ).fetchone()[0]
    assert rolsuper is False


def test_tests_use_the_test_database(pg_conn, pg_test_dbname):
    assert pg_conn.execute("SELECT current_database()").fetchone()[0] == pg_test_dbname
    assert pg_test_dbname != "forgelake_source"
