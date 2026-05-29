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


@dataclass(frozen=True)
class FinancialSyncPayload:
    reports: tuple[FinancialReport, ...]
    market_cap: Optional[MarketCapSnapshot] = None
