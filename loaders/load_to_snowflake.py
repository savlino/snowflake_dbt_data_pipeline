"""Load the source CSV files into Snowflake raw tables."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import kagglehub
import snowflake.connector
from snowflake.connector.errors import Error


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KAGGLE_DATASET = "jordizar/climb-dataset"
STAGE = "CLIMBERS_DB.RAW.CLIMBERS_STAGE"
FILE_FORMAT = "CLIMBERS_DB.RAW.CLIMBERS_CSV_FORMAT"

TABLES = (
    {
        "file": "climber_df.csv",
        "stage_path": "climbers",
        "table": "CLIMBERS_DB.RAW.CLIMBERS",
        "ddl": """
            CREATE OR REPLACE TABLE CLIMBERS_DB.RAW.CLIMBERS (
                USER_ID NUMBER(38, 0),
                COUNTRY VARCHAR,
                SEX NUMBER(38, 0),
                HEIGHT FLOAT,
                WEIGHT FLOAT,
                AGE FLOAT,
                YEARS_CL NUMBER(38, 0),
                DATE_FIRST TIMESTAMP_NTZ,
                DATE_LAST TIMESTAMP_NTZ,
                GRADES_COUNT NUMBER(38, 0),
                GRADES_FIRST NUMBER(38, 0),
                GRADES_LAST NUMBER(38, 0),
                GRADES_MAX NUMBER(38, 0),
                GRADES_MEAN FLOAT,
                YEAR_FIRST NUMBER(38, 0),
                YEAR_LAST NUMBER(38, 0)
            )
        """,
    },
    {
        "file": "grades_conversion_table.csv",
        "stage_path": "grades",
        "table": "CLIMBERS_DB.RAW.GRADES",
        "ddl": """
            CREATE OR REPLACE TABLE CLIMBERS_DB.RAW.GRADES (
                SOURCE_ROW_ID NUMBER(38, 0),
                GRADE_ID NUMBER(38, 0),
                GRADE_FRA VARCHAR(20)
            )
        """,
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Use local CSV files instead of downloading the dataset from Kaggle.",
    )
    return parser.parse_args()


def resolve_source_dir(source_dir: Path | None) -> Path:
    if source_dir is not None:
        return source_dir

    print(f"Downloading latest Kaggle dataset {KAGGLE_DATASET}...")
    try:
        return Path(kagglehub.dataset_download(KAGGLE_DATASET))
    except Exception as exc:
        raise RuntimeError(f"Could not download Kaggle dataset: {exc}") from exc


def ensure_sources_exist(source_dir: Path) -> None:
    missing_files = [
        config["file"]
        for config in TABLES
        if not (source_dir / config["file"]).is_file()
    ]
    if missing_files:
        missing = ", ".join(missing_files)
        raise FileNotFoundError(
            f"Missing source CSV file(s) in {source_dir}: {missing}"
        )


def get_connection() -> snowflake.connector.SnowflakeConnection:
    required_variables = (
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_ROLE",
        "SNOWFLAKE_WAREHOUSE",
        "SNOWFLAKE_DATABASE",
        "SNOWFLAKE_SCHEMA",
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
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        private_key_file=str(private_key_path),
        private_key_file_pwd=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
    )


def put_file(cursor, local_path: Path, stage_path: str) -> None:
    resolved_path = local_path.resolve()
    if os.name == "nt":
        file_uri = f"file://{resolved_path.as_posix()}"
    else:
        file_uri = resolved_path.as_uri()
    file_uri = file_uri.replace("'", "''")
    cursor.execute(
        f"PUT '{file_uri}' @{STAGE}/{stage_path} "
        "OVERWRITE = TRUE AUTO_COMPRESS = TRUE"
    )


def copy_into_table(cursor, table: str, stage_path: str) -> int:
    cursor.execute(
        f"COPY INTO {table} "
        f"FROM @{STAGE}/{stage_path} "
        f"FILE_FORMAT = (FORMAT_NAME = '{FILE_FORMAT}') "
        "FORCE = TRUE"
    )
    return sum(int(row[3] or 0) for row in cursor.fetchall())


def load_sources(connection, source_dir: Path) -> None:
    with connection.cursor() as cursor:
        for config in TABLES:
            cursor.execute(config["ddl"])

        for config in TABLES:
            local_path = source_dir / config["file"]
            put_file(cursor, local_path, config["stage_path"])
            row_count = copy_into_table(
                cursor, config["table"], config["stage_path"]
            )
            print(f"Loaded {row_count:,} rows into {config['table']}.")


def main() -> int:
    args = parse_args()
    try:
        source_dir = resolve_source_dir(args.source_dir)
        ensure_sources_exist(source_dir)
        connection = get_connection()
    except (Error, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Could not connect to Snowflake or validate inputs: {exc}", file=sys.stderr)
        return 1

    try:
        load_sources(connection, source_dir)
    except Error as exc:
        print(f"Snowflake load failed: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())