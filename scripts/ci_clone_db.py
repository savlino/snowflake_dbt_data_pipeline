"""Create and drop isolated Snowflake CI database clones."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import snowflake.connector
from snowflake.connector.errors import Error


CI_DATABASE_PREFIX = "CLIMBERS_CI_"
SOURCE_DATABASE = "CLIMBERS_DB"


def database_name_for_suffix(suffix: str) -> str:
    clean_suffix = re.sub(r"[^A-Za-z0-9_]", "", suffix).upper()
    if not clean_suffix:
        raise ValueError("Suffix must contain at least one letter, digit, or underscore.")
    return f"{CI_DATABASE_PREFIX}{clean_suffix}"


def get_connection() -> snowflake.connector.SnowflakeConnection:
    required_variables = (
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_ROLE",
        "SNOWFLAKE_WAREHOUSE",
        "SNOWFLAKE_PRIVATE_KEY_PATH",
    )
    missing_variables = [
        name for name in required_variables if not os.environ.get(name)
    ]
    if missing_variables:
        raise ValueError(
            "Missing required environment variable(s): "
            + ", ".join(missing_variables)
        )

    private_key_path = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"])
    if not private_key_path.is_file():
        raise FileNotFoundError(f"Private key file not found: {private_key_path}")

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        private_key_file=str(private_key_path),
        private_key_file_pwd=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
    )


def create_database(connection, database_name: str) -> None:
    if not database_name.startswith(CI_DATABASE_PREFIX):
        raise ValueError(f"Refusing to create non-CI database: {database_name}")
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE {database_name} CLONE {SOURCE_DATABASE}"
        )
    print(f"Created zero-copy clone {database_name} from {SOURCE_DATABASE}.")


def drop_database(connection, database_name: str) -> None:
    if not database_name.startswith(CI_DATABASE_PREFIX):
        raise ValueError(f"Refusing to drop non-CI database: {database_name}")
    with connection.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS {database_name}")
    print(f"Dropped CI clone {database_name} if it existed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("create", "drop"):
        action_parser = subparsers.add_parser(action)
        action_parser.add_argument("--suffix", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        database_name = database_name_for_suffix(args.suffix)
        connection = get_connection()
    except (Error, FileNotFoundError, ValueError) as exc:
        print(f"CI database operation failed: {exc}", file=sys.stderr)
        return 1

    try:
        if args.action == "create":
            create_database(connection, database_name)
        else:
            drop_database(connection, database_name)
    except (Error, ValueError) as exc:
        print(f"CI database operation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())