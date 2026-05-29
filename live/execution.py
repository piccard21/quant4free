from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from shared.db import get_engine

from .models import (
    CashMovementRequest,
    CashMovementResult,
    TradeExecutionRequest,
    TradeExecutionResult,
)


class LiveExecutionService:
    """Write-side service for real cash and manual trade execution."""

    def __init__(self, engine: Optional[Engine] = None) -> None:
        self.engine = engine or get_engine()

    def apply_cash_movement(self, request: CashMovementRequest) -> CashMovementResult:
        movement_type = _normalize_cash_movement_type(request.movement_type)
        amount = _round_money(request.amount)
        if amount <= 0:
            raise ValueError("amount must be greater than zero")

        with self.engine.begin() as conn:
            as_of_date = _resolve_as_of_date(conn, request.as_of_date)
            _assert_settings_snapshot_exists(conn, as_of_date)
            current_cash = _round_money(_load_current_cash(conn))
            _validate_cash_consistency(current_cash, _load_latest_ledger_balance(conn))

            if movement_type == "deposit":
                signed_amount = amount
                cash_after = _round_money(current_cash + amount)
            elif movement_type == "withdrawal":
                if amount > current_cash:
                    raise ValueError(
                        "withdrawal exceeds available cash: "
                        f"amount={amount:.6f}, available={current_cash:.6f}"
                    )
                signed_amount = _round_money(-amount)
                cash_after = _round_money(current_cash - amount)
            else:
                raise ValueError(f"unsupported cash movement type: {movement_type}")

            result = CashMovementResult(
                as_of_date=as_of_date,
                movement_type=movement_type,
                amount=signed_amount,
                cash_before=current_cash,
                cash_after=cash_after,
                booked_at=request.booked_at,
                dry_run=request.dry_run,
            )

            if request.dry_run:
                return result

            _insert_cash_ledger_entry(
                conn=conn,
                booked_at=request.booked_at,
                as_of_date=as_of_date,
                ticker=None,
                entry_type=movement_type,
                amount=signed_amount,
                balance_after=cash_after,
                trade_execution_id=None,
                notes=request.notes,
            )
            _insert_portfolio_cash(conn, cash_after, request.booked_at)
            return result

    def execute_trade(self, request: TradeExecutionRequest) -> TradeExecutionResult:
        ticker = _normalize_ticker(request.ticker)
        execution_type = request.execution_type.strip().upper()
        trade_plan_action = _normalize_trade_plan_action(request.trade_plan_action)
        shares = round(float(request.shares), 6)
        price = _round_money(request.price)
        fee = _round_money(request.fee)

        if execution_type not in {"BUY", "SELL"}:
            raise ValueError("execution_type must be BUY or SELL")
        if shares <= 0:
            raise ValueError("shares must be greater than zero")
        if price <= 0:
            raise ValueError("price must be greater than zero")
        if fee < 0:
            raise ValueError("fee must not be negative")

        with self.engine.begin() as conn:
            _assert_settings_snapshot_exists(conn, request.as_of_date)
            _assert_ticker_exists(conn, ticker)
            trade_plan_row = _validate_trade_plan_link(
                conn=conn,
                as_of_date=request.as_of_date,
                ticker=ticker,
                execution_type=execution_type,
                shares=shares,
                price=price,
                executed_at=request.executed_at,
                requested_plan_action=trade_plan_action,
                dry_run=request.dry_run,
            )

            current_cash = _round_money(_load_current_cash(conn))
            _validate_cash_consistency(current_cash, _load_latest_ledger_balance(conn))

            realized_profit = None
            tax_amount = 0.0
            tax_rate = _load_tax_rate(conn, request.as_of_date)

            if execution_type == "BUY":
                gross_amount = _round_money(shares * price)
                total_cash_needed = _round_money(gross_amount + fee)
                if total_cash_needed > current_cash:
                    raise ValueError(
                        "not enough cash for BUY: "
                        f"needed={total_cash_needed:.6f}, available={current_cash:.6f}"
                    )
                net_amount = _round_money(-total_cash_needed)
                cash_after_before_tax = _round_money(current_cash + net_amount)
                cash_after = cash_after_before_tax
            else:
                position = _load_open_position(conn, ticker)
                if position is None:
                    raise ValueError(f"no open position found for SELL of {ticker}")
                open_shares = _float(position["shares"])
                if shares > open_shares:
                    raise ValueError(
                        "SELL shares exceed open position: "
                        f"open={open_shares:.6f}, sell={shares:.6f}"
                    )
                gross_amount = _round_money(shares * price)
                net_amount = _round_money(gross_amount - fee)
                buy_price = _round_money(position["buy_price"])
                realized_profit = _round_money((price - buy_price) * shares)
                tax_amount = _round_money(max(realized_profit, 0.0) * tax_rate)
                cash_after_before_tax = _round_money(current_cash + net_amount)
                cash_after = _round_money(cash_after_before_tax - tax_amount)

            if cash_after < -0.000001:
                raise ValueError(f"negative cash after execution: {cash_after:.6f}")

            result = TradeExecutionResult(
                as_of_date=request.as_of_date,
                ticker=ticker,
                execution_type=execution_type,
                shares=shares,
                price=price,
                gross_amount=gross_amount,
                fee=fee,
                net_amount=net_amount,
                realized_profit=realized_profit,
                tax_amount=tax_amount,
                cash_before=current_cash,
                cash_after=cash_after,
                executed_at=request.executed_at,
                trade_execution_id=None,
                dry_run=request.dry_run,
            )

            if request.dry_run:
                return result

            if execution_type == "BUY":
                _apply_buy(conn, ticker, shares, price, request.executed_at)
                cash_entry_type = "trade_buy"
            else:
                _apply_sell(conn, ticker, shares, request.executed_at)
                cash_entry_type = "trade_sell"

            effective_plan_action = (
                str(trade_plan_row["action"]).upper()
                if trade_plan_row is not None
                else trade_plan_action
            )
            effective_execution_order = (
                trade_plan_row["execution_order"] if trade_plan_row is not None else None
            )
            effective_notes = (
                request.notes
                if trade_plan_row is not None or request.notes is not None
                else "manual off-plan trade"
            )

            trade_execution_id = _insert_trade_execution(
                conn=conn,
                as_of_date=request.as_of_date,
                ticker=ticker,
                execution_type=execution_type,
                trade_plan_action=effective_plan_action,
                executed_at=request.executed_at,
                shares=shares,
                price=price,
                gross_amount=gross_amount,
                fee=fee,
                net_amount=net_amount,
                realized_profit=realized_profit,
                tax_amount=tax_amount,
                trade_plan_execution_order=effective_execution_order,
                broker=request.broker,
                notes=effective_notes,
            )
            _insert_cash_ledger_entry(
                conn=conn,
                booked_at=request.executed_at,
                as_of_date=request.as_of_date,
                ticker=ticker,
                entry_type=cash_entry_type,
                amount=net_amount,
                balance_after=cash_after_before_tax,
                trade_execution_id=trade_execution_id,
                notes=effective_notes,
            )
            if tax_amount > 0:
                _insert_cash_ledger_entry(
                    conn=conn,
                    booked_at=request.executed_at,
                    as_of_date=request.as_of_date,
                    ticker=ticker,
                    entry_type="tax_payment",
                    amount=_round_money(-tax_amount),
                    balance_after=cash_after,
                    trade_execution_id=trade_execution_id,
                    notes=effective_notes,
                )
            _insert_portfolio_cash(conn, cash_after, request.executed_at)

            return TradeExecutionResult(
                **{
                    **result.__dict__,
                    "trade_execution_id": trade_execution_id,
                    "dry_run": False,
                }
            )


def _validate_trade_plan_link(
    conn: Connection,
    as_of_date: date,
    ticker: str,
    execution_type: str,
    shares: float,
    price: float,
    executed_at: datetime,
    requested_plan_action: str | None,
    dry_run: bool,
):
    duplicate = conn.execute(
        text(
            """
            SELECT id
            FROM live_trade_executions
            WHERE ticker = :ticker
              AND executed_at = :executed_at
              AND shares = :shares
              AND price = :price
              AND status = 'executed'
            LIMIT 1
            """
        ),
        {
            "ticker": ticker,
            "executed_at": executed_at,
            "shares": shares,
            "price": price,
        },
    ).scalar()
    if duplicate is not None and not dry_run:
        raise ValueError(f"possible duplicate trade execution: id={duplicate}")

    trade_plan_row = conn.execute(
        text(
            """
            SELECT
                as_of_date,
                ticker,
                action,
                execution_order,
                planned_shares,
                estimated_price,
                is_executable,
                skip_reason
            FROM live_trade_plan_items
            WHERE as_of_date = :as_of_date
              AND ticker = :ticker
            LIMIT 1
            """
        ),
        {"as_of_date": as_of_date, "ticker": ticker},
    ).mappings().first()

    if trade_plan_row is None:
        if requested_plan_action is not None:
            raise ValueError(
                "trade_plan_action was supplied, but no trade-plan row exists "
                f"for {ticker} on {as_of_date}"
            )
        return None

    action = str(trade_plan_row["action"]).upper()
    is_executable = int(trade_plan_row["is_executable"] or 0)
    if requested_plan_action is not None and requested_plan_action != action:
        raise ValueError(
            f"trade_plan_action {requested_plan_action} does not match plan action {action}"
        )

    plan_matches_execution = (
        (execution_type == "BUY" and action in {"BUY", "ADJUST_BUY"})
        or (execution_type == "SELL" and action in {"SELL", "ADJUST_SELL"})
    )
    enforce_plan = requested_plan_action is not None or plan_matches_execution
    if not enforce_plan:
        return None

    if is_executable != 1:
        raise ValueError(
            "trade-plan row is not executable: "
            f"ticker={ticker}, as_of_date={as_of_date}, skip_reason={trade_plan_row['skip_reason']}"
        )

    execution_order = trade_plan_row["execution_order"]
    if execution_order is not None:
        existing_by_plan = conn.execute(
            text(
                """
                SELECT id
                FROM live_trade_executions
                WHERE as_of_date = :as_of_date
                  AND ticker = :ticker
                  AND trade_plan_execution_order = :execution_order
                  AND status = 'executed'
                LIMIT 1
                """
            ),
            {
                "as_of_date": as_of_date,
                "ticker": ticker,
                "execution_order": execution_order,
            },
        ).scalar()
        if existing_by_plan is not None and not dry_run:
            raise ValueError(
                "trade-plan row was already executed: "
                f"ticker={ticker}, execution_order={execution_order}, id={existing_by_plan}"
            )

    if execution_type == "BUY" and action not in {"BUY", "ADJUST_BUY"}:
        raise ValueError(f"BUY execution does not match trade-plan action {action}")
    if execution_type == "SELL" and action not in {"SELL", "ADJUST_SELL"}:
        raise ValueError(f"SELL execution does not match trade-plan action {action}")

    return trade_plan_row


def _assert_settings_snapshot_exists(conn: Connection, as_of_date: date) -> None:
    exists = conn.execute(
        text(
            """
            SELECT 1
            FROM strategy_config_snapshots
            WHERE as_of_date = :as_of_date
            LIMIT 1
            """
        ),
        {"as_of_date": as_of_date},
    ).scalar()
    if exists is None:
        raise ValueError(f"missing strategy_config_snapshots row for {as_of_date}")


def _assert_ticker_exists(conn: Connection, ticker: str) -> None:
    exists = conn.execute(
        text(
            """
            SELECT 1
            FROM assets
            WHERE ticker = :ticker
            LIMIT 1
            """
        ),
        {"ticker": ticker},
    ).scalar()
    if exists is None:
        raise ValueError(f"ticker does not exist: {ticker}")


def _resolve_as_of_date(conn: Connection, requested: date | None) -> date:
    if requested is not None:
        return requested
    value = conn.execute(text("SELECT MAX(as_of_date) FROM strategy_config_snapshots")).scalar()
    if value is None:
        raise ValueError("as_of_date is required because no settings snapshot exists")
    return _date(value)


def _load_current_cash(conn: Connection) -> float:
    value = conn.execute(
        text(
            """
            SELECT cash_balance
            FROM live_cash_balances
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        )
    ).scalar()
    if value is None:
        raise ValueError("no live_cash_balances row found")
    return _float(value)


def _load_latest_ledger_balance(conn: Connection) -> float | None:
    value = conn.execute(
        text(
            """
            SELECT balance_after
            FROM live_cash_ledger
            ORDER BY booked_at DESC, id DESC
            LIMIT 1
            """
        )
    ).scalar()
    if value is None:
        return None
    return _float(value)


def _validate_cash_consistency(current_cash: float, ledger_cash: float | None) -> None:
    if ledger_cash is None:
        return
    diff = _round_money(current_cash - ledger_cash)
    if abs(diff) > 0.000001:
        raise ValueError(
            "cash inconsistency detected: "
            f"live_cash_balances={current_cash:.6f}, live_cash_ledger={ledger_cash:.6f}, diff={diff:.6f}"
        )


def _load_tax_rate(conn: Connection, as_of_date: date) -> float:
    snapshot_value = conn.execute(
        text(
            """
            SELECT tax_rate
            FROM strategy_config_snapshots
            WHERE as_of_date = :as_of_date
            LIMIT 1
            """
        ),
        {"as_of_date": as_of_date},
    ).scalar()
    if snapshot_value is not None:
        return _float(snapshot_value)

    active_value = conn.execute(
        text(
            """
            SELECT tax_rate
            FROM strategy_instances
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """
        )
    ).scalar()
    if active_value is not None:
        return _float(active_value)
    return 0.26375


def _load_open_position(conn: Connection, ticker: str):
    return conn.execute(
        text(
            """
            SELECT
                position_id,
                ticker,
                shares,
                buy_price,
                opened_at,
                is_open
            FROM live_positions
            WHERE ticker = :ticker
              AND is_open = 1
            ORDER BY opened_at ASC, position_id ASC
            LIMIT 1
            """
        ),
        {"ticker": ticker},
    ).mappings().first()


def _apply_buy(
    conn: Connection,
    ticker: str,
    shares: float,
    price: float,
    executed_at: datetime,
) -> None:
    existing_position = _load_open_position(conn, ticker)
    now = datetime.now()
    if existing_position is None:
        conn.execute(
            text(
                """
                INSERT INTO live_positions (
                    ticker,
                    shares,
                    buy_price,
                    opened_at,
                    is_open,
                    closed_at,
                    notes,
                    created_at,
                    updated_at
                ) VALUES (
                    :ticker,
                    :shares,
                    :buy_price,
                    :opened_at,
                    1,
                    NULL,
                    :notes,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "ticker": ticker,
                "shares": shares,
                "buy_price": price,
                "opened_at": executed_at,
                "notes": "Created by live execution service",
                "created_at": now,
                "updated_at": now,
            },
        )
        return

    old_shares = _float(existing_position["shares"])
    old_buy_price = _float(existing_position["buy_price"])
    new_total_shares = round(old_shares + shares, 6)
    new_avg_price = _round_money(
        ((old_shares * old_buy_price) + (shares * price)) / new_total_shares
    )
    conn.execute(
        text(
            """
            UPDATE live_positions
            SET
                shares = :shares,
                buy_price = :buy_price,
                updated_at = :updated_at
            WHERE position_id = :position_id
            """
        ),
        {
            "shares": new_total_shares,
            "buy_price": new_avg_price,
            "updated_at": now,
            "position_id": existing_position["position_id"],
        },
    )


def _apply_sell(conn: Connection, ticker: str, shares: float, executed_at: datetime) -> None:
    position = _load_open_position(conn, ticker)
    if position is None:
        raise ValueError(f"no open position found for SELL of {ticker}")

    old_shares = _float(position["shares"])
    remaining_shares = round(old_shares - shares, 6)
    if remaining_shares < 0:
        raise ValueError(f"negative remaining shares for {ticker}: {remaining_shares}")

    now = datetime.now()
    if remaining_shares == 0:
        conn.execute(
            text(
                """
                UPDATE live_positions
                SET
                    shares = 0,
                    is_open = 0,
                    closed_at = :closed_at,
                    updated_at = :updated_at
                WHERE position_id = :position_id
                """
            ),
            {
                "closed_at": executed_at,
                "updated_at": now,
                "position_id": position["position_id"],
            },
        )
        return

    conn.execute(
        text(
            """
            UPDATE live_positions
            SET
                shares = :shares,
                updated_at = :updated_at
            WHERE position_id = :position_id
            """
        ),
        {
            "shares": remaining_shares,
            "updated_at": now,
            "position_id": position["position_id"],
        },
    )


def _insert_trade_execution(
    conn: Connection,
    as_of_date: date,
    ticker: str,
    execution_type: str,
    trade_plan_action: str | None,
    executed_at: datetime,
    shares: float,
    price: float,
    gross_amount: float,
    fee: float,
    net_amount: float,
    realized_profit: float | None,
    tax_amount: float,
    trade_plan_execution_order: int | None,
    broker: str | None,
    notes: str | None,
) -> int:
    result = conn.execute(
        text(
            """
            INSERT INTO live_trade_executions (
                as_of_date,
                ticker,
                execution_type,
                trade_plan_action,
                executed_at,
                shares,
                price,
                gross_amount,
                fee,
                net_amount,
                realized_profit,
                tax_amount,
                trade_plan_execution_order,
                broker,
                notes,
                status,
                created_at
            ) VALUES (
                :as_of_date,
                :ticker,
                :execution_type,
                :trade_plan_action,
                :executed_at,
                :shares,
                :price,
                :gross_amount,
                :fee,
                :net_amount,
                :realized_profit,
                :tax_amount,
                :trade_plan_execution_order,
                :broker,
                :notes,
                'executed',
                :created_at
            )
            """
        ),
        {
            "as_of_date": as_of_date,
            "ticker": ticker,
            "execution_type": execution_type,
            "trade_plan_action": trade_plan_action,
            "executed_at": executed_at,
            "shares": shares,
            "price": price,
            "gross_amount": gross_amount,
            "fee": fee,
            "net_amount": net_amount,
            "realized_profit": realized_profit,
            "tax_amount": tax_amount,
            "trade_plan_execution_order": trade_plan_execution_order,
            "broker": broker,
            "notes": notes,
            "created_at": datetime.now(),
        },
    )
    return int(result.lastrowid)


def _insert_cash_ledger_entry(
    conn: Connection,
    booked_at: datetime,
    as_of_date: date,
    ticker: str | None,
    entry_type: str,
    amount: float,
    balance_after: float,
    trade_execution_id: int | None,
    notes: str | None,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO live_cash_ledger (
                booked_at,
                as_of_date,
                ticker,
                entry_type,
                amount,
                balance_after,
                trade_execution_id,
                notes,
                created_at
            ) VALUES (
                :booked_at,
                :as_of_date,
                :ticker,
                :entry_type,
                :amount,
                :balance_after,
                :trade_execution_id,
                :notes,
                :created_at
            )
            """
        ),
        {
            "booked_at": booked_at,
            "as_of_date": as_of_date,
            "ticker": ticker,
            "entry_type": entry_type,
            "amount": amount,
            "balance_after": balance_after,
            "trade_execution_id": trade_execution_id,
            "notes": notes,
            "created_at": datetime.now(),
        },
    )


def _insert_portfolio_cash(conn: Connection, cash_balance: float, updated_at: datetime) -> None:
    conn.execute(
        text(
            """
            INSERT INTO live_cash_balances (
                cash_balance,
                updated_at
            ) VALUES (
                :cash_balance,
                :updated_at
            )
            """
        ),
        {"cash_balance": cash_balance, "updated_at": updated_at},
    )


def _normalize_ticker(ticker: str) -> str:
    cleaned = ticker.strip().upper()
    if not cleaned:
        raise ValueError("ticker must not be empty")
    return cleaned


def _normalize_trade_plan_action(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    if cleaned not in {"BUY", "SELL", "ADJUST_BUY", "ADJUST_SELL"}:
        raise ValueError(f"unsupported trade_plan_action: {cleaned}")
    return cleaned


def _normalize_cash_movement_type(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in {"deposit", "withdrawal"}:
        raise ValueError("movement_type must be deposit or withdrawal")
    return cleaned


def _round_money(value: Any) -> float:
    return round(_float(value), 6)


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
