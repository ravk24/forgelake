# Proposal

## Why

Milestone 2 (data generator) and Milestone 3 (extraction and Bronze ingestion) both need fixed source contracts. They need to know what tables, columns, keys and file layouts exist, and which rules each source system enforces and which it leaves to the lakehouse. Without these contracts, the generator and the pipeline would each invent their own idea of the sources. AD-1 and AD-2 fix the shape of the sources (three PostgreSQL schemas, a CSV export, a JSON feed, audit columns, soft deletes, event IDs), but nothing yet makes them concrete, executable or testable.

## What Changes

- Define the column-level design of the eight PostgreSQL source tables across three schemas: `production` (factory, product, production_order, production_record), `inventory` (warehouse, inventory_transaction) and `maintenance` (machine, maintenance_record). This includes keys, types, allowed values, and an ER diagram in `docs/data-model.md`.
- Make the change-tracking contract from AD-2 real in the database:
  - `created_at`, `updated_at` and `is_deleted` on every table.
  - `updated_at` advances automatically on every update unless the writer sets it explicitly. The generator needs this to simulate late-arriving rows.
  - Indexes on `updated_at` support watermark extraction.
- Decide, table by table, which rules the database enforces (keys, code formats, foreign keys within a schema, allowed status values) and which it deliberately leaves unenforced (references across schemas, business-rule quantities). The unenforced rules are where AD-3 dirty data can enter. The lakehouse must catch them in Silver.
- Specify the Quality nightly CSV export: file naming, encoding, columns, timestamp and null conventions, and business rules.
- Specify the Machine Monitoring sensor feed: JSON Lines, a nested event structure, `event_id` and `event_timestamp`, valid sensor ranges, and rules for schema drift (new optional fields allowed).
- Add example files for both formats, plus machine-readable contracts that Spark can read them with. This proves the specifications are complete and unambiguous.
- Connect the WSL2 runtime to the PostgreSQL 17 instance that already runs on the Windows host, using a dedicated least-privilege role and source and test databases. The password is kept out of the repository. Add a small connection helper and a script that builds the schemas from versioned SQL files.
- Add integration tests against PostgreSQL that prove each enforced rule rejects bad rows, each deliberately unenforced rule accepts them, and the audit-column behaviour works.

## Capabilities

### New Capabilities
- `source-database`: the PostgreSQL side of the simulated operational systems. Covers schema and table structure, enforced and deliberately unenforced integrity rules, audit columns and soft deletes, automatic `updated_at`, watermark indexes, connection settings and building the schemas from versioned DDL.
- `quality-inspection-export`: the contract for the Quality system's nightly CSV export. Covers file naming, layout, columns, timestamp and null conventions, and business rules.
- `sensor-event-feed`: the contract for the Machine Monitoring JSON Lines event feed. Covers event structure, identity and timing fields, valid ranges, and schema-drift rules.

### Modified Capabilities
<!-- None. spark-runtime is unchanged; the file contracts reuse its session for their Spark read test. -->

## Impact

- **New files:** versioned DDL under `sql/source/`; a `forgelake.sources` package (DB connection settings, CSV and JSON contracts); `scripts/init_source_db.py`; example files and documentation under `docs/` (`data-model.md`, plus the CSV and JSON format specs); PostgreSQL integration tests.
- **Dependencies:** one new pinned driver, psycopg 3 (binary wheel). A new pytest marker `postgres`.
- **Developer machine:**
  - WSL2 must reach the Windows PostgreSQL service. The design uses WSL mirrored networking (one setting in `%UserProfile%\.wslconfig`); NAT plus a `pg_hba` rule is the fallback.
  - A one-time admin step creates the `forgelake` role and two databases on the Windows instance.
  - A `~/.pgpass` file in WSL holds the password.
  - Changing the networking mode restarts WSL, so the Spark environment check must pass again afterwards.
- **Docs and plan:** `docs/setup.md` gains the database setup. `ForgeLake_Plan.txt` Section 21 marks Milestone 1 done, and Section 8 points to `docs/data-model.md`.
- **Not affected:** no data generation (Milestone 2), no extraction or Bronze code (Milestone 3), no changes to the Spark runtime.
