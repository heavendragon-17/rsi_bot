"""
Download Historical Tick (aggTrades) Data from Binance Vision
=============================================================
Downloads monthly and daily aggregated trades for a given symbol.

Supports:
  - Single month:  --year 2026 --month 1
  - Multi-month:   --year 2026 --month 1 --months 3
  - Recent N months up to today:  --recent 3   (includes daily ticks for current month)
  - Auto-merge into single file:  --merge
"""

import argparse
import csv
import os
import zipfile
from datetime import UTC, date, datetime, timedelta

import requests  # type: ignore[import-untyped]
import structlog
from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
logger = structlog.get_logger()

BASE_URL = "https://data.binance.vision/data/futures/um"


# ── download helpers ─────────────────────────────────────────────────────────


def _download_zip(url: str, output_dir: str, label: str) -> str | None:
    """Download and extract a single zip from Binance Vision. Returns CSV path or None."""
    response = requests.get(url, stream=True, timeout=120)
    if response.status_code != 200:
        logger.warning("download_failed", status_code=response.status_code, label=label)
        return None

    os.makedirs(output_dir, exist_ok=True)
    zip_name = url.split("/")[-1]
    zip_path = os.path.join(output_dir, zip_name)

    with open(zip_path, "wb") as fd:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            fd.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as z:
        csv_filename = z.namelist()[0]
        z.extract(csv_filename, path=output_dir)

    extracted_path = os.path.join(output_dir, csv_filename)
    os.remove(zip_path)
    return extracted_path


def download_month(symbol: str, year: int, month: int, output_dir: str) -> str | None:
    """Download one month of aggTrades. Returns path to CSV or None."""
    clean = symbol.replace("/", "").upper()
    label = f"{clean}-aggTrades-{year}-{month:02d}"
    url = f"{BASE_URL}/monthly/aggTrades/{clean}/{label}.zip"

    logger.info("downloading_monthly", label=label)
    path = _download_zip(url, output_dir, label)
    if path:
        out = os.path.join(output_dir, f"{clean}_ticks_{year}_{month:02d}.csv")
        if os.path.exists(out):
            os.remove(out)
        os.rename(path, out)
        logger.info("monthly_download_complete", path=out)
        return out
    return None


def download_day(symbol: str, d: date, output_dir: str) -> str | None:
    """Download one day of aggTrades. Returns path to CSV or None."""
    clean = symbol.replace("/", "").upper()
    ds = d.strftime("%Y-%m-%d")
    label = f"{clean}-aggTrades-{ds}"
    url = f"{BASE_URL}/daily/aggTrades/{clean}/{label}.zip"

    path = _download_zip(url, output_dir, label)
    if path:
        out = os.path.join(output_dir, f"{clean}_ticks_day_{ds}.csv")
        if os.path.exists(out):
            os.remove(out)
        os.rename(path, out)
        return out
    return None


def download_days_range(symbol: str, start: date, end: date, output_dir: str) -> list[str]:
    """Download daily aggTrades for [start, end]. Returns list of CSV paths."""
    symbol.replace("/", "").upper()
    total = (end - start).days + 1
    logger.info("downloading_daily_ticks", start=str(start), end=str(end), total_days=total)

    paths = []
    failed = 0
    for i in range(total):
        d = start + timedelta(days=i)
        path = download_day(symbol, d, output_dir)
        if path:
            paths.append(path)
        else:
            failed += 1

    logger.info("daily_download_complete", downloaded=len(paths), total=total, failed=failed)
    return paths


# ── merge ─────────────────────────────────────────────────────────────────────


def merge_csvs(csv_paths: list[str], output_path: str) -> None:
    """Merge multiple tick CSVs (sorted by path = chronological) into one file."""
    logger.info("merging_csvs", file_count=len(csv_paths), output_path=output_path)
    header_written = False
    with open(output_path, "w", newline="") as out_f:
        writer = None
        for path in sorted(csv_paths):
            with open(path, newline="") as in_f:
                reader = csv.DictReader(in_f)
                if not header_written:
                    assert reader.fieldnames is not None, "CSV has no header"
                    writer = csv.DictWriter(out_f, fieldnames=reader.fieldnames)
                    writer.writeheader()
                    header_written = True
                assert writer is not None
                for row in reader:
                    writer.writerow(row)
    logger.info("merge_complete", output_path=output_path)


# ── plan builder ──────────────────────────────────────────────────────────────


def _build_recent_plan(symbol: str, months: int):
    """
    Build a download plan that covers exactly `months` months back from today.
    Uses monthly archives for completed months and daily archives for the
    current (incomplete) month.

    Returns: (monthly_list, daily_range_or_none)
      monthly_list: [(year, month), ...]
      daily_range:  (start_date, end_date) or None
    """
    now = datetime.now(UTC).date()
    target_start = now - relativedelta(months=months)

    # Completed months: any month < current month
    monthly = []
    cursor = date(target_start.year, target_start.month, 1)
    current_month_start = date(now.year, now.month, 1)

    while cursor < current_month_start:
        monthly.append((cursor.year, cursor.month))
        cursor += relativedelta(months=1)

    # Daily range: 1st of current month → yesterday (today may not be available)
    yesterday = now - timedelta(days=1)
    if current_month_start <= yesterday:
        daily_range = (current_month_start, yesterday)
    else:
        daily_range = None

    return monthly, daily_range


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download historical tick (aggTrades) data from Binance Vision",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Trading pair without slash (e.g. ZILUSDT)")
    parser.add_argument(
        "--year", type=int, default=None, help="Year to download (e.g. 2026). Defaults to current year."
    )
    parser.add_argument(
        "--month", type=int, default=None, help="Month to download (1-12). Defaults to last completed month."
    )
    parser.add_argument(
        "--months", type=int, default=1, help="Number of consecutive months to download (going backwards)."
    )
    parser.add_argument(
        "--recent",
        type=int,
        default=None,
        metavar="N",
        help="Download the last N months up to today. Automatically uses "
        "daily ticks for the current incomplete month. Implies --merge.",
    )
    parser.add_argument("--merge", action="store_true", help="Merge all downloaded data into a single CSV file.")
    parser.add_argument("--output", type=str, default=os.path.join(SCRIPT_DIR, "data"), help="Output directory")

    args = parser.parse_args()
    clean_symbol = args.symbol.replace("/", "").upper()

    # ── --recent mode (exact N months from today) ──────────────────────────
    if args.recent:
        monthly_plan, daily_range = _build_recent_plan(args.symbol, args.recent)
        now = datetime.now(UTC).date()
        target_start = now - relativedelta(months=args.recent)

        logger.info(
            "recent_download_plan",
            symbol=clean_symbol,
            months=args.recent,
            target_start=str(target_start),
            target_end=str(now),
            monthly_archives=len(monthly_plan),
            daily_range=f"{daily_range[0]} to {daily_range[1]}" if daily_range else None,
        )

        downloaded = []

        # Monthly downloads
        for y, m in monthly_plan:
            path = download_month(args.symbol, y, m, args.output)
            if path:
                downloaded.append(path)

        # Daily downloads for current month
        daily_paths = []
        if daily_range:
            daily_paths = download_days_range(args.symbol, daily_range[0], daily_range[1], args.output)
            downloaded.extend(daily_paths)

        if not downloaded:
            logger.warning("no_data_downloaded")
        elif len(downloaded) > 1:
            start_str = f"{target_start.strftime('%Y%m%d')}"
            end_str = f"{now.strftime('%Y%m%d')}"
            merged_name = f"{clean_symbol}_ticks_{start_str}_to_{end_str}.csv"
            merged_path = os.path.join(args.output, merged_name)
            merge_csvs(downloaded, merged_path)

            for p in downloaded:
                os.remove(p)
            logger.info("single_output_ready", path=merged_path)
        else:
            logger.info("single_file_downloaded", path=downloaded[0])

    # ── classic --year/--month/--months mode ───────────────────────────────
    else:
        now = datetime.now(UTC)
        if now.month == 1:
            default_year, default_month = now.year - 1, 12
        else:
            default_year, default_month = now.year, now.month - 1

        start_year = args.year if args.year else default_year
        start_month = args.month if args.month else default_month

        # Build month list going backwards from start
        months_list = []
        cur = date(start_year, start_month, 1)
        for _ in range(args.months):
            months_list.append((cur.year, cur.month))
            cur -= relativedelta(months=1)
        months_list.reverse()

        logger.info(
            "classic_download_plan",
            symbol=clean_symbol,
            months=[(y, m) for y, m in months_list],
        )

        downloaded = []
        for year, month in months_list:
            path = download_month(args.symbol, year, month, args.output)
            if path:
                downloaded.append(path)

        if not downloaded:
            logger.warning("no_data_downloaded")
        elif args.merge and len(downloaded) > 1:
            oldest_y, oldest_m = months_list[0]
            newest_y, newest_m = months_list[-1]
            merged_name = f"{clean_symbol}_ticks_{oldest_y}{oldest_m:02d}" f"_to_{newest_y}{newest_m:02d}.csv"
            merged_path = os.path.join(args.output, merged_name)
            merge_csvs(downloaded, merged_path)

            for p in downloaded:
                os.remove(p)
            logger.info("merged_output_ready", path=merged_path)
        elif args.merge and len(downloaded) == 1:
            logger.info("single_file_no_merge_needed")
        else:
            logger.info("download_complete", file_count=len(downloaded))
