-- Production system: factories, products, production orders and production records.
--
-- Applied by forgelake.sources.db.build_source_schemas (scripts/init_source_db.py) together
-- with 002 and 003, in file-name order, inside ONE transaction. No BEGIN/COMMIT here.
-- Design: openspec/changes/source-schema-design/design.md (D1-D4); docs/data-model.md.
--
-- Enforced inside this schema: own key format and uniqueness, foreign keys, allowed values,
-- structural sanity checks, no hard deletes. updated_at is maintained by trigger.

CREATE SCHEMA production;

-- Change tracking (D4) -------------------------------------------------------------------

CREATE FUNCTION production.set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- Advance updated_at unless the writer set a new value explicitly (late-arriving rows).
    IF NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at THEN
        NEW.updated_at := clock_timestamp();
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION production.reject_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'rows in %.% are soft-deleted: set is_deleted = true instead of DELETE',
        TG_TABLE_SCHEMA, TG_TABLE_NAME;
END
$$;

-- Tables (D3) ----------------------------------------------------------------------------

CREATE TABLE production.factory (
    factory_id     text        CONSTRAINT factory_pk PRIMARY KEY
                               CONSTRAINT factory_id_format CHECK (factory_id ~ '^FAC-[0-9]{3}$'),
    factory_name   text        NOT NULL,
    city           text        NOT NULL,
    country_code   char(2)     NOT NULL,
    time_zone      text        NOT NULL,   -- IANA name, e.g. Europe/Berlin
    opened_on      date,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    is_deleted     boolean     NOT NULL DEFAULT false
);

CREATE TABLE production.product (
    product_id      text          CONSTRAINT product_pk PRIMARY KEY
                                  CONSTRAINT product_id_format CHECK (product_id ~ '^PRD-[0-9]{5}$'),
    product_name    text          NOT NULL,
    product_type    text          NOT NULL
                                  CONSTRAINT product_type_allowed
                                  CHECK (product_type IN ('finished_good', 'component', 'raw_material')),
    category        text,
    unit_of_measure text          NOT NULL
                                  CONSTRAINT product_unit_allowed
                                  CHECK (unit_of_measure IN ('unit', 'kg', 'm', 'l')),
    standard_cost   numeric(12,2),
    created_at      timestamptz   NOT NULL DEFAULT now(),
    updated_at      timestamptz   NOT NULL DEFAULT now(),
    is_deleted      boolean       NOT NULL DEFAULT false
);

CREATE TABLE production.production_order (
    order_id          text        CONSTRAINT production_order_pk PRIMARY KEY
                                  CONSTRAINT production_order_id_format CHECK (order_id ~ '^PO-[0-9]{7}$'),
    factory_id        text        NOT NULL
                                  CONSTRAINT production_order_factory_fk REFERENCES production.factory (factory_id),
    product_id        text        NOT NULL
                                  CONSTRAINT production_order_product_fk REFERENCES production.product (product_id),
    order_date        date        NOT NULL,
    due_date          date        NOT NULL,
    planned_quantity  integer     NOT NULL
                                  CONSTRAINT production_order_planned_positive CHECK (planned_quantity > 0),
    status            text        NOT NULL
                                  CONSTRAINT production_order_status_allowed
                                  CHECK (status IN ('planned', 'released', 'in_progress', 'completed', 'cancelled')),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    is_deleted        boolean     NOT NULL DEFAULT false,
    CONSTRAINT production_order_due_after_order CHECK (due_date >= order_date)
);

CREATE TABLE production.production_record (
    record_id          text        CONSTRAINT production_record_pk PRIMARY KEY
                                   CONSTRAINT production_record_id_format CHECK (record_id ~ '^PR-[0-9]{8}$'),
    order_id           text        NOT NULL
                                   CONSTRAINT production_record_order_fk REFERENCES production.production_order (order_id),
    production_date    date        NOT NULL,
    shift              text        NOT NULL
                                   CONSTRAINT production_record_shift_allowed CHECK (shift IN ('A', 'B', 'C')),
    produced_quantity  integer     NOT NULL
                                   CONSTRAINT production_record_produced_nonnegative CHECK (produced_quantity >= 0),
    scrap_quantity     integer     NOT NULL
                                   CONSTRAINT production_record_scrap_nonnegative CHECK (scrap_quantity >= 0),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    is_deleted         boolean     NOT NULL DEFAULT false
);

-- Indexes: watermark extraction (updated_at) and foreign keys ----------------------------

CREATE INDEX factory_updated_at_idx           ON production.factory (updated_at);
CREATE INDEX product_updated_at_idx           ON production.product (updated_at);
CREATE INDEX production_order_updated_at_idx  ON production.production_order (updated_at);
CREATE INDEX production_record_updated_at_idx ON production.production_record (updated_at);

CREATE INDEX production_order_factory_id_idx  ON production.production_order (factory_id);
CREATE INDEX production_order_product_id_idx  ON production.production_order (product_id);
CREATE INDEX production_record_order_id_idx   ON production.production_record (order_id);

-- Triggers -------------------------------------------------------------------------------

CREATE TRIGGER factory_set_updated_at BEFORE UPDATE ON production.factory
    FOR EACH ROW EXECUTE FUNCTION production.set_updated_at();
CREATE TRIGGER factory_reject_delete BEFORE DELETE ON production.factory
    FOR EACH ROW EXECUTE FUNCTION production.reject_delete();

CREATE TRIGGER product_set_updated_at BEFORE UPDATE ON production.product
    FOR EACH ROW EXECUTE FUNCTION production.set_updated_at();
CREATE TRIGGER product_reject_delete BEFORE DELETE ON production.product
    FOR EACH ROW EXECUTE FUNCTION production.reject_delete();

CREATE TRIGGER production_order_set_updated_at BEFORE UPDATE ON production.production_order
    FOR EACH ROW EXECUTE FUNCTION production.set_updated_at();
CREATE TRIGGER production_order_reject_delete BEFORE DELETE ON production.production_order
    FOR EACH ROW EXECUTE FUNCTION production.reject_delete();

CREATE TRIGGER production_record_set_updated_at BEFORE UPDATE ON production.production_record
    FOR EACH ROW EXECUTE FUNCTION production.set_updated_at();
CREATE TRIGGER production_record_reject_delete BEFORE DELETE ON production.production_record
    FOR EACH ROW EXECUTE FUNCTION production.reject_delete();
