"""Environment self-check: proves Spark + Delta Lake (write, read, MERGE) work on this machine.

Steps are (name, function) pairs. Each function receives a shared context dict and may
return a short detail string. The runner stops at the first failure.
Run via: python scripts/check_env.py
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import traceback
from collections.abc import Callable, Iterable
from importlib import metadata
from pathlib import Path
from typing import Any

Step = tuple[str, Callable[[dict[str, Any]], str | None]]


def run_steps(
    steps: Iterable[Step],
    out: Callable[[str], None] = print,
    step_timeout: float | None = None,
) -> int:
    """Run steps in order; return 0 if all pass, 1 at the first failure.

    With step_timeout, a step still running after that many seconds counts as failed,
    so a hung step (e.g. a Spark startup that never completes) is reported instead of
    blocking forever. The hung step is left on a daemon thread and abandoned.
    """
    import threading

    ctx: dict[str, Any] = {}
    for name, fn in steps:
        result: dict[str, Any] = {}

        def target(fn=fn, result=result):
            try:
                result["detail"] = fn(ctx)
            except Exception as exc:  # noqa: BLE001 - report any failure with its step name
                result["error"] = exc
                result["trace"] = traceback.format_exc()

        worker = threading.Thread(target=target, name=f"env-check-{name}", daemon=True)
        worker.start()
        worker.join(step_timeout)

        if worker.is_alive():
            out(f"FAIL  {name}: timed out after {step_timeout:g}s (step hung)")
            return 1
        if "error" in result:
            exc = result["error"]
            out(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            out(result["trace"])
            return 1
        detail = result.get("detail")
        out(f"PASS  {name}" + (f": {detail}" if detail else ""))
    return 0


# --- versions ----------------------------------------------------------------

def detect_platform(system: str | None = None, release: str | None = None) -> str:
    system = system or platform.system()
    release = release or platform.release()
    if system == "Windows":
        return "native Windows"
    if system == "Linux" and "microsoft" in release.lower():
        return "Linux/WSL2"
    return system


def _java_version() -> str:
    java_home = os.environ.get("JAVA_HOME")
    java = os.path.join(java_home, "bin", "java") if java_home else shutil.which("java")
    if not java:
        raise RuntimeError("Java not found: set JAVA_HOME or put java on PATH")
    result = subprocess.run([java, "-version"], capture_output=True, text=True, check=True)
    match = re.search(r'version "([^"]+)"', result.stderr + result.stdout)
    if not match:
        raise RuntimeError(f"Could not parse Java version from: {result.stderr.strip()}")
    return match.group(1)


def versions_step(ctx: dict[str, Any]) -> str:
    parts = [
        f"Python {platform.python_version()}",
        f"Java {_java_version()}",
        f"Spark {metadata.version('pyspark')}",
        f"Delta {metadata.version('delta-spark')}",
        f"platform {detect_platform()}",
    ]
    return ", ".join(parts)


# --- Delta write / read / MERGE -----------------------------------------------
# Fixture mirrors the upsert pattern Bronze/Silver will use: one update + one insert.

INITIAL_ROWS = [(1, "running"), (2, "running"), (3, "running")]
MERGE_ROWS = [(2, "maintenance"), (4, "idle")]
EXPECTED_AFTER_MERGE = [(1, "running"), (2, "maintenance"), (3, "running"), (4, "idle")]
_SCHEMA = "id INT, status STRING"


def new_scratch_dir(root) -> Path:
    """Create a fresh, uniquely named directory under root for one check run."""
    import uuid
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = Path(root) / f"{stamp}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True)
    return path


def verify_merged_rows(rows: list[tuple]) -> None:
    if sorted(rows) != EXPECTED_AFTER_MERGE:
        raise AssertionError(f"MERGE result mismatch: expected {EXPECTED_AFTER_MERGE}, got {sorted(rows)}")


def delta_steps(scratch_dir) -> list[Step]:
    """Steps that exercise Delta Lake in the given scratch directory."""
    table_path = str(scratch_dir / "machines")

    def session(ctx):
        from forgelake.utils.spark import get_spark

        ctx["spark"] = get_spark(app_name="forgelake-env-check")
        return f"Spark {ctx['spark'].version}, master {ctx['spark'].sparkContext.master}"

    def create_df(ctx):
        ctx["df"] = ctx["spark"].createDataFrame(INITIAL_ROWS, _SCHEMA)
        return f"{ctx['df'].count()} rows"

    def write_delta(ctx):
        ctx["df"].write.format("delta").mode("overwrite").save(table_path)
        return table_path

    def read_delta(ctx):
        rows = ctx["spark"].read.format("delta").load(table_path).collect()
        if sorted((r.id, r.status) for r in rows) != INITIAL_ROWS:
            raise AssertionError(f"Read-back mismatch: {rows}")
        return f"{len(rows)} rows read back"

    def merge(ctx):
        from delta.tables import DeltaTable

        updates = ctx["spark"].createDataFrame(MERGE_ROWS, _SCHEMA)
        (
            DeltaTable.forPath(ctx["spark"], table_path).alias("t")
            .merge(updates.alias("u"), "t.id = u.id")
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
        return "1 update + 1 insert"

    def verify_merge(ctx):
        rows = ctx["spark"].read.format("delta").load(table_path).collect()
        verify_merged_rows([(r.id, r.status) for r in rows])
        return f"{len(rows)} rows, id 2 updated, id 4 inserted"

    return [
        ("session", session),
        ("create_df", create_df),
        ("write_delta", write_delta),
        ("read_delta", read_delta),
        ("merge", merge),
        ("verify_merge", verify_merge),
    ]


def default_steps(scratch_dir) -> list[Step]:
    return [("versions", versions_step), *delta_steps(scratch_dir)]


def cleanup(path, out: Callable[[str], None] = print) -> None:
    """Best-effort removal; Windows JVM file locks may block it, which is only a warning."""
    try:
        shutil.rmtree(path)
    except OSError as exc:
        out(f"WARN  could not remove scratch dir {path}: {exc}")
