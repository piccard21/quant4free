import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync raw ticker and daily candle data through the modular AP11 path."
    )
    parser.add_argument("--mode", choices=["init", "daily"], default="daily")
    parser.add_argument(
        "--ticker",
        action="append",
        default=None,
        help="Ticker to sync. Can be repeated; skips Wikipedia ticker refresh.",
    )
    parser.add_argument(
        "--tickers",
        default=None,
        help="Comma-separated tickers to sync; skips Wikipedia ticker refresh.",
    )
    parser.add_argument("--benchmark-ticker", default="SPY")
    parser.add_argument(
        "--skip-ticker-sync",
        action="store_true",
        help="Use existing active tickers from the database instead of Wikipedia.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the sync without external API calls or writes.",
    )
    parser.add_argument(
        "--plan-limit",
        type=int,
        default=10,
        help="Number of planned ticker date ranges to print.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
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
    from data.sync import PriceSyncService, SyncRequestPolicy

    args = parse_args()
    tickers = _parse_tickers(args.ticker, args.tickers)
    request_policy = SyncRequestPolicy(
        batch_size=args.batch_size,
        throttle_seconds=args.throttle_seconds,
        max_retries=args.max_retries,
        backoff_seconds=args.backoff_seconds,
        circuit_breaker_failures=args.circuit_breaker_failures,
    )
    result = PriceSyncService(request_policy=request_policy).run(
        mode=args.mode,
        tickers=tickers,
        benchmark_ticker=args.benchmark_ticker,
        sync_tickers=not args.skip_ticker_sync,
        dry_run=args.dry_run,
    )

    print(f"sync_prices={'dry_run' if result.dry_run else 'ok'}")
    print(f"mode={result.mode}")
    print(f"ticker_upserts={result.ticker_upserts}")
    print(f"deactivated_tickers={result.deactivated_tickers}")
    print(f"planned_tickers={len(result.planned)}")
    print(f"downloaded_tickers={result.downloaded_tickers}")
    print(f"upserted_candles={result.upserted_candles}")
    print(
        "request_policy "
        f"batch_size={request_policy.batch_size} "
        f"throttle_seconds={request_policy.throttle_seconds} "
        f"max_retries={request_policy.max_retries} "
        f"backoff_seconds={request_policy.backoff_seconds} "
        f"circuit_breaker_failures={request_policy.circuit_breaker_failures}"
    )
    if result.membership_sync_run_id is not None:
        print(f"membership_sync_run_id={result.membership_sync_run_id}")
    if result.sync_run_id is not None:
        print(f"price_sync_run_id={result.sync_run_id}")
    if args.plan_limit > 0:
        for item in result.planned[: args.plan_limit]:
            print(
                "plan "
                f"ticker={item.ticker} "
                f"provider={item.provider_key} "
                f"provider_symbol={item.provider_symbol} "
                f"start_date={item.start_date} "
                f"end_date={item.end_date}"
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
