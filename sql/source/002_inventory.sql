-- Inventory system: warehouses and inventory transactions.
--
-- Applied after 001 inside the same transaction (see 001_production.sql). No BEGIN/COMMIT here.
--
-- Deliberately NOT enforced (design D2; checked in Silver, see docs/data-model.md):
--   warehouse.factory_id, inventory_transaction.product_id and .reference_order_id refer to
--   the Production system. They are nullable, have no foreign key and no format check.
--   inventory_transaction.quantity has no range check (negative units can exist at source).

CREATE SCHEMA inventory;

-- Change tracking (D4) -------------------------------------------------------------------

CREATE FUNCTION inventory.set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- Advance updated_at unless the writer set a new value explicitly (late-arriving rows).
    IF NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at THEN
        NEW.updated_at := clock_timestamp();
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION inventory.reject_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'rows in %.% are soft-deleted: set is_deleted = true instead of DELETE',
        TG_TABLE_SCHEMA, TG_TABLE_NAME;
END
$$;

-- Tables (D3) ----------------------------------------------------------------------------

CREATE TABLE inventory.warehouse (
    warehouse_id    text        CONSTRAINT warehouse_pk PRIMARY KEY
                                CONSTRAINT warehouse_id_format CHECK (warehouse_id ~ '^WH-[0-9]{3}$'),
    factory_id      text,       -- open: Production system's factory, not validated here
    warehouse_name  text        NOT NULL,
    warehouse_type  text        NOT NULL
                                CONSTRAINT warehouse_type_allowed
                                CHECK (warehouse_type IN ('raw_material', 'finished_goods', 'spare_parts')),
    capacity_units  integer,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    is_deleted      boolean     NOT NULL DEFAULT false
);

CREATE TABLE inventory.inventory_transaction (
    transaction_id         text        CONSTRAINT inventory_transaction_pk PRIMARY KEY
                                       CONSTRAINT inventory_transaction_id_format
                                       CHECK (transaction_id ~ '^IT-[0-9]{9}$'),
    warehouse_id           text        NOT NULL
                                       CONSTRAINT inventory_transaction_warehouse_fk
                                       REFERENCES inventory.warehouse (warehouse_id),
    product_id             text,       -- open: Production system's product, not validated here
    reference_order_id     text,       -- open: Production system's order, not validated here
    transaction_type       text        NOT NULL
                                       CONSTRAINT inventory_transaction_type_allowed
                                       CHECK (transaction_type IN
                                              ('receipt', 'issue', 'transfer_in', 'transfer_out', 'adjustment')),
    quantity               integer     NOT NULL,   -- open: no range check
    transaction_timestamp  timestamptz NOT NULL,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    is_deleted             boolean     NOT NULL DEFAULT false
);

-- Indexes: watermark extraction (updated_at) and foreign keys ----------------------------

CREATE INDEX warehouse_updated_at_idx             ON inventory.warehouse (updated_at);
CREATE INDEX inventory_transaction_updated_at_idx ON inventory.inventory_transaction (updated_at);

CREATE INDEX inventory_transaction_warehouse_id_idx ON inventory.inventory_transaction (warehouse_id);

-- Triggers -------------------------------------------------------------------------------

CREATE TRIGGER warehouse_set_updated_at BEFORE UPDATE ON inventory.warehouse
    FOR EACH ROW EXECUTE FUNCTION inventory.set_updated_at();
CREATE TRIGGER warehouse_reject_delete BEFORE DELETE ON inventory.warehouse
    FOR EACH ROW EXECUTE FUNCTION inventory.reject_delete();

CREATE TRIGGER inventory_transaction_set_updated_at BEFORE UPDATE ON inventory.inventory_transaction
    FOR EACH ROW EXECUTE FUNCTION inventory.set_updated_at();
CREATE TRIGGER inventory_transaction_reject_delete BEFORE DELETE ON inventory.inventory_transaction
    FOR EACH ROW EXECUTE FUNCTION inventory.reject_delete();
