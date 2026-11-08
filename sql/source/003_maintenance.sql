-- Maintenance system: machines and maintenance records.
--
-- Applied after 002 inside the same transaction (see 001_production.sql). No BEGIN/COMMIT here.
--
-- Deliberately NOT enforced (design D2; checked in Silver, see docs/data-model.md):
--   machine.factory_id refers to the Production system. It is nullable, has no foreign key
--   and no format check.

CREATE SCHEMA maintenance;

-- Change tracking (D4) -------------------------------------------------------------------

CREATE FUNCTION maintenance.set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- Advance updated_at unless the writer set a new value explicitly (late-arriving rows).
    IF NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at THEN
        NEW.updated_at := clock_timestamp();
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION maintenance.reject_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'rows in %.% are soft-deleted: set is_deleted = true instead of DELETE',
        TG_TABLE_SCHEMA, TG_TABLE_NAME;
END
$$;

-- Tables (D3) ----------------------------------------------------------------------------

CREATE TABLE maintenance.machine (
    machine_id    text        CONSTRAINT machine_pk PRIMARY KEY
                              CONSTRAINT machine_id_format CHECK (machine_id ~ '^MCH-[0-9]{4}$'),
    factory_id    text,       -- open: Production system's factory, not validated here
    machine_name  text        NOT NULL,
    machine_type  text        NOT NULL
                              CONSTRAINT machine_type_allowed
                              CHECK (machine_type IN ('press', 'lathe', 'cnc_mill', 'welder', 'furnace',
                                                      'assembly_robot', 'paint_booth')),
    manufacturer  text,
    model         text,
    installed_on  date,
    status        text        NOT NULL
                              CONSTRAINT machine_status_allowed CHECK (status IN ('active', 'inactive', 'retired')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    is_deleted    boolean     NOT NULL DEFAULT false
);

CREATE TABLE maintenance.maintenance_record (
    maintenance_id    text          CONSTRAINT maintenance_record_pk PRIMARY KEY
                                    CONSTRAINT maintenance_record_id_format
                                    CHECK (maintenance_id ~ '^MR-[0-9]{7}$'),
    machine_id        text          NOT NULL
                                    CONSTRAINT maintenance_record_machine_fk
                                    REFERENCES maintenance.machine (machine_id),
    maintenance_type  text          NOT NULL
                                    CONSTRAINT maintenance_record_type_allowed
                                    CHECK (maintenance_type IN ('preventive', 'corrective', 'breakdown', 'inspection')),
    status            text          NOT NULL
                                    CONSTRAINT maintenance_record_status_allowed
                                    CHECK (status IN ('scheduled', 'in_progress', 'completed', 'cancelled')),
    started_at        timestamptz   NOT NULL,
    ended_at          timestamptz,  -- null while the work is open
    downtime_minutes  integer
                                    CONSTRAINT maintenance_record_downtime_nonnegative CHECK (downtime_minutes >= 0),
    cost              numeric(12,2)
                                    CONSTRAINT maintenance_record_cost_nonnegative CHECK (cost >= 0),
    technician        text,
    notes             text,
    created_at        timestamptz   NOT NULL DEFAULT now(),
    updated_at        timestamptz   NOT NULL DEFAULT now(),
    is_deleted        boolean       NOT NULL DEFAULT false,
    CONSTRAINT maintenance_record_end_after_start CHECK (ended_at >= started_at)
);

-- Indexes: watermark extraction (updated_at) and foreign keys ----------------------------

CREATE INDEX machine_updated_at_idx            ON maintenance.machine (updated_at);
CREATE INDEX maintenance_record_updated_at_idx ON maintenance.maintenance_record (updated_at);

CREATE INDEX maintenance_record_machine_id_idx ON maintenance.maintenance_record (machine_id);

-- Triggers -------------------------------------------------------------------------------

CREATE TRIGGER machine_set_updated_at BEFORE UPDATE ON maintenance.machine
    FOR EACH ROW EXECUTE FUNCTION maintenance.set_updated_at();
CREATE TRIGGER machine_reject_delete BEFORE DELETE ON maintenance.machine
    FOR EACH ROW EXECUTE FUNCTION maintenance.reject_delete();

CREATE TRIGGER maintenance_record_set_updated_at BEFORE UPDATE ON maintenance.maintenance_record
    FOR EACH ROW EXECUTE FUNCTION maintenance.set_updated_at();
CREATE TRIGGER maintenance_record_reject_delete BEFORE DELETE ON maintenance.maintenance_record
    FOR EACH ROW EXECUTE FUNCTION maintenance.reject_delete();
