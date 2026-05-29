from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from urllib.request import Request, urlopen

import pandas as pd

from .models import (
    DailyCandle,
    FinancialReport,
    FinancialSyncPayload,
    MarketCapSnapshot,
    TickerUpsert,
)


class WikipediaSP500TickerSource:
    """Fetch current S&P 500 constituents from Wikipedia."""

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    def list_tickers(self) -> list[TickerUpsert]:
        request = Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8")

        tables = pd.read_html(io.StringIO(html))
        if not tables:
            return []

        frame = tables[0][["Symbol", "Security", "GICS Sector"]].copy()
        frame.columns = ["ticker", "name", "sector"]
        frame["ticker"] = frame["ticker"].str.replace(".", "-", regex=False)
        return [
            TickerUpsert(
                ticker=str(row.ticker),
                name=str(row.name),
                sector=str(row.sector),
                is_active=True,
            )
            for row in frame.itertuples(index=False)
        ]


class YFinancePriceSource:
    """Download daily candles from yfinance."""

    def download_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        import yfinance as yf

        return yf.download(
            ticker,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
        )


class YFinanceFundamentalSource:
    """Read annual, TTM, and market-cap data from yfinance."""

    def load_fundamentals(
        self,
        ticker: str,
        imported_at: Optional[datetime] = None,
    ) -> FinancialSyncPayload:
        import yfinance as yf

        imported_at = imported_at or datetime.now()
        stock = yf.Ticker(ticker)
        reports: list[FinancialReport] = []

        annual = annual_report_from_yfinance(
            ticker=ticker,
            income=stock.financials.T,
            balance=stock.balance_sheet.T,
            cashflow=stock.cashflow.T,
            imported_at=imported_at,
        )
        if annual is not None:
            reports.append(annual)

        ttm = ttm_report_from_yfinance(
            ticker=ticker,
            quarterly_income=stock.quarterly_financials,
            quarterly_balance=stock.quarterly_balance_sheet,
            quarterly_cashflow=stock.quarterly_cashflow,
            imported_at=imported_at,
        )
        if ttm is not None:
            reports.append(ttm)

        market_cap = None
        value = stock.info.get("marketCap")
        if value:
            market_cap = MarketCapSnapshot(
                ticker=ticker,
                date=imported_at.date(),
                market_cap=int(value),
                imported_at=imported_at,
            )

        return FinancialSyncPayload(reports=tuple(reports), market_cap=market_cap)


def normalize_yfinance_prices(df: pd.DataFrame, ticker: str) -> list[DailyCandle]:
    """Normalize a yfinance OHLCV frame into daily candle records."""

    if df is None or df.empty:
        return []

    frame = _select_ticker_columns(df.copy(), ticker)
    frame = frame.reset_index()
    frame.columns = [str(column).lower().replace(" ", "_") for column in frame.columns]
    if "datetime" in frame.columns and "date" not in frame.columns:
        frame = frame.rename(columns={"datetime": "date"})
    if "adj_close" in frame.columns:
        frame = frame.drop(columns=["adj_close"])

    expected = ["date", "open", "high", "low", "close", "volume"]
    if any(column not in frame.columns for column in expected):
        return []

    frame = frame[expected].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    for column in ["open", "high", "low", "close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"])

    candles = []
    for row in frame.itertuples(index=False):
        candles.append(
            DailyCandle(
                ticker=ticker,
                date=row.date,
                open=_decimal_or_none(row.open),
                high=_decimal_or_none(row.high),
                low=_decimal_or_none(row.low),
                close=_decimal_or_none(row.close),
                volume=None if pd.isna(row.volume) else int(row.volume),
            )
        )
    return candles


def annual_report_from_yfinance(
    ticker: str,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cashflow: pd.DataFrame,
    imported_at: datetime,
) -> Optional[FinancialReport]:
    if income is None or income.empty or balance is None or balance.empty:
        return None

    report_date = pd.to_datetime(income.index[0]).date()
    return FinancialReport(
        ticker=ticker,
        report_date=report_date,
        report_type="annual",
        revenue=clean_number(
            first_existing_column(income, ["Total Revenue", "Operating Revenue"])
        ),
        net_income=clean_number(income.get("Net Income")),
        ebit=clean_number(
            first_existing_column(
                income,
                ["EBIT", "Operating Income", "Pretax Income", "Net Income"],
            )
        ),
        free_cash_flow=clean_number(cashflow.get("Free Cash Flow")),
        total_debt=clean_number(
            first_existing_column(balance, ["Total Debt", "Net Debt"])
        ),
        total_equity=clean_number(
            first_existing_column(
                balance,
                [
                    "Stockholders Equity",
                    "Common Stock Equity",
                    "Total Equity Gross Minority Interest",
                ],
            )
        ),
        cash_and_equivalents=clean_number(
            first_existing_column(
                balance,
                [
                    "Cash And Cash Equivalents",
                    "Cash Cash Equivalents And Short Term Investments",
                ],
            )
        ),
        source="Yahoo-Annual",
        imported_at=imported_at,
    )


def ttm_report_from_yfinance(
    ticker: str,
    quarterly_income: pd.DataFrame,
    quarterly_balance: pd.DataFrame,
    quarterly_cashflow: pd.DataFrame,
    imported_at: datetime,
) -> Optional[FinancialReport]:
    if (
        quarterly_income is None
        or quarterly_income.empty
        or quarterly_income.shape[1] < 4
    ):
        return None

    report_date = pd.to_datetime(quarterly_income.columns[0]).date()
    return FinancialReport(
        ticker=ticker,
        report_date=report_date,
        report_type="ttm",
        revenue=first_existing_index_sum(
            quarterly_income,
            ["Total Revenue", "Operating Revenue"],
        ),
        net_income=first_existing_index_sum(quarterly_income, ["Net Income"]),
        ebit=first_existing_index_sum(
            quarterly_income,
            ["EBIT", "Operating Income", "Pretax Income", "Net Income"],
        ),
        free_cash_flow=first_existing_index_sum(quarterly_cashflow, ["Free Cash Flow"]),
        total_debt=first_existing_index_value(
            quarterly_balance,
            ["Total Debt", "Net Debt"],
        ),
        total_equity=first_existing_index_value(
            quarterly_balance,
            [
                "Stockholders Equity",
                "Common Stock Equity",
                "Total Equity Gross Minority Interest",
            ],
        ),
        cash_and_equivalents=first_existing_index_value(
            quarterly_balance,
            [
                "Cash And Cash Equivalents",
                "Cash Cash Equivalents And Short Term Investments",
            ],
        ),
        source="Yahoo-TTM",
        imported_at=imported_at,
    )


def clean_number(value) -> int:
    try:
        if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
            value = value.iloc[0] if hasattr(value, "iloc") else value[0]
        if pd.isna(value) or str(value).lower() == "nan":
            return 0
        return int(float(value))
    except Exception:
        return 0


def first_existing_column(df: pd.DataFrame, keys: list[str]):
    if df is None or df.empty:
        return None
    for key in keys:
        if key in df.columns:
            return df.get(key)
    return None


def first_existing_index_sum(
    df: pd.DataFrame,
    keys: list[str],
    periods: int = 4,
) -> int:
    if df is None or df.empty:
        return 0
    for key in keys:
        if key in df.index:
            try:
                return clean_number(df.loc[key].iloc[:periods].sum())
            except Exception:
                continue
    return 0


def first_existing_index_value(df: pd.DataFrame, keys: list[str]) -> int:
    if df is None or df.empty:
        return 0
    for key in keys:
        if key in df.index:
            try:
                return clean_number(df.loc[key].iloc[0])
            except Exception:
                continue
    return 0


def _select_ticker_columns(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if not isinstance(df.columns, pd.MultiIndex):
        return df

    first_level = df.columns.get_level_values(0)
    last_level = df.columns.get_level_values(df.columns.nlevels - 1)
    if ticker in first_level:
        return df[ticker].copy()
    if ticker in last_level:
        return df.xs(ticker, axis=1, level=df.columns.nlevels - 1).copy()

    frame = df.copy()
    frame.columns = first_level
    return frame


def _decimal_or_none(value) -> Optional[Decimal]:
    if pd.isna(value):
        return None
    return Decimal(str(value))
