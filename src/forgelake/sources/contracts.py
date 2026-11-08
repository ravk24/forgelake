"""File contracts for the Quality CSV export and the Machine Monitoring sensor JSON feed.

The column and field lists are plain data, so the generator and docs can use them without a JVM.
The Spark schemas are built on demand (pyspark is imported lazily).

`nullable` is the contract's meaning (may the producer leave it empty?), not a Spark guarantee:
Spark treats every column read from a file as nullable, and missing required values are a Silver check.
Timestamps stay strings: CSV timestamps may lack an offset (resolved in Silver with the factory time
zone), and Silver casts both feeds' timestamps. Specs: docs/sources/quality-csv.md, sensor-json.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Field:
    name: str
    type: str  # "string", "int", "double" or "struct"
    nullable: bool
    description: str
    fields: tuple[Field, ...] = ()


QUALITY_CSV_COLUMNS: tuple[Field, ...] = (
    Field("inspection_id", "string", False, "INS-\\d{8}; unique across all exports (Silver check)"),
    Field("order_id", "string", False, "Production order, PO-\\d{7}"),
    Field("product_id", "string", False, "Product, PRD-\\d{5}"),
    Field("factory_id", "string", False, "Inspecting factory, FAC-\\d{3}"),
    Field("inspection_timestamp", "string", False, "ISO-8601 local date-time with UTC offset"),
    Field("inspector", "string", True, "Inspector name"),
    Field("inspected_quantity", "int", False, "Units inspected, >= 0"),
    Field("accepted_quantity", "int", False, "Units accepted, >= 0"),
    Field("rejected_quantity", "int", False, "Units rejected, >= 0; accepted + rejected = inspected"),
    Field("defect_count", "int", False, "Defects found, >= 0"),
    Field("defect_type", "string", True, "Main defect category; empty when no defect"),
    Field("quality_status", "string", False, "passed, failed or rework"),
    Field("remarks", "string", True, "Free text; may contain commas (quoted)"),
)

SENSOR_EVENT_FIELDS: tuple[Field, ...] = (
    Field("event_id", "string", False, "UUID; identical on duplicate deliveries"),
    Field("event_timestamp", "string", False, "When the machine produced the reading, ISO-8601 UTC with Z"),
    Field("schema_version", "int", False, "Bumped only for removed or retyped fields"),
    Field("machine_id", "string", False, "Machine, MCH-\\d{4}"),
    Field("factory_id", "string", False, "Factory, FAC-\\d{3}"),
    Field("status", "string", False, "running, idle, stopped or fault"),
    Field(
        "metrics",
        "struct",
        False,
        "Sensor readings",
        (
            Field("temperature_c", "double", True, "Valid -20..150 degrees C"),
            Field("vibration_mm_s", "double", True, "Valid 0..50 mm/s"),
            Field("pressure_bar", "double", True, "Valid 0..16 bar"),
            Field("runtime_hours", "double", True, ">= 0, non-decreasing per machine"),
        ),
    ),
    Field(
        "device",
        "struct",
        False,
        "Reporting sensor",
        (
            Field("sensor_id", "string", True, "Sensor identifier"),
            Field("firmware_version", "string", True, "Sensor firmware version"),
        ),
    ),
)


def quality_export_filename(business_date: date) -> str:
    """Name of the nightly Quality export for a business date."""
    return f"quality_inspections_{business_date:%Y%m%d}.csv"


def _spark_type(field: Field):
    from pyspark.sql import types as T

    if field.type == "struct":
        return T.StructType([_spark_field(f) for f in field.fields])
    return {"string": T.StringType(), "int": T.IntegerType(), "double": T.DoubleType()}[field.type]


def _spark_field(field: Field):
    from pyspark.sql.types import StructField

    return StructField(field.name, _spark_type(field), nullable=True)


def quality_csv_schema():
    """Spark StructType for the Quality CSV export, in header order."""
    from pyspark.sql.types import StructType

    return StructType([_spark_field(f) for f in QUALITY_CSV_COLUMNS])


def sensor_event_schema():
    """Spark StructType for one sensor event (nested metrics and device)."""
    from pyspark.sql.types import StructType

    return StructType([_spark_field(f) for f in SENSOR_EVENT_FIELDS])
