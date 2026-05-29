import argparse

from cli.errors import CliUsageError
from cli.orchestration import (
    StrategyRunConfig,
    factor_weights_from_args,
    print_model_portfolio,
    print_strategy_summary,
    run_strategy_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the AP12 modular daily pipeline."
    )
    parser.add_argument("--mode", choices=["init", "daily"], default="daily")
    parser.add_argument("--universe", default="sp500_active")
    parser.add_argument("--benchmark", default="spy")
    parser.add_argument("--benchmark-ticker", default="SPY")
    parser.add_argument("--as-of-date", type=_parse_date, default=None)
    parser.add_argument("--lookback-days", type=int, default=252)
    parser.add_argument("--portfolio-size", type=int, default=7)
    parser.add_argument("--value-weight", type=float, default=0.35)
    parser.add_argument("--quality-weight", type=float, default=0.30)
    parser.add_argument("--momentum-weight", type=float, default=0.35)
    parser.add_argument("--refresh-hours", type=int, default=24)
    parser.add_argument("--fundamental-limit", type=int, default=25)
    parser.add_argument(
        "--ticker",
        action="append",
        default=None,
        help="Ticker to sync. Can be repeated.",
    )
    parser.add_argument(
        "--tickers",
        default=None,
        help="Comma-separated tickers to sync.",
    )
    parser.add_argument(
        "--skip-ticker-sync",
        action="store_true",
        help="Use existing active tickers instead of refreshing S&P 500 membership.",
    )
    parser.add_argument(
        "--skip-data-sync",
        action="store_true",
        help="Run strategy/status steps against existing raw data only.",
    )
    parser.add_argument(
        "--dry-run-sync",
        action="store_true",
        help="Plan sync steps without external API calls or writes.",
    )
    parser.add_argument(
        "--model-limit",
        type=int,
        default=7,
        help="Number of model portfolio rows to print.",
    )
    return parser.parse_args()


def main() -> None:
    from data import FixtureDataProvider
    from data.sync import FundamentalSyncService, PriceSyncService

    args = parse_args()
    tickers = _parse_tickers(args.ticker, args.tickers)

    print("daily_run=started")
    if args.skip_data_sync:
        print("data_sync=skipped")
    else:
        price_result = PriceSyncService().run(
            mode=args.mode,
            tickers=tickers,
            benchmark_ticker=args.benchmark_ticker,
            sync_tickers=not args.skip_ticker_sync,
            dry_run=args.dry_run_sync,
        )
        fundamental_result = FundamentalSyncService().run(
            mode=args.mode,
            tickers=tickers,
            refresh_hours=args.refresh_hours,
            limit=args.fundamental_limit,
            dry_run=args.dry_run_sync,
        )
        print(f"data_sync={'dry_run' if args.dry_run_sync else 'ok'}")
        print(
            "prices "
            f"planned_tickers={len(price_result.planned)} "
            f"downloaded_tickers={price_result.downloaded_tickers} "
            f"upserted_candles={price_result.upserted_candles}"
        )
        print(
            "fundamentals "
            f"planned_tickers={len(fundamental_result.planned_tickers)} "
            f"updated_tickers={fundamental_result.updated_tickers} "
            f"upserted_reports={fundamental_result.upserted_reports} "
            f"upserted_market_caps={fundamental_result.upserted_market_caps}"
        )

    artifacts = run_strategy_snapshot(
        FixtureDataProvider(),
        StrategyRunConfig(
            universe_key=args.universe,
            benchmark_key=args.benchmark,
            as_of_date=args.as_of_date,
            lookback_days=args.lookback_days,
            portfolio_size=args.portfolio_size,
            factor_weights=factor_weights_from_args(args),
        ),
    )
    print_strategy_summary(artifacts)
    print_model_portfolio(artifacts, args.model_limit)
    print("daily_run=ok")


def _parse_date(value: str):
    from datetime import date

    return date.fromisoformat(value)


def _parse_tickers(
    repeated: list[str] | None,
    comma_separated: str | None,
) -> list[str] | None:
    values = []
    if repeated:
        values.extend(repeated)
    if comma_separated:
        values.extend(comma_separated.split(","))
    if not values:
        return None
    tickers = [value.strip().upper() for value in values if value.strip()]
    if not tickers:
        raise CliUsageError("ticker list is empty")
    return tickers


if __name__ == "__main__":
    from cli.errors import run_cli

    run_cli(main)
