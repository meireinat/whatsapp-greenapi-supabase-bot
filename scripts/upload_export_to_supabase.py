"""
Utility script to ingest the `export.csv` file into a Supabase table.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import logging
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from app.config import get_settings
from app.services.supabase_client import SupabaseService

DEFAULT_BATCH_SIZE = 500
DEFAULT_ENCODING = "cp1255"  # Windows-1255 is common for Hebrew exports

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload CSV export into Supabase.")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("export.csv"),
        help="Path to the CSV file (default: export.csv)",
    )
    parser.add_argument(
        "--table",
        required=True,
        help="Target Supabase table name (must exist beforehand).",
    )
    parser.add_argument(
        "--encoding",
        default=DEFAULT_ENCODING,
        help=f"File encoding (default: {DEFAULT_ENCODING})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of rows per insert batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect a sample of rows without writing to Supabase.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Number of rows to preview in dry-run mode (default: 5).",
    )
    return parser.parse_args()


def read_rows(path: Path, encoding: str) -> Iterable[dict[str, object]]:
    with path.open("r", encoding=encoding, newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            normalized_row: dict[str, object] = {}
            for key, value in row.items():
                column = key.strip()
                normalized_row[column] = _normalize_value(column, value)
            yield normalized_row


HEBREW_MONTHS = {
    "ינו": 1,
    "פבר": 2,
    "מרץ": 3,
    "אפר": 4,
    "מאי": 5,
    "יונ": 6,
    "יול": 7,
    "אוג": 8,
    "ספט": 9,
    "ספ": 9,  # לפעמים מופיע מקוצר יותר
    "אוק": 10,
    "אוקט": 10,
    "נוב": 11,
    "דצמ": 12,
    "דצ": 12,
}


def _normalize_value(column: str, value: str | None) -> object:
    if value is None:
        return None

    cleaned = value.strip()
    if cleaned == "":
        return None

    if column == "TARICH_PRIKA":
        parsed = _parse_hebrew_date(cleaned)
        return parsed or cleaned

    # Attempt numeric conversion for convenience
    try:
        if "." in cleaned:
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        return cleaned


def _parse_hebrew_date(raw: str) -> str | None:
    """
    Convert dates like '14-נוב-07' to ISO format '2007-11-14'.
    """
    try:
        day_str, month_he, year_str = raw.split("-")
    except ValueError:
        return None

    month_he = month_he.strip()
    month = HEBREW_MONTHS.get(month_he)
    if not month:
        return None

    try:
        day = int(day_str)
    except ValueError:
        return None

    try:
        year = int(year_str)
    except ValueError:
        return None

    if year < 100:
        year += 2000 if year < 80 else 1900

    try:
        return dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    load_dotenv()

    if not args.file.exists():
        raise FileNotFoundError(f"CSV file not found: {args.file}")

    settings = get_settings()
    service = SupabaseService(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key,
        schema=settings.supabase_schema,
    )

    if args.dry_run:
        logger.info("Running in dry-run mode. Showing up to %s rows.", args.sample_size)
        for index, row in enumerate(itertools.islice(read_rows(args.file, args.encoding), args.sample_size), start=1):
            print(f"Row {index}: {row}")
        return

    logger.info("Starting import of %s into table %s", args.file, args.table)
    service.bulk_insert(
        table=args.table,
        rows=read_rows(args.file, args.encoding),
        batch_size=args.batch_size,
    )
    logger.info("Import completed successfully.")


if __name__ == "__main__":
    main()

