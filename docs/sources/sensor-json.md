# Machine Monitoring Sensor Feed (JSON Lines)

High-volume sensor readings from the machines. Ingestion reads them with an explicit schema, deduplicates by event identity, and uses the event time to detect late arrivals.

- Contract in code: `forgelake.sources.contracts.SENSOR_EVENT_FIELDS` and `sensor_event_schema()`
- Example: [`examples/sensor_events_example.jsonl`](examples/sensor_events_example.jsonl)
- Tests: `tests/test_source_contracts.py`

## Files: JSON Lines

- UTF-8 JSON Lines: **one complete JSON object per line**, describing exactly one event, with no enclosing array. Extension `.jsonl`.
- Location: the Machine Monitoring source directory, `data/source/machine_monitoring/` (plan Section 10; configurable). File naming beyond the extension is left to the generator (Milestone 2), for example one file per chunk.
- A file is written once and **never modified afterwards**.

Reading with Spark: the explicit `sensor_event_schema()` (no schema inference), which also makes Spark ignore unknown fields.

## Event identity and timing

- `event_id`: a globally unique UUID string. When the same event is delivered twice, in the same file or in different files, both copies carry the **same** `event_id`, so the lakehouse can collapse them.
- `event_timestamp`: ISO-8601 in UTC with a `Z` suffix (`2026-03-14T07:00:00Z`), recording **when the machine produced the reading**, not when it was delivered.
- The feed has **no ingestion timestamp**. The pipeline adds `ingestion_timestamp` when it ingests the event; comparing the two exposes late arrivals (plan Section 11.2).

## Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `event_id` | string (UUID) | yes | Event identity |
| `event_timestamp` | string (ISO-8601 UTC, `Z`) | yes | When the reading was produced |
| `schema_version` | int | yes | Contract version, currently `1` |
| `machine_id` | string | yes | Machine, `MCH-\d{4}` |
| `factory_id` | string | yes | Factory, `FAC-\d{3}` |
| `status` | string | yes | `running`, `idle`, `stopped` or `fault` |
| `metrics.temperature_c` | double | no | Temperature in °C |
| `metrics.vibration_mm_s` | double | no | Vibration velocity in mm/s |
| `metrics.pressure_bar` | double | no | Pressure in bar |
| `metrics.runtime_hours` | double | no | Cumulative runtime in hours |
| `device.sensor_id` | string | no | Reporting sensor |
| `device.firmware_version` | string | no | Sensor firmware version |

Identifiers use the source database's business-identifier formats ([data-model.md](../data-model.md#identifier-formats)). A missing or `null` value means null.

## Valid sensor ranges: checks the lakehouse performs

| Metric | Minimum | Maximum |
|---|---|---|
| `temperature_c` | −20 °C | 150 °C |
| `vibration_mm_s` | 0 mm/s | 50 mm/s |
| `pressure_bar` | 0 bar | 16 bar |
| `runtime_hours` | 0 h | none; must not decrease for the same machine |

Readings outside a range are a known data issue (plan Section 9, invalid sensors). They do **not** make a file invalid: the events are kept in Bronze as delivered and flagged in Silver. Silver also deduplicates by `event_id`, checks `status` against the allowed values, and checks that `machine_id` and `factory_id` exist.

## Schema drift

- **Allowed without a version change:** producers may add new optional fields at the top level or inside `metrics` or `device`. The example's fault event carries `metrics.humidity_pct`, which is not in the contract.
- **Requires a new `schema_version`:** removing a documented field or changing its type.
- **Consumers** reading with the documented schema ignore fields they don't know, and all documented fields keep their values.
