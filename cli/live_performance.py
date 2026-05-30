import argparse
from datetime import date, timedelta


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show live Real/Shadow/Benchmark performance."
    )
    parser.add_argument("--benchmark", default="spy")
    parser.add_argument("--start-date", type=_parse_date, default=None)
    parser.add_argument("--end-date", type=_parse_date, default=None)
    parser.add_argument(
        "--base-value",
        type=float,
        default=None,
        help="Optional normalization base for all value series.",
    )
    parser.add_argument(
        "--curve-limit",
        type=int,
        default=10,
        help="Number of final performance-curve rows to print.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from cli.errors import CliUsageError
    from evaluation import get_benchmark_spec
    from live import LivePerformanceRepository, LivePerformanceService
    from shared import validate_live_capabilities

    try:
        benchmark = get_benchmark_spec(args.benchmark)
        validate_live_capabilities(
            live_workflow_key="live_performance",
            benchmark_key=benchmark.key,
        )
    except ValueError as exc:
        raise CliUsageError(str(exc)) from exc

    repository = LivePerformanceRepository()
    end_date = args.end_date or repository.latest_price_date(benchmark.ticker)
    if end_date is None:
        raise CliUsageError(
            f"benchmark {benchmark.ticker} has no price rows",
            hint="run cli.sync_prices or load fixtures/raw_market_data.sql first",
        )
    start_date = args.start_date or (end_date - timedelta(days=365))

    service = LivePerformanceService(repository)
    try:
        report = service.build_report(
            start_date=start_date,
            end_date=end_date,
            benchmark_ticker=benchmark.ticker,
            base_value=args.base_value,
        )
    except ValueError as exc:
        raise CliUsageError(
            str(exc),
            hint="verify live positions, shadow targets, cash balances, and benchmark prices",
        ) from exc

    print(f"benchmark={benchmark.key} ticker={report.benchmark_ticker}")
    print(f"start_date={report.start_date} end_date={report.end_date}")
    print(f"base_value={report.base_value:.2f}")
    print(
        "diagnostics="
        f"report_days:{report.diagnostics['report_days']},"
        f"real_positions:{report.diagnostics['real_positions']},"
        f"shadow_snapshots:{report.diagnostics['shadow_snapshots']},"
        f"shadow_positions:{report.diagnostics['shadow_positions']},"
        f"real_missing_price_days:{report.diagnostics['real_missing_price_days']},"
        f"shadow_missing_price_days:{report.diagnostics['shadow_missing_price_days']}"
    )
    for name in ("real", "shadow", "benchmark"):
        metrics = report.metrics[name]
        print(
            f"{name}_return={metrics.total_return:.6f} "
            f"{name}_benchmark_return={metrics.benchmark_return:.6f} "
            f"{name}_outperformance={metrics.outperformance:.6f} "
            f"{name}_max_drawdown={metrics.max_drawdown:.6f}"
        )

    if args.curve_limit > 0 and not report.curve.empty:
        print("performance_curve_tail=")
        print(report.curve.tail(args.curve_limit).to_string(index=False))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    from cli.errors import run_cli

    run_cli(main)
