# Tasks

## 1. Project skeleton and pinned dependencies

- [x] 1.1 Create `.gitignore` covering `.venv/`, `__pycache__/`, `.pytest_cache/`, `data/`, `spark-warehouse/`, `metastore_db/`, `derby.log`, `*.crc`, and verify `git status` shows none of these after a test run
- [x] 1.2 Create the skeleton `src/forgelake/__init__.py`, `src/forgelake/utils/__init__.py`, `tests/`, `scripts/` and `docs/`, and verify `python -c "import sys; sys.path.insert(0,'src'); import forgelake"` succeeds
- [x] 1.3 Choose the PySpark 4.x / delta-spark 4.x pair from Delta Lake's published compatibility table (newest pair listed as compatible; baseline 4.0.x / 4.0.x). Write exact `==` pins plus `pytest` to `requirements.txt`, and verify every line is pinned with `==`
- [x] 1.4 Add a minimal `pyproject.toml` (package `forgelake`, `src/` layout, `requires-python >=3.13`, pytest settings `pythonpath = ["src"]`, `testpaths = ["tests"]`, marker `spark`), and verify `pytest --collect-only` runs without errors
- [x] 1.5 Create `.venv` with `C:\Python313\python.exe -m venv .venv`, install `requirements.txt` and `-e .`, and verify with `pip freeze` that the PySpark and delta-spark versions exactly match the pins

## 2. Native Windows platform setup (time box starts here, about 1 hour after the first failure)

- [x] 2.1 Find the Hadoop version Spark bundles from the `hadoop-client-*` jar names in `.venv/Lib/site-packages/pyspark/jars`, and record it
- [x] 2.2 Download community-built `winutils.exe` and `hadoop.dll` for that Hadoop line into `C:\hadoop\bin`, record the source URL and SHA-256 of each file, and verify `C:\hadoop\bin\winutils.exe ls C:\` runs
- [x] 2.3 Set the user environment variables `JAVA_HOME` (Adoptium JDK 17 path) and `HADOOP_HOME=C:\hadoop`, and add `%HADOOP_HOME%\bin` to the user `PATH`. Verify in a new shell that `echo $env:JAVA_HOME`, `echo $env:HADOOP_HOME` and `where hadoop.dll` resolve

## 3. Shared Delta-enabled Spark session (TDD)

- [x] 3.1 Write failing tests in `tests/test_spark_session.py` (marked `spark`, session-scoped fixture): the session writes and reads a Delta table under `tmp_path`; a second `get_spark()` returns the same session; default `spark.sql.shuffle.partitions` is `8`; session time zone is `UTC`. Verify the tests fail because `forgelake.utils.spark` does not exist
- [x] 3.2 Write a failing pure-Python test for override precedence (keyword argument > `FORGELAKE_SPARK_*` environment variable > default) against a config-resolving helper, and verify it fails
- [x] 3.3 Implement `forgelake.utils.spark` (`get_spark` using `configure_spark_with_delta_pip`, Delta extension and catalog, `local[*]`, `4g` driver memory, 8 shuffle partitions, UTC, override resolution) and verify all tests from 3.1–3.2 pass

## 4. Environment self-check (TDD)

- [x] 4.1 Write failing unit tests for the step runner in `forgelake.utils.env_check`: all steps passing gives exit code 0; a step that raises gives a report naming that step, the error text, exit code 1, and no later steps run. Verify they fail
- [x] 4.2 Implement the step runner and the version-report step (Python, Java, Spark, Delta versions; platform shown as native Windows or Linux/WSL2), and verify the 4.1 tests pass
- [x] 4.3 Write a failing `spark`-marked test for the Delta steps: write ids 1–3, then merge with id 2 updated and id 4 inserted; expect 4 rows, id 2 changed, ids 1 and 3 untouched. Verify it fails
- [x] 4.4 Implement the `session`, `create_df`, `write_delta`, `read_delta`, `merge` and `verify_merge` steps using a unique scratch directory under `data/tmp/env_check/`, with best-effort cleanup that only warns on failure. Verify the 4.3 test passes
- [x] 4.5 Add `scripts/check_env.py` as a thin wrapper and run it twice in a row on native Windows. Verify both runs print PASS for every step and exit with code 0 (`$LASTEXITCODE`)
- [x] 4.6 Run the full suite `pytest` and verify every test passes

## 5. WSL2 fallback (only if groups 2–4 fail on native Windows within the time box; otherwise check each task off as "N/A: native passed")

- [x] 5.1 Record the native failure (failing step, error text, what was tried) for the setup document
- [x] 5.2 In Ubuntu-24.04: install OpenJDK 17 (apt) and Python 3.13 (deadsnakes PPA or `uv`), clone the repo into `~/forge-lake`, create `.venv` and install the pins. Verify `java -version` and the pinned versions with `pip freeze`
- [x] 5.3 Run `pytest` and `python scripts/check_env.py` twice inside WSL2. Verify all tests pass and both checks exit with code 0, with the platform reported as Linux/WSL2

## 6. Documentation and integration

- [x] 6.1 Write `docs/setup.md`: the chosen platform and why, exact Python, Java, Spark and Delta versions, environment variables, winutils source URLs and SHA-256 (if native), the first-run Maven download note, the one-line check command, and the outcome of the native attempt. Verify each command in it was actually run during this change
- [x] 6.2 Update `ForgeLake_Plan.txt` Section 5 with the verified versions and the chosen runtime, and set Milestone 0 in Section 21 to Done. Verify the plan and `docs/setup.md` agree
- [x] 6.3 Fresh-environment check: delete `.venv`, recreate it from `docs/setup.md` alone, and run `python scripts/check_env.py`. Verify it exits with code 0 with no undocumented steps

## Workflow follow-up

- Run `/opsx:archive env-spike` after review, which promotes `spark-runtime` to `openspec/specs/`.
- Merge `plan-v1.1` (or the spike branch) into `main`.
