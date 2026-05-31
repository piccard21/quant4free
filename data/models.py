from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class Ticker:
    ticker: str
    name: str
    sector: Optional[str]
    is_active: bool
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    removed_at: Optional[datetime]
    last_fundamental_update: Optional[datetime]
    asset_class: str = "equity"
    canonical_symbol: Optional[str] = None
    display_symbol: Optional[str] = None
    instrument_type: str = "stock"
    exchange_code: Optional[str] = None
    market: Optional[str] = "US"
    quote_currency: str = "USD"
    primary_provider_key: Optional[str] = "mysql_fixture"


@dataclass(frozen=True)
class DailyCandle:
    ticker: str
    date: date
    open: Optional[Decimal]
    high: Optional[Decimal]
    low: Optional[Decimal]
    close: Optional[Decimal]
    volume: Optional[int]


@dataclass(frozen=True)
class FinancialReport:
    ticker: str
    report_date: date
    report_type: str
    revenue: int
    net_income: int
    ebit: int
    free_cash_flow: int
    total_debt: int
    total_equity: int
    cash_and_equivalents: int
    source: Optional[str]
    imported_at: Optional[datetime]


@dataclass(frozen=True)
class MarketCapSnapshot:
    ticker: str
    date: date
    market_cap: Optional[int]
    imported_at: Optional[datetime]


@dataclass(frozen=True)
class TickerUpsert:
    ticker: str
    name: str
    sector: Optional[str]
    is_active: bool = True
    asset_class: str = "equity"
    canonical_symbol: Optional[str] = None
    display_symbol: Optional[str] = None
    instrument_type: str = "stock"
    exchange_code: Optional[str] = None
    market: Optional[str] = "US"
    quote_currency: str = "USD"
    primary_provider_key: Optional[str] = "mysql_fixture"


@dataclass(frozen=True)
class ProviderIdentifier:
    ticker: str
    provider_key: str
    identifier_scheme: str
    provider_symbol: str
    provider_asset_id: Optional[str] = None
    exchange_code: Optional[str] = None
    market: Optional[str] = None
    quote_currency: Optional[str] = None
    is_primary: bool = False
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    imported_at: Optional[datetime] = None


@dataclass(frozen=True)
class ProviderSymbolMapping:
    ticker: str
    provider_key: str
    provider_symbol: str
    identifier_scheme: str = "ticker"
    provider_asset_id: Optional[str] = None
    is_fallback: bool = False


@dataclass(frozen=True)
class UniverseRecord:
    key: str
    name: str
    description: Optional[str] = None
    asset_classes: tuple[str, ...] = ("equity",)
    membership_source_role: str = "membership"
    membership_provider_key: str = "mysql_fixture"
    membership_rule: str = "assets.is_active = 1"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class UniverseMemberUpsert:
    universe_key: str
    ticker: str
    valid_from: date
    valid_to: Optional[date] = None
    source_provider_key: Optional[str] = "mysql_fixture"
    imported_at: Optional[datetime] = None


@dataclass(frozen=True)
class FinancialSyncPayload:
    reports: tuple[FinancialReport, ...]
    market_cap: Optional[MarketCapSnapshot] = None
