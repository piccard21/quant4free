from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Mapping, Optional, Protocol

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class IndicatorResult:
    indicator_key: str
    values: "pd.DataFrame"


class Indicator(Protocol):
    """Contract for reproducible indicator calculations.

    Implementations receive normalized input data and return a DataFrame with
    at least ticker and indicator value columns documented by the indicator.
    Missing data must be represented explicitly as NaN/None, not hidden by
    implicit default scores.
    """

    key: str

    def compute(
        self,
        prices: "pd.DataFrame",
        fundamentals: Optional["pd.DataFrame"] = None,
        market_caps: Optional["pd.DataFrame"] = None,
        as_of_date: Optional[date] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> IndicatorResult:
        """Calculate indicator values for the supplied data snapshot."""
        ...
