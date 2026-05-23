import argparse
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import text

from shared.settings import engine, load_settings

MODEL_SNAPSHOT_TYPE = "model"
SHADOW_SNAPSHOT_TYPE = "shadow"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--as-of-date",
        dest="as_of_date",
        help="Optionaler Stichtag im Format YYYY-MM-DD. Standard: MAX(as_of_date) aus portfolio_snapshots model",
    )
    return parser.parse_args()


def get_latest_model_date():
    with engine.connect() as conn:
        as_of_date = conn.execute(text("""
            SELECT MAX(as_of_date)
            FROM portfolio_snapshots
            WHERE snapshot_type = 'model'
        """)).scalar()
    if as_of_date is None:
        raise ValueError("Keine Model Portfolio Snapshots gefunden.")
    return as_of_date


def resolve_as_of_date(cli_value):
    return cli_value if cli_value else get_latest_model_date()


def assert_shadow_snapshot_is_new(as_of_date):
    with engine.connect() as conn:
        exists = conn.execute(text("""
            SELECT 1
            FROM portfolio_snapshots
            WHERE as_of_date = :d AND snapshot_type = 'shadow'
            LIMIT 1
        """), {"d": as_of_date}).scalar()
    if exists is not None:
        raise ValueError(f"Für den Stichtag {as_of_date} existiert bereits ein Tradable-Shadow-Snapshot.")


def load_portfolio(as_of_date, snapshot_type):
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT
                as_of_date, ticker, portfolio_rank, source_rank, sector, target_weight,
                final_score, value_score, quality_score, momentum_score,
                trend_positive, buy_eligible, holding_start_date
            FROM portfolio_snapshots
            WHERE as_of_date = :d AND snapshot_type = :t
            ORDER BY portfolio_rank, ticker
        """), conn, params={"d": as_of_date, "t": snapshot_type})
    if not df.empty and "holding_start_date" in df.columns:
        df["holding_start_date"] = pd.to_datetime(df["holding_start_date"])
    return df


def load_model(as_of_date):
    # Model-Snapshots haben bei alten Schemas ggf. noch keine holding_start_date-Spalte.
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT
                as_of_date, ticker, portfolio_rank, source_rank, sector, target_weight,
                final_score, value_score, quality_score, momentum_score,
                trend_positive, buy_eligible
            FROM portfolio_snapshots
            WHERE as_of_date = :d AND snapshot_type = 'model'
            ORDER BY portfolio_rank, ticker
        """), conn, params={"d": as_of_date})
    return df


def get_previous_shadow_date(as_of_date):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT MAX(as_of_date)
            FROM portfolio_snapshots
            WHERE snapshot_type = 'shadow' AND as_of_date < :d
        """), {"d": as_of_date}).scalar()


def load_previous_shadow(as_of_date):
    previous_date = get_previous_shadow_date(as_of_date)
    if previous_date is None:
        return pd.DataFrame(), None
    return load_portfolio(previous_date, SHADOW_SNAPSHOT_TYPE), previous_date

def load_factor_scores(as_of_date):
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT
                as_of_date,
                ticker,
                final_rank AS source_rank,
                sector,
                final_score,
                value_score,
                quality_score,
                momentum_score,
                trend_positive,
                buy_eligible
            FROM factor_scores
            WHERE as_of_date = :d
        """), conn, params={"d": as_of_date})
    return df

def build_tradable_shadow(model, previous, scores, as_of_date, settings):
    if model.empty and previous.empty:
        return pd.DataFrame()

    as_of_ts = pd.to_datetime(as_of_date)
    min_hold_days = int(settings.min_holding_months * 30)

    # Turnover-Control für den Tradable Shadow.
    #
    # Der Tradable Shadow ist die regelkonforme Modellumsetzung. Deshalb muss
    # er dieselbe Grundidee wie Rebalance/Status verwenden:
    #
    #   effektives Limit = max(max_trades_per_month, fehlende Positionen)
    #
    # So bleibt die normale Turnover-Bremse aktiv, sobald das Portfolio voll ist.
    # Gleichzeitig kann ein zu kleines Shadow Portfolio kontrolliert bis zur
    # Zielgröße aufgefüllt werden. Das ist wichtig nach Änderungen von
    # portfolio_size, z. B. von 5 auf 10 Positionen.
    configured_max_changes = int(settings.max_trades_per_month)
    portfolio_size = int(settings.portfolio_size)
    previous_position_count = int(len(previous))
    missing_positions = max(0, portfolio_size - previous_position_count)
    max_changes = max(configured_max_changes, missing_positions)

    logger.info(
        "Tradable Shadow effektives Positionswechsel-Limit: %s = max(max_trades_per_month=%s, fehlende_positionen=%s)",
        max_changes,
        configured_max_changes,
        missing_positions,
    )

    model_tickers = set(model["ticker"].tolist()) if not model.empty else set()
    previous_tickers = set(previous["ticker"].tolist()) if not previous.empty else set()

    keep = set()
    sell_candidates = []

    for _, row in previous.iterrows():
        ticker = row["ticker"]
        holding_start = row.get("holding_start_date")
        if pd.isna(holding_start):
            holding_start = row["as_of_date"]
        holding_days = int((as_of_ts - pd.to_datetime(holding_start)).days)

        if ticker in model_tickers or holding_days < min_hold_days:
            keep.add(ticker)
        else:
            sell_candidates.append(ticker)

    buy_candidates = [
        row["ticker"]
        for _, row in model.sort_values(["portfolio_rank", "ticker"]).iterrows()
        if row["ticker"] not in previous_tickers
    ]

    used_changes = 0
    executed_sells = set()
    for ticker in sell_candidates:
        if used_changes >= max_changes:
            keep.add(ticker)
            continue
        executed_sells.add(ticker)
        used_changes += 1

    current = (previous_tickers - executed_sells) | keep

    # Harte Resize-Regel:
    # Wenn portfolio_size reduziert wurde, muss der Tradable Shadow
    # auf die neue Zielgröße schrumpfen.
    #
    # Das ist keine normale Faktorrotation, sondern eine bewusste
    # Strategie-/Kapitalentscheidung. Deshalb darf die Mindesthaltedauer
    # den Shadow-Resize nicht blockieren.
    if len(current) > portfolio_size:
        rank_map = {}

        if not scores.empty:
            for _, row in scores.iterrows():
                ticker = row["ticker"]
                rank = row.get("source_rank")
                rank_map[ticker] = int(rank) if pd.notna(rank) else 999999

        def shrink_sort_key(ticker):
            in_model = ticker in model_tickers
            rank = rank_map.get(ticker, 999999)
            return (
                0 if in_model else 1,
                rank,
                ticker,
            )

        ordered = sorted(current, key=shrink_sort_key)
        current = set(ordered[:portfolio_size])

    for ticker in buy_candidates:
        if used_changes >= max_changes:
            continue
        if len(current) >= int(settings.portfolio_size):
            continue
        current.add(ticker)
        used_changes += 1

    previous_map = previous.set_index("ticker").to_dict(orient="index") if not previous.empty else {}
    model_map = model.set_index("ticker").to_dict(orient="index") if not model.empty else {}
    score_map = scores.set_index("ticker").to_dict(orient="index") if not scores.empty else {}

    ordered_model = [t for t in model["ticker"].tolist() if t in current]
    ordered_other = sorted([t for t in current if t not in set(ordered_model)])

    rows = []

    for ticker in ordered_model + ordered_other:
        # Basis-Daten vom Score / Model / Previous
        if ticker in score_map:
            base = dict(score_map[ticker])
        elif ticker in model_map:
            base = dict(model_map[ticker])
        else:
            base = dict(previous_map[ticker])
    
        # Sector sauber setzen
        if "sector" not in base or pd.isna(base.get("sector")):
            if ticker in score_map and pd.notna(score_map[ticker].get("sector")):
                base["sector"] = score_map[ticker]["sector"]
            elif ticker in model_map and pd.notna(model_map[ticker].get("sector")):
                base["sector"] = model_map[ticker]["sector"]
            elif ticker in previous_map and pd.notna(previous_map[ticker].get("sector")):
                base["sector"] = previous_map[ticker]["sector"]
            else:
                base["sector"] = None  # falls kein Wert verfügbar
    
        # Holding Start setzen
        if ticker in previous_map:
            holding_start = previous_map[ticker].get("holding_start_date")
            if pd.isna(holding_start):
                holding_start = previous_map[ticker].get("as_of_date")
        else:
            holding_start = as_of_ts.date()
    
        base["ticker"] = ticker
        base["holding_start_date"] = pd.to_datetime(holding_start).date()
    
        rows.append(base)

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result = result.reset_index(drop=True)
    result["portfolio_rank"] = range(1, len(result) + 1)
    result["target_weight"] = 1.0 / len(result)
    return result


def save(df):
    if df.empty:
        logger.warning("Kein Tradable Shadow Portfolio zu speichern.")
        return
    df = df.copy()
    df["snapshot_type"] = SHADOW_SNAPSHOT_TYPE
    df["created_at"] = datetime.now()
    df = df.astype(object).where(pd.notnull(df), None)

    cols = [
        "as_of_date", "snapshot_type", "ticker", "portfolio_rank", "source_rank", "sector",
        "target_weight", "final_score", "value_score", "quality_score", "momentum_score",
        "trend_positive", "buy_eligible", "holding_start_date", "created_at",
    ]
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO portfolio_snapshots (
                as_of_date, snapshot_type, ticker, portfolio_rank, source_rank, sector,
                target_weight, final_score, value_score, quality_score, momentum_score,
                trend_positive, buy_eligible, holding_start_date, created_at
            ) VALUES (
                :as_of_date, :snapshot_type, :ticker, :portfolio_rank, :source_rank, :sector,
                :target_weight, :final_score, :value_score, :quality_score, :momentum_score,
                :trend_positive, :buy_eligible, :holding_start_date, :created_at
            )
        """), df[cols].to_dict(orient="records"))


def run(as_of_date=None):
    logger.info("=== BUILD TRADABLE SHADOW START ===")
    settings = load_settings()
    as_of_date = resolve_as_of_date(as_of_date)
    assert_shadow_snapshot_is_new(as_of_date)

    model = load_model(as_of_date)
    previous, previous_date = load_previous_shadow(as_of_date)
    logger.info("Stichtag: %s", as_of_date)
    logger.info("Model Positionen: %s", len(model))
    logger.info("Vorheriger Tradable Shadow: %s (%s Positionen)", previous_date or "-", len(previous))

    scores = load_factor_scores(as_of_date)
    shadow = build_tradable_shadow(model, previous, scores, as_of_date, settings)
    logger.info("Tradable Shadow Positionen: %s", len(shadow))
    if not shadow.empty:
        logger.info("\n%s", shadow[["portfolio_rank", "ticker", "sector", "source_rank", "holding_start_date"]].to_string(index=False))
    save(shadow)
    logger.info("=== BUILD TRADABLE SHADOW DONE ===")


if __name__ == "__main__":
    args = parse_args()
    run(as_of_date=args.as_of_date)


