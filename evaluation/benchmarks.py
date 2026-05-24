from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:
    from data.provider import DataProvider
    import pandas as pd


@dataclass(frozen=True)
class BenchmarkSpec:
    key: str
    ticker: str
    name: str


class Benchmark(Protocol):
    """Contract for benchmark price series used in reports and evaluations."""

    spec: BenchmarkSpec

    def load_prices(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Return benchmark OHLCV rows with the same schema as provider prices."""
        ...


class ProviderBenchmark:
    """Benchmark resolved through a DataProvider."""

    def __init__(self, spec: BenchmarkSpec, provider: "DataProvider") -> None:
        self.spec = spec
        self.provider = provider

    def load_prices(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        return self.provider.load_benchmark_prices(
            self.spec.ticker,
            start_date,
            end_date,
        )


BENCHMARK_SPECS: dict[str, BenchmarkSpec] = {
    "spy": BenchmarkSpec(
        key="spy",
        ticker="SPY",
        name="SPDR S&P 500 ETF Trust",
    ),
    "qqq": BenchmarkSpec(
        key="qqq",
        ticker="QQQ",
        name="Invesco QQQ Trust",
    ),
    "iwm": BenchmarkSpec(
        key="iwm",
        ticker="IWM",
        name="iShares Russell 2000 ETF",
    ),
}


def list_benchmark_specs() -> list[BenchmarkSpec]:
    return list(BENCHMARK_SPECS.values())


def get_benchmark_spec(key: str) -> BenchmarkSpec:
    try:
        return BENCHMARK_SPECS[key]
    except KeyError as exc:
        available = ", ".join(sorted(BENCHMARK_SPECS))
        raise ValueError(f"unknown benchmark '{key}'; available: {available}") from exc


def create_benchmark(key: str, provider: "DataProvider") -> Benchmark:
    return ProviderBenchmark(get_benchmark_spec(key), provider)
