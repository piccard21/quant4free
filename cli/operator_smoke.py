import argparse
from datetime import date, timedelta
from typing import Any

from cli.errors import CliUsageError, require_non_empty, run_cli


RAW_TABLES = {
    "tickers": None,
    "daily_candles": "date",
    "financial_reports": "report_date",
    "market_cap_snapshots": "date",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the AP10 operator smoke path: fixture health, strategy run, "
            "and benchmark backtest."
        )
    )
    parser.add_argument("--universe", default="sp500_active")
    parser.add_argument("--benchmark", default="spy")
    parser.add_argument("--start-date", type=_parse_date, default=None)
    parser.add_argument("--end-date", type=_parse_date, default=None)
    parser.add_argument("--initial-capital", type=float, default=10000.0)
    parser.add_argument("--rebalance-days", type=int, default=21)
    parser.add_argument("--lookback-days", type=int, default=252)
    parser.add_argument("--portfolio-size", type=int, default=7)
    parser.add_argument("--value-weight", type=float, default=0.35)
    parser.add_argument("--quality-weight", type=float, default=0.30)
    parser.add_argument("--momentum-weight", type=float, default=0.35)
    parser.add_argument(
        "--ranking-limit",
        type=int,
        default=5,
        help="Number of top strategy rows to print.",
    )
    parser.add_argument(
        "--trade-limit",
        type=int,
        default=5,
        help="Number of first backtest trades to print.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _validate_args(args)

    from data import FixtureDataProvider
    from evaluation import BacktestConfig, create_benchmark, run_backtest
    from indicators import compute_indicators, create_indicators
    from shared.db import get_engine, load_database_config, ping_database
    from sqlalchemy import text
    from strategies import StrategyContext, create_default_strategy
    from universes import create_universe

    print("operator_smoke=started")

    config = load_database_config()
    print(f"database={config.database} host={config.host} user={config.user}")
    print(f"ping={'ok' if ping_database() else 'failed'}")

    with get_engine().connect() as connection:
        for table_name, date_column in RAW_TABLES.items():
            row = connection.execute(
                _table_status_statement(text, table_name, date_column)
            ).mappings().one()
            print(_format_table_status(table_name, row))

    provider = FixtureDataProvider()
    try:
        universe = create_universe(args.universe, provider)
        benchmark = create_benchmark(args.benchmark, provider)
        strategy = create_default_strategy(
            factor_weights={
                "value": args.value_weight,
                "quality": args.quality_weight,
                "momentum": args.momentum_weight,
            },
            portfolio_size=args.portfolio_size,
        )
    except ValueError as exc:
        raise CliUsageError(str(exc), hint="use cli.framework_status --list-configs") from exc

    members = universe.load_members(args.end_date)
    require_non_empty(
        "universe members",
        len(members),
        hint="load raw fixture data or choose another --universe",
    )

    end_date = args.end_date or _latest_price_date(provider, members)
    start_date = args.start_date or (end_date - timedelta(days=365))
    load_start_date = start_date - timedelta(days=args.lookback_days + 7)

    prices = provider.load_prices(members, start_date=load_start_date, end_date=end_date)
    fundamentals = provider.load_fundamentals(
        members,
        report_type="ttm",
        end_date=end_date,
    )
    market_caps = provider.load_market_caps(members, end_date=end_date)
    benchmark_prices = benchmark.load_prices(start_date=load_start_date, end_date=end_date)

    require_non_empty(
        "price rows",
        len(prices),
        hint="load fixtures/raw_market_data.sql and verify cli.data_status --details",
    )
    require_non_empty(
        "benchmark price rows",
        len(benchmark_prices),
        hint="verify the selected benchmark has daily_candles rows",
    )

    print(
        "framework="
        f"provider:{provider.key} "
        f"universe:{universe.key} members:{len(members)} "
        f"benchmark:{benchmark.spec.key} ticker:{benchmark.spec.ticker}"
    )
    print(f"dates=start:{start_date} end:{end_date} load_start:{load_start_date}")

    indicator_values = compute_indicators(
        create_indicators(),
        prices=prices,
        fundamentals=fundamentals,
        market_caps=market_caps,
        as_of_date=end_date,
        params={
            "momentum_return": {"lookback_days": args.lookback_days},
            "relative_strength": {"lookback_days": args.lookback_days},
        },
    )
    require_non_empty(
        "indicator rows",
        len(indicator_values),
        hint="verify prices, ttm fundamentals, and market-cap snapshots overlap",
    )

    strategy_result = strategy.run(
        StrategyContext(
            as_of_date=end_date,
            universe=members,
            prices=prices,
            fundamentals=fundamentals,
            market_caps=market_caps,
            benchmark_prices=benchmark_prices,
            indicators={"default": indicator_values},
        )
    )
    require_non_empty(
        "strategy ranking rows",
        len(strategy_result.rankings),
        hint="verify indicator data covers enough universe members",
    )

    print(
        "strategy="
        f"{strategy_result.strategy_key} version:{strategy_result.strategy_version} "
        f"rows:{len(strategy_result.rankings)} "
        f"eligible:{strategy_result.diagnostics['eligible_rows']} "
        f"selected:{strategy_result.diagnostics['selected_rows']}"
    )
    if args.ranking_limit > 0:
        print("ranking_head=")
        print(strategy_result.rankings.head(args.ranking_limit).to_string(index=False))

    backtest_result = run_backtest(
        strategy=strategy,
        config=BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            initial_capital=args.initial_capital,
            rebalance_days=args.rebalance_days,
            lookback_days=args.lookback_days,
            transaction_cost_bps=10.0,
            params={
                "factor_weights": {
                    "value": args.value_weight,
                    "quality": args.quality_weight,
                    "momentum": args.momentum_weight,
                },
                "portfolio_size": args.portfolio_size,
            },
        ),
        universe=members,
        prices=prices,
        fundamentals=fundamentals,
        market_caps=market_caps,
        benchmark_prices=benchmark_prices,
    )
    require_non_empty(
        "backtest equity rows",
        len(backtest_result.equity_curve),
        hint="choose a date range with overlapping universe and benchmark prices",
    )

    print(
        "backtest="
        f"trading_days:{backtest_result.diagnostics['trading_days']} "
        f"rebalances:{backtest_result.diagnostics['rebalance_count']} "
        f"trades:{backtest_result.diagnostics['trade_count']}"
    )
    for name, value in backtest_result.metrics.items():
        print(f"{name}={value:.6f}")
    if args.trade_limit > 0 and not backtest_result.trades.empty:
        print("trades_head=")
        print(backtest_result.trades.head(args.trade_limit).to_string(index=False))

    print("operator_smoke=ok")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _validate_args(args: argparse.Namespace) -> None:
    if args.initial_capital <= 0:
        raise CliUsageError("initial capital must be positive")
    if args.rebalance_days <= 0:
        raise CliUsageError("rebalance days must be positive")
    if args.lookback_days <= 0:
        raise CliUsageError("lookback days must be positive")
    if args.portfolio_size <= 0:
        raise CliUsageError("portfolio size must be positive")
    if (
        args.start_date is not None
        and args.end_date is not None
        and args.start_date > args.end_date
    ):
        raise CliUsageError("start date must be before or equal to end date")


def _latest_price_date(provider, members: list[str]) -> date:
    prices = provider.load_prices(members)
    if prices.empty:
        raise CliUsageError(
            "no price data available for selected universe",
            hint="load fixtures/raw_market_data.sql and rerun cli.data_status --details",
        )
    return prices["date"].max()


def _table_status_statement(text_fn, table_name: str, date_column: str | None):
    if date_column is None:
        return text_fn(f"SELECT COUNT(*) AS row_count FROM {table_name}")
    return text_fn(
        f"""
        SELECT
            COUNT(*) AS row_count,
            MIN({date_column}) AS min_date,
            MAX({date_column}) AS max_date
        FROM {table_name}
        """
    )


def _format_table_status(table_name: str, row: dict[str, Any]) -> str:
    parts = [f"raw.{table_name}", f"rows={row['row_count']}"]
    if row.get("min_date") is not None:
        parts.append(f"from={row['min_date']}")
    if row.get("max_date") is not None:
        parts.append(f"to={row['max_date']}")
    return " ".join(parts)


if __name__ == "__main__":
    run_cli(main)
