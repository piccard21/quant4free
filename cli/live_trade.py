import argparse
from datetime import date, datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Book a manual live trade execution."
    )
    parser.add_argument(
        "--as-of-date",
        required=True,
        type=_parse_date,
        help="Strategy or trade-plan snapshot date in YYYY-MM-DD format.",
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol.")
    parser.add_argument(
        "--execution-type",
        required=True,
        choices=["BUY", "SELL"],
        help="Actual broker execution direction.",
    )
    parser.add_argument("--shares", required=True, type=float, help="Executed shares.")
    parser.add_argument("--price", required=True, type=float, help="Execution price per share.")
    parser.add_argument("--fee", type=float, default=1.0, help="Trade fee.")
    parser.add_argument(
        "--executed-at",
        type=_parse_datetime,
        default=None,
        help="Execution timestamp in YYYY-MM-DD HH:MM:SS format. Defaults to now.",
    )
    parser.add_argument(
        "--trade-plan-action",
        default=None,
        help="Optional expected trade-plan action: BUY, SELL, ADJUST_BUY, ADJUST_SELL.",
    )
    parser.add_argument("--broker", default=None, help="Optional broker name.")
    parser.add_argument("--notes", default=None, help="Optional execution note.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the prospective execution without writing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from cli.errors import CliUsageError

    try:
        from live import LiveExecutionService, TradeExecutionRequest
        from shared import CapabilityValidationError, validate_live_capabilities
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"missing Python dependency: {exc.name}; "
            "install requirements with .venv/bin/python -m pip install -r requirements.txt"
        ) from exc

    try:
        validate_live_capabilities(live_workflow_key="live_trade")
    except CapabilityValidationError as exc:
        raise CliUsageError(str(exc)) from exc

    result = LiveExecutionService().execute_trade(
        TradeExecutionRequest(
            as_of_date=args.as_of_date,
            ticker=args.ticker,
            execution_type=args.execution_type,
            shares=args.shares,
            price=args.price,
            fee=args.fee,
            executed_at=args.executed_at or datetime.now(),
            trade_plan_action=args.trade_plan_action,
            broker=args.broker,
            notes=args.notes,
            dry_run=args.dry_run,
        )
    )

    print(f"dry_run={result.dry_run}")
    print(f"trade_execution_id={result.trade_execution_id}")
    print(f"as_of_date={result.as_of_date}")
    print(f"ticker={result.ticker}")
    print(f"execution_type={result.execution_type}")
    print(f"shares={result.shares:.6f}")
    print(f"price={result.price:.6f}")
    print(f"gross_amount={result.gross_amount:.6f}")
    print(f"fee={result.fee:.6f}")
    print(f"net_amount={result.net_amount:.6f}")
    print(
        "realized_profit="
        + ("None" if result.realized_profit is None else f"{result.realized_profit:.6f}")
    )
    print(f"tax_amount={result.tax_amount:.6f}")
    print(f"cash_before={result.cash_before:.6f}")
    print(f"cash_after={result.cash_after:.6f}")
    print(f"executed_at={result.executed_at}")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected datetime format YYYY-MM-DD HH:MM:SS"
        ) from exc


if __name__ == "__main__":
    from cli.errors import run_cli

    run_cli(main)
