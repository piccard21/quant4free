
import argparse
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import text

from shared.settings import engine, load_settings

SNAPSHOT_TYPE = "model"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--as-of-date",
        dest="as_of_date",
        help="Optionaler Stichtag im Format YYYY-MM-DD. Standard: MAX(as_of_date) aus factor_scores",
    )
    return parser.parse_args()


def get_latest_date():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(as_of_date) FROM factor_scores"))
        as_of_date = result.scalar()

    if as_of_date is None:
        raise ValueError("Keine factor_scores vorhanden")

    return as_of_date


def resolve_as_of_date(cli_value: str | None):
    return cli_value if cli_value else get_latest_date()


def load_candidates(as_of_date):
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT *
                FROM factor_scores
                WHERE as_of_date = :d
                  AND buy_eligible = 1
                ORDER BY final_rank ASC
            """),
            conn,
            params={"d": as_of_date}
        )
    return df


def build_portfolio(df: pd.DataFrame, settings) -> pd.DataFrame:
    if df.empty:
        return df

    selected = []
    sector_count = {}

    for _, row in df.iterrows():
        sector = row["sector"]
        count = sector_count.get(sector, 0)

        if count >= settings.max_sector_positions:
            continue

        selected.append(row)
        sector_count[sector] = count + 1

        if len(selected) >= settings.portfolio_size:
            break

    portfolio = pd.DataFrame(selected)

    if portfolio.empty:
        return portfolio

    portfolio = portfolio.sort_values("final_rank").reset_index(drop=True)
    portfolio["portfolio_rank"] = range(1, len(portfolio) + 1)
    portfolio["target_weight"] = 1.0 / len(portfolio)

    return portfolio


def assert_model_snapshot_is_new(as_of_date) -> None:
    with engine.connect() as conn:
        exists = conn.execute(
            text("""
                SELECT 1
                FROM portfolio_snapshots
                WHERE as_of_date = :as_of_date
                  AND snapshot_type = :snapshot_type
                LIMIT 1
            """),
            {"as_of_date": as_of_date, "snapshot_type": SNAPSHOT_TYPE},
        ).scalar()

    if exists is not None:
        raise ValueError(
            f"Für den Stichtag {as_of_date} existiert bereits ein eingefrorener Model-Portfolio-Snapshot. "
            "Der Lauf wird abgebrochen, damit keine Snapshots überschrieben oder still ignoriert werden."
        )


def save(df: pd.DataFrame):
    if df.empty:
        logger.warning("Kein Portfolio zu speichern")
        return

    as_of_date = df["as_of_date"].iloc[0]
    assert_model_snapshot_is_new(as_of_date)

    df = df.copy()
    df["snapshot_type"] = SNAPSHOT_TYPE
    df["source_rank"] = df["final_rank"]
    df["created_at"] = datetime.now()

    insert_sql = text("""
        INSERT INTO portfolio_snapshots (
            as_of_date,
            snapshot_type,
            ticker,
            portfolio_rank,
            source_rank,
            sector,
            target_weight,
            final_score,
            value_score,
            quality_score,
            momentum_score,
            trend_positive,
            buy_eligible,
            created_at
        ) VALUES (
            :as_of_date,
            :snapshot_type,
            :ticker,
            :portfolio_rank,
            :source_rank,
            :sector,
            :target_weight,
            :final_score,
            :value_score,
            :quality_score,
            :momentum_score,
            :trend_positive,
            :buy_eligible,
            :created_at
        )
    """)

    with engine.begin() as conn:
        conn.execute(insert_sql, df.to_dict(orient="records"))


def run(as_of_date: str | None = None):
    logger.info("=== BUILD MODEL PORTFOLIO START ===")

    settings = load_settings()
    date = resolve_as_of_date(as_of_date)

    logger.info(
        "Verwende Settings: version=%s | portfolio_size=%s | max_sector_positions=%s",
        settings.strategy_version,
        settings.portfolio_size,
        settings.max_sector_positions,
    )
    logger.info("Stichtag: %s", date)

    candidates = load_candidates(date)
    logger.info("Kandidaten: %s", len(candidates))

    portfolio = build_portfolio(candidates, settings)
    logger.info("Model Portfolio Größe: %s", len(portfolio))

    if not portfolio.empty:
        logger.info(
            "\n%s",
            portfolio[["portfolio_rank", "ticker", "sector", "final_rank"]].to_string(index=False)
        )

    save(portfolio)
    logger.info("=== BUILD MODEL PORTFOLIO DONE ===")


if __name__ == "__main__":
    args = parse_args()
    run(as_of_date=args.as_of_date)


