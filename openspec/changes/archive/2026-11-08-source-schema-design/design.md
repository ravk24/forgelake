# Design

## Context

See proposal.md (Why) and the three spec deltas for the requirements. This section covers only the state that shapes the approach. It was observed on 2026-11-08.

| Item | State |
|---|---|
| Runtime | Code, Spark and pytest run in WSL2 Ubuntu-24.04 (`~/forge-lake`, Python 3.13.15). Settled in Milestone 0. |
| PostgreSQL | PostgreSQL 17 runs as the Windows service `postgresql-x64-17` (data dir `C:\Program Files\PostgreSQL\17\data`). `listen_addresses='*'`, port 5432. `pg_hba.conf` allows only `127.0.0.1/32` and `::1/128`, with `scram-sha-256`. Windows `psql.exe` is on `PATH`. The user chose this instance over installing PostgreSQL in WSL or Docker. |
| Network | WSL uses **NAT** mode (gateway `172.23.64.1`). Port 5432 is closed from WSL on both `127.0.0.1` and the gateway. There is no `%UserProfile%\.wslconfig`. |
| Code conventions | Settings resolve as keyword argument > `FORGELAKE_*` env var > default (see `forgelake.utils.spark`). pytest markers keep slow suites selectable. Exact `==` pins live in `requirements.txt`. |

## Goals / Non-Goals

**Goals:**
- One executable source of truth for each source contract: DDL for PostgreSQL, and a contract module plus an example file for CSV and JSON. Milestone 2 writes to these contracts and Milestone 3 reads them.
- Every "enforced" and "not enforced" rule in the spec is a test, so a later DDL edit can't silently change what dirt can enter.

**Non-Goals:**
- No migration framework (Alembic, Flyway). Source data is synthetic and can be regenerated from a seed, so rebuilding with an explicit reset is enough for now.
- No reading or writing of real CSV or JSON volumes, and no Bronze read options. Milestone 3 decides whether Bronze reads with the typed contract or with all columns as strings.
- No stock-level snapshot table. Available stock is derived from transactions in Gold, which avoids a second source of truth that contradicts the first.
- No new `spark-runtime` behaviour, and no PostgreSQL step in `check_env.py`.

## Decisions

### D1. Text business identifiers as primary keys
- Each entity has one identifier with a fixed format. The format is enforced by `CHECK` on the owning table and is the same identifier everywhere, including in the CSV and JSON feeds:

  | Entity | Format | Entity | Format |
  |---|---|---|---|
  | factory | `FAC-\d{3}` | warehouse | `WH-\d{3}` |
  | product | `PRD-\d{5}` | inventory_transaction | `IT-\d{9}` |
  | production_order | `PO-\d{7}` | machine | `MCH-\d{4}` |
  | production_record | `PR-\d{8}` | maintenance_record | `MR-\d{7}` |
  | quality inspection (CSV) | `INS-\d{8}` | sensor event (JSON) | UUID |

- Why: real operational exports carry business codes, not database sequence numbers. AD-3's "`FAC-001` vs `fac_1`" dirt only means something if the reference is a code. Surrogate integer keys are a Gold concern (dimension keys). Widths fit the plan's volumes with headroom, for example 100K orders in 7 digits.
- Alternative: integer identity keys plus a separate code column. Rejected: two identifiers per entity, and every feed would have to pick one.

### D2. Enforcement matrix: strict within a system, open between systems
- Enforced (rejected by PostgreSQL): own PK format and uniqueness; `NOT NULL` on own key and on parent keys within the same schema; FKs within a schema (`production_order → factory, product`; `production_record → production_order`; `inventory_transaction → warehouse`; `maintenance_record → machine`); allowed values for status and type columns; structural sanity checks that a real OLTP would have (`planned_quantity > 0`, `produced_quantity >= 0`, `scrap_quantity >= 0`, `due_date >= order_date`, `ended_at >= started_at`, `downtime_minutes >= 0`, `cost >= 0`); no row deletion.
- Deliberately not enforced: every column that refers to another schema (`warehouse.factory_id`, `inventory_transaction.product_id`, `inventory_transaction.reference_order_id`, `machine.factory_id`). These are nullable, have no FK and no format check. Also not enforced: the range of `inventory_transaction.quantity`.
- Why: separate schemas stand in for separate systems, and separate systems can't validate each other's keys (AD-1). That leaves room for exactly the PostgreSQL-side dirt AD-3 needs (null `product_id`, `fac_1`, -50 units), while the rest of the database behaves like a well-built system. `docs/data-model.md` carries the matrix and names the Silver check that covers each open rule.
- Alternative: no constraints at all, to make dirt easy. Rejected: unrealistic, and it would hide the lesson of which failures a source can and can't prevent.

### D3. Table columns
Shared on every table: `created_at timestamptz NOT NULL DEFAULT now()`, `updated_at timestamptz NOT NULL DEFAULT now()`, `is_deleted boolean NOT NULL DEFAULT false`.

| Table | Columns besides the key and shared columns |
|---|---|
| production.factory | factory_name, city, country_code `char(2)`, time_zone (IANA name, used by Silver to resolve offset-less CSV timestamps), opened_on `date` |
| production.product | product_name, product_type (`finished_good`, `component`, `raw_material`), category, unit_of_measure (`unit`, `kg`, `m`, `l`), standard_cost `numeric(12,2)` |
| production.production_order | factory_id FK, product_id FK, order_date, due_date, planned_quantity `int`, status (`planned`, `released`, `in_progress`, `completed`, `cancelled`) |
| production.production_record | order_id FK, production_date, shift (`A`, `B`, `C`), produced_quantity `int`, scrap_quantity `int` |
| inventory.warehouse | factory_id (open), warehouse_name, warehouse_type (`raw_material`, `finished_goods`, `spare_parts`), capacity_units `int` |
| inventory.inventory_transaction | warehouse_id FK, product_id (open), reference_order_id (open), transaction_type (`receipt`, `issue`, `transfer_in`, `transfer_out`, `adjustment`), quantity `int` (open), transaction_timestamp `timestamptz` |
| maintenance.machine | factory_id (open), machine_name, machine_type (`press`, `lathe`, `cnc_mill`, `welder`, `furnace`, `assembly_robot`, `paint_booth`), manufacturer, model, installed_on, status (`active`, `inactive`, `retired`) |
| maintenance.maintenance_record | machine_id FK, maintenance_type (`preventive`, `corrective`, `breakdown`, `inspection`), status (`scheduled`, `in_progress`, `completed`, `cancelled`), started_at, ended_at (null while open), downtime_minutes, cost `numeric(12,2)`, technician, notes |

- Actual production quantity is the sum of `production_record.produced_quantity`. It is not a stored column on the order, so it can't drift out of step with the records.
- Allowed values use `CHECK (col IN (...))`, not PostgreSQL enum types. A text check is visible to JDBC and Spark as plain strings, and it is easier to extend in a DDL edit.
- Indexes: one on `updated_at` per table (watermark extraction), plus one on each FK column (joins and FK checks).

### D4. Triggers: automatic `updated_at`, no hard deletes
- `BEFORE UPDATE`: if `NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at`, set `NEW.updated_at := clock_timestamp()`. An explicit new value is kept. That gives the generator its way to simulate late-arriving rows (a row committed now with an old `updated_at`). `clock_timestamp()` rather than `now()` ensures several updates inside one transaction still advance.
- `BEFORE DELETE`: raise an exception (`rows are soft-deleted: set is_deleted = true`).
- Each schema gets its own copy of the two trigger functions (`production.set_updated_at()` and so on), so each "system" is self-contained and the database holds only the three application schemas.
- Alternative: set `updated_at` from application code only. Rejected: any writer that forgets would silently break watermark extraction.

### D5. Versioned DDL and a guarded rebuild
- `sql/source/001_production.sql`, `002_inventory.sql`, `003_maintenance.sql` are applied in file-name order, all in **one transaction**, so a failed build leaves nothing half-created.
- `scripts/init_source_db.py [--reset] [--database NAME]` is a thin wrapper around `forgelake.sources.db.build_source_schemas(conn, reset)`. If any of the three schemas already exists and `--reset` is absent, it exits with code 1 and a message. With `--reset`, it runs `DROP SCHEMA … CASCADE` first, inside the same transaction.
- Why not migrations: nothing downstream depends on preserving source rows, because Milestone 2 regenerates them from `--seed`. Revisit if the source ever holds data that can't be regenerated.

### D6. Connection: psycopg 3, settings by env var, password via `~/.pgpass`
- Driver: `psycopg[binary]`, exact-pinned. It is the current PostgreSQL driver for Python, and its binary wheel bundles libpq, so no system packages are needed in WSL. The newest release with Python 3.13 wheels is chosen at implementation time.
- `forgelake.sources.db` follows the spark helper's pattern. `resolve_pg_settings(overrides, env)` resolves host `127.0.0.1`, port `5432`, database `forgelake_source` and user `forgelake`, overridable by `FORGELAKE_PG_HOST`, `_PORT`, `_DATABASE` and `_USER`. `connect(**overrides)` returns a psycopg connection.
- The password is never passed by our code. libpq reads `~/.pgpass` (mode 600, line `127.0.0.1:5432:*:forgelake:<password>`) or `PGPASSWORD`. No `.env` file and no extra dependency.
- Alternative: python-dotenv with a gitignored `.env`. Rejected: an extra dependency for something libpq already does, and a secrets file inside the repo directory is one `git add -f` away from being committed.

### D7. Role and databases (one-time admin step, run by the user)
- `sql/admin/create_role_and_databases.sql` is run once from Windows: `psql -U postgres -h 127.0.0.1 -f …`. It sets the new password with psql `\password` (hidden input, SCRAM hash computed client-side), creates `ROLE forgelake LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE`, creates databases `forgelake_source` and `forgelake_source_test`, both `OWNER forgelake`, and revokes `CONNECT` and `TEMP` from `PUBLIC` on both.
- Only the user knows the `postgres` superuser password, so this task is theirs. Claude prepares the script and verifies the result.
- Tests use `forgelake_source_test` (overridable by `FORGELAKE_PG_TEST_DATABASE`) and never touch `forgelake_source`. The tests' session fixture rebuilds the test schemas with reset once. Each test then runs inside a transaction that is rolled back, so tests can't affect one another.

### D8. WSL reaches Windows PostgreSQL through mirrored networking
- Set `[wsl2] networkingMode=mirrored` in `%UserProfile%\.wslconfig`, then run `wsl --shutdown`. In mirrored mode, `127.0.0.1` inside WSL reaches the Windows host's loopback services. The existing `pg_hba` loopback rules then admit WSL connections, with no PostgreSQL or firewall changes, and the connection stays off the network.
- Fallback, if mirrored mode fails or breaks Spark: stay on NAT, add `host all forgelake 172.16.0.0/12 scram-sha-256` to `pg_hba.conf`, and add a Windows Firewall inbound rule for TCP 5432 limited to the WSL interface. Then set `FORGELAKE_PG_HOST` to the gateway address. This needs admin rights and changes PostgreSQL's exposure, which is why it isn't the first choice.
- Changing the networking mode restarts the whole VM, so the Spark check (`check_env.py` twice, plus the full pytest suite) must pass again before this decision counts as settled.

### D9. File contracts as code: `forgelake.sources.contracts`
- Each contract holds the column or field list (name, logical type, nullable, description) as plain Python data. It also has a function that builds the matching Spark `StructType`, importing pyspark lazily so the module loads without a JVM.
- Quality CSV: logical types are string identifiers, int quantities and string `inspection_timestamp`. The timestamp stays a string because the offset may be missing (spec), and resolving it is Silver's job.
- Sensor JSON: the schema is nested, with `metrics` and `device` as structs. `event_timestamp` is a string in the contract for the same reason; Silver casts it.
- Example files live in `docs/sources/examples/` (`quality_inspections_20260314.csv`, `sensor_events_example.jsonl`). They are small and hand-written, and they include the edge cases the specs name: a quoted comma, an empty field, a duplicate `inspection_id`, an offset-less timestamp, a duplicate event, and an unknown `metrics.humidity_pct` field. A `spark`-marked test reads each file with its contract schema in `PERMISSIVE` mode and asserts there are zero corrupt records.
- Specifications: `docs/sources/quality-csv.md` and `docs/sources/sensor-json.md`, including the sensor valid ranges: temperature −20…150 °C, vibration 0…50 mm/s, pressure 0…16 bar, runtime_hours ≥ 0 and non-decreasing per machine.

### D10. Tests
- New marker `postgres`. Database tests fail with a clear connection error rather than skipping when the database is unreachable, so a broken setup can't pass silently. `pytest -m "not postgres and not spark"` remains the fast offline suite.
- One test per spec scenario where it is mechanical: rejected inserts assert the specific SQLSTATE class (`23505` unique, `23514` check, `23503` FK); the open rules assert success; the trigger tests compare timestamps; the index test reads `pg_indexes`; the role test reads `pg_roles.rolsuper`.
- Pure-Python unit tests cover settings resolution and the rebuild guard's decision logic.

## Risks / Trade-offs

- [Mirrored networking is a VM-wide change and could disturb Spark, which binds to 127.0.0.1, or other WSL tools] → Re-run the Milestone 0 check right after switching. Fall back to NAT as in D8. Revert by deleting the `.wslconfig` line and running `wsl --shutdown`.
- [Dependence on a Windows service outside the repo: version, configuration and uptime are not reproducible from the repo] → `docs/setup.md` records the PostgreSQL version and the exact admin steps. The connection settings allow pointing at any other PostgreSQL later (WSL or Docker) without code changes.
- [Text primary keys are wider than integers] → Irrelevant at these volumes. Gold adds integer surrogate keys anyway.
- [Rebuild-with-reset loses data] → Guarded by the explicit `--reset` flag. Source data is regenerable by design. The test database is separate.
- [The contract types for CSV and JSON could disagree with what Bronze actually needs] → Milestone 3 may read everything as strings into Bronze and apply the contract types in Silver. The contract still defines the meaning and is the single place to change it.

## Migration Plan

- Order: networking (D8) → admin step (D7) → `.pgpass` → dependency pin → DDL and build → tests → contracts → docs.
- Rollback: drop the two databases and the `forgelake` role (`DROP DATABASE …; DROP ROLE forgelake;` as `postgres`), remove the `.wslconfig` line and run `wsl --shutdown`, and delete `~/.pgpass`. Repo changes are confined to new files, plus pin and marker additions.
