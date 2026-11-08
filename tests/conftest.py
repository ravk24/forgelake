import os

import pytest


@pytest.fixture(scope="session")
def spark():
    """One shared local Spark session for every `spark`-marked test (startup is slow)."""
    from forgelake.utils.spark import get_spark

    session = get_spark(app_name="forgelake-tests")
    yield session
    session.stop()


@pytest.fixture(scope="session")
def pg_test_dbname():
    """Database the `postgres` tests use; never the development source database."""
    return os.environ.get("FORGELAKE_PG_TEST_DATABASE", "forgelake_source_test")


def _connect_test_db(dbname, **kwargs):
    """Connect to the test database, or fail the test with an actionable message (never skip)."""
    import psycopg

    from forgelake.sources.db import connect

    try:
        return connect(dbname=dbname, **kwargs)
    except psycopg.OperationalError as exc:
        pytest.fail(
            f"PostgreSQL test database {dbname!r} is unreachable: {exc}\n"
            "See docs/setup.md, 'PostgreSQL access' (Windows service running? ~/.pgpass present?).",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def source_schemas(pg_test_dbname):
    """Rebuild the source schemas in the test database once per test session (committed)."""
    from forgelake.sources.db import build_source_schemas

    with _connect_test_db(pg_test_dbname) as conn:
        build_source_schemas(conn, reset=True)


@pytest.fixture
def db(source_schemas, pg_conn):
    """A rolled-back connection to the test database with freshly built source schemas."""
    return pg_conn


@pytest.fixture
def pg_conn(pg_test_dbname):
    """A connection to the test database inside a transaction that is rolled back afterwards."""
    conn = _connect_test_db(pg_test_dbname)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
