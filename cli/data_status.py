import argparse
from datetime import date, datetime, timedelta
from typing import Any


RAW_TABLES = {
    "assets": None,
    "asset_provider_identifiers": None,
    "universes": None,
    "universe_members": None,
    "asset_price_bars": "date",
    "asset_fundamental_reports": "report_date",
    "asset_market_caps": "date",
    "data_sync_runs": "started_at",
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
    parser.add_argument(
        "--universe",
        default="sp500_active",
        help="Universe used for data quality diagnostics with --details.",
    )
    parser.add_argument(
        "--as-of-date",
        type=_parse_date,
        default=None,
        help="As-of date for freshness diagnostics. Defaults to today.",
    )
    parser.add_argument(
        "--price-stale-days",
        type=int,
        default=5,
        help="Price rows older than this many days are reported as stale.",
    )
    parser.add_argument(
        "--fundamental-stale-days",
        type=int,
        default=550,
        help="TTM fundamental rows older than this many days are reported as stale.",
    )
    parser.add_argument(
        "--market-cap-stale-days",
        type=int,
        default=10,
        help="Market-cap rows older than this many days are reported as stale.",
    )
    parser.add_argument(
        "--identifier-provider",
        default=None,
        help=(
            "Provider key used for identifier coverage diagnostics. Defaults to "
            "--provider when set, otherwise mysql_fixture."
        ),
    )
    parser.add_argument(
        "--identifier-scheme",
        default="ticker",
        help="Provider identifier scheme used for coverage diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-limit",
        type=int,
        default=10,
        help="Number of missing/stale tickers to print per data quality line.",
    )
    parser.add_argument(
        "--sync-limit",
        type=int,
        default=5,
        help="Number of recent data_sync_runs rows to show with --details.",
    )
    parser.add_argument(
        "--sync-type",
        choices=["membership", "prices", "fundamentals"],
        default=None,
        help="Filter detailed sync-run output by sync type.",
    )
    parser.add_argument(
        "--sync-status",
        choices=["started", "ok", "failed"],
        default=None,
        help="Filter detailed sync-run output by status.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Filter detailed sync-run output by provider key.",
    )
    parser.add_argument(
        "--source-role",
        default=None,
        help="Filter detailed sync-run output by source role.",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Filter detailed sync-run output to runs started in the last N days.",
    )
    parser.add_argument(
        "--stale-started-minutes",
        type=int,
        default=120,
        help="Minutes after which a started sync run is reported as stale.",
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
            for row in connection.execute(
                text(
                    """
                    SELECT asset_class, COUNT(*) AS row_count
                    FROM assets
                    GROUP BY asset_class
                    ORDER BY asset_class
                    """
                )
            ).mappings():
                print(
                    "asset_class="
                    f"{row['asset_class']} "
                    f"assets={row['row_count']}"
                )
            for row in connection.execute(
                text(
                    """
                    SELECT
                        u.universe_key,
                        COUNT(*) AS member_count
                    FROM universes u
                    LEFT JOIN universe_members um
                        ON um.universe_id = u.id
                        AND um.valid_to IS NULL
                    GROUP BY u.universe_key
                    ORDER BY u.universe_key
                    """
                )
            ).mappings():
                print(
                    "universe="
                    f"{row['universe_key']} "
                    f"current_members={row['member_count']}"
                )
            for row in connection.execute(
                text(
                    """
                    SELECT provider_key, identifier_scheme, COUNT(*) AS row_count
                    FROM asset_provider_identifiers
                    GROUP BY provider_key, identifier_scheme
                    ORDER BY provider_key, identifier_scheme
                    """
                )
            ).mappings():
                print(
                    "provider_identifiers="
                    f"{row['provider_key']} "
                    f"scheme={row['identifier_scheme']} "
                    f"rows={row['row_count']}"
                )
            sync_statement, sync_params = _data_sync_runs_query(args, text)
            for row in connection.execute(sync_statement, sync_params).mappings():
                print(_format_data_sync_run(row))
            diagnostics = connection.execute(
                _data_sync_diagnostics_query(text),
                {
                    "stale_started_at": datetime.now()
                    - timedelta(minutes=args.stale_started_minutes),
                },
            ).mappings().one()
            print(_format_data_sync_diagnostics(diagnostics))
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

            from data.diagnostics import (
                DataQualityDiagnostics,
                format_data_quality_report,
            )

            identifier_provider = (
                args.identifier_provider or args.provider or "mysql_fixture"
            )
            report = DataQualityDiagnostics().build_report(
                universe_key=args.universe,
                benchmark_ticker=args.benchmark_ticker,
                as_of_date=args.as_of_date,
                price_stale_days=args.price_stale_days,
                fundamental_stale_days=args.fundamental_stale_days,
                market_cap_stale_days=args.market_cap_stale_days,
                identifier_provider_key=identifier_provider,
                identifier_scheme=args.identifier_scheme,
                sync_provider_key=args.provider,
                stale_started_minutes=args.stale_started_minutes,
            )
            for line in format_data_quality_report(
                report,
                sample_limit=args.diagnostic_limit,
            ):
                print(line)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


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


def _format_data_sync_run(row: dict[str, Any]) -> str:
    parts = [
        f"sync_run={row['id']}",
        f"type={row['sync_type']}",
        f"provider={row['provider_key']}",
        f"source_role={row['source_role']}",
        f"mode={row['mode']}",
        f"status={row['status']}",
        f"started={row['started_at']}",
        f"planned={row['planned_items']}",
        f"processed={row['processed_items']}",
        f"upserted_rows={row['upserted_rows']}",
    ]
    if row.get("finished_at") is not None:
        parts.append(f"finished={row['finished_at']}")
    if row.get("error_message"):
        parts.append(f"error={row['error_message']}")
    return " ".join(parts)


def _data_sync_runs_query(args: argparse.Namespace, text_fn):
    clauses = []
    params: dict[str, Any] = {"limit": max(args.sync_limit, 0)}
    if args.sync_type:
        clauses.append("sync_type = :sync_type")
        params["sync_type"] = args.sync_type
    if args.sync_status:
        clauses.append("status = :sync_status")
        params["sync_status"] = args.sync_status
    if args.provider:
        clauses.append("provider_key = :provider")
        params["provider"] = args.provider
    if args.source_role:
        clauses.append("source_role = :source_role")
        params["source_role"] = args.source_role
    if args.since_days is not None:
        clauses.append("started_at >= :started_since")
        params["started_since"] = datetime.now() - timedelta(days=args.since_days)
    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)
    return (
        text_fn(
            f"""
            SELECT
                id,
                sync_type,
                provider_key,
                source_role,
                mode,
                status,
                started_at,
                finished_at,
                planned_items,
                processed_items,
                upserted_rows,
                error_message
            FROM data_sync_runs
            {where_sql}
            ORDER BY started_at DESC, id DESC
            LIMIT :limit
            """
        ),
        params,
    )


def _data_sync_diagnostics_query(text_fn):
    return text_fn(
        """
        SELECT
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_runs,
            SUM(
                CASE
                    WHEN status = 'started' AND started_at < :stale_started_at
                    THEN 1
                    ELSE 0
                END
            ) AS stale_started_runs,
            MAX(CASE WHEN status = 'ok' THEN started_at ELSE NULL END) AS latest_ok,
            MAX(CASE WHEN status = 'failed' THEN started_at ELSE NULL END) AS latest_failed
        FROM data_sync_runs
        """
    )


def _format_data_sync_diagnostics(row: dict[str, Any]) -> str:
    return (
        "sync_diagnostics "
        f"failed_runs={row['failed_runs'] or 0} "
        f"stale_started_runs={row['stale_started_runs'] or 0} "
        f"latest_ok={row['latest_ok']} "
        f"latest_failed={row['latest_failed']}"
    )


if __name__ == "__main__":
    from cli.errors import run_cli

    run_cli(main)
