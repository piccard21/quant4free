from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping, Optional

import pandas as pd

from .base import IndicatorResult


@dataclass(frozen=True)
class MomentumReturnIndicator:
    """Return over a configurable calendar-day lookback."""

    key: str = "momentum_return"
    default_lookback_days: int = 252

    def compute(
        self,
        prices: pd.DataFrame,
        fundamentals: Optional[pd.DataFrame] = None,
        market_caps: Optional[pd.DataFrame] = None,
        as_of_date: Optional[date] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> IndicatorResult:
        lookback_days = int(
            (params or {}).get("lookback_days", self.default_lookback_days)
        )
        values = _momentum_frame(prices, as_of_date, lookback_days)
        values = values.rename(columns={"return": self.key})
        return IndicatorResult(self.key, values)


@dataclass(frozen=True)
class RelativeStrengthIndicator:
    """Cross-sectional percentile rank of momentum within the supplied universe."""

    key: str = "relative_strength"
    default_lookback_days: int = 252

    def compute(
        self,
        prices: pd.DataFrame,
        fundamentals: Optional[pd.DataFrame] = None,
        market_caps: Optional[pd.DataFrame] = None,
        as_of_date: Optional[date] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> IndicatorResult:
        lookback_days = int(
            (params or {}).get("lookback_days", self.default_lookback_days)
        )
        values = _momentum_frame(prices, as_of_date, lookback_days)
        values[self.key] = values["return"].rank(pct=True)
        return IndicatorResult(
            self.key,
            values[["ticker", "as_of_date", "lookback_days", self.key]],
        )


@dataclass(frozen=True)
class EarningsYieldIndicator:
    key: str = "earnings_yield"

    def compute(
        self,
        prices: pd.DataFrame,
        fundamentals: Optional[pd.DataFrame] = None,
        market_caps: Optional[pd.DataFrame] = None,
        as_of_date: Optional[date] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> IndicatorResult:
        values = _fundamental_market_cap_frame(
            fundamentals,
            market_caps,
            as_of_date,
        )
        values[self.key] = _safe_divide(values["net_income"], values["market_cap"])
        return IndicatorResult(self.key, values[_fundamental_columns(self.key)])


@dataclass(frozen=True)
class FreeCashFlowYieldIndicator:
    key: str = "free_cash_flow_yield"

    def compute(
        self,
        prices: pd.DataFrame,
        fundamentals: Optional[pd.DataFrame] = None,
        market_caps: Optional[pd.DataFrame] = None,
        as_of_date: Optional[date] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> IndicatorResult:
        values = _fundamental_market_cap_frame(
            fundamentals,
            market_caps,
            as_of_date,
        )
        values[self.key] = _safe_divide(values["free_cash_flow"], values["market_cap"])
        return IndicatorResult(self.key, values[_fundamental_columns(self.key)])


@dataclass(frozen=True)
class ReturnOnEquityIndicator:
    key: str = "return_on_equity"

    def compute(
        self,
        prices: pd.DataFrame,
        fundamentals: Optional[pd.DataFrame] = None,
        market_caps: Optional[pd.DataFrame] = None,
        as_of_date: Optional[date] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> IndicatorResult:
        values = _fundamental_market_cap_frame(
            fundamentals,
            market_caps,
            as_of_date,
        )
        values[self.key] = _safe_divide(values["net_income"], values["total_equity"])
        return IndicatorResult(self.key, values[_fundamental_columns(self.key)])


@dataclass(frozen=True)
class DebtToEquityIndicator:
    key: str = "debt_to_equity"

    def compute(
        self,
        prices: pd.DataFrame,
        fundamentals: Optional[pd.DataFrame] = None,
        market_caps: Optional[pd.DataFrame] = None,
        as_of_date: Optional[date] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> IndicatorResult:
        values = _fundamental_market_cap_frame(
            fundamentals,
            market_caps,
            as_of_date,
        )
        values[self.key] = _safe_divide(values["total_debt"], values["total_equity"])
        return IndicatorResult(self.key, values[_fundamental_columns(self.key)])


def _momentum_frame(
    prices: pd.DataFrame,
    as_of_date: Optional[date],
    lookback_days: int,
) -> pd.DataFrame:
    required_columns = {"ticker", "date", "close"}
    _require_columns(prices, required_columns, "prices")
    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    if as_of_date is not None:
        frame = frame[frame["date"] <= as_of_date]
    effective_as_of = as_of_date or frame["date"].max()
    if pd.isna(effective_as_of):
        return pd.DataFrame(
            columns=[
                "ticker",
                "as_of_date",
                "lookback_days",
                "start_date",
                "end_date",
                "start_close",
                "end_close",
                "return",
            ]
        )

    target_start = effective_as_of - timedelta(days=lookback_days)
    rows = []
    for ticker, group in frame.sort_values("date").groupby("ticker"):
        history = group[group["date"] <= effective_as_of]
        end = history.tail(1)
        start = history[history["date"] <= target_start].tail(1)
        if end.empty or start.empty:
            rows.append(
                {
                    "ticker": ticker,
                    "as_of_date": effective_as_of,
                    "lookback_days": lookback_days,
                    "start_date": pd.NA,
                    "end_date": end["date"].iloc[0] if not end.empty else pd.NA,
                    "start_close": pd.NA,
                    "end_close": end["close"].iloc[0] if not end.empty else pd.NA,
                    "return": pd.NA,
                }
            )
            continue
        start_close = start["close"].iloc[0]
        end_close = end["close"].iloc[0]
        rows.append(
            {
                "ticker": ticker,
                "as_of_date": effective_as_of,
                "lookback_days": lookback_days,
                "start_date": start["date"].iloc[0],
                "end_date": end["date"].iloc[0],
                "start_close": start_close,
                "end_close": end_close,
                "return": _scalar_return(start_close, end_close),
            }
        )
    return pd.DataFrame(rows)


def _fundamental_market_cap_frame(
    fundamentals: Optional[pd.DataFrame],
    market_caps: Optional[pd.DataFrame],
    as_of_date: Optional[date],
) -> pd.DataFrame:
    if fundamentals is None:
        fundamentals = pd.DataFrame(
            columns=[
                "ticker",
                "report_date",
                "net_income",
                "free_cash_flow",
                "total_debt",
                "total_equity",
            ]
        )
    if market_caps is None:
        market_caps = pd.DataFrame(columns=["ticker", "date", "market_cap"])
    _require_columns(
        fundamentals,
        {
            "ticker",
            "report_date",
            "net_income",
            "free_cash_flow",
            "total_debt",
            "total_equity",
        },
        "fundamentals",
    )
    _require_columns(market_caps, {"ticker", "date", "market_cap"}, "market_caps")

    latest_fundamentals = _latest_by_date(
        fundamentals,
        "report_date",
        as_of_date,
    )
    latest_market_caps = _latest_by_date(market_caps, "date", as_of_date)
    values = latest_fundamentals.merge(
        latest_market_caps[["ticker", "date", "market_cap"]],
        how="outer",
        on="ticker",
    )
    if values.empty:
        return pd.DataFrame(
            columns=[
                "ticker",
                "as_of_date",
                "report_date",
                "market_cap_date",
                "net_income",
                "free_cash_flow",
                "total_debt",
                "total_equity",
                "market_cap",
            ]
        )
    values = values.rename(columns={"date": "market_cap_date"})
    values["as_of_date"] = as_of_date
    for column in [
        "net_income",
        "free_cash_flow",
        "total_debt",
        "total_equity",
        "market_cap",
    ]:
        values[column] = pd.to_numeric(values[column], errors="coerce")
    return values


def _latest_by_date(
    frame: pd.DataFrame,
    date_column: str,
    as_of_date: Optional[date],
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    values = frame.copy()
    values[date_column] = pd.to_datetime(values[date_column]).dt.date
    if as_of_date is not None:
        values = values[values[date_column] <= as_of_date]
    if values.empty:
        return values
    indexes = values.sort_values(date_column).groupby("ticker")[date_column].idxmax()
    return values.loc[indexes].reset_index(drop=True)


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = numerator / denominator
    return result.where(denominator.notna() & (denominator != 0))


def _scalar_return(start_close: Any, end_close: Any) -> Any:
    if pd.isna(start_close) or pd.isna(end_close) or start_close == 0:
        return pd.NA
    return (end_close / start_close) - 1


def _fundamental_columns(indicator_key: str) -> list[str]:
    return [
        "ticker",
        "as_of_date",
        "report_date",
        "market_cap_date",
        indicator_key,
    ]


def _require_columns(frame: pd.DataFrame, columns: set[str], name: str) -> None:
    missing = columns.difference(frame.columns)
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(sorted(missing))}")
