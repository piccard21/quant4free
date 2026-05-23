import logging
import time
import warnings
import argparse
from datetime import datetime

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from shared.settings import engine, load_settings


# --------------------------------------------------
# WARNINGS
# --------------------------------------------------

warnings.simplefilter(action="ignore", category=FutureWarning)


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# ARGUMENTE
# --------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["init", "daily"],
        default="daily",
        help="init = vollständiger Erstimport aller aktiven Ticker, daily = rollierendes Update",
    )
    return parser.parse_args()


# --------------------------------------------------
# HELPER
# --------------------------------------------------

def clean(val):
    try:
        if hasattr(val, "__iter__") and not isinstance(val, (str, bytes)):
            val = val[0]
        if pd.isna(val) or str(val).lower() == "nan":
            return 0
        return int(float(val))
    except Exception:
        return 0


def first_existing_column(df: pd.DataFrame, keys: list[str]):
    if df is None or df.empty:
        return None
    for key in keys:
        if key in df.columns:
            return df.get(key)
    return None


def first_existing_index_sum(df: pd.DataFrame, keys: list[str], periods: int = 4):
    if df is None or df.empty:
        return 0
    for key in keys:
        if key in df.index:
            try:
                return clean(df.loc[key].iloc[:periods].sum())
            except Exception:
                continue
    return 0


def first_existing_index_value(df: pd.DataFrame, keys: list[str]):
    if df is None or df.empty:
        return 0
    for key in keys:
        if key in df.index:
            try:
                return clean(df.loc[key].iloc[0])
            except Exception:
                continue
    return 0


def save_to_db(data):
    with engine.begin() as conn:
        stmt = text("""
            INSERT INTO financial_reports
            (
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
                source,
                imported_at
            )
            VALUES
            (
                :ticker,
                :report_date,
                :report_type,
                :revenue,
                :net_income,
                :ebit,
                :free_cash_flow,
                :total_debt,
                :total_equity,
                :cash_and_equivalents,
                :source,
                :imported_at
            )
            ON DUPLICATE KEY UPDATE
                revenue = VALUES(revenue),
                net_income = VALUES(net_income),
                ebit = VALUES(ebit),
                report_type = VALUES(report_type),
                free_cash_flow = VALUES(free_cash_flow),
                total_debt = VALUES(total_debt),
                total_equity = VALUES(total_equity),
                cash_and_equivalents = VALUES(cash_and_equivalents),
                imported_at = VALUES(imported_at)
        """)
        conn.execute(stmt, data)


def save_market_cap(ticker, mcap):
    with engine.begin() as conn:
        stmt = text("""
            INSERT INTO market_cap_snapshots (ticker, date, market_cap, imported_at)
            VALUES (:ticker, :date, :market_cap, :imported_at)
            ON DUPLICATE KEY UPDATE
                market_cap = VALUES(market_cap),
                imported_at = VALUES(imported_at)
        """)
        conn.execute(stmt, {
            "ticker": ticker,
            "date": datetime.now().date(),
            "market_cap": int(mcap),
            "imported_at": datetime.now(),
        })


# --------------------------------------------------
# CORE
# --------------------------------------------------

def update_ticker_fundamentals(ticker_symbol):
    stock = yf.Ticker(ticker_symbol)
    now = datetime.now()

    try:
        # ---------------------------
        # ANNUAL
        # ---------------------------
        df_inc = stock.financials.T
        df_bal = stock.balance_sheet.T
        df_cf = stock.cashflow.T

        if not df_inc.empty and not df_bal.empty:
            latest_annual_date = df_inc.index[0]

            annual_ebit = first_existing_column(
                df_inc,
                ["EBIT", "Operating Income", "Pretax Income", "Net Income"],
            )

            annual_revenue = first_existing_column(
                df_inc,
                ["Total Revenue", "Operating Revenue"],
            )

            annual_equity = first_existing_column(
                df_bal,
                ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
            )

            annual_debt = first_existing_column(
                df_bal,
                ["Total Debt", "Net Debt"],
            )

            annual_cash = first_existing_column(
                df_bal,
                ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
            )

            save_to_db({
                "ticker": ticker_symbol,
                "report_date": latest_annual_date.date(),
                "report_type": "annual",
                "revenue": clean(annual_revenue),
                "net_income": clean(df_inc.get("Net Income")),
                "ebit": clean(annual_ebit),
                "free_cash_flow": clean(df_cf.get("Free Cash Flow")),
                "total_debt": clean(annual_debt),
                "total_equity": clean(annual_equity),
                "cash_and_equivalents": clean(annual_cash),
                "source": "Yahoo-Annual",
                "imported_at": now,
            })

        # ---------------------------
        # TTM
        # ---------------------------
        q_inc = stock.quarterly_financials
        q_bal = stock.quarterly_balance_sheet
        q_cf = stock.quarterly_cashflow

        if not q_inc.empty and q_inc.shape[1] >= 4:
            latest_q_date = q_inc.columns[0].date()

            ttm_ebit = first_existing_index_sum(
                q_inc,
                ["EBIT", "Operating Income", "Pretax Income", "Net Income"],
            )

            ttm_revenue = first_existing_index_sum(
                q_inc,
                ["Total Revenue", "Operating Revenue"],
            )

            ttm_net_income = first_existing_index_sum(
                q_inc,
                ["Net Income"],
            )

            ttm_fcf = first_existing_index_sum(
                q_cf,
                ["Free Cash Flow"],
            )

            ttm_debt = first_existing_index_value(
                q_bal,
                ["Total Debt", "Net Debt"],
            )

            ttm_equity = first_existing_index_value(
                q_bal,
                ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
            )

            ttm_cash = first_existing_index_value(
                q_bal,
                ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
            )

            save_to_db({
                "ticker": ticker_symbol,
                "report_date": latest_q_date,
                "report_type": "ttm",
                "revenue": ttm_revenue,
                "net_income": ttm_net_income,
                "ebit": ttm_ebit,
                "free_cash_flow": ttm_fcf,
                "total_debt": ttm_debt,
                "total_equity": ttm_equity,
                "cash_and_equivalents": ttm_cash,
                "source": "Yahoo-TTM",
                "imported_at": now,
            })

        # ---------------------------
        # MARKET CAP
        # ---------------------------
        info = stock.info
        mcap = info.get("marketCap")
        if mcap:
            save_market_cap(ticker_symbol, mcap)

        return True

    except Exception as e:
        logger.error("Fehler bei %s: %s", ticker_symbol, e)
        return False


# --------------------------------------------------
# TICKER AUSWAHL (DB-SETTINGS)
# --------------------------------------------------

def get_tickers_for_sync(mode, settings):
    with engine.connect() as conn:
        if mode == "init":
            query = text("""
                SELECT ticker
                FROM tickers
                WHERE is_active = 1
                ORDER BY ticker
            """)
            return conn.execute(query).scalars().all()

        query = text("""
            SELECT ticker
            FROM tickers
            WHERE is_active = 1
              AND (
                  last_fundamental_update IS NULL
                  OR last_fundamental_update < DATE_SUB(NOW(), INTERVAL :hours HOUR)
              )
            ORDER BY last_fundamental_update ASC
            LIMIT :limit
        """)

        return conn.execute(query, {
            "hours": settings.fundamental_refresh_hours,
            "limit": settings.daily_fundamental_limit,
        }).scalars().all()


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def run_fundamental_sync(mode="daily"):
    settings = load_settings()

    logger.info("Starte Fundamental-Sync im Modus: %s", mode.upper())
    logger.info(
        "Settings: limit=%s | refresh_hours=%s",
        settings.daily_fundamental_limit,
        settings.fundamental_refresh_hours,
    )

    tickers = get_tickers_for_sync(mode, settings)

    if not tickers:
        logger.info("Keine Ticker zu aktualisieren.")
        return

    logger.info("Zu verarbeitende Ticker: %s", len(tickers))

    for i, ticker in enumerate(tickers, start=1):
        logger.info("Verarbeite %s (%s/%s)...", ticker, i, len(tickers))

        if update_ticker_fundamentals(ticker):
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE tickers SET last_fundamental_update = NOW() WHERE ticker = :t"),
                    {"t": ticker},
                )

        time.sleep(2)


if __name__ == "__main__":
    args = parse_args()
    run_fundamental_sync(mode=args.mode)
