from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, text

from live import CashMovementRequest, LiveExecutionService, TradeExecutionRequest


def test_cash_deposit_updates_ledger_and_portfolio_cash():
    engine = _build_engine()
    service = LiveExecutionService(engine)

    result = service.apply_cash_movement(
        CashMovementRequest(
            movement_type="deposit",
            amount=250,
            as_of_date=date(2026, 5, 22),
            booked_at=datetime(2026, 5, 23, 10, 0, 0),
            notes="test deposit",
        )
    )

    assert result.cash_before == 1000
    assert result.cash_after == 1250
    assert result.amount == 250
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM cash_ledger")).scalar_one() == 1
        assert conn.execute(
            text("SELECT balance_after FROM cash_ledger")
        ).scalar_one() == 1250
        assert conn.execute(
            text("SELECT cash_balance FROM portfolio_cash ORDER BY id DESC LIMIT 1")
        ).scalar_one() == 1250


def test_cash_withdrawal_dry_run_does_not_write():
    engine = _build_engine()
    service = LiveExecutionService(engine)

    result = service.apply_cash_movement(
        CashMovementRequest(
            movement_type="withdrawal",
            amount=100,
            as_of_date=date(2026, 5, 22),
            booked_at=datetime(2026, 5, 23, 10, 0, 0),
            dry_run=True,
        )
    )

    assert result.cash_after == 900
    assert result.dry_run is True
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM cash_ledger")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM portfolio_cash")).scalar_one() == 1


def test_buy_execution_creates_position_trade_cash_and_ledger_rows():
    engine = _build_engine()
    service = LiveExecutionService(engine)

    result = service.execute_trade(
        TradeExecutionRequest(
            as_of_date=date(2026, 5, 22),
            ticker="aaa",
            execution_type="BUY",
            shares=5,
            price=100,
            fee=1,
            executed_at=datetime(2026, 5, 23, 11, 0, 0),
        )
    )

    assert result.trade_execution_id == 1
    assert result.ticker == "AAA"
    assert result.net_amount == -501
    assert result.cash_after == 499
    with engine.connect() as conn:
        position = conn.execute(
            text("SELECT ticker, shares, buy_price, is_open FROM portfolio_positions")
        ).mappings().one()
        assert dict(position) == {
            "ticker": "AAA",
            "shares": 5,
            "buy_price": 100,
            "is_open": 1,
        }
        assert conn.execute(text("SELECT COUNT(*) FROM trade_executions")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM cash_ledger")).scalar_one() == 1
        assert conn.execute(
            text("SELECT cash_balance FROM portfolio_cash ORDER BY id DESC LIMIT 1")
        ).scalar_one() == 499


def test_sell_execution_reduces_position_books_tax_and_cash():
    engine = _build_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO portfolio_positions (
                    ticker, shares, buy_price, opened_at, is_open, created_at, updated_at
                ) VALUES (
                    'AAA', 10, 80, '2026-05-01 10:00:00', 1,
                    '2026-05-01 10:00:00', '2026-05-01 10:00:00'
                )
                """
            )
        )

    service = LiveExecutionService(engine)
    result = service.execute_trade(
        TradeExecutionRequest(
            as_of_date=date(2026, 5, 22),
            ticker="AAA",
            execution_type="SELL",
            shares=4,
            price=100,
            fee=1,
            executed_at=datetime(2026, 5, 23, 11, 0, 0),
        )
    )

    assert result.gross_amount == 400
    assert result.net_amount == 399
    assert result.realized_profit == 80
    assert result.tax_amount == 20
    assert result.cash_after == 1379
    with engine.connect() as conn:
        assert conn.execute(text("SELECT shares FROM portfolio_positions")).scalar_one() == 6
        assert conn.execute(text("SELECT COUNT(*) FROM cash_ledger")).scalar_one() == 2
        assert conn.execute(
            text(
                """
                SELECT balance_after
                FROM cash_ledger
                WHERE entry_type = 'tax_payment'
                """
            )
        ).scalar_one() == 1379


def test_trade_execution_rejects_cash_ledger_mismatch():
    engine = _build_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO cash_ledger (
                    booked_at, as_of_date, entry_type, amount, balance_after, created_at
                ) VALUES (
                    '2026-05-22 10:00:00', '2026-05-22', 'deposit', 999, 999,
                    '2026-05-22 10:00:00'
                )
                """
            )
        )

    service = LiveExecutionService(engine)
    with pytest.raises(ValueError, match="cash inconsistency"):
        service.execute_trade(
            TradeExecutionRequest(
                as_of_date=date(2026, 5, 22),
                ticker="AAA",
                execution_type="BUY",
                shares=1,
                price=10,
                fee=1,
                executed_at=datetime(2026, 5, 23, 11, 0, 0),
            )
        )


def _build_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE tickers (
                    ticker TEXT PRIMARY KEY
                )
                """
            )
        )
        conn.execute(text("INSERT INTO tickers (ticker) VALUES ('AAA'), ('BBB')"))
        conn.execute(
            text(
                """
                CREATE TABLE strategy_settings_snapshots (
                    as_of_date DATE PRIMARY KEY,
                    tax_rate REAL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO strategy_settings_snapshots (as_of_date, tax_rate)
                VALUES ('2026-05-22', 0.25)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE strategy_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tax_rate REAL,
                    is_active INTEGER
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE portfolio_cash (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cash_balance REAL NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO portfolio_cash (cash_balance, updated_at)
                VALUES (1000, '2026-05-22 09:00:00')
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE portfolio_positions (
                    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    shares REAL NOT NULL,
                    buy_price REAL,
                    opened_at DATETIME NOT NULL,
                    closed_at DATETIME,
                    is_open INTEGER NOT NULL DEFAULT 1,
                    notes TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE trade_plan_snapshots (
                    as_of_date DATE NOT NULL,
                    ticker TEXT NOT NULL,
                    action TEXT NOT NULL,
                    execution_order INTEGER,
                    planned_shares REAL,
                    estimated_price REAL,
                    is_executable INTEGER NOT NULL DEFAULT 0,
                    skip_reason TEXT,
                    PRIMARY KEY (as_of_date, ticker)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE trade_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    as_of_date DATE NOT NULL,
                    ticker TEXT NOT NULL,
                    execution_type TEXT NOT NULL,
                    trade_plan_action TEXT,
                    executed_at DATETIME NOT NULL,
                    shares REAL NOT NULL,
                    price REAL NOT NULL,
                    gross_amount REAL NOT NULL,
                    fee REAL NOT NULL DEFAULT 0,
                    net_amount REAL NOT NULL,
                    realized_profit REAL,
                    tax_amount REAL NOT NULL DEFAULT 0,
                    trade_plan_execution_order INTEGER,
                    broker TEXT,
                    notes TEXT,
                    status TEXT NOT NULL DEFAULT 'executed',
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE cash_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    booked_at DATETIME NOT NULL,
                    as_of_date DATE NOT NULL,
                    ticker TEXT,
                    entry_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    trade_execution_id INTEGER,
                    notes TEXT,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
    return engine
