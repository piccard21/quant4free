from datetime import date

import pytest
from sqlalchemy import create_engine, text

from live import LivePerformanceRepository, LivePerformanceService


def test_live_performance_compares_real_shadow_and_benchmark():
    engine = _build_engine()
    service = LivePerformanceService(LivePerformanceRepository(engine))

    report = service.build_report(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        benchmark_ticker="SPY",
    )

    assert report.base_value == 100
    assert list(report.curve["date"]) == [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
    ]
    assert list(report.curve["real_value"]) == [100, 105, 110]
    assert list(report.curve["shadow_value"]) == [100, 105, 105]
    assert list(report.curve["benchmark_value"]) == [100, 101, 102]
    assert report.metrics["real"].total_return == pytest.approx(0.10)
    assert report.metrics["shadow"].total_return == pytest.approx(0.05)
    assert report.metrics["benchmark"].total_return == pytest.approx(0.02)
    assert report.metrics["real"].outperformance == pytest.approx(0.08)
    assert report.metrics["shadow"].outperformance == pytest.approx(0.03)
    assert report.diagnostics["real_positions"] == 1
    assert report.diagnostics["shadow_snapshots"] == 1
    assert report.diagnostics["report_days"] == 3


def test_live_performance_rebalances_shadow_on_new_snapshot():
    engine = _build_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO portfolio_target_items (
                    as_of_date, snapshot_type, ticker, target_weight
                ) VALUES
                    ('2026-01-02', 'shadow', 'AAA', 1.0)
                """
            )
        )

    service = LivePerformanceService(LivePerformanceRepository(engine))
    report = service.build_report(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        benchmark_ticker="SPY",
    )

    assert list(report.curve["shadow_value"]) == pytest.approx([100, 105, 114.545455])


def test_live_performance_base_value_normalizes_all_value_series():
    engine = _build_engine()
    service = LivePerformanceService(LivePerformanceRepository(engine))

    report = service.build_report(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        benchmark_ticker="SPY",
        base_value=1000,
    )

    assert list(report.curve["real_value"]) == [1000, 1050, 1100]
    assert list(report.curve["shadow_value"]) == [1000, 1050, 1050]
    assert list(report.curve["benchmark_value"]) == [1000, 1010, 1020]


def test_live_performance_rejects_missing_shadow_targets():
    engine = _build_engine(include_shadow=False)
    service = LivePerformanceService(LivePerformanceRepository(engine))

    with pytest.raises(ValueError, match="no shadow portfolio targets"):
        service.build_report(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
            benchmark_ticker="SPY",
        )


def _build_engine(include_shadow: bool = True):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE asset_price_bars (
                    ticker TEXT NOT NULL,
                    date DATE NOT NULL,
                    close REAL,
                    PRIMARY KEY (ticker, date)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO asset_price_bars (ticker, date, close) VALUES
                    ('AAA', '2026-01-01', 10),
                    ('AAA', '2026-01-02', 11),
                    ('AAA', '2026-01-03', 12),
                    ('BBB', '2026-01-01', 20),
                    ('BBB', '2026-01-02', 20),
                    ('BBB', '2026-01-03', 18),
                    ('SPY', '2026-01-01', 100),
                    ('SPY', '2026-01-02', 101),
                    ('SPY', '2026-01-03', 102)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE portfolio_target_items (
                    as_of_date DATE,
                    snapshot_type TEXT,
                    ticker TEXT,
                    target_weight REAL
                )
                """
            )
        )
        if include_shadow:
            conn.execute(
                text(
                    """
                    INSERT INTO portfolio_target_items (
                        as_of_date, snapshot_type, ticker, target_weight
                    ) VALUES
                        ('2026-01-01', 'shadow', 'AAA', 0.5),
                        ('2026-01-01', 'shadow', 'BBB', 0.5)
                    """
                )
            )
        conn.execute(
            text(
                """
                CREATE TABLE live_positions (
                    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    shares REAL NOT NULL,
                    buy_price REAL,
                    opened_at DATETIME NOT NULL,
                    closed_at DATETIME,
                    is_open INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO live_positions (
                    ticker, shares, buy_price, opened_at, is_open
                ) VALUES (
                    'AAA', 5, 10, '2025-12-31 10:00:00', 1
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE live_cash_balances (
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
                INSERT INTO live_cash_balances (cash_balance, updated_at)
                VALUES (50, '2025-12-31 10:00:00')
                """
            )
        )
    return engine
