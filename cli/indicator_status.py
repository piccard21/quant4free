import argparse
from datetime import date, timedelta
from typing import Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AP6 indicator calculations against fixture-backed raw data."
    )
    parser.add_argument(
        "--universe",
        default="sp500_active",
        help="Universe configuration key.",
    )
    parser.add_argument(
        "--as-of-date",
        type=_parse_date,
        default=None,
        help="Calculation date in YYYY-MM-DD format. Defaults to latest price date.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=252,
        help="Calendar-day lookback for momentum and relative strength.",
    )
    parser.add_argument(
        "--indicator",
        action="append",
        dest="indicators",
        help="Indicator key to calculate. Repeat to select multiple indicators.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of rows to print.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from data import FixtureDataProvider
        from indicators import compute_indicators, create_indicators
        from universes import create_universe
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"missing Python dependency: {exc.name}; "
            "install requirements with .venv/bin/python -m pip install -r requirements.txt"
        ) from exc

    provider = FixtureDataProvider()
    try:
        universe = create_universe(args.universe, provider)
        indicators = create_indicators(args.indicators)
    except ValueError as exc:
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
    values = compute_indicators(
        indicators,
        prices=prices,
        fundamentals=fundamentals,
        market_caps=market_caps,
        as_of_date=as_of_date,
        params={
            "momentum_return": {"lookback_days": args.lookback_days},
            "relative_strength": {"lookback_days": args.lookback_days},
        },
    )

    print(f"provider={provider.key}")
    print(f"universe={universe.key} members={len(members)}")
    print(f"as_of_date={as_of_date}")
    print(f"indicators={','.join(indicator.key for indicator in indicators)}")
    print(f"rows={len(values)}")
    if not values.empty and args.limit > 0:
        print(values.head(args.limit).to_string(index=False))


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
