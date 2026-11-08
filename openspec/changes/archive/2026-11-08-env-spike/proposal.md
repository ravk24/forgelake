# Proposal

## Why

Every later milestone depends on PySpark and Delta Lake working on this machine, and that combination (Python 3.13, Java 17, Spark, delta-spark, Hadoop native binaries on Windows) is the project's biggest technical risk (AD-6). We need to prove a working, pinned stack before designing schemas or writing pipelines, so that no work is built on an unverified foundation.

## What Changes

- Pin mutually compatible versions of Python, PySpark, delta-spark and Java in the repository.
- Add the minimal project skeleton needed to hold that code (`src/forgelake/`, `tests/`, `scripts/`, dependency pins, `.gitignore`) using the v1.1 naming (AD-7).
- Add one reusable way to create a local Spark session configured for Delta Lake, so later milestones all use the same configuration.
- Add an environment check that runs the full proof end to end: start Spark, create a DataFrame, write a Delta table, read it back, run a `MERGE`, and verify the result. It reports pass or fail clearly.
- Try native Windows first, time-boxed to about an hour. This uses community-built `winutils.exe` and `hadoop.dll` matched to Spark's bundled Hadoop version. If native Windows fails within the time box, run Spark in WSL2 (Ubuntu-24.04) instead.
- Record the outcome: which runtime was chosen, the exact versions, and the setup steps, so a fresh machine can reproduce it.

## Capabilities

### New Capabilities
- `spark-runtime`: a reproducible local Spark and Delta Lake runtime for ForgeLake. It covers pinned versions, consistent session configuration, a self-check that proves Delta write, read and MERGE, and documented setup for the chosen platform.

### Modified Capabilities
<!-- None: no specs exist yet. -->

## Impact

- **New files:** dependency pins, project metadata, `.gitignore`, the `forgelake` package with a Spark session module, an environment-check script, tests, and a setup document under `docs/`.
- **Developer machine:** a Python virtual environment. If native Windows works: `JAVA_HOME` and `HADOOP_HOME` set, with winutils binaries under a local Hadoop folder. Third-party binaries, accepted for the time-boxed attempt. If not: a Python, Java and Spark setup inside WSL2 Ubuntu-24.04.
- **Plan:** `ForgeLake_Plan.txt` Section 5 gets the verified versions and the chosen runtime once the spike finishes.
- **Not affected:** no source schemas, data generation or pipeline logic. Those start in Milestone 1.
