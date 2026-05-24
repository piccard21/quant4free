from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Optional, Sequence

from sqlalchemy import Engine, bindparam, text

from shared.db import get_engine

from .models import DailyCandle, FinancialReport, MarketCapSnapshot, Ticker

if TYPE_CHECKING:
    import pandas as pd


class RawDataRepository:
    """Read-only access to legacy-compatible raw market data tables."""

    def __init__(self, engine: Optional[Engine] = None) -> None:
        self.engine = engine or get_engine()

    def list_tickers(self, active_only: bool = False) -> list[Ticker]:
        sql = """
            SELECT
                ticker,
                name,
                sector,
                is_active,
                first_seen,
                last_seen,
                removed_at,
                last_fundamental_update
            FROM tickers
        """
        params: dict[str, Any] = {}
        if active_only:
            sql += " WHERE is_active = :is_active"
            params["is_active"] = 1
        sql += " ORDER BY ticker"

        rows = self._mappings(sql, params)
        return [
            Ticker(
                ticker=row["ticker"],
                name=row["name"],
                sector=row["sector"],
                is_active=bool(row["is_active"]),
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                removed_at=row["removed_at"],
                last_fundamental_update=row["last_fundamental_update"],
            )
            for row in rows
        ]

    def get_ticker(self, ticker: str) -> Optional[Ticker]:
        rows = self._mappings(
            """
            SELECT
                ticker,
                name,
                sector,
                is_active,
                first_seen,
                last_seen,
                removed_at,
                last_fundamental_update
            FROM tickers
            WHERE ticker = :ticker
            LIMIT 1
            """,
            {"ticker": ticker},
        )
        if not rows:
            return None
        row = rows[0]
        return Ticker(
            ticker=row["ticker"],
            name=row["name"],
            sector=row["sector"],
            is_active=bool(row["is_active"]),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            removed_at=row["removed_at"],
            last_fundamental_update=row["last_fundamental_update"],
        )

    def load_daily_candles(
        self,
        tickers: Optional[Sequence[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        sql = """
            SELECT ticker, date, open, high, low, close, volume
            FROM daily_candles
            WHERE 1 = 1
        """
        params = self._date_params(start_date, end_date)
        sql = self._add_date_filter(sql, start_date, end_date)
        sql = self._add_ticker_filter(sql, params, tickers)
        sql += " ORDER BY ticker, date"
        return self._read_dataframe(sql, params, tickers=tickers)

    def latest_daily_candles(
        self,
        tickers: Optional[Sequence[str]] = None,
        as_of_date: Optional[date] = None,
    ) -> list[DailyCandle]:
        sql = """
            SELECT dc.ticker, dc.date, dc.open, dc.high, dc.low, dc.close, dc.volume
            FROM daily_candles dc
            JOIN (
                SELECT ticker, MAX(date) AS max_date
                FROM daily_candles
                WHERE (:as_of_date IS NULL OR date <= :as_of_date)
        """
        params: dict[str, Any] = {"as_of_date": as_of_date}
        sql = self._add_ticker_filter(sql, params, tickers)
        sql += """
                GROUP BY ticker
            ) latest
                ON latest.ticker = dc.ticker
                AND latest.max_date = dc.date
            ORDER BY dc.ticker
        """
        rows = self._mappings(sql, params, tickers=tickers)
        return [
            DailyCandle(
                ticker=row["ticker"],
                date=row["date"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
            for row in rows
        ]

    def load_financial_reports(
        self,
        tickers: Optional[Sequence[str]] = None,
        report_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        sql = """
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
                source,
                imported_at
            FROM financial_reports
            WHERE 1 = 1
        """
        params = self._date_params(start_date, end_date)
        sql = self._add_date_filter(sql, start_date, end_date, column="report_date")
        if report_type is not None:
            sql += " AND report_type = :report_type"
            params["report_type"] = report_type
        sql = self._add_ticker_filter(sql, params, tickers)
        sql += " ORDER BY ticker, report_type, report_date"
        return self._read_dataframe(sql, params, tickers=tickers)

    def latest_financial_reports(
        self,
        report_type: str = "ttm",
        tickers: Optional[Sequence[str]] = None,
        as_of_date: Optional[date] = None,
    ) -> list[FinancialReport]:
        sql = """
            SELECT
                fr.ticker,
                fr.report_date,
                fr.report_type,
                fr.revenue,
                fr.net_income,
                fr.ebit,
                fr.free_cash_flow,
                fr.total_debt,
                fr.total_equity,
                fr.cash_and_equivalents,
                fr.source,
                fr.imported_at
            FROM financial_reports fr
            JOIN (
                SELECT ticker, report_type, MAX(report_date) AS max_report_date
                FROM financial_reports
                WHERE report_type = :report_type
                  AND (:as_of_date IS NULL OR report_date <= :as_of_date)
        """
        params: dict[str, Any] = {
            "report_type": report_type,
            "as_of_date": as_of_date,
        }
        sql = self._add_ticker_filter(sql, params, tickers)
        sql += """
                GROUP BY ticker, report_type
            ) latest
                ON latest.ticker = fr.ticker
                AND latest.report_type = fr.report_type
                AND latest.max_report_date = fr.report_date
            ORDER BY fr.ticker
        """
        rows = self._mappings(sql, params, tickers=tickers)
        return [
            FinancialReport(
                ticker=row["ticker"],
                report_date=row["report_date"],
                report_type=row["report_type"],
                revenue=int(row["revenue"] or 0),
                net_income=int(row["net_income"] or 0),
                ebit=int(row["ebit"] or 0),
                free_cash_flow=int(row["free_cash_flow"] or 0),
                total_debt=int(row["total_debt"] or 0),
                total_equity=int(row["total_equity"] or 0),
                cash_and_equivalents=int(row["cash_and_equivalents"] or 0),
                source=row["source"],
                imported_at=row["imported_at"],
            )
            for row in rows
        ]

    def load_market_caps(
        self,
        tickers: Optional[Sequence[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        sql = """
            SELECT ticker, date, market_cap, imported_at
            FROM market_cap_snapshots
            WHERE 1 = 1
        """
        params = self._date_params(start_date, end_date)
        sql = self._add_date_filter(sql, start_date, end_date)
        sql = self._add_ticker_filter(sql, params, tickers)
        sql += " ORDER BY ticker, date"
        return self._read_dataframe(sql, params, tickers=tickers)

    def latest_market_caps(
        self,
        tickers: Optional[Sequence[str]] = None,
        as_of_date: Optional[date] = None,
    ) -> list[MarketCapSnapshot]:
        sql = """
            SELECT mcs.ticker, mcs.date, mcs.market_cap, mcs.imported_at
            FROM market_cap_snapshots mcs
            JOIN (
                SELECT ticker, MAX(date) AS max_date
                FROM market_cap_snapshots
                WHERE (:as_of_date IS NULL OR date <= :as_of_date)
        """
        params: dict[str, Any] = {"as_of_date": as_of_date}
        sql = self._add_ticker_filter(sql, params, tickers)
        sql += """
                GROUP BY ticker
            ) latest
                ON latest.ticker = mcs.ticker
                AND latest.max_date = mcs.date
            ORDER BY mcs.ticker
        """
        rows = self._mappings(sql, params, tickers=tickers)
        return [
            MarketCapSnapshot(
                ticker=row["ticker"],
                date=row["date"],
                market_cap=row["market_cap"],
                imported_at=row["imported_at"],
            )
            for row in rows
        ]

    def _mappings(
        self,
        sql: str,
        params: dict[str, Any],
        tickers: Optional[Sequence[str]] = None,
    ) -> list[dict[str, Any]]:
        if tickers is not None and not tickers:
            return []
        statement = self._statement(sql, tickers)
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(statement, params).mappings()
            ]

    def _read_dataframe(
        self,
        sql: str,
        params: dict[str, Any],
        tickers: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        import pandas as pd

        if tickers is not None and not tickers:
            return pd.DataFrame()
        statement = self._statement(sql, tickers)
        with self.engine.connect() as connection:
            return pd.read_sql_query(statement, connection, params=params)

    @staticmethod
    def _statement(sql: str, tickers: Optional[Sequence[str]] = None):
        statement = text(sql)
        if tickers is not None:
            statement = statement.bindparams(bindparam("tickers", expanding=True))
        return statement

    @staticmethod
    def _add_ticker_filter(
        sql: str,
        params: dict[str, Any],
        tickers: Optional[Sequence[str]],
    ) -> str:
        if tickers is None:
            return sql
        params["tickers"] = list(tickers)
        return sql + " AND ticker IN :tickers"

    @staticmethod
    def _date_params(
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date
        return params

    @staticmethod
    def _add_date_filter(
        sql: str,
        start_date: Optional[date],
        end_date: Optional[date],
        column: str = "date",
    ) -> str:
        if start_date is not None:
            sql += f" AND {column} >= :start_date"
        if end_date is not None:
            sql += f" AND {column} <= :end_date"
        return sql


def load_tickers(active_only: bool = False) -> list[Ticker]:
    return RawDataRepository().list_tickers(active_only=active_only)


def load_daily_candles(
    tickers: Optional[Sequence[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    return RawDataRepository().load_daily_candles(tickers, start_date, end_date)


def latest_daily_candles(
    tickers: Optional[Sequence[str]] = None,
    as_of_date: Optional[date] = None,
) -> list[DailyCandle]:
    return RawDataRepository().latest_daily_candles(tickers, as_of_date)


def load_financial_reports(
    tickers: Optional[Sequence[str]] = None,
    report_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    return RawDataRepository().load_financial_reports(
        tickers,
        report_type,
        start_date,
        end_date,
    )


def latest_financial_reports(
    report_type: str = "ttm",
    tickers: Optional[Sequence[str]] = None,
    as_of_date: Optional[date] = None,
) -> list[FinancialReport]:
    return RawDataRepository().latest_financial_reports(
        report_type,
        tickers,
        as_of_date,
    )


def load_market_caps(
    tickers: Optional[Sequence[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    return RawDataRepository().load_market_caps(tickers, start_date, end_date)


def latest_market_caps(
    tickers: Optional[Sequence[str]] = None,
    as_of_date: Optional[date] = None,
) -> list[MarketCapSnapshot]:
    return RawDataRepository().latest_market_caps(tickers, as_of_date)
