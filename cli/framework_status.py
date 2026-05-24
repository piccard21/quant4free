import argparse
from datetime import date
from typing import Optional

from data import FixtureDataProvider
from evaluation import BenchmarkSpec, ProviderBenchmark
from universes import ActiveTickerUniverse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show AP3 provider, universe, and benchmark contract status."
    )
    parser.add_argument(
        "--benchmark-ticker",
        default="SPY",
        help="Ticker used as benchmark price series.",
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
    provider = FixtureDataProvider()
    universe = ActiveTickerUniverse(provider)
    benchmark = ProviderBenchmark(
        BenchmarkSpec(
            key=args.benchmark_ticker.lower(),
            ticker=args.benchmark_ticker,
            name=f"{args.benchmark_ticker} benchmark",
        ),
        provider,
    )

    members = universe.load_members()
    benchmark_prices = benchmark.load_prices(args.start_date, args.end_date)

    print(f"provider={provider.key}")
    print(f"universe={universe.key} members={len(members)}")
    print(
        "benchmark="
        f"{benchmark.spec.ticker} rows={len(benchmark_prices)}"
        f"{_date_range_suffix(benchmark_prices)}"
    )


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _date_range_suffix(frame) -> str:
    if frame.empty or "date" not in frame:
        return ""
    return f" from={frame['date'].min()} to={frame['date'].max()}"


if __name__ == "__main__":
    main()
