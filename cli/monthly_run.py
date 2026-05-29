import argparse

from cli.orchestration import (
    StrategyRunConfig,
    factor_weights_from_args,
    print_model_portfolio,
    print_strategy_summary,
    run_strategy_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the AP12 modular monthly pipeline."
    )
    parser.add_argument("--universe", default="sp500_active")
    parser.add_argument("--benchmark", default="spy")
    parser.add_argument("--as-of-date", type=_parse_date, default=None)
    parser.add_argument("--lookback-days", type=int, default=252)
    parser.add_argument("--portfolio-size", type=int, default=7)
    parser.add_argument("--value-weight", type=float, default=0.35)
    parser.add_argument("--quality-weight", type=float, default=0.30)
    parser.add_argument("--momentum-weight", type=float, default=0.35)
    parser.add_argument(
        "--model-limit",
        type=int,
        default=7,
        help="Number of model portfolio rows to print.",
    )
    return parser.parse_args()


def main() -> None:
    from data import FixtureDataProvider

    args = parse_args()
    print("monthly_run=started")
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
    print(
        "monthly_artifacts="
        f"model_rows:{len(artifacts.model_portfolio)} "
        "shadow:deferred_until_AP13 "
        "rebalance:deferred_until_AP13 "
        "trade_plan:deferred_until_AP13"
    )
    print("monthly_run=ok")


def _parse_date(value: str):
    from datetime import date

    return date.fromisoformat(value)


if __name__ == "__main__":
    from cli.errors import run_cli

    run_cli(main)
