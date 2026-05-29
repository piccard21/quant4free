from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class PortfolioTarget:
    ticker: str
    source: str
    as_of_date: date
    target_weight: float
    rank: int | None = None
    sector: str | None = None


@dataclass(frozen=True)
class RealPosition:
    ticker: str
    shares: float
    average_price: float
    opened_at: date | datetime
    current_price: float | None = None

    @property
    def valuation_price(self) -> float:
        if self.current_price is not None:
            return float(self.current_price)
        return float(self.average_price)

    @property
    def market_value(self) -> float:
        return round(float(self.shares) * self.valuation_price, 6)


@dataclass(frozen=True)
class ExecutionGap:
    ticker: str
    model_weight: float
    shadow_weight: float
    real_weight: float
    real_value: float
    state: str
    weight_gap: float
    shares: float = 0.0


@dataclass(frozen=True)
class LivePortfolioStatus:
    as_of_date: date | None
    model_positions: int
    shadow_positions: int
    real_positions: int
    cash_balance: float
    invested_value: float
    total_value: float
    gaps: tuple[ExecutionGap, ...]

    @property
    def actionable_gaps(self) -> tuple[ExecutionGap, ...]:
        return tuple(gap for gap in self.gaps if gap.state != "aligned")


@dataclass(frozen=True)
class CashMovementRequest:
    movement_type: str
    amount: float
    booked_at: datetime
    as_of_date: date | None = None
    notes: str | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class CashMovementResult:
    as_of_date: date
    movement_type: str
    amount: float
    cash_before: float
    cash_after: float
    booked_at: datetime
    dry_run: bool


@dataclass(frozen=True)
class TradeExecutionRequest:
    as_of_date: date
    ticker: str
    execution_type: str
    shares: float
    price: float
    fee: float
    executed_at: datetime
    trade_plan_action: str | None = None
    broker: str | None = None
    notes: str | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class TradeExecutionResult:
    as_of_date: date
    ticker: str
    execution_type: str
    shares: float
    price: float
    gross_amount: float
    fee: float
    net_amount: float
    realized_profit: float | None
    tax_amount: float
    cash_before: float
    cash_after: float
    executed_at: datetime
    trade_execution_id: int | None
    dry_run: bool
