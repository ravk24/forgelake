"""Rebuild-guard decision for the source schema build (pure Python, no database)."""

import pytest

from forgelake.sources.db import SOURCE_SCHEMAS, SchemasExistError, check_build_allowed


def test_source_schemas_are_the_three_systems():
    assert SOURCE_SCHEMAS == ("production", "inventory", "maintenance")


def test_empty_database_may_be_built():
    check_build_allowed(existing=set(), reset=False)


def test_existing_schemas_without_reset_refused():
    with pytest.raises(SchemasExistError, match="--reset"):
        check_build_allowed(existing={"inventory"}, reset=False)


def test_existing_schemas_with_reset_allowed():
    check_build_allowed(existing={"production", "inventory", "maintenance"}, reset=True)
