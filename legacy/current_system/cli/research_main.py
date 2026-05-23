import argparse
import logging
import subprocess
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["performance"])
    parser.add_argument(
        "--as-of-date",
        dest="as_of_date",
        help="Optionaler Stichtag im Format YYYY-MM-DD",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Alle fehlenden Stichtage berechnen",
    )
    return parser.parse_args()


def run_step(description: str, command: list[str]) -> None:
    logger.info(description)
    result = subprocess.run(command)
    if result.returncode != 0:
        logger.error("Fehler bei Schritt: %s", description)
        sys.exit(1)


def run_performance(as_of_date: str | None = None, backfill: bool = False) -> None:
    cmd = ["python", "-m", "research.build_performance"]

    if as_of_date:
        cmd += ["--as-of-date", as_of_date]

    if backfill:
        cmd += ["--mode", "backfill"]

    run_step("Starte Performance...", cmd)


def run() -> None:
    args = parse_args()

    if args.mode == "performance":
        run_performance(
            as_of_date=args.as_of_date,
            backfill=args.backfill
        )
    else:
        logger.error("Unbekannter Modus: %s", args.mode)
        sys.exit(1)


if __name__ == "__main__":
    run()
