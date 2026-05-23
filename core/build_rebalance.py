
import argparse
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import text

from shared.settings import (
    engine,
    load_settings,
    save_settings_snapshot,
    find_existing_snapshot_tables,
)

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
        help="Optionaler Stichtag im Format YYYY-MM-DD. Standard: MAX(as_of_date) aus portfolio_snapshots shadow",
    )
    return parser.parse_args()


def get_latest_shadow_date():
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT MAX(as_of_date)
                FROM portfolio_snapshots
                WHERE snapshot_type = 'shadow'
            """)
        )
        as_of_date = result.scalar()

    if as_of_date is None:
        raise ValueError("Keine Shadow Portfolio Snapshots gefunden.")

    return as_of_date


def resolve_as_of_date(cli_value: str | None):
    return cli_value if cli_value else get_latest_shadow_date()


def assert_rebalance_snapshot_is_new(as_of_date) -> None:
    existing_tables = find_existing_snapshot_tables(as_of_date)

    if existing_tables:
        joined = ", ".join(existing_tables)
        raise ValueError(
            f"Für den Stichtag {as_of_date} existieren bereits eingefrorene Rebalance-Snapshots in: {joined}. "
            "Der Lauf wird abgebrochen, damit keine Snapshots überschrieben werden."
        )


def load_shadow_portfolio(as_of_date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    as_of_date,
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
                    buy_eligible
                FROM portfolio_snapshots
                WHERE as_of_date = :as_of_date
                  AND snapshot_type = 'shadow'
                ORDER BY portfolio_rank
            """),
            conn,
            params={"as_of_date": as_of_date},
        )
    return df


def load_real_positions() -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    ticker,
                    shares,
                    buy_price,
                    opened_at,
                    is_open
                FROM portfolio_positions
                WHERE is_open = 1
                ORDER BY opened_at ASC
            """),
            conn,
        )

    if not df.empty:
        df["opened_at"] = pd.to_datetime(df["opened_at"])

    return df


def load_factor_scores(as_of_date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    ticker,
                    final_rank AS source_rank,
                    final_score,
                    value_score,
                    quality_score,
                    momentum_score,
                    trend_positive
                FROM factor_scores
                WHERE as_of_date = :as_of_date
            """),
            conn,
            params={"as_of_date": as_of_date},
        )
    return df


def build_rebalance(
    shadow: pd.DataFrame,
    real: pd.DataFrame,
    factor_scores: pd.DataFrame,
    as_of_date,
    settings,
) -> pd.DataFrame:
    shadow = shadow.copy()
    real = real.copy()

    shadow_tickers = set(shadow["ticker"].tolist()) if not shadow.empty else set()
    real_tickers = set(real["ticker"].tolist()) if not real.empty else set()

    suggestions = []
    as_of_ts = pd.to_datetime(as_of_date)

    min_hold_days = int(settings.min_holding_months * 30)

    # Turnover-Control für echte Positionswechsel (BUY/SELL)
    configured_max_changes = int(settings.max_trades_per_month)
    portfolio_size = int(getattr(settings, "portfolio_size", len(shadow) if not shadow.empty else configured_max_changes))
    real_position_count = int(len(real))
    missing_positions = max(0, portfolio_size - real_position_count)
    max_changes = max(configured_max_changes, missing_positions)

    # ---------------------
    # BUY / HOLD Kandidaten aus Shadow
    # ---------------------
    for _, row in shadow.iterrows():
        ticker = row["ticker"]
        # row stammt aus shadow DataFrame
        sector = row.get("sector") if "sector" in row else "UNKNOWN"
        if sector is None or pd.isna(sector):
            # fallback aus factor_scores
            score_row = factor_scores.loc[factor_scores["ticker"] == ticker]
            if not score_row.empty:
                sector = score_row.iloc[0].get("sector")
            else:
                sector = "UNKNOWN"
    
        if ticker in real_tickers:
            real_row = real.loc[real["ticker"] == ticker].iloc[0]
            opened_at = real_row["opened_at"]
            holding_days = int((as_of_ts - opened_at).days) if pd.notna(opened_at) else None
    
            suggestions.append({
                "as_of_date": as_of_date,
                "ticker": ticker,
                "sector": sector,
                "action": "HOLD",
                "reason": "already_in_real_portfolio",
                "source_rank": int(row["source_rank"]) if pd.notna(row["source_rank"]) else None,
                "target_weight": float(row["target_weight"]) if pd.notna(row["target_weight"]) else None,
                "current_shares": float(real_row["shares"]) if pd.notna(real_row["shares"]) else None,
                "opened_at": opened_at.date() if pd.notna(opened_at) else None,
                "holding_days": holding_days,
                "min_hold_ok": 1,
            })
        else:
            suggestions.append({
                "as_of_date": as_of_date,
                "ticker": ticker,
                "sector": sector,
                "action": "BUY",
                "reason": "in_shadow_not_in_real",
                "source_rank": int(row["source_rank"]) if pd.notna(row["source_rank"]) else None,
                "target_weight": float(row["target_weight"]) if pd.notna(row["target_weight"]) else None,
                "current_shares": None,
                "opened_at": None,
                "holding_days": None,
                "min_hold_ok": 1,
            })

    # ---------------------
    # SELL Kandidaten aus Real, die nicht mehr im Shadow sind
    # ---------------------
    for _, row in real.iterrows():
        ticker = row["ticker"]
        if ticker in shadow_tickers:
            continue
    
        opened_at = row["opened_at"]
        holding_days = int((as_of_ts - opened_at).days) if pd.notna(opened_at) else None
        min_hold_ok = 1 if holding_days is None or holding_days >= min_hold_days else 0
    
        if min_hold_ok == 1:
            action = "SELL"
            reason = "in_real_not_in_shadow"
        else:
            action = "HOLD"
            reason = "min_hold_not_reached"
    
        # Score-Row aus factor_scores holen
        score_row = factor_scores.loc[factor_scores["ticker"] == ticker]
        if not score_row.empty:
            score_row = score_row.iloc[0]
            current_rank = int(score_row["source_rank"]) if pd.notna(score_row["source_rank"]) else None
            sector = score_row.get("sector")
            if sector is None or pd.isna(sector):
                sector = "UNKNOWN"  # fallback
        else:
            current_rank = None
            sector = "UNKNOWN"  # fallback
    
        suggestions.append({
            "as_of_date": as_of_date,
            "ticker": ticker,
            "sector": sector,  # jetzt sicher gefüllt
            "action": action,
            "reason": reason,
            "source_rank": current_rank,
            "target_weight": None,
            "current_shares": float(row["shares"]) if pd.notna(row["shares"]) else None,
            "opened_at": opened_at.date() if pd.notna(opened_at) else None,
            "holding_days": holding_days,
            "min_hold_ok": min_hold_ok,
        })
    # ---------------------
    # Sortierung nach Turnover-Limit
    # ---------------------
    result = pd.DataFrame(suggestions)
    if result.empty:
        return result

    used_changes = 0
    sell_candidates = result.loc[result["action"] == "SELL"].copy()
    buy_candidates = result.loc[result["action"] == "BUY"].copy()
    buy_candidates = buy_candidates.sort_values(["source_rank", "ticker"], na_position="last")

    for idx in sell_candidates.index:
        if used_changes < max_changes:
            used_changes += 1
        else:
            result.loc[idx, "action"] = "HOLD"
            result.loc[idx, "reason"] = "turnover_limit_reached"

    for idx in buy_candidates.index:
        if used_changes < max_changes:
            used_changes += 1
        else:
            result.loc[idx, "action"] = "HOLD"
            result.loc[idx, "reason"] = "turnover_limit_reached"

    action_order = {"SELL": 1, "BUY": 2, "HOLD": 3}
    result["sort_key"] = result["action"].map(action_order).fillna(99)
    result = result.sort_values(["sort_key", "source_rank", "ticker"], na_position="last")
    result = result.drop(columns=["sort_key"]).reset_index(drop=True)

    return result


def save_suggestions(df: pd.DataFrame, conn) -> None:
    if df.empty:
        logger.warning("Keine Rebalance-Vorschläge zu speichern.")
        return

    df = df.copy()
    df["created_at"] = datetime.now()
    df = df.astype(object)
    df = df.where(pd.notnull(df), None)

    insert_sql = text("""
        INSERT INTO rebalance_suggestions (
            as_of_date,
            ticker,
            sector,
            action,
            reason,
            source_rank,
            target_weight,
            current_shares,
            opened_at,
            holding_days,
            min_hold_ok,
            created_at
        ) VALUES (
            :as_of_date,
            :ticker,
            :sector,
            :action,
            :reason,
            :source_rank,
            :target_weight,
            :current_shares,
            :opened_at,
            :holding_days,
            :min_hold_ok,
            :created_at
        )
    """)

    conn.execute(insert_sql, df.to_dict(orient="records"))


def save_decision_log(df: pd.DataFrame, factor_scores: pd.DataFrame, settings, conn) -> None:
    if df.empty:
        logger.warning("Kein Decision Log zu speichern.")
        return

    df = df.copy()

    score_cols = [
        "ticker",
        "source_rank",
        "final_score",
        "value_score",
        "quality_score",
        "momentum_score",
        "trend_positive",
    ]
    scores_small = factor_scores[score_cols].drop_duplicates("ticker")

    df = df.merge(scores_small, on="ticker", how="left", suffixes=("", "_score"))

    if "source_rank_score" in df.columns:
        df["source_rank"] = df["source_rank"].fillna(df["source_rank_score"])
        df = df.drop(columns=["source_rank_score"])

    df["trend_positive"] = pd.to_numeric(df["trend_positive"], errors="coerce").fillna(0).astype(int)
    df["strategy_version"] = settings.strategy_version
    df["created_at"] = datetime.now()

    df = df.astype(object)
    df = df.where(pd.notnull(df), None)

    insert_sql = text("""
        INSERT INTO decision_log (
            as_of_date,
            ticker,
            action,
            reason,
            source_rank,
            final_score,
            value_score,
            quality_score,
            momentum_score,
            trend_positive,
            holding_days,
            min_hold_ok,
            strategy_version,
            created_at
        ) VALUES (
            :as_of_date,
            :ticker,
            :action,
            :reason,
            :source_rank,
            :final_score,
            :value_score,
            :quality_score,
            :momentum_score,
            :trend_positive,
            :holding_days,
            :min_hold_ok,
            :strategy_version,
            :created_at
        )
    """)

    conn.execute(insert_sql, df.to_dict(orient="records"))


def run(as_of_date: str | None = None):
    logger.info("=== BUILD REBALANCE START ===")

    settings = load_settings()
    as_of_date = resolve_as_of_date(as_of_date)
    assert_rebalance_snapshot_is_new(as_of_date)

    logger.info(
        "Verwende Settings: version=%s | min_holding_months=%s | portfolio_size=%s | max_trades_per_month=%s",
        settings.strategy_version,
        settings.min_holding_months,
        settings.portfolio_size,
        settings.max_trades_per_month,
    )
    logger.info("Stichtag: %s", as_of_date)

    shadow = load_shadow_portfolio(as_of_date)
    real = load_real_positions()
    factor_scores = load_factor_scores(as_of_date)

    logger.info("Shadow Positionen: %s", len(shadow))
    logger.info("Reale offene Positionen: %s", len(real))

    missing_positions = max(0, int(settings.portfolio_size) - len(real))
    effective_max_trades = max(int(settings.max_trades_per_month), missing_positions)
    logger.info(
        "Effektives Positionswechsel-Limit: %s = max(max_trades_per_month=%s, fehlende_positionen=%s)",
        effective_max_trades,
        settings.max_trades_per_month,
        missing_positions,
    )

    suggestions = build_rebalance(shadow, real, factor_scores, as_of_date, settings)

    logger.info("Rebalance-Vorschläge: %s", len(suggestions))
    if not suggestions.empty:
        logger.info("\n%s", suggestions[["ticker", "action", "reason", "source_rank", "holding_days", "min_hold_ok"]].to_string(index=False))

    with engine.begin() as conn:
        save_settings_snapshot(as_of_date, settings, conn=conn)
        save_suggestions(suggestions, conn)
        save_decision_log(suggestions, factor_scores, settings, conn)

    logger.info("Settings-Snapshot gespeichert für %s", as_of_date)
    logger.info("Rebalance-Snapshot und Decision Log unveränderlich eingefroren für %s", as_of_date)
    logger.info("=== BUILD REBALANCE DONE ===")


if __name__ == "__main__":
    args = parse_args()
    run(as_of_date=args.as_of_date)

