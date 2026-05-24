from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional, Sequence

import pandas as pd

from .base import Indicator, IndicatorResult
from .core import (
    DebtToEquityIndicator,
    EarningsYieldIndicator,
    FreeCashFlowYieldIndicator,
    MomentumReturnIndicator,
    RelativeStrengthIndicator,
    ReturnOnEquityIndicator,
)


DEFAULT_INDICATORS: tuple[Indicator, ...] = (
    MomentumReturnIndicator(),
    RelativeStrengthIndicator(),
    EarningsYieldIndicator(),
    FreeCashFlowYieldIndicator(),
    ReturnOnEquityIndicator(),
    DebtToEquityIndicator(),
)


def list_indicator_keys() -> list[str]:
    return [indicator.key for indicator in DEFAULT_INDICATORS]


def get_indicator(key: str) -> Indicator:
    for indicator in DEFAULT_INDICATORS:
        if indicator.key == key:
            return indicator
    available = ", ".join(list_indicator_keys())
    raise ValueError(f"unknown indicator '{key}'; available: {available}")


def create_indicators(keys: Optional[Sequence[str]] = None) -> list[Indicator]:
    if keys is None:
        return list(DEFAULT_INDICATORS)
    return [get_indicator(key) for key in keys]


def compute_indicators(
    indicators: Sequence[Indicator],
    prices: pd.DataFrame,
    fundamentals: Optional[pd.DataFrame] = None,
    market_caps: Optional[pd.DataFrame] = None,
    as_of_date: Optional[date] = None,
    params: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> pd.DataFrame:
    results = [
        indicator.compute(
            prices=prices,
            fundamentals=fundamentals,
            market_caps=market_caps,
            as_of_date=as_of_date,
            params=(params or {}).get(indicator.key),
        )
        for indicator in indicators
    ]
    return merge_indicator_results(results)


def merge_indicator_results(results: Sequence[IndicatorResult]) -> pd.DataFrame:
    merged: Optional[pd.DataFrame] = None
    for result in results:
        frame = result.values.copy()
        if "ticker" not in frame.columns:
            raise ValueError(f"{result.indicator_key} result missing ticker column")
        value_columns = [
            column for column in frame.columns if column == result.indicator_key
        ]
        if not value_columns:
            raise ValueError(
                f"{result.indicator_key} result missing {result.indicator_key} column"
            )
        frame = frame[["ticker", result.indicator_key]]
        if merged is None:
            merged = frame
        else:
            merged = merged.merge(frame, how="outer", on="ticker")
    if merged is None:
        return pd.DataFrame(columns=["ticker"])
    return merged.sort_values("ticker").reset_index(drop=True)
