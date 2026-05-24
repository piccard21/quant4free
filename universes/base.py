from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:
    from data.provider import DataProvider


@dataclass(frozen=True)
class UniverseDefinition:
    key: str
    name: str
    description: Optional[str] = None
    active_only: bool = True


class UniverseLoader(Protocol):
    """Contract for loading investable ticker sets.

    Implementations return ticker symbols only. Metadata and historical
    membership rules stay behind the loader so strategies can remain agnostic.
    """

    key: str

    def load_members(self, as_of_date: Optional[date] = None) -> list[str]:
        """Return ticker symbols that belong to the universe on as_of_date."""
        ...


class ActiveTickerUniverse:
    """Universe backed by tickers.is_active from the fixture schema."""

    key = "active_tickers"

    def __init__(
        self,
        provider: "DataProvider",
        definition: Optional[UniverseDefinition] = None,
    ) -> None:
        self.provider = provider
        self.definition = definition or UNIVERSE_DEFINITIONS[self.key]
        self.key = self.definition.key

    def load_members(self, as_of_date: Optional[date] = None) -> list[str]:
        tickers = self.provider.list_tickers(active_only=self.definition.active_only)
        return [ticker.ticker for ticker in tickers]


UNIVERSE_DEFINITIONS: dict[str, UniverseDefinition] = {
    "sp500_active": UniverseDefinition(
        key="sp500_active",
        name="S&P 500 active fixture universe",
        description=(
            "Fixture-compatible default universe using currently active tickers."
        ),
        active_only=True,
    ),
    "active_tickers": UniverseDefinition(
        key="active_tickers",
        name="Active tickers",
        description="All tickers where tickers.is_active = 1.",
        active_only=True,
    ),
    "all_tickers": UniverseDefinition(
        key="all_tickers",
        name="All tickers",
        description="All tickers known to the raw-data provider.",
        active_only=False,
    ),
}


def list_universe_definitions() -> list[UniverseDefinition]:
    return list(UNIVERSE_DEFINITIONS.values())


def get_universe_definition(key: str) -> UniverseDefinition:
    try:
        return UNIVERSE_DEFINITIONS[key]
    except KeyError as exc:
        available = ", ".join(sorted(UNIVERSE_DEFINITIONS))
        raise ValueError(f"unknown universe '{key}'; available: {available}") from exc


def create_universe(key: str, provider: "DataProvider") -> UniverseLoader:
    return ActiveTickerUniverse(provider, get_universe_definition(key))
