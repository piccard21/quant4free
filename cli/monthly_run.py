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
        description="Run the modular monthly pipeline."
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
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist model, shadow, rebalance, decision-log, and trade-plan artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    from data import FixtureDataProvider

    args = parse_args()
    config = _strategy_config(args)
    print("monthly_run=started")
    artifacts = run_strategy_snapshot(
        FixtureDataProvider(),
        config,
    )
    print_strategy_summary(artifacts)
    print_model_portfolio(artifacts, args.model_limit)
    operational_result = _run_operational_persistence(artifacts, persist=args.persist)
    print(
        "monthly_artifacts="
        f"model_rows:{operational_result.model_rows} "
        f"shadow_rows:{operational_result.shadow_rows} "
        f"rebalance_rows:{operational_result.rebalance_rows} "
        f"decision_rows:{operational_result.decision_rows} "
        f"trade_plan_rows:{operational_result.trade_plan_rows} "
        f"exec_buys:{operational_result.executable_buys} "
        f"exec_sells:{operational_result.executable_sells} "
        f"skipped:{operational_result.skipped_trades} "
        f"persisted:{str(not operational_result.dry_run).lower()}"
    )
    print("monthly_run=ok")


def _strategy_config(args) -> StrategyRunConfig:
    if not args.persist:
        return StrategyRunConfig(
            universe_key=args.universe,
            benchmark_key=args.benchmark,
            as_of_date=args.as_of_date,
            lookback_days=args.lookback_days,
            portfolio_size=args.portfolio_size,
            factor_weights=factor_weights_from_args(args),
        )

    from live import OperationalRepository

    try:
        settings = OperationalRepository().load_active_settings()
    except ValueError as exc:
        raise CliUsageError(
            str(exc),
            hint="load init.sql or create one active strategy_instances row before using --persist",
        ) from exc
    return StrategyRunConfig(
        universe_key=args.universe,
        benchmark_key=args.benchmark,
        as_of_date=args.as_of_date,
        lookback_days=settings.return_lookback_days,
        portfolio_size=settings.portfolio_size,
        factor_weights={
            "value": settings.value_weight,
            "quality": settings.quality_weight,
            "momentum": settings.momentum_weight,
        },
    )


def _run_operational_persistence(artifacts, persist: bool):
    from live import OperationalPersistenceResult, OperationalPersistenceService

    if not persist:
        return OperationalPersistenceResult(
            as_of_date=artifacts.as_of_date,
            model_rows=len(artifacts.model_portfolio),
            shadow_rows=0,
            rebalance_rows=0,
            decision_rows=0,
            trade_plan_rows=0,
            executable_buys=0,
            executable_sells=0,
            skipped_trades=0,
            dry_run=True,
        )
    try:
        return OperationalPersistenceService().run(artifacts, persist=persist)
    except ValueError as exc:
        raise CliUsageError(
            str(exc),
            hint="choose a new --as-of-date or inspect existing live snapshots before rerunning --persist",
        ) from exc


def _parse_date(value: str):
    from datetime import date

    return date.fromisoformat(value)


if __name__ == "__main__":
    from cli.errors import run_cli

    run_cli(main)
