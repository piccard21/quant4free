import argparse
import logging

from sqlalchemy import text

from shared.settings import engine, load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ändert aktive Strategie-Settings im laufenden Betrieb. Neue Werte gelten nur für künftige Snapshots."
    )
    parser.add_argument("--portfolio-size", type=int, default=None)
    parser.add_argument("--max-trades-per-month", type=int, default=None)
    parser.add_argument("--max-sector-positions", type=int, default=None)
    parser.add_argument("--min-holding-months", type=int, default=None)
    parser.add_argument(
        "--max-funding-sell-pct",
        type=float,
        default=None,
        help="Variante C: maximaler Positionswert-Anteil je bestehender Position für Funding-ADJUST_SELLs, z. B. 0.20",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def validate_args(args) -> None:
    if args.portfolio_size is not None and args.portfolio_size <= 0:
        raise ValueError("--portfolio-size muss > 0 sein")
    if args.max_trades_per_month is not None and args.max_trades_per_month <= 0:
        raise ValueError("--max-trades-per-month muss > 0 sein")
    if args.max_sector_positions is not None and args.max_sector_positions <= 0:
        raise ValueError("--max-sector-positions muss > 0 sein")
    if args.min_holding_months is not None and args.min_holding_months < 0:
        raise ValueError("--min-holding-months darf nicht negativ sein")
    if args.max_funding_sell_pct is not None and not (0 <= args.max_funding_sell_pct <= 1):
        raise ValueError("--max-funding-sell-pct muss zwischen 0 und 1 liegen")


def main():
    args = parse_args()
    validate_args(args)

    updates = {}
    if args.portfolio_size is not None:
        updates["portfolio_size"] = args.portfolio_size
    if args.max_trades_per_month is not None:
        updates["max_trades_per_month"] = args.max_trades_per_month
    if args.max_sector_positions is not None:
        updates["max_sector_positions"] = args.max_sector_positions
    if args.min_holding_months is not None:
        updates["min_holding_months"] = args.min_holding_months
    if args.max_funding_sell_pct is not None:
        updates["max_funding_sell_pct"] = args.max_funding_sell_pct

    if not updates:
        logger.info("Keine Änderung angegeben.")
        return

    before = load_settings()
    logger.info(
        "Aktuell: portfolio_size=%s | max_trades_per_month=%s | max_sector_positions=%s | min_holding_months=%s | max_funding_sell_pct=%.4f",
        before.portfolio_size,
        before.max_trades_per_month,
        before.max_sector_positions,
        before.min_holding_months,
        before.max_funding_sell_pct,
    )

    set_clause = ", ".join([f"{key} = :{key}" for key in updates])
    sql = text(f"""
        UPDATE strategy_settings
        SET {set_clause}
        WHERE is_active = 1
    """)

    if args.dry_run:
        logger.info("DRY-RUN: Würde ändern: %s", updates)
        return

    with engine.begin() as conn:
        conn.execute(sql, updates)

    after = load_settings()
    logger.info(
        "Neu: portfolio_size=%s | max_trades_per_month=%s | max_sector_positions=%s | min_holding_months=%s | max_funding_sell_pct=%.4f",
        after.portfolio_size,
        after.max_trades_per_month,
        after.max_sector_positions,
        after.min_holding_months,
        after.max_funding_sell_pct,
    )
    logger.info("Hinweis: Bereits eingefrorene Snapshots bleiben unverändert.")


if __name__ == "__main__":
    main()


