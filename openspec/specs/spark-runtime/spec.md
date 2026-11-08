# spark-runtime Specification

## Purpose

Provides a reproducible, version-pinned local Spark runtime with Delta Lake support that every ForgeLake pipeline stage uses, plus a self-check that proves the runtime can perform the Delta operations the lakehouse depends on.

## Requirements

### Requirement: Pinned runtime versions
The project SHALL declare exact versions for PySpark and delta-spark, and SHALL document the required Python and Java versions, such that a fresh installation from those pins produces a runtime that passes the environment check.

#### Scenario: Install from pins
- **WHEN** a developer creates a fresh virtual environment and installs the project's pinned dependencies
- **THEN** the installed PySpark and delta-spark versions exactly match the declared pins

#### Scenario: Unpinned dependency rejected
- **WHEN** the dependency declarations are inspected
- **THEN** PySpark and delta-spark each have an exact version (no ranges or unpinned entries)

### Requirement: Shared Delta-enabled Spark session
The project SHALL provide a single way to obtain a local Spark session that is configured for Delta Lake, so that all pipeline stages use identical Spark and Delta configuration.

#### Scenario: Session supports Delta
- **WHEN** a caller obtains a Spark session through the shared entry point
- **THEN** the session can write and read tables in Delta format without further configuration

#### Scenario: Session is reused
- **WHEN** a caller obtains the shared session twice in the same process
- **THEN** the same active session is returned rather than a second one being started

### Requirement: Session fits development hardware
The shared session SHALL run in local mode with driver memory and shuffle parallelism bounded for a 16 GB development machine, and these settings SHALL be overridable through configuration rather than code changes.

#### Scenario: Default local configuration
- **WHEN** a session is obtained with no overrides
- **THEN** it runs in local mode with the documented default memory and shuffle-partition settings

#### Scenario: Override through configuration
- **WHEN** a configuration override for driver memory or shuffle partitions is supplied
- **THEN** the session uses the overridden value

### Requirement: Environment self-check
The project SHALL provide an environment check, runnable by a single documented command, that creates a DataFrame, writes it as a Delta table, reads it back, performs a Delta MERGE that both updates and inserts rows, and verifies the merged result.

#### Scenario: Healthy environment
- **WHEN** the environment check runs on a correctly set-up machine
- **THEN** every step reports success, the merged table contains the expected updated and inserted rows, and the command exits with status 0

#### Scenario: Broken environment
- **WHEN** any step fails (for example Java is missing, native Hadoop binaries are missing, or the MERGE result differs from expected)
- **THEN** the check names the failing step, shows the underlying error, and exits with a non-zero status

#### Scenario: Repeatable run
- **WHEN** the environment check runs twice in a row
- **THEN** both runs pass, because each run uses its own scratch location and does not depend on leftovers from earlier runs

### Requirement: Runtime report
The environment check SHALL report the Python, Java, Spark and Delta Lake versions and the operating platform it ran on.

#### Scenario: Versions shown
- **WHEN** the environment check runs
- **THEN** its output lists the Python, Java, Spark and Delta Lake versions and whether it ran on native Windows or Linux/WSL2

### Requirement: Documented reproducible setup
The project SHALL document the chosen runtime platform (native Windows or WSL2) and the exact setup steps, including any environment variables and native binaries, such that following the document on a fresh machine leads to a passing environment check.

#### Scenario: Follow the setup document
- **WHEN** a developer follows the setup document step by step
- **THEN** the environment check passes without undocumented steps

#### Scenario: Platform decision recorded
- **WHEN** the spike concludes
- **THEN** the documentation states which platform was chosen, why, and what failed on the rejected platform if it was tried
