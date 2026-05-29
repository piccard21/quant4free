import argparse
from datetime import date, datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Book an AP9 live cash movement into the real portfolio ledger."
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=["deposit", "withdrawal"],
        help="Cash movement type.",
    )
    parser.add_argument(
        "--amount",
        required=True,
        type=float,
        help="Positive cash amount.",
    )
    parser.add_argument(
        "--as-of-date",
        type=_parse_date,
        default=None,
        help="Strategy snapshot date in YYYY-MM-DD format. Defaults to latest settings snapshot.",
    )
    parser.add_argument(
        "--booked-at",
        type=_parse_datetime,
        default=None,
        help="Booking timestamp in YYYY-MM-DD HH:MM:SS format. Defaults to now.",
    )
    parser.add_argument("--notes", default=None, help="Optional booking note.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the prospective booking without writing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from live import CashMovementRequest, LiveExecutionService
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"missing Python dependency: {exc.name}; "
            "install requirements with .venv/bin/python -m pip install -r requirements.txt"
        ) from exc

    result = LiveExecutionService().apply_cash_movement(
        CashMovementRequest(
            movement_type=args.type,
            amount=args.amount,
            as_of_date=args.as_of_date,
            booked_at=args.booked_at or datetime.now(),
            notes=args.notes,
            dry_run=args.dry_run,
        )
    )

    print(f"dry_run={result.dry_run}")
    print(f"as_of_date={result.as_of_date}")
    print(f"type={result.movement_type}")
    print(f"amount={result.amount:.6f}")
    print(f"cash_before={result.cash_before:.6f}")
    print(f"cash_after={result.cash_after:.6f}")
    print(f"booked_at={result.booked_at}")


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
