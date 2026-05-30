import argparse
from datetime import date, timedelta


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the AP7 Value/Quality/Momentum strategy against fixture-backed raw data."
    )
    parser.add_argument(
        "--universe",
        default="sp500_active",
        help="Universe configuration key.",
    )
    parser.add_argument(
        "--benchmark",
        default="spy",
        help="Benchmark configuration key.",
    )
    parser.add_argument(
        "--as-of-date",
        type=_parse_date,
        default=None,
        help="Strategy date in YYYY-MM-DD format. Defaults to latest price date.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=252,
        help="Calendar-day lookback for momentum and relative strength.",
    )
    parser.add_argument(
        "--portfolio-size",
        type=int,
        default=7,
        help="Number of ranked tickers with non-zero model weight.",
    )
    parser.add_argument("--value-weight", type=float, default=0.35)
    parser.add_argument("--quality-weight", type=float, default=0.30)
    parser.add_argument("--momentum-weight", type=float, default=0.35)
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of ranking rows to print.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from data import FixtureDataProvider
        from evaluation import create_benchmark
        from indicators import compute_indicators, create_indicators
        from shared import CapabilityValidationError, validate_strategy_run_capabilities
        from strategies import StrategyContext, create_default_strategy
        from universes import create_universe
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"missing Python dependency: {exc.name}; "
            "install requirements with .venv/bin/python -m pip install -r requirements.txt"
        ) from exc

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
        validate_strategy_run_capabilities(
            strategy_key=strategy.key,
            universe_key=universe.key,
            benchmark_key=benchmark.spec.key,
            provider_key=provider.key,
        )
    except (CapabilityValidationError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    members = universe.load_members(args.as_of_date)
    as_of_date = args.as_of_date or _latest_price_date(provider, members)
    start_date = as_of_date - timedelta(days=args.lookback_days + 7)

    prices = provider.load_prices(members, start_date=start_date, end_date=as_of_date)
    fundamentals = provider.load_fundamentals(
        members,
        report_type="ttm",
        end_date=as_of_date,
    )
    market_caps = provider.load_market_caps(members, end_date=as_of_date)
    benchmark_prices = benchmark.load_prices(start_date=start_date, end_date=as_of_date)
    indicator_values = compute_indicators(
        create_indicators(),
        prices=prices,
        fundamentals=fundamentals,
        market_caps=market_caps,
        as_of_date=as_of_date,
        params={
            "momentum_return": {"lookback_days": args.lookback_days},
            "relative_strength": {"lookback_days": args.lookback_days},
        },
    )

    result = strategy.run(
        StrategyContext(
            as_of_date=as_of_date,
            universe=members,
            prices=prices,
            fundamentals=fundamentals,
            market_caps=market_caps,
            benchmark_prices=benchmark_prices,
            indicators={"default": indicator_values},
        )
    )

    print(f"provider={provider.key}")
    print(f"universe={universe.key} members={len(members)}")
    print(f"benchmark={benchmark.spec.key} ticker={benchmark.spec.ticker}")
    print(f"strategy={result.strategy_key} version={result.strategy_version}")
    print(f"as_of_date={result.as_of_date}")
    print(
        "weights="
        f"value:{args.value_weight:.2f},"
        f"quality:{args.quality_weight:.2f},"
        f"momentum:{args.momentum_weight:.2f}"
    )
    print(
        f"rows={len(result.rankings)} "
        f"eligible={result.diagnostics['eligible_rows']} "
        f"selected={result.diagnostics['selected_rows']}"
    )
    if not result.rankings.empty and args.limit > 0:
        print(result.rankings.head(args.limit).to_string(index=False))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _latest_price_date(provider, members: list[str]) -> date:
    prices = provider.load_prices(members)
    if prices.empty:
        raise SystemExit("no price data available for selected universe")
    return prices["date"].max()


if __name__ == "__main__":
    from cli.errors import run_cli

    run_cli(main)
