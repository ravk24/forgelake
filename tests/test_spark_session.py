import pytest

from forgelake.utils.spark import get_spark, resolve_spark_settings


# --- Delta-enabled shared session (requires a JVM) -------------------------

@pytest.mark.spark
def test_session_writes_and_reads_delta(spark, tmp_path):
    path = str(tmp_path / "people")
    spark.createDataFrame([(1, "a"), (2, "b")], "id INT, name STRING") \
        .write.format("delta").save(path)

    rows = spark.read.format("delta").load(path).orderBy("id").collect()

    assert [(r.id, r.name) for r in rows] == [(1, "a"), (2, "b")]


@pytest.mark.spark
def test_second_call_returns_same_session(spark):
    assert get_spark() is spark


@pytest.mark.spark
def test_default_shuffle_partitions_is_eight(spark):
    assert spark.conf.get("spark.sql.shuffle.partitions") == "8"


@pytest.mark.spark
def test_driver_binds_to_loopback(spark):
    # Local mode never needs the network; binding to the Wi-Fi/WSL adapter address
    # made startup intermittently hang on Windows (executor heartbeat re-register NPE).
    assert spark.conf.get("spark.driver.host") == "127.0.0.1"
    assert spark.conf.get("spark.driver.bindAddress") == "127.0.0.1"


@pytest.mark.spark
def test_workers_use_driver_interpreter(spark):
    # Otherwise workers start whatever `python3` is on PATH (Ubuntu's 3.12 in WSL),
    # and PySpark refuses mismatched minor versions.
    import sys

    def worker_version(_):
        import sys as worker_sys

        return worker_sys.version_info[:2]

    seen = spark.sparkContext.parallelize([0], 1).map(worker_version).collect()

    assert seen == [sys.version_info[:2]]


@pytest.mark.spark
def test_session_time_zone_is_utc(spark):
    assert spark.conf.get("spark.sql.session.timeZone") == "UTC"


# --- Override precedence (pure Python, no JVM) ------------------------------

def test_defaults_when_nothing_overridden():
    settings = resolve_spark_settings(overrides={}, env={})
    assert settings == {"driver_memory": "4g", "shuffle_partitions": 8}


def test_env_var_overrides_default():
    env = {"FORGELAKE_SPARK_DRIVER_MEMORY": "6g", "FORGELAKE_SPARK_SHUFFLE_PARTITIONS": "16"}
    settings = resolve_spark_settings(overrides={}, env=env)
    assert settings == {"driver_memory": "6g", "shuffle_partitions": 16}


def test_keyword_argument_beats_env_var():
    env = {"FORGELAKE_SPARK_DRIVER_MEMORY": "6g", "FORGELAKE_SPARK_SHUFFLE_PARTITIONS": "16"}
    settings = resolve_spark_settings(overrides={"driver_memory": "2g", "shuffle_partitions": 4}, env=env)
    assert settings == {"driver_memory": "2g", "shuffle_partitions": 4}


def test_unknown_override_rejected():
    with pytest.raises(ValueError, match="executor_cores"):
        resolve_spark_settings(overrides={"executor_cores": 2}, env={})
