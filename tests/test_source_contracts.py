"""File contracts: Quality CSV export and sensor JSON feed (quality-inspection-export, sensor-event-feed specs)."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from forgelake.sources.contracts import (
    QUALITY_CSV_COLUMNS,
    SENSOR_EVENT_FIELDS,
    quality_csv_schema,
    quality_export_filename,
    sensor_event_schema,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "docs" / "sources" / "examples"
QUALITY_EXAMPLE = EXAMPLES / "quality_inspections_20260314.csv"
SENSOR_EXAMPLE = EXAMPLES / "sensor_events_example.jsonl"
CORRUPT = "_corrupt_record"


# Pure Python ---------------------------------------------------------------------------


def test_quality_columns_match_example_header():
    header = QUALITY_EXAMPLE.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert [c.name for c in QUALITY_CSV_COLUMNS] == header


def test_quality_columns_are_the_documented_ones():
    assert [c.name for c in QUALITY_CSV_COLUMNS] == [
        "inspection_id", "order_id", "product_id", "factory_id", "inspection_timestamp", "inspector",
        "inspected_quantity", "accepted_quantity", "rejected_quantity", "defect_count", "defect_type",
        "quality_status", "remarks",
    ]


def test_quality_export_filename_carries_business_date():
    assert quality_export_filename(date(2026, 3, 14)) == "quality_inspections_20260314.csv"
    assert QUALITY_EXAMPLE.name == quality_export_filename(date(2026, 3, 14))


def test_sensor_fields_are_the_documented_ones():
    top = {f.name: f for f in SENSOR_EVENT_FIELDS}
    assert list(top) == ["event_id", "event_timestamp", "schema_version", "machine_id", "factory_id",
                         "status", "metrics", "device"]
    assert [f.name for f in top["metrics"].fields] == [
        "temperature_c", "vibration_mm_s", "pressure_bar", "runtime_hours"]
    assert [f.name for f in top["device"].fields] == ["sensor_id", "firmware_version"]


def test_every_sensor_line_is_one_complete_event():
    for line in SENSOR_EXAMPLE.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        assert isinstance(event, dict)
        assert {f.name for f in SENSOR_EVENT_FIELDS} <= set(event)


def test_contracts_import_without_pyspark():
    code = "import sys, forgelake.sources.contracts; print('pyspark' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# Spark: read the examples with the contract schemas -----------------------------------


def _with_corrupt_column(schema):
    from pyspark.sql.types import StringType, StructField, StructType

    return StructType(schema.fields + [StructField(CORRUPT, StringType(), True)])


@pytest.fixture(scope="module")
def quality_rows(spark):
    df = (
        spark.read.option("header", True)
        .option("mode", "PERMISSIVE")
        .option("columnNameOfCorruptRecord", CORRUPT)
        .schema(_with_corrupt_column(quality_csv_schema()))
        .csv(str(QUALITY_EXAMPLE))
    )
    return df.collect()


@pytest.fixture(scope="module")
def sensor_df(spark):
    df = (
        spark.read.option("mode", "PERMISSIVE")
        .option("columnNameOfCorruptRecord", CORRUPT)
        .schema(_with_corrupt_column(sensor_event_schema()))
        .json(str(SENSOR_EXAMPLE))
    )
    return df.cache()


@pytest.mark.spark
def test_quality_example_reads_without_corrupt_records(quality_rows):
    assert len(quality_rows) == 6
    assert [r[CORRUPT] for r in quality_rows] == [None] * 6


@pytest.mark.spark
def test_quality_quoted_comma_stays_one_field(quality_rows):
    first = quality_rows[0]
    assert first["remarks"] == "Minor scratch, within tolerance"
    assert first["inspected_quantity"] == 50


@pytest.mark.spark
def test_quality_empty_field_reads_as_null(quality_rows):
    second = quality_rows[1]
    assert second["remarks"] is None
    assert second["defect_type"] is None


@pytest.mark.spark
def test_quality_duplicate_inspection_keeps_file_readable(quality_rows):
    ids = [r["inspection_id"] for r in quality_rows]
    assert ids.count("INS-00000103") == 2


@pytest.mark.spark
def test_quality_timestamp_kept_as_text(quality_rows):
    stamps = [r["inspection_timestamp"] for r in quality_rows]
    assert "2026-03-14T08:15:00+01:00" in stamps
    assert "2026-03-14T13:30:00" in stamps  # offset-less: resolved in Silver


@pytest.mark.spark
def test_sensor_example_reads_without_corrupt_records(sensor_df):
    assert sensor_df.count() == 6
    assert sensor_df.filter(sensor_df[CORRUPT].isNotNull()).count() == 0


@pytest.mark.spark
def test_sensor_nested_metrics_are_numeric(sensor_df):
    from pyspark.sql.types import DoubleType

    assert isinstance(sensor_df.schema["metrics"].dataType["temperature_c"].dataType, DoubleType)
    temps = [r["t"] for r in sensor_df.selectExpr("metrics.temperature_c AS t").collect()]
    assert 68.4 in temps


@pytest.mark.spark
def test_sensor_unknown_field_ignored(sensor_df):
    assert "humidity_pct" not in sensor_df.schema["metrics"].dataType.fieldNames()
    fault = sensor_df.filter("status = 'fault'").collect()[0]
    assert fault["metrics"]["temperature_c"] == 97.5
    assert fault["device"]["firmware_version"] == "2.3.0"


@pytest.mark.spark
def test_sensor_duplicate_delivery_shares_event_id(sensor_df):
    assert sensor_df.count() - sensor_df.select("event_id").distinct().count() == 1
