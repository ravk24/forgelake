# ForgeLake Local Setup

Verified on 2026-11-07 by the Milestone 0 environment spike (`openspec/changes/env-spike`). The fresh-environment rebuild was checked on 2026-11-08.

Quick check on an existing setup, from Windows:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc "cd ~/forge-lake && .venv/bin/python scripts/check_env.py"
```

## Chosen platform: WSL2 (Ubuntu-24.04)

Spark runs inside WSL2. Native Windows was tried first and rejected: about 1 run in 4 hung forever at Spark startup (see [Native Windows attempt](#native-windows-attempt-rejected)). AD-6 says to fall back rather than debug Windows past the time box.

Results on WSL2:
- 10 of 10 consecutive `scripts/check_env.py` runs passed.
- The full test suite (24 tests) passed in about 26 s, against about 120 s on native Windows.
- The repository lives in the Linux filesystem at `~/forge-lake`, not under `/mnt/c`, for speed and to avoid file-locking quirks (design D6). Edit it from Windows with VS Code's **WSL** extension (`code ~/forge-lake` from the Ubuntu shell).

## Verified versions

| Component | Version | Notes |
|---|---|---|
| Windows host | 11 (build 26300), 16 GB RAM | WSL2 gets 7 GB by default |
| WSL distro | Ubuntu-24.04, kernel 6.18 (WSL2) | |
| Python | 3.13.15 | installed with `uv`; Ubuntu's own `python3` is 3.12 and is **not** used |
| Java | OpenJDK 17.0.20.1 | `openjdk-17-jdk-headless` from apt |
| PySpark | 4.2.0 | pinned in `requirements.txt`; bundles Hadoop 3.5.0 and Scala 2.13 |
| delta-spark | 4.4.1 | pinned; declares `pyspark>=4.0.1,<=4.2.0`; JVM artefact `io.delta:delta-spark_4.2_2.13:4.4.1` |

## Steps

Run these in an **Ubuntu-24.04** shell (`wsl -d Ubuntu-24.04`) unless marked otherwise.

### 1. Java 17

```bash
sudo apt-get update && sudo apt-get install -y openjdk-17-jdk-headless
java -version   # openjdk version "17.0.20.1"
```

If you don't know the Linux password, run the install as root from a **Windows** terminal; no password is needed:

```powershell
wsl -d Ubuntu-24.04 -u root -- bash -c "apt-get update && apt-get install -y openjdk-17-jdk-headless"
```

To reset the Linux password, also from Windows, run `wsl -d Ubuntu-24.04 -u root passwd <linux-user>`.

### 2. Python 3.13 with uv

`uv` was already installed on this machine at `~/.local/bin/uv`. If it's missing, install it by following https://docs.astral.sh/uv/getting-started/installation/. Then:

```bash
~/.local/bin/uv python install 3.13    # creates ~/.local/bin/python3.13
~/.local/bin/python3.13 --version      # Python 3.13.x
```

### 3. Repository and virtual environment

```bash
git clone https://github.com/ravk24/forgelake.git ~/forge-lake   # main must include the env-spike work
cd ~/forge-lake
~/.local/bin/python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt -e .
```

### 4. Run the environment check

```bash
.venv/bin/python scripts/check_env.py
```

A healthy machine prints `PASS` for `versions` (reporting `platform Linux/WSL2`), `session`, `create_df`, `write_delta`, `read_delta`, `merge` and `verify_merge`, then `RESULT: PASS`, and exits with code 0. A failing or hung step is named, for example `FAIL  session: timed out after 300s`, and the check exits with code 1.

Test suite:

```bash
.venv/bin/python -m pytest              # everything (~30 s)
.venv/bin/python -m pytest -m "not spark"   # fast, no JVM
```

## Configuration

| Environment variable | Default | Effect |
|---|---|---|
| `FORGELAKE_SPARK_DRIVER_MEMORY` | `4g` | Driver JVM heap. Only applies when the first session in a process starts. |
| `FORGELAKE_SPARK_SHUFFLE_PARTITIONS` | `8` | `spark.sql.shuffle.partitions` |
| `FORGELAKE_CHECK_STEP_TIMEOUT` | `300` | Seconds before an environment-check step counts as hung |

Keyword arguments to `forgelake.utils.spark.get_spark()` take precedence over these variables. The shared session always uses `local[*]`, time zone `UTC`, and a driver bound to `127.0.0.1`. It also sets `PYSPARK_PYTHON` to the running interpreter if that variable is unset.

## Known quirks

- **First run needs internet.** Spark downloads the Delta jars from Maven Central into `~/.ivy2.5.2/`. Later runs use that cache.
- **Python version mismatch.** If workers ever report `PYTHON_VERSION_MISMATCH ... 3.12 than that in driver: 3.13`, something has set `PYSPARK_PYTHON` to Ubuntu's `python3`. Unset it, because `get_spark()` picks the right interpreter on its own.
- **Memory.** WSL2 gets 7 GB by default. To give Spark more for later performance work, set `memory=` in `%UserProfile%\.wslconfig` on Windows, then run `wsl --shutdown`.
- `WARNING: Using incubator modules: jdk.incubator.vector` is printed by Spark 4.x on Java 17 and is expected.
- The check's scratch tables go to `data/tmp/env_check/<timestamp>-<id>/`, which is gitignored and removed after each run.

## Native Windows attempt: rejected

What worked: PySpark 4.2.0 with delta-spark 4.4.1, OpenJDK 17.0.20.1, and `JAVA_HOME`/`HADOOP_HOME` set. Hadoop native binaries came from the `cdarlint/winutils` hadoop-3.3.6 build, a mismatch with the bundled Hadoop 3.5.0 because no 3.5 build is published. It was pinned to commit `7386986d5d8a079b5cd4464f4599766dd27e7d13`:

| File | SHA-256 |
|---|---|
| `winutils.exe` | `496a591eb1e67df2a620f710d529ba6ddfe1c19149e6647cc4e320bb0efd8553` |
| `hadoop.dll` | `d7ab36a68518748cef142be2da5069b4c763c2cd764c1d2e6ac48c7200405be3` |

With those, Delta write, read and `MERGE` succeed and the test suite passes.

Why it was rejected: Spark startup is unreliable. Across 11 runs of the check and the test suite, 3 hung forever in the `session` step, in both PowerShell and Git Bash. The executor logs repeat every 10 s and never recover:

```text
WARN Executor: Issue communicating with driver in heartbeater
Caused by: java.lang.NullPointerException: Cannot invoke
  "org.apache.spark.storage.BlockManagerId.executorId()" because "idWithoutTopologyInfo" is null
  at org.apache.spark.storage.BlockManagerMasterEndpoint.register(BlockManagerMasterEndpoint.scala:696)
```

What was ruled out or tried:
1. PowerShell stderr redirection. It hangs in Git Bash too; an earlier draft of this document wrongly blamed it.
2. Slow hostname resolution. It resolves in 0.01 s.
3. Binding the driver to `127.0.0.1`. No measurable improvement, but the setting is kept because it's correct for local mode.

Other Windows-only noise: at shutdown, Spark can't delete `%TEMP%\spark-*` because the JVM holds a jar open, and logs `IOException: Failed to delete`. It's harmless.

### Leftovers on the Windows host (now unused)

- `C:\PrCa\ForgeLake\.venv\`
- `C:\hadoop\`
- User environment variables `JAVA_HOME` and `HADOOP_HOME`
- `C:\hadoop\bin` in the user `PATH`

Remove them if you're not keeping native Windows as an option. They don't affect WSL.

## Rollback (WSL)

Delete `~/forge-lake/.venv`. Optionally run `sudo apt-get remove openjdk-17-jdk-headless` and `uv python uninstall 3.13`.
