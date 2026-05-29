import argparse
from datetime import date, timedelta


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the AP8 Value/Quality/Momentum backtest against fixture-backed raw data."
    )
    parser.add_argument("--universe", default="sp500_active")
    parser.add_argument("--benchmark", default="spy")
    parser.add_argument("--start-date", type=_parse_date, default=None)
    parser.add_argument("--end-date", type=_parse_date, default=None)
    parser.add_argument("--initial-capital", type=float, default=10000.0)
    parser.add_argument("--rebalance-days", type=int, default=21)
    parser.add_argument("--lookback-days", type=int, default=252)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--portfolio-size", type=int, default=7)
    parser.add_argument("--value-weight", type=float, default=0.35)
    parser.add_argument("--quality-weight", type=float, default=0.30)
    parser.add_argument("--momentum-weight", type=float, default=0.35)
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Create AP8 tables if needed and store the run.",
    )
    parser.add_argument(
        "--equity-limit",
        type=int,
        default=5,
        help="Number of final equity-curve rows to print.",
    )
    parser.add_argument(
        "--trade-limit",
        type=int,
        default=10,
        help="Number of first trade rows to print.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from data import FixtureDataProvider
        from evaluation import BacktestConfig, EvaluationRepository, create_benchmark
        from evaluation import run_backtest
        from strategies import create_default_strategy
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
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    members = universe.load_members(args.end_date)
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

    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=args.initial_capital,
        rebalance_days=args.rebalance_days,
        lookback_days=args.lookback_days,
        transaction_cost_bps=args.transaction_cost_bps,
        params={
            "factor_weights": {
                "value": args.value_weight,
                "quality": args.quality_weight,
                "momentum": args.momentum_weight,
            },
            "portfolio_size": args.portfolio_size,
        },
    )
    result = run_backtest(
        strategy=strategy,
        config=config,
        universe=members,
        prices=prices,
        fundamentals=fundamentals,
        market_caps=market_caps,
        benchmark_prices=benchmark_prices,
    )

    stored = None
    if args.persist:
        repository = EvaluationRepository()
        repository.ensure_schema()
        stored = repository.save_backtest_result(
            result,
            universe_key=universe.key,
            benchmark_key=benchmark.spec.key,
            provider_key=provider.key,
        )

    print(f"provider={provider.key}")
    print(f"universe={universe.key} members={len(members)}")
    print(f"benchmark={benchmark.spec.key} ticker={benchmark.spec.ticker}")
    print(f"strategy={result.strategy_key} version={result.strategy_version}")
    print(f"start_date={result.start_date} end_date={result.end_date}")
    print(
        f"initial_capital={args.initial_capital:.2f} "
        f"rebalance_days={args.rebalance_days} "
        f"lookback_days={args.lookback_days} "
        f"transaction_cost_bps={args.transaction_cost_bps:.2f}"
    )
    print(
        f"trading_days={result.diagnostics['trading_days']} "
        f"rebalances={result.diagnostics['rebalance_count']} "
        f"trades={result.diagnostics['trade_count']}"
    )
    for name, value in result.metrics.items():
        print(f"{name}={value:.6f}")
    if stored is not None:
        print(f"stored_run_id={stored.run_id} run_key={stored.run_key}")
    if not result.equity_curve.empty and args.equity_limit > 0:
        print("equity_curve_tail=")
        print(result.equity_curve.tail(args.equity_limit).to_string(index=False))
    if not result.trades.empty and args.trade_limit > 0:
        print("trades_head=")
        print(result.trades.head(args.trade_limit).to_string(index=False))


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
