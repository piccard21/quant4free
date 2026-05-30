from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

import pandas as pd
from sqlalchemy import Engine, bindparam, text

from shared.db import get_engine


@dataclass(frozen=True)
class PerformanceMetrics:
    total_return: float
    benchmark_return: float
    outperformance: float
    max_drawdown: float


@dataclass(frozen=True)
class LivePerformanceReport:
    start_date: date
    end_date: date
    benchmark_ticker: str
    base_value: float
    curve: pd.DataFrame
    metrics: dict[str, PerformanceMetrics]
    diagnostics: dict[str, int]


class LivePerformanceRepository:
    """Read-only access for live performance reporting."""

    def __init__(self, engine: Optional[Engine] = None) -> None:
        self.engine = engine or get_engine()

    def latest_price_date(self, ticker: str) -> date | None:
        with self.engine.connect() as conn:
            return conn.execute(
                text("SELECT MAX(date) FROM asset_price_bars WHERE ticker = :ticker"),
                {"ticker": ticker.upper()},
            ).scalar()

    def load_shadow_targets(self, end_date: date) -> pd.DataFrame:
        return self._read_dataframe(
            """
            SELECT as_of_date, ticker, target_weight
            FROM portfolio_target_items
            WHERE snapshot_type = 'shadow'
              AND as_of_date <= :end_date
            ORDER BY as_of_date, ticker
            """,
            {"end_date": end_date},
        )

    def load_real_positions(self, start_date: date, end_date: date) -> pd.DataFrame:
        return self._read_dataframe(
            """
            SELECT ticker, shares, buy_price, opened_at, closed_at, is_open
            FROM live_positions
            WHERE DATE(opened_at) <= :end_date
              AND (closed_at IS NULL OR DATE(closed_at) >= :start_date)
            ORDER BY opened_at, ticker
            """,
            {"start_date": start_date, "end_date": end_date},
        )

    def load_cash_balances(self, end_date: date) -> pd.DataFrame:
        return self._read_dataframe(
            """
            SELECT cash_balance, updated_at
            FROM live_cash_balances
            WHERE DATE(updated_at) <= :end_date
            ORDER BY updated_at, id
            """,
            {"end_date": end_date},
        )

    def load_prices(self, tickers: Sequence[str], end_date: date) -> pd.DataFrame:
        tickers = sorted({ticker.upper() for ticker in tickers if ticker})
        if not tickers:
            return pd.DataFrame(columns=["ticker", "date", "close"])

        statement = text(
            """
            SELECT ticker, date, close
            FROM asset_price_bars
            WHERE ticker IN :tickers
              AND date <= :end_date
            ORDER BY ticker, date
            """
        ).bindparams(bindparam("tickers", expanding=True))
        with self.engine.connect() as conn:
            return pd.read_sql_query(
                statement,
                conn,
                params={"tickers": tickers, "end_date": end_date},
            )

    def _read_dataframe(self, sql: str, params: dict) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql_query(text(sql), conn, params=params)


class LivePerformanceService:
    """Build Real-vs-Shadow-vs-Benchmark performance reports."""

    def __init__(self, repository: Optional[LivePerformanceRepository] = None) -> None:
        self.repository = repository or LivePerformanceRepository()

    def build_report(
        self,
        *,
        start_date: date,
        end_date: date,
        benchmark_ticker: str = "SPY",
        base_value: float | None = None,
    ) -> LivePerformanceReport:
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")
        benchmark_ticker = benchmark_ticker.upper()

        shadow_targets = _normalize_targets(
            self.repository.load_shadow_targets(end_date)
        )
        real_positions = _normalize_positions(
            self.repository.load_real_positions(start_date, end_date)
        )
        cash_balances = _normalize_cash(self.repository.load_cash_balances(end_date))

        tickers = {benchmark_ticker}
        tickers.update(shadow_targets["ticker"].dropna().astype(str).str.upper())
        tickers.update(real_positions["ticker"].dropna().astype(str).str.upper())
        prices = _normalize_prices(self.repository.load_prices(sorted(tickers), end_date))
        if prices.empty:
            raise ValueError("no price data available for live performance report")

        price_pivot = _close_price_pivot(prices)
        if benchmark_ticker not in price_pivot.columns:
            raise ValueError(f"no benchmark prices available for {benchmark_ticker}")

        benchmark_close = price_pivot[benchmark_ticker].dropna()
        report_dates = [
            item
            for item in benchmark_close.index
            if start_date <= item <= end_date
        ]
        if not report_dates:
            raise ValueError("no benchmark prices available in report date range")
        if shadow_targets.empty:
            raise ValueError("no shadow portfolio targets available")

        raw_real_values, real_missing = _real_values(
            report_dates,
            price_pivot,
            real_positions,
            cash_balances,
        )
        resolved_base = _resolve_base_value(base_value, raw_real_values)
        real_values = _normalize_real_values(raw_real_values, resolved_base)
        shadow_values, shadow_missing = _shadow_values(
            report_dates,
            price_pivot,
            shadow_targets,
            resolved_base,
        )
        benchmark_values = _benchmark_values(
            report_dates,
            benchmark_close,
            resolved_base,
        )

        curve = pd.DataFrame(
            {
                "date": report_dates,
                "real_value": real_values,
                "shadow_value": shadow_values,
                "benchmark_value": benchmark_values,
            }
        )
        curve["real_return"] = _returns(curve["real_value"])
        curve["shadow_return"] = _returns(curve["shadow_value"])
        curve["benchmark_return"] = _returns(curve["benchmark_value"])
        curve["real_drawdown"] = _drawdown(curve["real_value"])
        curve["shadow_drawdown"] = _drawdown(curve["shadow_value"])
        curve["benchmark_drawdown"] = _drawdown(curve["benchmark_value"])

        benchmark_return = _total_return(curve["benchmark_value"])
        metrics = {
            "real": _metrics(curve["real_value"], benchmark_return),
            "shadow": _metrics(curve["shadow_value"], benchmark_return),
            "benchmark": PerformanceMetrics(
                total_return=benchmark_return,
                benchmark_return=benchmark_return,
                outperformance=0.0,
                max_drawdown=_max_drawdown(curve["benchmark_value"]),
            ),
        }
        diagnostics = {
            "report_days": len(curve),
            "real_positions": len(real_positions),
            "shadow_snapshots": int(shadow_targets["as_of_date"].nunique()),
            "shadow_positions": int(len(shadow_targets)),
            "real_missing_price_days": real_missing,
            "shadow_missing_price_days": shadow_missing,
        }
        return LivePerformanceReport(
            start_date=report_dates[0],
            end_date=report_dates[-1],
            benchmark_ticker=benchmark_ticker,
            base_value=resolved_base,
            curve=curve,
            metrics=metrics,
            diagnostics=diagnostics,
        )


def _normalize_targets(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["as_of_date", "ticker", "target_weight"])
    result = frame.copy()
    result["as_of_date"] = pd.to_datetime(result["as_of_date"]).dt.date
    result["ticker"] = result["ticker"].astype(str).str.upper()
    result["target_weight"] = result["target_weight"].map(_float)
    return result


def _normalize_positions(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=["ticker", "shares", "buy_price", "opened_at", "closed_at", "is_open"]
        )
    result = frame.copy()
    result["ticker"] = result["ticker"].astype(str).str.upper()
    result["shares"] = result["shares"].map(_float)
    result["buy_price"] = result["buy_price"].map(_float)
    result["opened_at"] = pd.to_datetime(result["opened_at"]).dt.date
    result["closed_at"] = pd.to_datetime(result["closed_at"]).dt.date
    return result


def _normalize_cash(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["cash_balance", "updated_at"])
    result = frame.copy()
    result["cash_balance"] = result["cash_balance"].map(_float)
    result["updated_at"] = pd.to_datetime(result["updated_at"]).dt.date
    return result


def _normalize_prices(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["ticker", "date", "close"])
    result = frame.copy()
    result["ticker"] = result["ticker"].astype(str).str.upper()
    result["date"] = pd.to_datetime(result["date"]).dt.date
    result["close"] = result["close"].map(_float)
    return result


def _close_price_pivot(prices: pd.DataFrame) -> pd.DataFrame:
    pivot = prices.pivot_table(
        index="date",
        columns="ticker",
        values="close",
        aggfunc="last",
    ).sort_index()
    return pivot.ffill()


def _real_values(
    report_dates: Sequence[date],
    prices: pd.DataFrame,
    positions: pd.DataFrame,
    cash_balances: pd.DataFrame,
) -> tuple[list[float], int]:
    values: list[float] = []
    missing_days = 0
    for current_date in report_dates:
        cash = _cash_on_date(cash_balances, current_date)
        invested = 0.0
        missing = False
        for _, row in positions.iterrows():
            closed_at = row["closed_at"]
            is_active = row["opened_at"] <= current_date and (
                pd.isna(closed_at) or closed_at >= current_date
            )
            if not is_active:
                continue
            price = _price_on_date(prices, str(row["ticker"]), current_date)
            if price is None:
                missing = True
                continue
            invested += float(row["shares"]) * price
        if missing:
            missing_days += 1
        values.append(round(cash + invested, 6))
    return values, missing_days


def _shadow_values(
    report_dates: Sequence[date],
    prices: pd.DataFrame,
    targets: pd.DataFrame,
    base_value: float,
) -> tuple[list[float], int]:
    values: list[float] = []
    units: dict[str, float] = {}
    active_snapshot: date | None = None
    current_value = float(base_value)
    missing_days = 0

    for current_date in report_dates:
        snapshot_date = _latest_snapshot_date(targets, current_date)
        if snapshot_date is None:
            values.append(float("nan"))
            continue

        if active_snapshot != snapshot_date:
            carried_value = _units_value(units, prices, current_date)
            if carried_value is not None:
                current_value = carried_value
            units = _allocate_shadow_units(
                targets[targets["as_of_date"] == snapshot_date],
                prices,
                current_date,
                current_value,
            )
            active_snapshot = snapshot_date

        value = _units_value(units, prices, current_date)
        if value is None:
            missing_days += 1
            values.append(float("nan"))
        else:
            current_value = value
            values.append(round(value, 6))
    return values, missing_days


def _benchmark_values(
    report_dates: Sequence[date],
    benchmark_close: pd.Series,
    base_value: float,
) -> list[float]:
    start_price = float(benchmark_close.loc[report_dates[0]])
    if start_price == 0:
        raise ValueError("benchmark start price must be non-zero")
    return [
        round(float(base_value) * float(benchmark_close.loc[current_date]) / start_price, 6)
        for current_date in report_dates
    ]


def _allocate_shadow_units(
    targets: pd.DataFrame,
    prices: pd.DataFrame,
    current_date: date,
    portfolio_value: float,
) -> dict[str, float]:
    units: dict[str, float] = {}
    for _, row in targets.iterrows():
        ticker = str(row["ticker"])
        price = _price_on_date(prices, ticker, current_date)
        if price is None or price == 0:
            continue
        units[ticker] = (float(portfolio_value) * float(row["target_weight"])) / price
    return units


def _units_value(
    units: dict[str, float],
    prices: pd.DataFrame,
    current_date: date,
) -> float | None:
    if not units:
        return None
    value = 0.0
    for ticker, shares in units.items():
        price = _price_on_date(prices, ticker, current_date)
        if price is None:
            return None
        value += shares * price
    return value


def _price_on_date(prices: pd.DataFrame, ticker: str, current_date: date) -> float | None:
    if ticker not in prices.columns or current_date not in prices.index:
        return None
    value = prices.at[current_date, ticker]
    if pd.isna(value):
        return None
    return float(value)


def _cash_on_date(cash_balances: pd.DataFrame, current_date: date) -> float:
    if cash_balances.empty:
        return 0.0
    rows = cash_balances[cash_balances["updated_at"] <= current_date]
    if rows.empty:
        return 0.0
    return float(rows.iloc[-1]["cash_balance"])


def _latest_snapshot_date(targets: pd.DataFrame, current_date: date) -> date | None:
    rows = targets[targets["as_of_date"] <= current_date]
    if rows.empty:
        return None
    return rows["as_of_date"].max()


def _resolve_base_value(base_value: float | None, real_values: Sequence[float]) -> float:
    if base_value is not None:
        if base_value <= 0:
            raise ValueError("base_value must be positive")
        return float(base_value)
    first_real = float(real_values[0]) if real_values else 0.0
    return first_real if first_real > 0 else 100.0


def _normalize_real_values(values: Sequence[float], base_value: float) -> list[float]:
    if not values:
        return []
    start = float(values[0])
    if start <= 0:
        return [float(value) for value in values]
    factor = float(base_value) / start
    return [round(float(value) * factor, 6) for value in values]


def _returns(values: pd.Series) -> pd.Series:
    return values.pct_change()


def _drawdown(values: pd.Series) -> pd.Series:
    running_max = values.cummax()
    return (values / running_max) - 1


def _total_return(values: pd.Series) -> float:
    valid = values.dropna()
    if len(valid) < 2:
        return 0.0
    start = float(valid.iloc[0])
    end = float(valid.iloc[-1])
    return (end / start) - 1 if start else 0.0


def _max_drawdown(values: pd.Series) -> float:
    drawdown = _drawdown(values).dropna()
    if drawdown.empty:
        return 0.0
    return float(drawdown.min())


def _metrics(values: pd.Series, benchmark_return: float) -> PerformanceMetrics:
    total_return = _total_return(values)
    return PerformanceMetrics(
        total_return=total_return,
        benchmark_return=benchmark_return,
        outperformance=total_return - benchmark_return,
        max_drawdown=_max_drawdown(values),
    )


def _float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)
