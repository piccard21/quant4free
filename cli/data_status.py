import argparse
from typing import Any

from sqlalchemy import text

from shared.db import get_engine, load_database_config, ping_database


RAW_TABLES = {
    "tickers": None,
    "daily_candles": "date",
    "financial_reports": "report_date",
    "market_cap_snapshots": "date",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show read-only raw data availability for the modular framework."
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Include active ticker and latest record details.",
    )
    parser.add_argument(
        "--benchmark-ticker",
        default="SPY",
        help="Ticker used to check benchmark price availability.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_database_config()

    print(f"database={config.database} host={config.host} user={config.user}")
    print(f"ping={'ok' if ping_database() else 'failed'}")

    with get_engine().connect() as connection:
        for table_name, date_column in RAW_TABLES.items():
            if date_column is None:
                statement = text(f"SELECT COUNT(*) AS row_count FROM {table_name}")
            else:
                statement = text(
                    f"""
                    SELECT
                        COUNT(*) AS row_count,
                        MIN({date_column}) AS min_date,
                        MAX({date_column}) AS max_date
                    FROM {table_name}
                    """
                )
            row = connection.execute(statement).mappings().one()
            print(_format_table_status(table_name, row))

        if args.details:
            active_tickers = connection.execute(
                text("SELECT COUNT(*) FROM tickers WHERE is_active = 1")
            ).scalar_one()
            latest_price_rows = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM daily_candles
                    WHERE date = (SELECT MAX(date) FROM daily_candles)
                    """
                )
            ).scalar_one()
            print(f"active_tickers={active_tickers}")
            print(f"latest_price_rows={latest_price_rows}")
            benchmark = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS row_count,
                        MIN(date) AS min_date,
                        MAX(date) AS max_date
                    FROM daily_candles
                    WHERE ticker = :ticker
                    """
                ),
                {"ticker": args.benchmark_ticker},
            ).mappings().one()
            print(_format_benchmark_status(args.benchmark_ticker, benchmark))


def _format_table_status(table_name: str, row: dict[str, Any]) -> str:
    parts = [
        table_name,
        f"rows={row['row_count']}",
    ]
    if row.get("min_date") is not None:
        parts.append(f"from={row['min_date']}")
    if row.get("max_date") is not None:
        parts.append(f"to={row['max_date']}")
    return " ".join(parts)


def _format_benchmark_status(ticker: str, row: dict[str, Any]) -> str:
    parts = [
        f"benchmark={ticker}",
        f"rows={row['row_count']}",
    ]
    if row.get("min_date") is not None:
        parts.append(f"from={row['min_date']}")
    if row.get("max_date") is not None:
        parts.append(f"to={row['max_date']}")
    return " ".join(parts)


if __name__ == "__main__":
    main()
