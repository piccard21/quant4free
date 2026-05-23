import argparse
import logging
import subprocess
import sys

from sqlalchemy import text

from shared.settings import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# HELPER
# --------------------------------------------------

def run_step(name: str, command: list[str]) -> None:
    logger.info(name)
    result = subprocess.run(command)
    if result.returncode != 0:
        logger.error("Fehler bei Schritt: %s", name)
        sys.exit(1)


def get_latest_market_date():
    """
    Liefert den letzten verfügbaren Handelstag aus daily_candles.

    Wichtig:
    Daily-Pipeline muss denselben Stichtag für Factor Metrics,
    Factor Scores und Performance verwenden. Sonst entstehen z. B.
    am Wochenende Factor-Snapshots für heute, aber Performance für
    den letzten Handelstag.
    """
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT MAX(date) FROM daily_candles")
        ).scalar()


def get_latest_trade_plan_date():
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT MAX(as_of_date) FROM trade_plan_summary")
        ).scalar()


# --------------------------------------------------
# CORE PIPELINES
# --------------------------------------------------

def run_daily(no_performance: bool = False) -> None:
    logger.info("=== CORE DAILY START ===")

    run_step(
        "Starte Price Sync...",
        ["python", "-m", "core.sync_prices"],
    )

    run_step(
        "Starte Fundamental Sync...",
        ["python", "-m", "core.sync_fundamentals"],
    )

    as_of_date = get_latest_market_date()
    if as_of_date is None:
        logger.error("Kein Market-Date in daily_candles gefunden.")
        sys.exit(1)

    as_of_date = str(as_of_date)
    logger.info("Daily-Stichtag: %s", as_of_date)

    run_step(
        "Starte Factor Metrics...",
        ["python", "-m", "core.build_factor_metrics", "--as-of-date", as_of_date],
    )

    run_step(
        "Starte Factor Scores...",
        ["python", "-m", "core.build_factor_scores", "--as-of-date", as_of_date],
    )

    if not no_performance:
        run_step(
            "Starte Performance...",
            ["python", "-m", "research.build_performance", "--as-of-date", as_of_date],
        )

    logger.info("=== CORE DAILY DONE ===")


def run_monthly(no_performance: bool = False) -> None:
    logger.info("=== CORE MONTHLY START ===")

    run_step(
        "Starte Portfolio Build...",
        ["python", "-m", "core.build_portfolio"],
    )

    run_step(
        "Starte Tradable Shadow Build...",
        ["python", "-m", "core.build_tradable_shadow"],
    )

    run_step(
        "Starte Rebalance...",
        ["python", "-m", "core.build_rebalance"],
    )

    run_step(
        "Starte Trade Plan...",
        ["python", "-m", "core.build_trade_plan"],
    )

    if not no_performance:
        as_of_date = get_latest_trade_plan_date()

        if as_of_date is None:
            logger.error(
                "Keine trade_plan_summary gefunden. "
                "Performance kann nicht für den Monthly-Stichtag berechnet werden."
            )
            sys.exit(1)

        run_step(
            f"Starte Performance für Monthly-Stichtag {as_of_date}...",
            [
                "python",
                "-m",
                "research.build_performance",
                "--as-of-date",
                str(as_of_date),
            ],
        )

    logger.info("=== CORE MONTHLY DONE ===")


# --------------------------------------------------
# CLI
# --------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Core Pipeline Runner")

    parser.add_argument(
        "mode",
        choices=["daily", "monthly"],
        help="Pipeline-Modus",
    )

    parser.add_argument(
        "--no-performance",
        action="store_true",
        help="Performance-Berechnung überspringen",
    )

    return parser.parse_args()


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    args = parse_args()

    if args.mode == "daily":
        run_daily(no_performance=args.no_performance)

    elif args.mode == "monthly":
        run_monthly(no_performance=args.no_performance)


if __name__ == "__main__":
    main()


