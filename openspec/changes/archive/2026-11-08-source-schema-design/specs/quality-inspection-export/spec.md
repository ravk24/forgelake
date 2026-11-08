# Spec Delta

## Purpose

Defines the file contract for the Quality system's nightly inspection export. The generator writes files to this contract, and ingestion reads them without guessing types or layout.

## ADDED Requirements

### Requirement: One file per nightly export
Each export SHALL be one file named `quality_inspections_<YYYYMMDD>.csv`, where the date is the export's business date, placed in the Quality source directory. A file SHALL be written once and never modified afterwards, so that each file is one unit of change.

#### Scenario: File name identifies the export
- **WHEN** the export for business date 2026-03-14 is produced
- **THEN** it is a single file named `quality_inspections_20260314.csv`

### Requirement: CSV layout
Export files SHALL be UTF-8 without a byte-order mark, comma-separated, with one header row, RFC 4180 double-quote quoting, and line endings of either LF or CRLF. The header SHALL contain the documented columns in the documented order.

#### Scenario: Header matches the contract
- **WHEN** the first line of an export file is read
- **THEN** it lists exactly the documented column names in the documented order

#### Scenario: Embedded comma survives
- **WHEN** a free-text value contains a comma
- **THEN** the value is quoted and reads back as a single field

### Requirement: Documented columns
Each row SHALL describe one inspection with these columns: `inspection_id`, `order_id`, `product_id`, `factory_id`, `inspection_timestamp`, `inspector`, `inspected_quantity`, `accepted_quantity`, `rejected_quantity`, `defect_count`, `defect_type`, `quality_status`, `remarks`. Identifiers SHALL use the same business-identifier formats as the source database.

#### Scenario: Example file reads cleanly against the contract
- **WHEN** the repository's example export is read with the contract's explicit column types, without type inference
- **THEN** every row parses and no row is flagged as malformed

### Requirement: Null and timestamp conventions
An empty field SHALL mean null. `inspection_timestamp` SHALL be an ISO-8601 local date-time of the inspecting factory, with a UTC offset. Rows without an offset are a known data issue, which the lakehouse resolves using the factory's time zone.

#### Scenario: Empty field is null
- **WHEN** a row has an empty `remarks` field
- **THEN** the value reads as null, not as an empty string

#### Scenario: Offset carried
- **WHEN** a correctly formed timestamp is read
- **THEN** it contains a UTC offset, so that it converts to UTC without any other information

### Requirement: Business rules documented, not enforced at export
For a valid inspection, accepted plus rejected quantity SHALL equal inspected quantity, all quantities SHALL be non-negative, `quality_status` SHALL be one of `passed`, `failed` or `rework`, and `inspection_id` SHALL be unique across all exports. The contract SHALL document these rules as checks the lakehouse performs, and SHALL NOT treat a violation as making a file invalid.

#### Scenario: Rules listed for downstream checks
- **WHEN** the export specification is read
- **THEN** it lists each business rule above and states that violations are kept in Bronze and handled in Silver

#### Scenario: Duplicate inspection does not invalidate the file
- **WHEN** an export contains the same `inspection_id` twice
- **THEN** the file still satisfies the layout contract and remains readable
