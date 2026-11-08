"""ForgeLake environment self-check.

Proves the local Spark + Delta Lake runtime works: versions, session, DataFrame,
Delta write, read-back, MERGE (update + insert) and result verification.
Exit code 0 = healthy, 1 = a step failed or hung (named in the output).

Usage:  python scripts/check_env.py
Env:    FORGELAKE_CHECK_STEP_TIMEOUT  seconds per step before it counts as hung (default 300)
"""

import os
import sys
from pathlib import Path

from forgelake.utils.env_check import cleanup, default_steps, new_scratch_dir, run_steps

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRATCH_ROOT = REPO_ROOT / "data" / "tmp" / "env_check"


def main() -> int:
    step_timeout = float(os.environ.get("FORGELAKE_CHECK_STEP_TIMEOUT", "300"))
    scratch = new_scratch_dir(SCRATCH_ROOT)
    print(f"ForgeLake environment check (scratch: {scratch}, step timeout: {step_timeout:g}s)")
    code = run_steps(default_steps(scratch), step_timeout=step_timeout)

    if code == 0:
        from pyspark.sql import SparkSession

        active = SparkSession.getActiveSession()
        if active is not None:
            active.stop()
    cleanup(scratch)
    print("RESULT: " + ("PASS" if code == 0 else "FAIL"))
    sys.stdout.flush()
    if code != 0:
        # A hung step may hold the Spark JVM; exit hard instead of waiting on it.
        # The JVM gateway exits when this process's pipe to it closes.
        os._exit(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
