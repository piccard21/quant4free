import argparse
from datetime import date
from typing import Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show provider, configured universe, and benchmark status."
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
        "--benchmark-ticker",
        default=None,
        help="Ad-hoc benchmark ticker override kept for AP3 compatibility.",
    )
    parser.add_argument(
        "--list-configs",
        action="store_true",
        help="List configured universes and benchmarks without querying prices.",
    )
    parser.add_argument(
        "--start-date",
        type=_parse_date,
        default=None,
        help="Optional benchmark start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end-date",
        type=_parse_date,
        default=None,
        help="Optional benchmark end date in YYYY-MM-DD format.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from data import FixtureDataProvider
        from evaluation import (
            create_benchmark,
            list_benchmark_specs,
        )
        from universes import create_universe, list_universe_definitions
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"missing Python dependency: {exc.name}; "
            "install requirements with .venv/bin/python -m pip install -r requirements.txt"
        ) from exc

    if args.list_configs:
        print("universes:")
        for definition in list_universe_definitions():
            asset_classes = ",".join(definition.asset_classes)
            print(
                f"  {definition.key}: {definition.name} "
                f"asset_classes={asset_classes} "
                f"membership_provider={definition.membership_provider_key}"
            )
        print("benchmarks:")
        for spec in list_benchmark_specs():
            print(f"  {spec.key}: {spec.ticker} ({spec.name})")
        return

    provider = FixtureDataProvider()
    try:
        universe = create_universe(args.universe, provider)
        benchmark = _create_benchmark(args, provider, create_benchmark)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    members = universe.load_members()
    benchmark_prices = benchmark.load_prices(args.start_date, args.end_date)

    print(f"provider={provider.key}")
    print(f"universe={universe.key} members={len(members)}")
    print(
        "benchmark="
        f"{benchmark.spec.key} ticker={benchmark.spec.ticker}"
        f" rows={len(benchmark_prices)}"
        f"{_date_range_suffix(benchmark_prices)}"
    )


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _date_range_suffix(frame) -> str:
    if frame.empty or "date" not in frame:
        return ""
    return f" from={frame['date'].min()} to={frame['date'].max()}"


def _create_benchmark(args, provider, create_benchmark):
    from evaluation import BenchmarkSpec, ProviderBenchmark

    if args.benchmark_ticker:
        ticker = args.benchmark_ticker.upper()
        return ProviderBenchmark(
            BenchmarkSpec(
                key=ticker.lower(),
                ticker=ticker,
                name=f"{ticker} benchmark",
            ),
            provider,
        )
    return create_benchmark(args.benchmark, provider)


if __name__ == "__main__":
    from cli.errors import run_cli

    run_cli(main)
