import argparse
from typing import Any


RAW_TABLES = {
    "assets": None,
    "asset_price_bars": "date",
    "asset_fundamental_reports": "report_date",
    "asset_market_caps": "date",
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

    try:
        from sqlalchemy import text
        from shared.db import get_engine, load_database_config, ping_database
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"missing Python dependency: {exc.name}; "
            "install requirements with .venv/bin/python -m pip install -r requirements.txt"
        ) from exc

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
            for row in connection.execute(
                text(
                    """
                    SELECT
                        report_type,
                        COUNT(*) AS row_count,
                        COUNT(DISTINCT ticker) AS ticker_count,
                        MIN(report_date) AS min_report_date,
                        MAX(report_date) AS max_report_date,
                        MIN(imported_at) AS min_imported_at,
                        MAX(imported_at) AS max_imported_at
                    FROM asset_fundamental_reports
                    GROUP BY report_type
                    ORDER BY report_type
                    """
                )
            ).mappings():
                print(_format_financial_report_status(row))

            active_tickers = connection.execute(
                text("SELECT COUNT(*) FROM assets WHERE is_active = 1")
            ).scalar_one()
            latest_price_rows = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM asset_price_bars
                    WHERE date = (SELECT MAX(date) FROM asset_price_bars)
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
                    FROM asset_price_bars
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


def _format_financial_report_status(row: dict[str, Any]) -> str:
    parts = [
        f"asset_fundamental_reports.{row['report_type']}",
        f"rows={row['row_count']}",
        f"assets={row['ticker_count']}",
    ]
    if row.get("min_report_date") is not None and row.get("max_report_date") is not None:
        parts.append(f"report_dates={row['min_report_date']}..{row['max_report_date']}")
    if row.get("min_imported_at") is not None and row.get("max_imported_at") is not None:
        parts.append(
            f"imported={row['min_imported_at']}..{row['max_imported_at']}"
        )
    return " ".join(parts)


if __name__ == "__main__":
    from cli.errors import run_cli

    run_cli(main)
