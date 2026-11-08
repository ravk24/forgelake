# Tasks

All code, test and git work happens in the WSL copy `~/forge-lake`. Windows-side steps are marked **(Windows)**, and steps that need the `postgres` superuser password are marked **(user)**.

## 1. WSL to Windows PostgreSQL connectivity (D8)

- [x] 1.1 **(Windows)** Add `[wsl2]` / `networkingMode=mirrored` to `%UserProfile%\.wslconfig`, then run `wsl --shutdown`. Verify that `wslinfo --networking-mode` prints `mirrored` and that a TCP probe from WSL to `127.0.0.1:5432` connects
- [x] 1.2 Re-verify the Spark runtime after the VM restart. Verify that `.venv/bin/python scripts/check_env.py` passes twice with exit code 0 and that the full `pytest` suite passes. If either fails, switch to the NAT fallback in D8 (with the user's approval for the `pg_hba` and firewall edits) and record the reason
- [x] 1.3 Record the networking setup and how to revert it in a new "PostgreSQL access" section of `docs/setup.md`. Verify that each command in the section was run in 1.1–1.2

## 2. Role, databases and credentials (D7)

- [x] 2.1 Write `sql/admin/create_role_and_databases.sql` (password via psql `\password`, hidden input; role `forgelake` with `NOSUPERUSER NOCREATEDB NOCREATEROLE`; databases `forgelake_source` and `forgelake_source_test` owned by `forgelake`; `CONNECT` and `TEMP` revoked from `PUBLIC`). Verify that `grep -i password` finds no literal password in the file
- [x] 2.2 **(user, Windows)** Run the script with `psql -U postgres -h 127.0.0.1 -f sql/admin/create_role_and_databases.sql`. Verify with `psql -U postgres -h 127.0.0.1 -c "\du forgelake" -c "\l forgelake_source*"` that the role is not a superuser and that both databases exist, owned by `forgelake`
- [x] 2.3 **(user)** In WSL, create `~/.pgpass` with `127.0.0.1:5432:*:forgelake:<password>` and `chmod 600`. Verify that `stat -c %a ~/.pgpass` prints `600` and that the file is outside the repository
- [x] 2.4 Document 2.1–2.3, plus the PostgreSQL server version (`SELECT version()`), in the `docs/setup.md` PostgreSQL section. Verify that the documented commands match what was run

## 3. Driver, settings and connection helper (D6, TDD)

- [x] 3.1 Pick the newest `psycopg[binary]` 3.x release that publishes CPython 3.13 manylinux wheels, pin it with `==` in `requirements.txt`, and install it. Verify that `pip freeze` shows the exact pin
- [x] 3.2 Add the `postgres` marker to `pyproject.toml`. Write failing pure-Python tests for `resolve_pg_settings`: defaults (`127.0.0.1`, `5432`, `forgelake_source`, `forgelake`), precedence of `FORGELAKE_PG_*` env vars, keyword over env, and an unknown key raising `ValueError`. Verify that they fail because `forgelake.sources.db` does not exist
- [x] 3.3 Implement `forgelake/sources/__init__.py` and `forgelake/sources/db.py` (`resolve_pg_settings` and `connect`, with no password handling in code). Verify that the 3.2 tests pass
- [x] 3.4 Add a `tests/conftest.py` fixture that connects to the test database (`FORGELAKE_PG_TEST_DATABASE`, default `forgelake_source_test`) and fails with a clear message if it is unreachable. Write `postgres`-marked tests: the connected role is not a superuser (`pg_roles.rolsuper`), and the current database is the test database. Verify that they pass, and that they fail with the clear message when `FORGELAKE_PG_PORT` points at a closed port

## 4. Source DDL and guarded build (D1–D5, TDD)

- [x] 4.1 Write failing `postgres` tests for the build guard and structure: building on an empty database creates exactly the 3 schemas and 8 tables; a second build without reset exits non-zero and changes nothing; a build with reset rebuilds. Write a failing pure-Python unit test for the guard decision (existing schemas and no reset → refuse). Verify that they fail
- [x] 4.2 Write `sql/source/001_production.sql`, `002_inventory.sql` and `003_maintenance.sql` per D1–D4: tables and columns from D3, PK format checks, FKs within each schema, allowed-value checks, structural checks, shared change-tracking columns, per-schema `set_updated_at` and no-delete trigger functions, and the `updated_at` and FK indexes. Verify that each file applies cleanly to the test database inside one transaction
- [x] 4.3 Implement `build_source_schemas(conn, reset)` in `forgelake.sources.db` (files in name order, one transaction, the guard) and `scripts/init_source_db.py [--reset] [--database NAME]`. Verify that the 4.1 tests pass, and that `scripts/init_source_db.py` builds `forgelake_source` and exits 0
- [x] 4.4 Write `postgres` tests for the enforced rules: duplicate PK → `23505`; malformed own key (`fac_1`) → `23514`; orphan within a schema (`production_record` with an unknown order) → `23503`; undocumented status (`done`) → `23514`; `DELETE` → error, with the row still present. Verify that they pass against the 4.2 DDL
- [x] 4.5 Write `postgres` tests for the deliberately open rules: unknown `product_id` on an inventory transaction accepted; `machine.factory_id = 'fac_1'` accepted; null `product_id` accepted; quantity −50 accepted. Verify that they pass
- [x] 4.6 Write `postgres` tests for change tracking: insert defaults (`created_at = updated_at`, `is_deleted` false); an update without `updated_at` advances it; an update with an explicit past `updated_at` keeps it; a soft delete sets `is_deleted` and advances `updated_at`; every table has an index whose leading column is `updated_at` (from `pg_indexes`). Verify that they pass
- [x] 4.7 Write `docs/data-model.md`: a Mermaid ER diagram of the 8 tables plus the CSV and JSON entities, per-table columns with types and allowed values, the identifier formats, and the enforcement matrix (enforced vs open, with the Silver check responsible for each open rule). Verify that every open rule tested in 4.5 appears in the matrix

## 5. File contracts (D9, TDD)

- [x] 5.1 Write `docs/sources/examples/quality_inspections_20260314.csv` and `docs/sources/examples/sensor_events_example.jsonl` with the edge cases listed in D9. Verify by inspection that each named edge case is present, and that every identifier uses the D1 formats
- [x] 5.2 Write failing tests: pure-Python, the CSV contract's column names and order match the example file's header; `spark`, reading each example with its contract schema in `PERMISSIVE` mode gives zero corrupt records, an empty `remarks` reads as null, the quoted comma stays one field, nested `metrics.temperature_c` is numeric, and the unknown `humidity_pct` field is ignored. Verify that they fail because `forgelake.sources.contracts` does not exist
- [x] 5.3 Implement `forgelake/sources/contracts.py` (field lists as plain data, with lazy-pyspark `quality_csv_schema()` and `sensor_event_schema()`). Verify that the 5.2 tests pass
- [x] 5.4 Write `docs/sources/quality-csv.md` and `docs/sources/sensor-json.md` (naming, layout, columns or fields, null and timestamp conventions, business rules and sensor ranges marked as Silver checks, schema-drift rule). Verify that every requirement in the `quality-inspection-export` and `sensor-event-feed` spec deltas is covered by a section

## 6. Integration and plan

- [x] 6.1 Run the whole suite in WSL (`pytest`, then `pytest -m "not postgres and not spark"`). Verify that all tests pass and that the fast subset runs without a JVM or a database
- [x] 6.2 Confirm that no secret is tracked: `git grep -i` for the password (entered by the user, not echoed) finds nothing, and `git status` shows no `.pgpass` or `.env`. Verify that both checks come back clean
- [x] 6.3 Update `ForgeLake_Plan.txt`: Section 5 PostgreSQL row (Windows service reached from WSL2 by mirrored networking), Section 8 pointer to `docs/data-model.md`, and Section 21 Milestone 1 set to Done with Milestone 2 as the next step. Verify that the plan, `docs/data-model.md` and `docs/setup.md` agree

## Workflow follow-up

- Run `/opsx:archive source-schema-design` after review. It promotes `source-database`, `quality-inspection-export` and `sensor-event-feed` to `openspec/specs/`.
- Commit on a feature branch, push, and merge into `main`.
