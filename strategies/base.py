from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Mapping, Protocol, Sequence

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class StrategyContext:
    as_of_date: date
    universe: Sequence[str]
    prices: "pd.DataFrame"
    fundamentals: "pd.DataFrame"
    market_caps: "pd.DataFrame"
    benchmark_prices: "pd.DataFrame"
    params: Mapping[str, Any] = field(default_factory=dict)
    indicators: Mapping[str, "pd.DataFrame"] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyResult:
    strategy_key: str
    strategy_version: str
    as_of_date: date
    rankings: "pd.DataFrame"
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


class Strategy(Protocol):
    """Contract for strategy modules.

    Strategies consume a fully prepared StrategyContext and return rankings,
    signals, or model-portfolio candidates. They must not read raw SQL directly.
    """

    key: str
    version: str

    def run(self, context: StrategyContext) -> StrategyResult:
        """Execute the strategy for one evaluation date."""
        ...
