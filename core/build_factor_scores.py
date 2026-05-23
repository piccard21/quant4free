import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import text

from shared.settings import engine, load_settings


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# HELPER
# --------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--as-of-date",
        dest="as_of_date",
        help="Optionaler Stichtag im Format YYYY-MM-DD. Standard: MAX(as_of_date) aus factor_metrics",
    )
    return parser.parse_args()


def get_latest_as_of_date():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(as_of_date) FROM factor_metrics"))
        as_of_date = result.scalar()

    if as_of_date is None:
        raise ValueError("Keine Daten in factor_metrics gefunden.")

    return as_of_date


def resolve_as_of_date(cli_value: str | None):
    if cli_value:
        return pd.to_datetime(cli_value).date()
    return get_latest_as_of_date()


def load_metrics(as_of_date):
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT *
                FROM factor_metrics
                WHERE as_of_date = :as_of_date
            """),
            conn,
            params={"as_of_date": as_of_date},
        )
    return df


def percentile_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    s = s.replace([np.inf, -np.inf], np.nan)

    valid = s.dropna()
    if valid.empty:
        return pd.Series(index=series.index, dtype=float)

    ascending = True if higher_is_better else False
    ranked = valid.rank(method="average", pct=True, ascending=ascending) * 100.0

    result = pd.Series(index=series.index, dtype=float)
    result.loc[valid.index] = ranked

    return result


def mean_ignore_nan(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    values = df[columns].apply(pd.to_numeric, errors="coerce")
    values = values.replace([np.inf, -np.inf], np.nan)
    return values.mean(axis=1, skipna=True)


def score_sector_relative(
    df: pd.DataFrame,
    source_col: str,
    target_col: str,
    higher_is_better: bool,
):
    df[target_col] = (
        df.groupby("sector", group_keys=False)[source_col]
        .apply(lambda s: percentile_rank(s, higher_is_better=higher_is_better))
    )
    return df


def score_global(
    df: pd.DataFrame,
    source_col: str,
    target_col: str,
    higher_is_better: bool,
):
    df[target_col] = percentile_rank(df[source_col], higher_is_better=higher_is_better)
    return df


# --------------------------------------------------
# CORE
# --------------------------------------------------

def compute_scores(df: pd.DataFrame, settings) -> pd.DataFrame:
    df = df.copy()

    valid = df[df["is_valid"] == 1].copy()

    if valid.empty:
        raise ValueError("Keine gültigen Titel in factor_metrics gefunden.")

    raw_numeric_cols = [
        "ev_to_ebit",
        "free_cash_flow_yield",
        "earnings_yield",
        "roe",
        "debt_to_equity",
        "revenue_growth",
        "return_12m",
        "return_6m",
        "rel_strength_12m",
    ]
    for col in raw_numeric_cols:
        if col in valid.columns:
            valid[col] = pd.to_numeric(valid[col], errors="coerce")
            valid[col] = valid[col].replace([np.inf, -np.inf], np.nan)

    # VALUE
    valid = score_sector_relative(
        valid, "ev_to_ebit", "ev_to_ebit_score", higher_is_better=False
    )
    valid = score_sector_relative(
        valid, "free_cash_flow_yield", "free_cash_flow_yield_score", higher_is_better=True
    )
    valid = score_sector_relative(
        valid, "earnings_yield", "earnings_yield_score", higher_is_better=True
    )

    # QUALITY
    valid = score_sector_relative(
        valid, "roe", "roe_score", higher_is_better=True
    )
    valid = score_sector_relative(
        valid, "debt_to_equity", "debt_to_equity_score", higher_is_better=False
    )
    valid = score_sector_relative(
        valid, "revenue_growth", "revenue_growth_score", higher_is_better=True
    )

    # MOMENTUM
    valid = score_global(
        valid, "return_12m", "return_12m_score", higher_is_better=True
    )
    valid = score_global(
        valid, "return_6m", "return_6m_score", higher_is_better=True
    )
    valid = score_global(
        valid, "rel_strength_12m", "rel_strength_12m_score", higher_is_better=True
    )

    score_cols = [
        "ev_to_ebit_score",
        "free_cash_flow_yield_score",
        "earnings_yield_score",
        "roe_score",
        "debt_to_equity_score",
        "revenue_growth_score",
        "return_12m_score",
        "return_6m_score",
        "rel_strength_12m_score",
    ]
    for col in score_cols:
        if col in valid.columns:
            valid[col] = pd.to_numeric(valid[col], errors="coerce")
            valid[col] = valid[col].replace([np.inf, -np.inf], np.nan)

    valid["value_score"] = mean_ignore_nan(
        valid,
        [
            "ev_to_ebit_score",
            "free_cash_flow_yield_score",
            "earnings_yield_score",
        ],
    )

    valid["quality_score"] = mean_ignore_nan(
        valid,
        [
            "roe_score",
            "debt_to_equity_score",
            "revenue_growth_score",
        ],
    )

    valid["momentum_return_score"] = (
        0.5 * valid["return_12m_score"]
        + 0.5 * valid["return_6m_score"]
    )

    valid["momentum_score"] = (
        settings.momentum_return_weight * valid["momentum_return_score"]
        + settings.momentum_rel_strength_weight * valid["rel_strength_12m_score"]
    )

    valid["final_score"] = (
        valid["value_score"] * settings.value_weight
        + valid["quality_score"] * settings.quality_weight
        + valid["momentum_score"] * settings.momentum_weight
    )
    valid["final_score"] = pd.to_numeric(valid["final_score"], errors="coerce")
    valid["final_score"] = valid["final_score"].replace([np.inf, -np.inf], np.nan)

    valid = valid[valid["final_score"].notna()].copy()

    if valid.empty:
        raise ValueError("Keine rankbaren Titel gefunden: final_score ist überall leer.")

    valid["final_rank"] = (
        valid["final_score"]
        .rank(method="first", ascending=False)
        .astype("Int64")
    )

    valid["trend_positive"] = pd.to_numeric(
        valid["trend_positive"],
        errors="coerce",
    ).fillna(0).astype(int)

    valid["buy_eligible"] = (
        (valid["final_rank"] <= settings.buy_rank_threshold)
        & (valid["trend_positive"] == 1)
    ).astype(int)

    valid["sell_flag"] = (
        (valid["final_rank"] > settings.sell_rank_threshold)
        | (valid["trend_positive"] == 0)
    ).astype(int)

    return valid


def prepare_output(scored: pd.DataFrame) -> pd.DataFrame:
    scored = scored.copy()
    scored["created_at"] = datetime.now()

    cols = [
        "as_of_date",
        "ticker",
        "sector",
        "ev_to_ebit_score",
        "free_cash_flow_yield_score",
        "earnings_yield_score",
        "roe_score",
        "debt_to_equity_score",
        "revenue_growth_score",
        "return_12m_score",
        "return_6m_score",
        "rel_strength_12m_score",
        "value_score",
        "quality_score",
        "momentum_score",
        "final_score",
        "final_rank",
        "trend_positive",
        "buy_eligible",
        "sell_flag",
        "created_at",
    ]

    for col in cols:
        if col not in scored.columns:
            scored[col] = np.nan

    scored["final_rank"] = pd.to_numeric(scored["final_rank"], errors="coerce")

    return scored[cols]


def save_to_db(df: pd.DataFrame):
    if df.empty:
        logger.warning("Keine Scores zum Speichern vorhanden.")
        return

    as_of_date = df["as_of_date"].iloc[0]

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM factor_scores WHERE as_of_date = :as_of_date"),
            {"as_of_date": as_of_date},
        )

    df.to_sql(
        "factor_scores",
        engine,
        if_exists="append",
        index=False,
        method="multi",
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def run(as_of_date):
    logger.info("Starte Factor Scores Berechnung...")

    settings = load_settings()

    logger.info(
        "Verwende Settings: version=%s | weights=(%.2f / %.2f / %.2f) | momentum_subweights=(%.2f / %.2f) | buy_rank<=%s | sell_rank>%s",
        settings.strategy_version,
        settings.value_weight,
        settings.quality_weight,
        settings.momentum_weight,
        settings.momentum_return_weight,
        settings.momentum_rel_strength_weight,
        settings.buy_rank_threshold,
        settings.sell_rank_threshold,
    )
    logger.info("Stichtag: %s", as_of_date)

    df = load_metrics(as_of_date)
    logger.info("Geladene Metrics: %s", len(df))

    scored = compute_scores(df, settings)
    output = prepare_output(scored)

    logger.info("Rankbare Titel: %s", len(output))

    save_to_db(output)

    logger.info(
        "Factor Scores gespeichert für %s gültige Ticker. Top Rank: %s",
        len(output),
        output["final_rank"].min() if not output.empty else None,
    )


if __name__ == "__main__":
    args = parse_args()
    as_of_date = resolve_as_of_date(args.as_of_date)
    run(as_of_date)
