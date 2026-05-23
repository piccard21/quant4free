import argparse
import logging
from datetime import datetime, date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text

from shared.settings import (
    engine,
    load_settings,
    BENCHMARK_TICKER,
    RETURN_6M_LOOKBACK_DAYS,
)


LOOKAHEAD_LAG_DAYS = 45


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# ARGUMENTE
# --------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--as-of-date",
        dest="as_of_date",
        help="Optionaler Stichtag im Format YYYY-MM-DD. Standard: heute.",
    )
    parser.add_argument(
        "--fundamental-lag-days",
        dest="fundamental_lag_days",
        type=int,
        default=LOOKAHEAD_LAG_DAYS,
        help="Lookahead-Schutz für Fundamentals in Tagen. Standard: 45",
    )
    parser.add_argument(
        "--allow-market-cap-fallback",
        action="store_true",
        help=(
            "Wenn keine historische Market Cap <= as_of_date existiert, "
            "verwende die neueste verfügbare Market Cap als Fallback. "
            "Für strikt saubere historische Tests besser NICHT setzen."
        ),
    )
    return parser.parse_args()


# --------------------------------------------------
# HELPER
# --------------------------------------------------

def resolve_as_of_date(value: str | None) -> date:
    if value:
        return pd.to_datetime(value).date()
    return datetime.now().date()


def load_data(as_of_date: date, fundamental_cutoff: date):
    with engine.connect() as conn:
        prices = pd.read_sql(
            text("""
                SELECT ticker, date, close
                FROM daily_candles
                WHERE date <= :as_of_date
            """),
            conn,
            params={"as_of_date": as_of_date},
        )

        fundamentals = pd.read_sql(
            text("""
                SELECT
                    ticker,
                    report_date,
                    report_type,
                    revenue,
                    net_income,
                    ebit,
                    free_cash_flow,
                    total_debt,
                    total_equity,
                    cash_and_equivalents,
                    imported_at
                FROM financial_reports
                WHERE report_type = 'ttm'
                  AND report_date <= :fundamental_cutoff
            """),
            conn,
            params={"fundamental_cutoff": fundamental_cutoff},
        )

        market_caps = pd.read_sql(
            text("""
                SELECT ticker, date, market_cap, imported_at
                FROM market_cap_snapshots
            """),
            conn,
        )

        tickers = pd.read_sql(
            text("""
                SELECT ticker, sector
                FROM tickers
                WHERE is_active = 1
            """),
            conn,
        )

    if not prices.empty:
        prices["date"] = pd.to_datetime(prices["date"])

    if not fundamentals.empty:
        fundamentals["report_date"] = pd.to_datetime(fundamentals["report_date"])

    if not market_caps.empty:
        market_caps["date"] = pd.to_datetime(market_caps["date"])

    return prices, fundamentals, market_caps, tickers


# --------------------------------------------------
# PRICE METRICS
# --------------------------------------------------

def compute_price_metrics(prices: pd.DataFrame, settings) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(
            columns=[
                "ticker",
                "price_date",
                "current_price",
                "sma_200",
                "return_12m",
                "return_6m",
                "rel_strength_12m",
            ]
        )

    prices = prices.copy()
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices = prices.dropna(subset=["ticker", "date", "close"]).copy()
    prices = prices.sort_values(["ticker", "date"])

    sma_days = int(settings.sma_days)
    lookback_12m = int(settings.return_lookback_days)

    prices["sma_200"] = prices.groupby("ticker")["close"].transform(
        lambda x: x.rolling(sma_days, min_periods=sma_days).mean()
    )

    prices["return_12m"] = prices.groupby("ticker")["close"].transform(
        lambda x: x / x.shift(lookback_12m) - 1
    )

    prices["return_6m"] = prices.groupby("ticker")["close"].transform(
        lambda x: x / x.shift(RETURN_6M_LOOKBACK_DAYS) - 1
    )

    latest = prices.groupby("ticker").tail(1).copy()

    benchmark_row = latest[latest["ticker"] == BENCHMARK_TICKER].copy()
    benchmark_return_12m = np.nan
    if not benchmark_row.empty:
        benchmark_return_12m = pd.to_numeric(
            benchmark_row["return_12m"].iloc[0],
            errors="coerce",
        )

    latest["rel_strength_12m"] = latest["return_12m"] - benchmark_return_12m

    latest = latest.rename(
        columns={
            "date": "price_date",
            "close": "current_price",
        }
    )

    return latest[
        [
            "ticker",
            "price_date",
            "current_price",
            "sma_200",
            "return_12m",
            "return_6m",
            "rel_strength_12m",
        ]
    ].copy()


# --------------------------------------------------
# FUNDAMENTALS
# --------------------------------------------------

def compute_fundamentals_latest(fundamentals: pd.DataFrame) -> pd.DataFrame:
    if fundamentals.empty:
        return pd.DataFrame(
            columns=[
                "ticker",
                "report_date",
                "report_type",
                "revenue",
                "net_income",
                "ebit",
                "free_cash_flow",
                "total_debt",
                "total_equity",
                "cash_and_equivalents",
                "imported_at",
            ]
        )

    df = fundamentals.copy()
    df = df.sort_values(["ticker", "report_date"])
    latest = df.groupby("ticker").tail(1).copy()
    return latest


def compute_revenue_growth(fundamentals: pd.DataFrame) -> pd.DataFrame:
    if fundamentals.empty:
        return pd.DataFrame(columns=["ticker", "revenue_growth"])

    df = fundamentals.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")

    results = []

    for ticker, group in df.groupby("ticker"):
        group = group.sort_values("report_date").copy()

        if len(group) < 2:
            results.append({"ticker": ticker, "revenue_growth": np.nan})
            continue

        latest = group.iloc[-1]
        target_date = latest["report_date"] - pd.Timedelta(days=365)

        historical = group[group["report_date"] <= target_date].copy()

        if historical.empty:
            results.append({"ticker": ticker, "revenue_growth": np.nan})
            continue

        previous = historical.iloc[-1]

        latest_revenue = latest["revenue"]
        previous_revenue = previous["revenue"]

        if pd.isna(latest_revenue) or pd.isna(previous_revenue) or previous_revenue <= 0:
            growth = np.nan
        else:
            growth = (latest_revenue / previous_revenue) - 1

        results.append({"ticker": ticker, "revenue_growth": growth})

    return pd.DataFrame(results)


# --------------------------------------------------
# MARKET CAP
# --------------------------------------------------

def compute_market_cap_latest(
    market_caps: pd.DataFrame,
    as_of_date: date,
    allow_fallback: bool = False,
) -> tuple[pd.DataFrame, int, int]:
    if market_caps.empty:
        return (
            pd.DataFrame(columns=["ticker", "market_cap_date", "market_cap"]),
            0,
            0,
        )

    df = market_caps.copy()
    df["market_cap"] = pd.to_numeric(df["market_cap"], errors="coerce")
    df = df.dropna(subset=["ticker", "date", "market_cap"]).copy()

    historical = df[df["date"] <= pd.Timestamp(as_of_date)].copy()
    historical_latest = (
        historical.sort_values(["ticker", "date"])
        .groupby("ticker")
        .tail(1)
        .copy()
    )
    historical_latest = historical_latest.rename(columns={"date": "market_cap_date"})

    historical_count = len(historical_latest)

    if not allow_fallback:
        return historical_latest[["ticker", "market_cap_date", "market_cap"]], historical_count, 0

    all_latest = (
        df.sort_values(["ticker", "date"])
        .groupby("ticker")
        .tail(1)
        .copy()
        .rename(columns={"date": "market_cap_date"})
    )

    missing_tickers = set(all_latest["ticker"]) - set(historical_latest["ticker"])
    fallback_df = all_latest[all_latest["ticker"].isin(missing_tickers)].copy()
    fallback_count = len(fallback_df)

    combined = pd.concat([historical_latest, fallback_df], ignore_index=True)
    combined = combined.sort_values(["ticker", "market_cap_date"]).drop_duplicates("ticker", keep="first")

    return combined[["ticker", "market_cap_date", "market_cap"]], historical_count, fallback_count


# --------------------------------------------------
# METRICS
# --------------------------------------------------

def compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    numeric_cols = [
        "current_price",
        "market_cap",
        "revenue",
        "net_income",
        "ebit",
        "free_cash_flow",
        "total_debt",
        "total_equity",
        "cash_and_equivalents",
        "sma_200",
        "return_12m",
        "return_6m",
        "rel_strength_12m",
        "revenue_growth",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["enterprise_value"] = (
        df["market_cap"]
        + df["total_debt"].fillna(0)
        - df["cash_and_equivalents"].fillna(0)
    )

    df.loc[df["enterprise_value"] <= 0, "enterprise_value"] = np.nan

    df["ev_to_ebit"] = df["enterprise_value"] / df["ebit"].replace(0, np.nan)
    df["free_cash_flow_yield"] = (
        df["free_cash_flow"] / df["enterprise_value"].replace(0, np.nan)
    )
    df["earnings_yield"] = (
        df["ebit"] / df["enterprise_value"].replace(0, np.nan)
    )

    df["roe"] = df["net_income"] / df["total_equity"].replace(0, np.nan)
    df["debt_to_equity"] = (
        df["total_debt"] / df["total_equity"].replace(0, np.nan)
    )

    return df


# --------------------------------------------------
# FILTER
# --------------------------------------------------

def apply_filters(df: pd.DataFrame, settings) -> pd.DataFrame:
    df = df.copy()

    df["is_valid"] = 1
    df["exclusion_reason"] = None

    def invalidate(mask, reason):
        open_mask = mask & (df["is_valid"] == 1)
        df.loc[open_mask, "is_valid"] = 0
        df.loc[open_mask, "exclusion_reason"] = reason

    invalidate(df["current_price"].isna(), "missing_price")
    invalidate(df["current_price"] <= settings.min_price, "price_below_min")
    invalidate(df["market_cap"].isna(), "missing_market_cap")
    invalidate(df["market_cap"] <= settings.min_market_cap, "market_cap_too_small")
    invalidate(df["ebit"].isna(), "missing_ebit")
    invalidate(df["ebit"] <= 0, "invalid_ebit")
    invalidate(df["total_equity"].isna(), "missing_equity")
    invalidate(df["total_equity"] <= 0, "invalid_equity")
    invalidate(df["sma_200"].isna(), "missing_200dma")
    invalidate(df["return_12m"].isna(), "missing_12m_return")
    invalidate(df["return_6m"].isna(), "missing_6m_return")

    return df


# --------------------------------------------------
# OUTPUT / SAVE
# --------------------------------------------------

def prepare_output(df: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    df = df.copy()

    df["as_of_date"] = as_of_date
    df["trend_positive"] = (
        (df["current_price"].notna())
        & (df["sma_200"].notna())
        & (df["current_price"] > df["sma_200"])
    ).astype(int)

    df["created_at"] = datetime.now()

    cols = [
        "as_of_date",
        "ticker",
        "sector",
        "price_date",
        "report_date",
        "market_cap_date",
        "current_price",
        "sma_200",
        "trend_positive",
        "market_cap",
        "enterprise_value",
        "ev_to_ebit",
        "free_cash_flow_yield",
        "earnings_yield",
        "roe",
        "debt_to_equity",
        "revenue_growth",
        "return_12m",
        "return_6m",
        "rel_strength_12m",
        "is_valid",
        "exclusion_reason",
        "created_at",
    ]

    for col in cols:
        if col not in df.columns:
            df[col] = np.nan

    return df[cols].copy()


def save_to_db(df: pd.DataFrame) -> None:
    if df.empty:
        logger.warning("Keine Daten zum Speichern vorhanden.")
        return

    as_of_date = df["as_of_date"].iloc[0]

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM factor_metrics WHERE as_of_date = :as_of_date"),
            {"as_of_date": as_of_date},
        )

    df.to_sql(
        "factor_metrics",
        engine,
        if_exists="append",
        index=False,
        method="multi",
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def run(
    as_of_date: date | None = None,
    fundamental_lag_days: int = LOOKAHEAD_LAG_DAYS,
    allow_market_cap_fallback: bool = False,
) -> None:
    logger.info("Starte Factor Metrics...")

    settings = load_settings()
    as_of_date = as_of_date or datetime.now().date()
    fundamental_cutoff = as_of_date - timedelta(days=fundamental_lag_days)

    logger.info("Stichtag: %s", as_of_date)
    logger.info(
        "Fundamental-Cutoff (Lookahead-Schutz, %s Tage Lag): %s",
        fundamental_lag_days,
        fundamental_cutoff,
    )

    prices, fundamentals, market_caps, tickers = load_data(
        as_of_date=as_of_date,
        fundamental_cutoff=fundamental_cutoff,
    )

    logger.info(
        "Input geladen: prices=%s | fundamentals=%s | market_caps_total=%s | tickers=%s",
        len(prices),
        len(fundamentals),
        len(market_caps),
        len(tickers),
    )

    price_metrics = compute_price_metrics(prices, settings)
    fundamentals_latest = compute_fundamentals_latest(fundamentals)
    growth = compute_revenue_growth(fundamentals)

    mcap, mcap_hist_count, mcap_fallback_count = compute_market_cap_latest(
        market_caps=market_caps,
        as_of_date=as_of_date,
        allow_fallback=allow_market_cap_fallback,
    )

    logger.info(
        "Market Cap Verwendung: historical=%s | fallback=%s | total=%s",
        mcap_hist_count,
        mcap_fallback_count,
        len(mcap),
    )

    df = tickers.merge(price_metrics, on="ticker", how="left")
    df = df.merge(mcap, on="ticker", how="left")
    df = df.merge(fundamentals_latest, on="ticker", how="left")
    df = df.merge(growth, on="ticker", how="left", suffixes=("", "_calc"))

    if "revenue_growth_calc" in df.columns:
        df["revenue_growth"] = df["revenue_growth_calc"]
        df = df.drop(columns=["revenue_growth_calc"])

    df = compute_metrics(df)
    df = apply_filters(df, settings)
    df = prepare_output(df, as_of_date)

    valid_count = int((df["is_valid"] == 1).sum())
    logger.info("Gültige Titel nach Filter: %s / %s", valid_count, len(df))

    save_to_db(df)

    logger.info("Fertig: %s Ticker gespeichert für %s", len(df), as_of_date)


if __name__ == "__main__":
    args = parse_args()
    run(
        as_of_date=resolve_as_of_date(args.as_of_date),
        fundamental_lag_days=args.fundamental_lag_days,
        allow_market_cap_fallback=args.allow_market_cap_fallback,
    )
