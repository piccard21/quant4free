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

    def __init__(self, provider: "DataProvider") -> None:
        self.provider = provider

    def load_members(self, as_of_date: Optional[date] = None) -> list[str]:
        tickers = self.provider.list_tickers(active_only=True)
        return [ticker.ticker for ticker in tickers]
