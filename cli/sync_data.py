import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the AP11 modular price and fundamental syncs."
    )
    parser.add_argument("--mode", choices=["init", "daily"], default="daily")
    parser.add_argument("--benchmark-ticker", default="SPY")
    parser.add_argument(
        "--ticker",
        action="append",
        default=None,
        help="Ticker to sync. Can be repeated.",
    )
    parser.add_argument(
        "--tickers",
        default=None,
        help="Comma-separated tickers to sync.",
    )
    parser.add_argument(
        "--skip-ticker-sync",
        action="store_true",
        help="Use existing active tickers from the database instead of Wikipedia.",
    )
    parser.add_argument("--refresh-hours", type=int, default=24)
    parser.add_argument("--fundamental-limit", type=int, default=25)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan both sync steps without external API calls or writes.",
    )
    parser.add_argument(
        "--price-batch-size",
        type=int,
        default=25,
        help="Price provider requests per batch before an optional throttle pause.",
    )
    parser.add_argument(
        "--fundamental-batch-size",
        type=int,
        default=10,
        help="Fundamental provider requests per batch before an optional throttle pause.",
    )
    parser.add_argument(
        "--throttle-seconds",
        type=float,
        default=0.0,
        help="Seconds to sleep between provider request batches.",
    )
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--backoff-seconds", type=float, default=1.0)
    parser.add_argument("--circuit-breaker-failures", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    from data.sync import FundamentalSyncService, PriceSyncService, SyncRequestPolicy

    args = parse_args()
    tickers = _parse_tickers(args.ticker, args.tickers)
    price_policy = SyncRequestPolicy(
        batch_size=args.price_batch_size,
        throttle_seconds=args.throttle_seconds,
        max_retries=args.max_retries,
        backoff_seconds=args.backoff_seconds,
        circuit_breaker_failures=args.circuit_breaker_failures,
    )
    fundamental_policy = SyncRequestPolicy(
        batch_size=args.fundamental_batch_size,
        throttle_seconds=args.throttle_seconds,
        max_retries=args.max_retries,
        backoff_seconds=args.backoff_seconds,
        circuit_breaker_failures=args.circuit_breaker_failures,
    )
    price_result = PriceSyncService(request_policy=price_policy).run(
        mode=args.mode,
        tickers=tickers,
        benchmark_ticker=args.benchmark_ticker,
        sync_tickers=not args.skip_ticker_sync,
        dry_run=args.dry_run,
    )
    fundamental_result = FundamentalSyncService(
        request_policy=fundamental_policy
    ).run(
        mode=args.mode,
        tickers=tickers,
        refresh_hours=args.refresh_hours,
        limit=args.fundamental_limit,
        dry_run=args.dry_run,
    )

    print(f"sync_data={'dry_run' if args.dry_run else 'ok'}")
    print(
        "prices "
        f"planned_tickers={len(price_result.planned)} "
        f"downloaded_tickers={price_result.downloaded_tickers} "
        f"upserted_candles={price_result.upserted_candles} "
        f"batch_size={price_policy.batch_size}"
    )
    if price_result.membership_sync_run_id is not None:
        print(f"membership_sync_run_id={price_result.membership_sync_run_id}")
    if price_result.sync_run_id is not None:
        print(f"price_sync_run_id={price_result.sync_run_id}")
    print(
        "fundamentals "
        f"planned_tickers={len(fundamental_result.planned_tickers)} "
        f"updated_tickers={fundamental_result.updated_tickers} "
        f"upserted_reports={fundamental_result.upserted_reports} "
        f"upserted_market_caps={fundamental_result.upserted_market_caps} "
        f"batch_size={fundamental_policy.batch_size}"
    )
    print(
        "request_policy "
        f"throttle_seconds={args.throttle_seconds} "
        f"max_retries={args.max_retries} "
        f"backoff_seconds={args.backoff_seconds} "
        f"circuit_breaker_failures={args.circuit_breaker_failures}"
    )
    if fundamental_result.sync_run_id is not None:
        print(f"fundamental_sync_run_id={fundamental_result.sync_run_id}")


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
