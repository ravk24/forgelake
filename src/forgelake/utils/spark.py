"""Shared, Delta-enabled local Spark session for every ForgeLake pipeline stage.

Settings precedence: keyword argument > FORGELAKE_SPARK_* environment variable > default.
Defaults are sized for a 16 GB development machine.

Note: driver memory only takes effect when the JVM starts. Once a session exists,
get_spark() returns it unchanged, so later overrides of driver memory are ignored.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import Any

DEFAULTS: dict[str, Any] = {"driver_memory": "4g", "shuffle_partitions": 8}

_ENV_VARS = {
    "driver_memory": ("FORGELAKE_SPARK_DRIVER_MEMORY", str),
    "shuffle_partitions": ("FORGELAKE_SPARK_SHUFFLE_PARTITIONS", int),
}


def resolve_spark_settings(overrides: Mapping[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    """Merge defaults, environment variables and explicit overrides."""
    unknown = set(overrides) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown Spark setting(s): {', '.join(sorted(unknown))}")

    settings = dict(DEFAULTS)
    for key, (var, cast) in _ENV_VARS.items():
        if var in env:
            settings[key] = cast(env[var])
    settings.update(overrides)
    return settings


def get_spark(app_name: str = "forgelake", **overrides: Any):
    """Return the active local Spark session with Delta Lake enabled, creating it if needed."""
    from delta import configure_spark_with_delta_pip
    from pyspark.sql import SparkSession

    active = SparkSession.getActiveSession()
    if active is not None:
        return active

    settings = resolve_spark_settings(overrides, os.environ)
    # Workers must run the driver's interpreter; otherwise they start whatever `python3`
    # is on PATH (Ubuntu's 3.12 in WSL) and fail with PYTHON_VERSION_MISMATCH.
    # PySpark reads this env var (not spark.pyspark.python) when launching workers.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    builder = (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        # Local mode needs no network: binding to the host's Wi-Fi/WSL adapter address
        # made startup intermittently hang on Windows (heartbeat re-register NPE loop).
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.memory", settings["driver_memory"])
        .config("spark.sql.shuffle.partitions", str(settings["shuffle_partitions"]))
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.ui.showConsoleProgress", "false")
    )
    return configure_spark_with_delta_pip(builder).getOrCreate()
