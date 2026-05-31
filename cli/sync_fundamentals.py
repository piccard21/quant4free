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
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Provider requests per batch before an optional throttle pause.",
    )
    parser.add_argument(
        "--throttle-seconds",
        type=float,
        default=0.0,
        help="Seconds to sleep between provider request batches.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Retries per provider request before failing the sync run.",
    )
    parser.add_argument(
        "--backoff-seconds",
        type=float,
        default=1.0,
        help="Initial retry backoff in seconds; retries use exponential backoff.",
    )
    parser.add_argument(
        "--circuit-breaker-failures",
        type=int,
        default=5,
        help="Consecutive failed provider requests before opening the circuit breaker.",
    )
    return parser.parse_args()


def main() -> None:
    from data.sync import FundamentalSyncService, SyncRequestPolicy

    args = parse_args()
    request_policy = SyncRequestPolicy(
        batch_size=args.batch_size,
        throttle_seconds=args.throttle_seconds,
        max_retries=args.max_retries,
        backoff_seconds=args.backoff_seconds,
        circuit_breaker_failures=args.circuit_breaker_failures,
    )
    result = FundamentalSyncService(request_policy=request_policy).run(
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
    print(
        "request_policy "
        f"batch_size={request_policy.batch_size} "
        f"throttle_seconds={request_policy.throttle_seconds} "
        f"max_retries={request_policy.max_retries} "
        f"backoff_seconds={request_policy.backoff_seconds} "
        f"circuit_breaker_failures={request_policy.circuit_breaker_failures}"
    )
    if result.sync_run_id is not None:
        print(f"fundamental_sync_run_id={result.sync_run_id}")
    if args.plan_limit > 0:
        for item in result.planned[: args.plan_limit]:
            print(
                "plan "
                f"ticker={item.ticker} "
                f"provider={item.provider_key} "
                f"provider_symbol={item.provider_symbol}"
            )


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
