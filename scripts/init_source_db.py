"""Build the PostgreSQL source schemas (production, inventory, maintenance) from sql/source/*.sql.

All DDL files are applied in one transaction, so a failed build leaves nothing half-created.
Existing schemas are only dropped with --reset.

Usage (WSL, from the repository root):
    .venv/bin/python scripts/init_source_db.py [--reset] [--database NAME]

Exit codes: 0 built, 1 schemas exist and --reset was not given, 2 connection or DDL error.
Connection settings: FORGELAKE_PG_* environment variables; password from ~/.pgpass (docs/setup.md).
"""

from __future__ import annotations

import argparse
import sys

from forgelake.sources.db import SOURCE_SCHEMAS, SchemasExistError, build_source_schemas, connect


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the ForgeLake PostgreSQL source schemas.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="drop and rebuild existing source schemas (destroys their data)",
    )
    parser.add_argument(
        "--database",
        help="database to build in (default: FORGELAKE_PG_DATABASE or forgelake_source)",
    )
    args = parser.parse_args(argv)

    import psycopg

    overrides = {"dbname": args.database} if args.database else {}
    try:
        with connect(**overrides) as conn:
            dbname = conn.info.dbname
            files = build_source_schemas(conn, reset=args.reset)
    except SchemasExistError as exc:
        print(f"init_source_db: {exc}", file=sys.stderr)
        return 1
    except (psycopg.Error, OSError) as exc:
        print(f"init_source_db: build failed, nothing was changed: {exc}", file=sys.stderr)
        return 2

    action = "Rebuilt" if args.reset else "Built"
    print(f"{action} schemas {', '.join(SOURCE_SCHEMAS)} in {dbname} from {', '.join(f.name for f in files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
