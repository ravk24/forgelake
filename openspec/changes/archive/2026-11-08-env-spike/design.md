# Design

## Context

See proposal.md (Why). The machine state was observed on 2026-11-07:

| Item | State |
|---|---|
| OS | Windows 11 (build 26300), 16 GB RAM |
| Python | 3.13.5 at `C:\Python313`; no PySpark or delta-spark installed; pytest 8.3.5 installed globally |
| Java | OpenJDK 17.0.20.1 (Eclipse Adoptium) on `PATH`; `JAVA_HOME` unset |
| Hadoop | No `HADOOP_HOME`, no winutils |
| Docker | CLI present, engine not running |
| WSL2 | Ubuntu-24.04 installed (stopped) |
| Repo | Planning documents only; no code, no `src/`, no `.gitignore` |

Fixed constraints: Python 3.13 and Java 17 are already installed and stay unless the spike shows they can't work. The package name is `forgelake` (AD-7). The fallback order is native Windows, then WSL2, then Docker (AD-6). The user chose a time-boxed native-first attempt and accepted community-built winutils binaries for it.

## Goals / Non-Goals

**Goals:**
- A version pin set that is proven by passing the self-check, not assumed from release notes.
- A single shared Spark session entry point that Milestones 3–7 import instead of building their own sessions.
- A self-check script short enough to rerun after any environment change.

**Non-Goals:**
- No configuration-file system. Overrides use environment variables for now; a config module can arrive with Milestone 3, when storage paths need it.
- No Docker setup, unless both native Windows and WSL2 fail.
- No CI pipeline, no performance tuning beyond safe memory defaults.
- No PostgreSQL connectivity. That comes in Milestone 1.

## Decisions

### D1. Version line: Spark 4.x with the matching delta-spark 4.x
- Candidate pair: the newest PySpark 4.x release together with the delta-spark release that Delta Lake's compatibility table lists for it. The baseline known to be compatible is PySpark 4.0.x with delta-spark 4.0.x. The implementer checks the table at implementation time and picks the newest pair that it lists as compatible.
- Why: the Spark 3.5 line doesn't officially support Python 3.13. Spark 4.x supports Python 3.13 and Java 17, which are both already installed. Delta pins its major and minor version to Spark's, so the two versions are always chosen together.
- Alternatives: (a) downgrade to Python 3.12 and use Spark 3.5 with Delta 3.x. That is more mature but means installing a second Python, and Spark 3.5 is the older line. Rejected unless 4.x fails. (b) Java 21. Not needed, because 17 is supported and installed.
- Pins: exact `==` versions go in `requirements.txt`, as named in the plan's repo layout. A minimal `pyproject.toml` declares the `forgelake` package in a `src/` layout and the pytest settings. It contains no version ranges that conflict with the pins.

### D2. Delta jars come from `configure_spark_with_delta_pip`
- delta-spark's helper adds the matching Delta Maven coordinates to `spark.jars.packages`, so the Python and JVM sides can't drift apart.
- Cost: the first run downloads the jars into the Ivy cache, which needs internet; later runs work offline.
- Alternative: vendoring the jars into the repo. Rejected, because it adds binary files to Git and creates a second place where versions have to be kept in sync.

### D3. One session module: `forgelake.utils.spark`
- `get_spark(app_name=..., **overrides)` builds or returns the active session (`getOrCreate`). Defaults: `local[*]`, driver memory `4g`, `spark.sql.shuffle.partitions=8`, Delta SQL extension and catalog enabled, and a fixed UTC session time zone. UTC is fixed now because Silver will standardise mixed time zones (AD-3), and a host-dependent default would make results differ between machines.
- Overrides: keyword arguments win over the environment variables `FORGELAKE_SPARK_DRIVER_MEMORY` and `FORGELAKE_SPARK_SHUFFLE_PARTITIONS`, which win over the defaults.
- Caveat: driver memory only takes effect when the JVM starts. A second `get_spark` call with different memory reuses the existing session, and this is documented. The reuse scenario in the spec covers this.

### D4. The self-check is a list of named steps: `scripts/check_env.py`
- Steps: `versions`, then `session`, `create_df`, `write_delta`, `read_delta`, `merge` and `verify_merge`. Each step is a small function. A runner executes them in order, prints `PASS`/`FAIL` with the step name, stops at the first failure, prints the exception, and exits with status 1. If every step passes, it exits with status 0.
- MERGE fixture: write 3 rows (ids 1–3). Merge 2 rows: id 2 with a changed value, which tests the update path, and id 4, which is new and tests the insert path. Expected result: 4 rows, id 2 updated, ids 1 and 3 untouched. This is the same upsert pattern Bronze and Silver will use (AD-2), so the check proves the operation the project actually needs.
- Scratch location: `data/tmp/env_check/<timestamp>-<random>/`. `data/` is gitignored. Each run gets a fresh directory, which avoids stale-table effects. Cleanup is best-effort: on Windows, a JVM file lock can block deletion, so a failed delete produces a warning, not a failure.
- The step runner sits in the package (`forgelake.utils.env_check`) and the script is a thin wrapper around it. That way the steps can be unit-tested, and the failure-reporting scenario can be tested by putting a deliberately failing step into the list.

### D5. Native Windows attempt, time-boxed
- Read the Hadoop version Spark bundles from the `hadoop-client-*` jar names in `pyspark/jars`. Get community-built `winutils.exe` and `hadoop.dll` for that Hadoop line, set them up under `C:\hadoop\bin`, and set `HADOOP_HOME=C:\hadoop` and `JAVA_HOME` to the Adoptium JDK. `hadoop.dll` also goes on `PATH`, meaning `%HADOOP_HOME%\bin`.
- Record the download source URL and the SHA-256 of both binaries in the setup document so the choice can be audited.
- **Deviation (2026-11-07, approved by the user):** PySpark 4.2.0 bundles Hadoop 3.5.0, and no widely used repo publishes a 3.5 winutils build. We use `cdarlint/winutils` hadoop-3.3.6 (the most widely used source), pinned to a commit. The mismatch is accepted because the Windows native calls Spark uses have changed little across Hadoop 3.x. The self-check decides: if it fails, D6 applies.
- Time box: about 1 hour of work after the first failure. If the check still fails, record the error and switch to D6. Don't chase Windows-specific JVM issues beyond the time box (AD-6).

### D6. WSL2 fallback (only if D5 fails)
- In Ubuntu-24.04: install Python 3.13 if the distro's version differs (deadsnakes PPA or `uv`), OpenJDK 17 from apt, and a virtual environment with the same `requirements.txt`. No winutils is needed on Linux.
- Keep the repo in the WSL filesystem (`~/forge-lake`) and edit with VS Code Remote-WSL. `/mnt/c` is much slower for Spark's many small-file operations and has its own locking quirks.
- The same `check_env.py` runs unchanged, which shows the code is platform-neutral.

### D7. Documentation
- `docs/setup.md`: the chosen platform, exact versions, environment variables, binary sources and checksums, the one command to run the check, and a short record of the native attempt (passed, or what failed). Section 5 of the master plan gets the verified versions.

## Risks / Trade-offs

- [Community winutils binaries are unsigned third-party code] → The user accepted them for the time-boxed attempt. Record the source URL and SHA-256, take them only from a widely used repo, and match the exact Hadoop line. WSL2 needs none of this.
- [Spark 4.x on Python 3.13 is newer and less battle-tested] → The self-check is the arbiter. Fallback within D1: Python 3.12 with Spark 3.5 and Delta 3.x.
- [The first run needs Maven access for the Delta jars] → Document it. Later runs use the Ivy cache. A corporate proxy would need `spark.jars.ivySettings`, which isn't expected here.
- [Spark startup makes tests slow, around 10–30 seconds] → Use one session-scoped pytest fixture and mark Spark tests `spark`, so pure-Python tests can run without them.
- [Windows file locks leave scratch directories behind] → Each run uses a unique directory, cleanup failures only warn, and `data/` is gitignored.
- [A WSL2 fallback splits the workflow between Windows and Linux] → Accepted. A single repo location inside WSL with VS Code Remote-WSL keeps it to one place.

## Migration Plan

This is a new environment with nothing to migrate. Rollback: delete `.venv/`, `C:\hadoop` and the two user environment variables. Repo changes are confined to new files.
