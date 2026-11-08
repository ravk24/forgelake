"""Integrity rules and change tracking of the source schemas (source-database spec, design D2-D4).

Every test runs in a transaction that is rolled back (fixture `db`), so tests can't see each other.
"""

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.postgres

# (table, primary-key column, key of the row inserted by the `rows` fixture)
TABLES = [
    ("production.factory", "factory_id", "FAC-001"),
    ("production.product", "product_id", "PRD-00001"),
    ("production.production_order", "order_id", "PO-0000001"),
    ("production.production_record", "record_id", "PR-00000001"),
    ("inventory.warehouse", "warehouse_id", "WH-001"),
    ("inventory.inventory_transaction", "transaction_id", "IT-000000001"),
    ("maintenance.machine", "machine_id", "MCH-0001"),
    ("maintenance.maintenance_record", "maintenance_id", "MR-0000001"),
]
TABLE_IDS = [t[0] for t in TABLES]

INSERT_FACTORY = (
    "INSERT INTO production.factory (factory_id, factory_name, city, country_code, time_zone) "
    "VALUES (%s, 'Plant Berlin', 'Berlin', 'DE', 'Europe/Berlin')"
)
INSERT_ORDER = (
    "INSERT INTO production.production_order "
    "(order_id, factory_id, product_id, order_date, due_date, planned_quantity, status) "
    "VALUES (%s, 'FAC-001', 'PRD-00001', '2026-03-01', '2026-03-10', 100, %s)"
)
INSERT_RECORD = (
    "INSERT INTO production.production_record "
    "(record_id, order_id, production_date, shift, produced_quantity, scrap_quantity) "
    "VALUES (%s, %s, '2026-03-02', 'A', 90, 2)"
)
INSERT_TRANSACTION = (
    "INSERT INTO inventory.inventory_transaction "
    "(transaction_id, warehouse_id, product_id, reference_order_id, transaction_type, quantity, "
    "transaction_timestamp) VALUES (%s, 'WH-001', %s, NULL, 'receipt', %s, '2026-03-02T08:00:00Z')"
)
INSERT_MACHINE = (
    "INSERT INTO maintenance.machine (machine_id, factory_id, machine_name, machine_type, status) "
    "VALUES (%s, %s, 'Press 2', 'press', 'active')"
)


@pytest.fixture
def rows(db):
    """One valid row in each of the 8 source tables."""
    db.execute(INSERT_FACTORY, ("FAC-001",))
    db.execute(
        "INSERT INTO production.product (product_id, product_name, product_type, unit_of_measure) "
        "VALUES ('PRD-00001', 'Gear housing', 'finished_good', 'unit')"
    )
    db.execute(INSERT_ORDER, ("PO-0000001", "released"))
    db.execute(INSERT_RECORD, ("PR-00000001", "PO-0000001"))
    db.execute(
        "INSERT INTO inventory.warehouse (warehouse_id, factory_id, warehouse_name, warehouse_type) "
        "VALUES ('WH-001', 'FAC-001', 'Finished goods Berlin', 'finished_goods')"
    )
    db.execute(INSERT_TRANSACTION, ("IT-000000001", "PRD-00001", 100))
    db.execute(INSERT_MACHINE, ("MCH-0001", "FAC-001"))
    db.execute(
        "INSERT INTO maintenance.maintenance_record "
        "(maintenance_id, machine_id, maintenance_type, status, started_at, ended_at, downtime_minutes, cost) "
        "VALUES ('MR-0000001', 'MCH-0001', 'preventive', 'completed', "
        "'2026-03-02T06:00:00Z', '2026-03-02T07:30:00Z', 90, 250.00)"
    )
    return db


def assert_rejected(conn, sqlstate, query, params=()):
    """The statement fails with `sqlstate`; a savepoint keeps the test transaction usable."""
    import psycopg

    with pytest.raises(psycopg.Error) as exc:
        with conn.transaction():
            conn.execute(query, params)
    assert exc.value.sqlstate == sqlstate, exc.value
    return exc.value


def fetch_one(conn, query, params=()):
    return conn.execute(query, params).fetchone()


# Enforced rules (4.4) ------------------------------------------------------------------


def test_duplicate_primary_key_rejected(rows):
    assert_rejected(rows, "23505", INSERT_FACTORY, ("FAC-001",))


def test_malformed_own_key_rejected(db):
    assert_rejected(db, "23514", INSERT_FACTORY, ("fac_1",))


def test_missing_own_key_rejected(db):
    assert_rejected(db, "23502", INSERT_FACTORY, (None,))


def test_orphan_within_a_schema_rejected(rows):
    assert_rejected(rows, "23503", INSERT_RECORD, ("PR-00000002", "PO-9999999"))


def test_undocumented_status_rejected(rows):
    assert_rejected(rows, "23514", INSERT_ORDER, ("PO-0000002", "done"))


@pytest.mark.parametrize(("table", "pk", "key"), TABLES, ids=TABLE_IDS)
def test_hard_delete_rejected_and_row_kept(rows, table, pk, key):
    error = assert_rejected(rows, "P0001", f"DELETE FROM {table} WHERE {pk} = %s", (key,))

    assert "soft-deleted" in str(error)
    assert fetch_one(rows, f"SELECT count(*) FROM {table} WHERE {pk} = %s", (key,))[0] == 1


# Deliberately open rules (4.5) ---------------------------------------------------------


def test_unknown_cross_system_product_accepted(rows):
    rows.execute(INSERT_TRANSACTION, ("IT-000000002", "PRD-99999", 10))
    assert fetch_one(rows, "SELECT count(*) FROM production.product WHERE product_id = 'PRD-99999'")[0] == 0


def test_inconsistently_formatted_cross_system_factory_accepted(rows):
    rows.execute(INSERT_MACHINE, ("MCH-0002", "fac_1"))
    assert fetch_one(rows, "SELECT factory_id FROM maintenance.machine WHERE machine_id = 'MCH-0002'")[0] == "fac_1"


def test_null_cross_system_product_accepted(rows):
    rows.execute(INSERT_TRANSACTION, ("IT-000000002", None, 10))
    assert fetch_one(
        rows, "SELECT product_id FROM inventory.inventory_transaction WHERE transaction_id = 'IT-000000002'"
    ) == (None,)


def test_negative_inventory_quantity_accepted(rows):
    rows.execute(INSERT_TRANSACTION, ("IT-000000002", "PRD-00001", -50))
    assert fetch_one(
        rows, "SELECT quantity FROM inventory.inventory_transaction WHERE transaction_id = 'IT-000000002'"
    ) == (-50,)


# Change tracking (4.6) -----------------------------------------------------------------


@pytest.mark.parametrize(("table", "pk", "key"), TABLES, ids=TABLE_IDS)
def test_insert_defaults(rows, table, pk, key):
    created_at, updated_at, is_deleted, tx_time = fetch_one(
        rows, f"SELECT created_at, updated_at, is_deleted, now() FROM {table} WHERE {pk} = %s", (key,)
    )
    assert created_at == updated_at == tx_time
    assert is_deleted is False


@pytest.mark.parametrize(("table", "pk", "key"), TABLES, ids=TABLE_IDS)
def test_update_advances_updated_at(rows, table, pk, key):
    query = f"SELECT updated_at FROM {table} WHERE {pk} = %s"
    before = fetch_one(rows, query, (key,))[0]

    rows.execute(f"UPDATE {table} SET is_deleted = is_deleted WHERE {pk} = %s", (key,))

    assert fetch_one(rows, query, (key,))[0] > before


@pytest.mark.parametrize(("table", "pk", "key"), TABLES, ids=TABLE_IDS)
def test_explicit_past_updated_at_kept(rows, table, pk, key):
    past = datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc)

    rows.execute(f"UPDATE {table} SET updated_at = %s WHERE {pk} = %s", (past, key))

    assert fetch_one(rows, f"SELECT updated_at FROM {table} WHERE {pk} = %s", (key,))[0] == past


@pytest.mark.parametrize(("table", "pk", "key"), TABLES, ids=TABLE_IDS)
def test_soft_delete_visible_to_watermark(rows, table, pk, key):
    query = f"SELECT is_deleted, updated_at FROM {table} WHERE {pk} = %s"
    before = fetch_one(rows, query, (key,))[1]

    rows.execute(f"UPDATE {table} SET is_deleted = true WHERE {pk} = %s", (key,))

    is_deleted, updated_at = fetch_one(rows, query, (key,))
    assert is_deleted is True
    assert updated_at > before


@pytest.mark.parametrize(("table", "pk", "key"), TABLES, ids=TABLE_IDS)
def test_updated_at_leads_an_index(db, table, pk, key):
    leading = db.execute(
        "SELECT a.attname FROM pg_index i "
        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0] "
        "WHERE i.indrelid = %s::regclass",
        (table,),
    ).fetchall()
    assert ("updated_at",) in leading
