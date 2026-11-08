"""Connection-settings resolution for the source PostgreSQL databases (pure Python, no database)."""

import pytest

from forgelake.sources.db import resolve_pg_settings


def test_defaults_point_at_local_forgelake_source():
    assert resolve_pg_settings({}, {}) == {
        "host": "127.0.0.1",
        "port": 5432,
        "dbname": "forgelake_source",
        "user": "forgelake",
    }


def test_environment_overrides_defaults():
    env = {
        "FORGELAKE_PG_HOST": "db.example",
        "FORGELAKE_PG_PORT": "6543",
        "FORGELAKE_PG_DATABASE": "other_db",
        "FORGELAKE_PG_USER": "someone",
    }
    assert resolve_pg_settings({}, env) == {
        "host": "db.example",
        "port": 6543,
        "dbname": "other_db",
        "user": "someone",
    }


def test_keyword_overrides_environment():
    settings = resolve_pg_settings({"dbname": "kw_db"}, {"FORGELAKE_PG_DATABASE": "env_db"})
    assert settings["dbname"] == "kw_db"


def test_unknown_setting_rejected():
    with pytest.raises(ValueError, match="password"):
        resolve_pg_settings({"password": "x"}, {})
