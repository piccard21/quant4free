from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional, Protocol, Sequence

from .models import Ticker
from .repository import RawDataRepository

if TYPE_CHECKING:
    import pandas as pd


class DataProvider(Protocol):
    """Contract for read-only market and fundamental data access.

    DataFrame results use the database column names from the raw data tables.
    Implementations must not mutate portfolio, run, or live-trading state.
    """

    key: str

    def list_tickers(self, active_only: bool = False) -> list[Ticker]:
        """Return known tickers, optionally restricted to active universe members."""
        ...

    def load_prices(
        self,
        tickers: Optional[Sequence[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Return OHLCV rows with ticker, date, open, high, low, close, volume."""
        ...

    def load_fundamentals(
        self,
        tickers: Optional[Sequence[str]] = None,
        report_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Return financial report rows for the requested ticker/date range."""
        ...

    def load_market_caps(
        self,
        tickers: Optional[Sequence[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Return market-cap snapshot rows for the requested ticker/date range."""
        ...

    def load_benchmark_prices(
        self,
        benchmark_ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Return benchmark OHLCV rows using the same schema as load_prices."""
        ...


class FixtureDataProvider:
    """DataProvider backed by the legacy-compatible MySQL fixture schema."""

    key = "mysql_fixture"

    def __init__(self, repository: Optional[RawDataRepository] = None) -> None:
        self.repository = repository or RawDataRepository()

    def list_tickers(self, active_only: bool = False) -> list[Ticker]:
        return self.repository.list_tickers(active_only=active_only)

    def load_prices(
        self,
        tickers: Optional[Sequence[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        return self.repository.load_daily_candles(tickers, start_date, end_date)

    def load_fundamentals(
        self,
        tickers: Optional[Sequence[str]] = None,
        report_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        return self.repository.load_financial_reports(
            tickers,
            report_type,
            start_date,
            end_date,
        )

    def load_market_caps(
        self,
        tickers: Optional[Sequence[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        return self.repository.load_market_caps(tickers, start_date, end_date)

    def load_benchmark_prices(
        self,
        benchmark_ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        if not benchmark_ticker:
            raise ValueError("benchmark_ticker must not be empty")
        return self.load_prices([benchmark_ticker], start_date, end_date)
