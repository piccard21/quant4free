import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync raw financial reports and market-cap snapshots through AP11."
    )
    parser.add_argument("--mode", choices=["init", "daily"], default="daily")
    parser.add_argument(
        "--ticker",
        action="append",
        default=None,
        help="Ticker to sync. Can be repeated and bypasses refresh selection.",
    )
    parser.add_argument(
        "--tickers",
        default=None,
        help="Comma-separated tickers to sync and bypass refresh selection.",
    )
    parser.add_argument(
        "--refresh-hours",
        type=int,
        default=24,
        help="Daily mode refresh threshold for last_fundamental_update.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum daily-mode tickers selected from the database.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the sync without external API calls or writes.",
    )
    parser.add_argument(
        "--plan-limit",
        type=int,
        default=25,
        help="Number of planned tickers to print.",
    )
    return parser.parse_args()


def main() -> None:
    from data.sync import FundamentalSyncService

    args = parse_args()
    result = FundamentalSyncService().run(
        mode=args.mode,
        tickers=_parse_tickers(args.ticker, args.tickers),
        refresh_hours=args.refresh_hours,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print(f"sync_fundamentals={'dry_run' if result.dry_run else 'ok'}")
    print(f"mode={result.mode}")
    print(f"planned_tickers={len(result.planned_tickers)}")
    print(f"updated_tickers={result.updated_tickers}")
    print(f"upserted_reports={result.upserted_reports}")
    print(f"upserted_market_caps={result.upserted_market_caps}")
    if args.plan_limit > 0:
        for ticker in result.planned_tickers[: args.plan_limit]:
            print(f"plan ticker={ticker}")


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
    return [value.strip().upper() for value in values if value.strip()]


if __name__ == "__main__":
    from cli.errors import run_cli

    run_cli(main)
