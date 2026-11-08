# Quality Inspection Export (CSV)

The Quality system exports the day's inspections once a night. The generator (Milestone 2) writes files to this contract, and ingestion reads them without guessing types or layout.

- Contract in code: `forgelake.sources.contracts.QUALITY_CSV_COLUMNS` and `quality_csv_schema()`
- Example: [`examples/quality_inspections_20260314.csv`](examples/quality_inspections_20260314.csv)
- Tests: `tests/test_source_contracts.py`

## Files: one per nightly export

- Name: `quality_inspections_<YYYYMMDD>.csv`, where the date is the export's **business date** (`quality_export_filename(date)`). The export for 2026-03-14 is `quality_inspections_20260314.csv`.
- Location: the Quality source directory, `data/source/quality/` (plan Section 10; configurable).
- A file is written once and **never modified afterwards**. Each file is one unit of change: the pipeline records which files it has processed (plan Section 11.2).

## Layout

- UTF-8 **without** a byte-order mark.
- Comma-separated, exactly one header row.
- Quoting per RFC 4180: a value containing a comma, a double quote or a line break is enclosed in double quotes, and an embedded double quote is doubled (`""`).
- Line endings LF or CRLF.
- The header lists the columns below, in this order.

Reading with Spark: `header=true`, the explicit `quality_csv_schema()` (no `inferSchema`), and `escape='"'` so that doubled quotes follow RFC 4180 (Spark's default escape is a backslash).

## Columns

| # | Column | Type | Required | Meaning |
|---|---|---|---|---|
| 1 | `inspection_id` | string | yes | `INS-\d{8}` |
| 2 | `order_id` | string | yes | Production order, `PO-\d{7}` |
| 3 | `product_id` | string | yes | Product, `PRD-\d{5}` |
| 4 | `factory_id` | string | yes | Inspecting factory, `FAC-\d{3}` |
| 5 | `inspection_timestamp` | string (ISO-8601) | yes | Local date-time of the factory, with UTC offset |
| 6 | `inspector` | string | no | Inspector name |
| 7 | `inspected_quantity` | int | yes | Units inspected |
| 8 | `accepted_quantity` | int | yes | Units accepted |
| 9 | `rejected_quantity` | int | yes | Units rejected |
| 10 | `defect_count` | int | yes | Defects found |
| 11 | `defect_type` | string | no | Main defect category, empty when there is no defect |
| 12 | `quality_status` | string | yes | `passed`, `failed` or `rework` |
| 13 | `remarks` | string | no | Free text, may contain commas |

Identifiers use the same business-identifier formats as the source database ([data-model.md](../data-model.md#identifier-formats)).

## Nulls and timestamps

- An **empty field means null**, for every column. `remarks` written as nothing between two commas reads as null, not as an empty string.
- `inspection_timestamp` is an ISO-8601 local date-time **with** UTC offset, for example `2026-03-14T08:15:00+01:00`, so it converts to UTC without other information. The contract keeps it as a string; Silver parses it.
- Known data issue: some rows arrive **without an offset** (`2026-03-14T13:30:00`). Silver resolves them with the inspecting factory's `production.factory.time_zone` (plan Section 9, mixed time zones).

## Business rules: checks the lakehouse performs

These rules hold for a valid inspection, but the export does **not** enforce them. A violation never makes a file invalid: the rows are kept in Bronze as delivered and handled in Silver.

| Rule | Silver handling |
|---|---|
| `inspection_id` is unique across all exports | Deduplicate; the example repeats `INS-00000103` and still satisfies the layout contract |
| `accepted_quantity + rejected_quantity = inspected_quantity` | Flag or quarantine |
| All quantities and `defect_count` are `>= 0` | Flag or quarantine |
| `quality_status` is `passed`, `failed` or `rework` | Flag or quarantine |
| Timestamp carries an offset | Resolve with the factory time zone |
| `order_id`, `product_id`, `factory_id` exist in Production | Referential check |
