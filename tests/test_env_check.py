import pytest

from forgelake.utils.env_check import run_steps


def _collect():
    lines = []
    return lines, lines.append


def test_all_steps_pass_returns_zero():
    lines, out = _collect()
    steps = [("first", lambda ctx: None), ("second", lambda ctx: "detail")]

    code = run_steps(steps, out=out)

    assert code == 0
    assert any("PASS" in line and "first" in line for line in lines)
    assert any("PASS" in line and "second" in line and "detail" in line for line in lines)


def test_failing_step_is_named_with_error_and_returns_one():
    lines, out = _collect()

    def broken(ctx):
        raise RuntimeError("java not found")

    code = run_steps([("ok", lambda ctx: None), ("session", broken)], out=out)

    assert code == 1
    report = "\n".join(lines)
    assert "FAIL" in report and "session" in report
    assert "java not found" in report


def test_steps_after_failure_do_not_run():
    ran = []

    def broken(ctx):
        raise RuntimeError("boom")

    run_steps([("broken", broken), ("later", lambda ctx: ran.append("later"))], out=lambda _: None)

    assert ran == []


def test_steps_share_context():
    def producer(ctx):
        ctx["value"] = 42

    seen = {}

    def consumer(ctx):
        seen["value"] = ctx["value"]

    assert run_steps([("produce", producer), ("consume", consumer)], out=lambda _: None) == 0
    assert seen == {"value": 42}


# --- Version / platform report ----------------------------------------------

from forgelake.utils.env_check import detect_platform, versions_step  # noqa: E402


@pytest.mark.parametrize(
    ("system", "release", "expected"),
    [
        ("Windows", "11", "native Windows"),
        ("Linux", "5.15.167.4-microsoft-standard-WSL2", "Linux/WSL2"),
        ("Linux", "6.8.0-45-generic", "Linux"),
    ],
)
def test_detect_platform(system, release, expected):
    assert detect_platform(system=system, release=release) == expected


def test_versions_step_reports_all_components():
    import platform as _p

    import pyspark

    ctx = {}
    detail = versions_step(ctx)

    assert f"Python {_p.python_version()}" in detail
    assert "Java 17" in detail
    assert f"Spark {pyspark.__version__}" in detail
    assert "Delta 4.4.1" in detail
    assert "native Windows" in detail or "Linux" in detail


# --- Delta write / read / MERGE ---------------------------------------------

from forgelake.utils.env_check import (  # noqa: E402
    EXPECTED_AFTER_MERGE,
    delta_steps,
    new_scratch_dir,
    verify_merged_rows,
)


def test_scratch_dirs_are_unique_per_run(tmp_path):
    first, second = new_scratch_dir(tmp_path), new_scratch_dir(tmp_path)
    assert first != second
    assert first.parent == tmp_path and second.parent == tmp_path


def test_verify_accepts_expected_merge_result():
    verify_merged_rows(list(EXPECTED_AFTER_MERGE))


def test_verify_rejects_wrong_merge_result():
    wrong = [row for row in EXPECTED_AFTER_MERGE if row[0] != 4]  # insert path missing
    with pytest.raises(AssertionError, match="MERGE"):
        verify_merged_rows(wrong)


@pytest.mark.spark
def test_delta_steps_update_and_insert(spark, tmp_path):
    lines = []
    code = run_steps(delta_steps(scratch_dir=tmp_path), out=lines.append)

    assert code == 0, "\n".join(lines)
    rows = spark.read.format("delta").load(str(tmp_path / "machines")).orderBy("id").collect()
    assert [(r.id, r.status) for r in rows] == [
        (1, "running"),
        (2, "maintenance"),  # updated by MERGE
        (3, "running"),
        (4, "idle"),         # inserted by MERGE
    ]


# --- Hang detection -----------------------------------------------------------

def test_step_exceeding_timeout_fails_with_step_name():
    import time

    lines = []
    code = run_steps([("session", lambda ctx: time.sleep(5))], out=lines.append, step_timeout=0.2)

    assert code == 1
    report = "\n".join(lines)
    assert "FAIL" in report and "session" in report and "timed out" in report


def test_step_timeout_does_not_affect_fast_steps():
    assert run_steps([("fast", lambda ctx: None)], out=lambda _: None, step_timeout=5) == 0
