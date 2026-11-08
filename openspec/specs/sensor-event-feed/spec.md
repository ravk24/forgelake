# sensor-event-feed Specification

## Purpose
Defines the file contract for the Machine Monitoring sensor feed: high-volume, nested JSON events that ingestion can read with an explicit schema, deduplicate by event identity, and use to detect late arrivals.

## Requirements

### Requirement: JSON Lines files
Sensor events SHALL be delivered as UTF-8 JSON Lines files (one complete JSON object per line, no enclosing array) with the extension `.jsonl`, placed in the Machine Monitoring source directory. A file SHALL be written once and never modified afterwards.

#### Scenario: One event per line
- **WHEN** any line of a sensor file is parsed on its own
- **THEN** it is a complete JSON object describing exactly one event

### Requirement: Event identity and timing
Every event SHALL carry a globally unique `event_id` (UUID string) and an `event_timestamp` (ISO-8601 in UTC, with a `Z` suffix) recording when the machine produced the reading. The feed SHALL NOT contain an ingestion timestamp; the pipeline adds one when it ingests the event.

#### Scenario: Duplicate delivery identifiable
- **WHEN** the same event is delivered twice, in the same file or in different files
- **THEN** both copies carry the same `event_id`, so the lakehouse can collapse them

#### Scenario: Late arrival detectable
- **WHEN** an event reaches the feed hours after it was produced
- **THEN** its `event_timestamp` still records the production time, so comparing it with the pipeline's ingestion timestamp exposes the delay

### Requirement: Nested event structure
Each event SHALL contain the top-level fields `event_id`, `event_timestamp`, `schema_version`, `machine_id`, `factory_id` and `status`, a nested `metrics` object (`temperature_c`, `vibration_mm_s`, `pressure_bar`, `runtime_hours`) and a nested `device` object (`sensor_id`, `firmware_version`). `status` SHALL be one of `running`, `idle`, `stopped` or `fault`, and identifiers SHALL use the source database's business-identifier formats.

#### Scenario: Example file reads cleanly against the contract
- **WHEN** the repository's example feed is read with the contract's explicit nested schema, without schema inference
- **THEN** every event parses, the nested metric values are accessible as numbers, and no record is flagged as malformed

### Requirement: Valid sensor ranges documented
The contract SHALL document the physically valid range of each metric (temperature, vibration, pressure, runtime). Readings outside a range are a known data issue that the lakehouse flags; they SHALL NOT make a file invalid.

#### Scenario: Ranges available for quality checks
- **WHEN** the sensor feed specification is read
- **THEN** it states a minimum and maximum for each metric, and that out-of-range readings are kept in Bronze and flagged in Silver

### Requirement: Backward-compatible schema drift
Producers SHALL be allowed to add new optional fields, at the top level or inside `metrics` or `device`, without changing `schema_version`. Removing or retyping a documented field SHALL require a new `schema_version`. Consumers reading with the documented schema SHALL ignore fields they do not know.

#### Scenario: Unknown field tolerated
- **WHEN** an event contains an extra field `metrics.humidity_pct` that is not in the contract
- **THEN** reading with the contract's schema still succeeds, and all documented fields keep their values
