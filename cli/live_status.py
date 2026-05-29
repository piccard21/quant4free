import argparse
from datetime import date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show AP9 live Model/Shadow/Real portfolio status."
    )
    parser.add_argument(
        "--as-of-date",
        type=_parse_date,
        default=None,
        help="Snapshot date in YYYY-MM-DD format. Defaults to latest shadow/model snapshot.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of execution-gap rows to print.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Print aligned rows too.",
    )
    parser.add_argument(
        "--weight-tolerance",
        type=float,
        default=0.001,
        help="Absolute weight tolerance for aligned real positions.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from live import LivePortfolioRepository, build_live_status
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"missing Python dependency: {exc.name}; "
            "install requirements with .venv/bin/python -m pip install -r requirements.txt"
        ) from exc

    repository = LivePortfolioRepository()
    model = repository.load_targets("model", args.as_of_date)
    shadow = repository.load_targets("shadow", args.as_of_date)
    real = repository.load_real_positions(args.as_of_date)
    cash = repository.load_cash_balance()

    status = build_live_status(
        model=model,
        shadow=shadow,
        real=real,
        cash_balance=cash,
        as_of_date=args.as_of_date,
        weight_tolerance=args.weight_tolerance,
    )

    print(f"as_of_date={status.as_of_date}")
    print(
        "positions="
        f"model:{status.model_positions},"
        f"shadow:{status.shadow_positions},"
        f"real:{status.real_positions}"
    )
    print(
        f"cash={status.cash_balance:.2f} "
        f"invested={status.invested_value:.2f} "
        f"total={status.total_value:.2f}"
    )
    print(f"actionable_gaps={len(status.actionable_gaps)}")

    rows = status.gaps if args.all else status.actionable_gaps
    rows = rows[: max(args.limit, 0)]
    if rows:
        print(
            "ticker state model_weight shadow_weight real_weight "
            "weight_gap shares real_value"
        )
        for gap in rows:
            print(
                f"{gap.ticker} {gap.state} "
                f"{gap.model_weight:.6f} {gap.shadow_weight:.6f} "
                f"{gap.real_weight:.6f} {gap.weight_gap:.6f} "
                f"{gap.shares:.6f} {gap.real_value:.2f}"
            )


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    main()
