from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional, Sequence

from sqlalchemy import Engine, bindparam, text

from shared.db import get_engine

from .models import (
    DailyCandle,
    FinancialReport,
    MarketCapSnapshot,
    Ticker,
    TickerUpsert,
)

if TYPE_CHECKING:
    import pandas as pd


class RawDataRepository:
    """Access to canonical raw market data tables."""

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
            FROM assets
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
            FROM assets
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
            FROM asset_price_bars
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
            FROM asset_price_bars dc
            JOIN (
                SELECT ticker, MAX(date) AS max_date
                FROM asset_price_bars
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
            FROM asset_fundamental_reports
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
            FROM asset_fundamental_reports fr
            JOIN (
                SELECT ticker, report_type, MAX(report_date) AS max_report_date
                FROM asset_fundamental_reports
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
            FROM asset_market_caps
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
            FROM asset_market_caps mcs
            JOIN (
                SELECT ticker, MAX(date) AS max_date
                FROM asset_market_caps
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

    def latest_candle_date(self, ticker: str) -> Optional[date]:
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT MAX(date) FROM asset_price_bars WHERE ticker = :ticker"),
                {"ticker": ticker},
            ).scalar_one()

    def upsert_tickers(
        self,
        tickers: Sequence[TickerUpsert],
        sync_time: Optional[datetime] = None,
    ) -> int:
        if not tickers:
            return 0
        sync_time = sync_time or datetime.now()
        rows = [
            {
                "ticker": item.ticker,
                "name": item.name,
                "sector": item.sector,
                "is_active": 1 if item.is_active else 0,
                "sync_time": sync_time,
            }
            for item in tickers
        ]
        dialect = self.engine.dialect.name
        if dialect == "sqlite":
            statement = text(
                """
                INSERT INTO assets
                    (ticker, name, sector, is_active, first_seen, last_seen, removed_at)
                VALUES
                    (:ticker, :name, :sector, :is_active, :sync_time, :sync_time, NULL)
                ON CONFLICT(ticker) DO UPDATE SET
                    name = excluded.name,
                    sector = excluded.sector,
                    is_active = excluded.is_active,
                    last_seen = excluded.last_seen,
                    removed_at = NULL
                """
            )
        else:
            statement = text(
                """
                INSERT INTO assets
                    (ticker, name, sector, is_active, first_seen, last_seen, removed_at)
                VALUES
                    (:ticker, :name, :sector, :is_active, :sync_time, :sync_time, NULL)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    sector = VALUES(sector),
                    is_active = VALUES(is_active),
                    last_seen = VALUES(last_seen),
                    removed_at = NULL
                """
            )
        with self.engine.begin() as connection:
            connection.execute(statement, rows)
        return len(rows)

    def deactivate_missing_active_tickers(
        self,
        current_tickers: Sequence[str],
        sync_time: Optional[datetime] = None,
    ) -> int:
        if not current_tickers:
            return 0
        sync_time = sync_time or datetime.now()
        statement = text(
            """
            UPDATE assets
            SET is_active = 0, removed_at = :sync_time
            WHERE is_active = 1 AND ticker NOT IN :tickers
            """
        ).bindparams(bindparam("tickers", expanding=True))
        with self.engine.begin() as connection:
            result = connection.execute(
                statement,
                {"tickers": list(current_tickers), "sync_time": sync_time},
            )
        return int(result.rowcount or 0)

    def ensure_ticker(
        self,
        ticker: str,
        name: str,
        sector: Optional[str],
        is_active: bool,
        sync_time: Optional[datetime] = None,
    ) -> None:
        self.upsert_tickers(
            [
                TickerUpsert(
                    ticker=ticker,
                    name=name,
                    sector=sector,
                    is_active=is_active,
                )
            ],
            sync_time=sync_time,
        )

    def upsert_daily_candles(self, candles: Sequence[DailyCandle]) -> int:
        if not candles:
            return 0
        rows = [
            {
                "ticker": candle.ticker,
                "date": candle.date,
                "open": _db_decimal(candle.open),
                "high": _db_decimal(candle.high),
                "low": _db_decimal(candle.low),
                "close": _db_decimal(candle.close),
                "volume": candle.volume,
            }
            for candle in candles
        ]
        dialect = self.engine.dialect.name
        if dialect == "sqlite":
            statement = text(
                """
                INSERT INTO asset_price_bars
                    (ticker, date, open, high, low, close, volume)
                VALUES
                    (:ticker, :date, :open, :high, :low, :close, :volume)
                ON CONFLICT(ticker, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume
                """
            )
        else:
            statement = text(
                """
                INSERT INTO asset_price_bars
                    (ticker, date, open, high, low, close, volume)
                VALUES
                    (:ticker, :date, :open, :high, :low, :close, :volume)
                ON DUPLICATE KEY UPDATE
                    open = VALUES(open),
                    high = VALUES(high),
                    low = VALUES(low),
                    close = VALUES(close),
                    volume = VALUES(volume)
                """
            )
        with self.engine.begin() as connection:
            connection.execute(statement, rows)
        return len(rows)

    def select_tickers_for_fundamental_sync(
        self,
        mode: str,
        refresh_hours: int,
        limit: int,
        now: Optional[datetime] = None,
    ) -> list[str]:
        if mode == "init":
            return [ticker.ticker for ticker in self.list_tickers(active_only=True)]

        threshold = (now or datetime.now()) - timedelta(hours=refresh_hours)
        rows = self._mappings(
            """
            SELECT ticker
            FROM assets
            WHERE is_active = 1
              AND (
                  last_fundamental_update IS NULL
                  OR last_fundamental_update < :threshold
              )
            ORDER BY last_fundamental_update ASC
            LIMIT :limit
            """,
            {"threshold": threshold, "limit": limit},
        )
        return [row["ticker"] for row in rows]

    def upsert_financial_reports(self, reports: Sequence[FinancialReport]) -> int:
        if not reports:
            return 0
        rows = [
            {
                "ticker": report.ticker,
                "report_date": report.report_date,
                "report_type": report.report_type,
                "revenue": report.revenue,
                "net_income": report.net_income,
                "ebit": report.ebit,
                "free_cash_flow": report.free_cash_flow,
                "total_debt": report.total_debt,
                "total_equity": report.total_equity,
                "cash_and_equivalents": report.cash_and_equivalents,
                "source": report.source,
                "imported_at": report.imported_at,
            }
            for report in reports
        ]
        dialect = self.engine.dialect.name
        if dialect == "sqlite":
            statement = text(
                """
                INSERT INTO asset_fundamental_reports
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
                ON CONFLICT(ticker, report_date, report_type) DO UPDATE SET
                    revenue = excluded.revenue,
                    net_income = excluded.net_income,
                    ebit = excluded.ebit,
                    free_cash_flow = excluded.free_cash_flow,
                    total_debt = excluded.total_debt,
                    total_equity = excluded.total_equity,
                    cash_and_equivalents = excluded.cash_and_equivalents,
                    source = excluded.source,
                    imported_at = excluded.imported_at
                """
            )
        else:
            statement = text(
                """
                INSERT INTO asset_fundamental_reports
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
                    free_cash_flow = VALUES(free_cash_flow),
                    total_debt = VALUES(total_debt),
                    total_equity = VALUES(total_equity),
                    cash_and_equivalents = VALUES(cash_and_equivalents),
                    source = VALUES(source),
                    imported_at = VALUES(imported_at)
                """
            )
        with self.engine.begin() as connection:
            connection.execute(statement, rows)
        return len(rows)

    def upsert_market_caps(self, snapshots: Sequence[MarketCapSnapshot]) -> int:
        if not snapshots:
            return 0
        rows = [
            {
                "ticker": snapshot.ticker,
                "date": snapshot.date,
                "market_cap": snapshot.market_cap,
                "imported_at": snapshot.imported_at,
            }
            for snapshot in snapshots
        ]
        dialect = self.engine.dialect.name
        if dialect == "sqlite":
            statement = text(
                """
                INSERT INTO asset_market_caps
                    (ticker, date, market_cap, imported_at)
                VALUES
                    (:ticker, :date, :market_cap, :imported_at)
                ON CONFLICT(ticker, date) DO UPDATE SET
                    market_cap = excluded.market_cap,
                    imported_at = excluded.imported_at
                """
            )
        else:
            statement = text(
                """
                INSERT INTO asset_market_caps
                    (ticker, date, market_cap, imported_at)
                VALUES
                    (:ticker, :date, :market_cap, :imported_at)
                ON DUPLICATE KEY UPDATE
                    market_cap = VALUES(market_cap),
                    imported_at = VALUES(imported_at)
                """
            )
        with self.engine.begin() as connection:
            connection.execute(statement, rows)
        return len(rows)

    def mark_fundamental_updated(
        self,
        ticker: str,
        updated_at: Optional[datetime] = None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE assets
                    SET last_fundamental_update = :updated_at
                    WHERE ticker = :ticker
                    """
                ),
                {
                    "ticker": ticker,
                    "updated_at": updated_at or datetime.now(),
                },
            )

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


def _db_decimal(value):
    if value is None:
        return None
    return str(value)
