from datetime import date, datetime

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from live.operations import (
    OperationalArtifacts,
    OperationalRepository,
    OperationalSettings,
    build_decision_log,
    build_rebalance_suggestions,
    build_shadow_snapshot,
    build_trade_plan,
)


def test_shadow_keeps_recent_non_model_holding_and_adds_top_model_candidate():
    settings = _settings(portfolio_size=2, min_holding_months=3, max_trades_per_month=1)
    as_of_date = date(2026, 5, 22)
    model = pd.DataFrame(
        [
            _snapshot("AAA", 1, 0.5, as_of_date, snapshot_type="model"),
            _snapshot("BBB", 2, 0.5, as_of_date, snapshot_type="model"),
        ]
    )
    previous = pd.DataFrame(
        [
            _snapshot(
                "CCC",
                1,
                1.0,
                date(2026, 5, 1),
                snapshot_type="shadow",
                holding_start_date=date(2026, 5, 1),
            )
        ]
    )
    rankings = pd.DataFrame(
        [
            _ranking("AAA", 1),
            _ranking("BBB", 2),
            _ranking("CCC", 99),
        ]
    )

    shadow = build_shadow_snapshot(model, previous, rankings, as_of_date, settings)

    assert list(shadow["ticker"]) == ["AAA", "CCC"]
    assert shadow.loc[shadow["ticker"] == "CCC", "holding_start_date"].iloc[0] == date(2026, 5, 1)
    assert shadow["target_weight"].tolist() == [0.5, 0.5]


def test_rebalance_and_trade_plan_create_sell_then_buy_with_cash_simulation():
    settings = _settings(portfolio_size=2, min_holding_months=0, max_trades_per_month=2)
    as_of_date = date(2026, 5, 22)
    shadow = pd.DataFrame([_snapshot("AAA", 1, 0.5, as_of_date, snapshot_type="shadow")])
    real = pd.DataFrame(
        [
            {
                "ticker": "BBB",
                "shares": 10,
                "buy_price": 40,
                "opened_at": datetime(2026, 1, 1, 10, 0, 0),
                "is_open": 1,
            }
        ]
    )
    rankings = pd.DataFrame([_ranking("AAA", 1), _ranking("BBB", 99)])

    rebalance = build_rebalance_suggestions(shadow, real, rankings, as_of_date, settings)
    prices = pd.DataFrame(
        [
            {"ticker": "AAA", "current_price": 100},
            {"ticker": "BBB", "current_price": 50},
        ]
    )
    trade_plan, summary = build_trade_plan(
        as_of_date=as_of_date,
        rebalance=rebalance,
        real=real,
        prices=prices,
        cash_before=1000,
        settings=settings,
    )

    assert rebalance["action"].tolist() == ["SELL", "BUY"]
    assert trade_plan.loc[trade_plan["ticker"] == "BBB", "action"].iloc[0] == "SELL"
    assert trade_plan.loc[trade_plan["ticker"] == "AAA", "action"].iloc[0] == "BUY"
    assert summary["executable_sells"] == 1
    assert summary["executable_buys"] == 1
    assert summary["positions_after"] == 1


def test_repository_persists_operational_artifacts_and_rejects_duplicate_date():
    engine = _build_engine()
    repository = OperationalRepository(engine)
    settings = _settings()
    as_of_date = date(2026, 5, 22)
    model = pd.DataFrame([_snapshot("AAA", 1, 1.0, as_of_date, snapshot_type="model")])
    shadow = pd.DataFrame([_snapshot("AAA", 1, 1.0, as_of_date, snapshot_type="shadow")])
    rebalance = build_rebalance_suggestions(
        shadow=shadow,
        real=pd.DataFrame(),
        rankings=pd.DataFrame([_ranking("AAA", 1)]),
        as_of_date=as_of_date,
        settings=settings,
    )
    decision_log = build_decision_log(rebalance, pd.DataFrame([_ranking("AAA", 1)]), settings)
    trade_plan, summary = build_trade_plan(
        as_of_date=as_of_date,
        rebalance=rebalance,
        real=pd.DataFrame(),
        prices=pd.DataFrame([{"ticker": "AAA", "current_price": 100}]),
        cash_before=1000,
        settings=settings,
    )
    artifacts = OperationalArtifacts(
        model=model,
        shadow=shadow,
        rebalance=rebalance,
        decision_log=decision_log,
        trade_plan=trade_plan,
        trade_plan_summary=summary,
    )

    repository.assert_artifacts_are_new(as_of_date)
    repository.save_artifacts(settings, artifacts)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM portfolio_snapshots")).scalar_one() == 2
        assert conn.execute(text("SELECT COUNT(*) FROM rebalance_suggestions")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM decision_log")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM trade_plan_snapshots")).scalar_one() == 1

    with pytest.raises(ValueError, match="operational artifacts already exist"):
        repository.assert_artifacts_are_new(as_of_date)


def _settings(**overrides):
    values = {
        "strategy_version": "test",
        "value_weight": 0.35,
        "quality_weight": 0.30,
        "momentum_weight": 0.35,
        "momentum_return_weight": 0.40,
        "momentum_rel_strength_weight": 0.60,
        "min_price": 10,
        "min_market_cap": 1_000_000,
        "sma_days": 200,
        "return_lookback_days": 252,
        "buy_rank_threshold": 10,
        "sell_rank_threshold": 20,
        "portfolio_size": 1,
        "max_sector_positions": 2,
        "min_holding_months": 0,
        "max_trades_per_month": 2,
        "daily_fundamental_limit": 25,
        "fundamental_refresh_hours": 24,
        "tax_rate": 0.25,
        "max_funding_sell_pct": 0.20,
    }
    values.update(overrides)
    return OperationalSettings(**values)


def _snapshot(
    ticker,
    rank,
    target_weight,
    as_of_date,
    snapshot_type,
    holding_start_date=None,
):
    return {
        "as_of_date": as_of_date,
        "snapshot_type": snapshot_type,
        "ticker": ticker,
        "portfolio_rank": rank,
        "source_rank": rank,
        "sector": "Tech",
        "target_weight": target_weight,
        "final_score": 0.9,
        "value_score": 0.8,
        "quality_score": 0.7,
        "momentum_score": 0.6,
        "trend_positive": 1,
        "buy_eligible": 1,
        "holding_start_date": holding_start_date,
        "created_at": datetime(2026, 5, 22, 12, 0, 0),
    }


def _ranking(ticker, rank):
    return {
        "ticker": ticker,
        "rank": rank,
        "source_rank": rank,
        "sector": "Tech",
        "final_score": 1.0 / rank,
        "composite_score": 1.0 / rank,
        "value_score": 0.8,
        "quality_score": 0.7,
        "momentum_score": 0.6,
        "trend_positive": 1,
        "buy_eligible": 1 if rank == 1 else 0,
    }


def _build_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE strategy_settings_snapshots (
                    as_of_date DATE PRIMARY KEY,
                    strategy_version TEXT,
                    value_weight REAL,
                    quality_weight REAL,
                    momentum_weight REAL,
                    momentum_return_weight REAL,
                    momentum_rel_strength_weight REAL,
                    min_price REAL,
                    min_market_cap INTEGER,
                    sma_days INTEGER,
                    return_lookback_days INTEGER,
                    buy_rank_threshold INTEGER,
                    sell_rank_threshold INTEGER,
                    portfolio_size INTEGER,
                    max_sector_positions INTEGER,
                    min_holding_months INTEGER,
                    max_trades_per_month INTEGER,
                    daily_fundamental_limit INTEGER,
                    fundamental_refresh_hours INTEGER,
                    tax_rate REAL,
                    max_funding_sell_pct REAL,
                    created_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE portfolio_snapshots (
                    as_of_date DATE,
                    snapshot_type TEXT,
                    ticker TEXT,
                    portfolio_rank INTEGER,
                    source_rank INTEGER,
                    sector TEXT,
                    target_weight REAL,
                    final_score REAL,
                    value_score REAL,
                    quality_score REAL,
                    momentum_score REAL,
                    trend_positive INTEGER,
                    buy_eligible INTEGER,
                    holding_start_date DATE,
                    created_at DATETIME,
                    PRIMARY KEY (as_of_date, snapshot_type, ticker)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE rebalance_suggestions (
                    as_of_date DATE,
                    ticker TEXT,
                    sector TEXT,
                    action TEXT,
                    reason TEXT,
                    source_rank INTEGER,
                    target_weight REAL,
                    current_shares REAL,
                    opened_at DATE,
                    holding_days INTEGER,
                    min_hold_ok INTEGER,
                    created_at DATETIME,
                    PRIMARY KEY (as_of_date, ticker)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE decision_log (
                    as_of_date DATE,
                    ticker TEXT,
                    action TEXT,
                    reason TEXT,
                    source_rank INTEGER,
                    final_score REAL,
                    value_score REAL,
                    quality_score REAL,
                    momentum_score REAL,
                    trend_positive INTEGER,
                    holding_days INTEGER,
                    min_hold_ok INTEGER,
                    strategy_version TEXT,
                    created_at DATETIME,
                    PRIMARY KEY (as_of_date, ticker)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE trade_plan_summary (
                    as_of_date DATE PRIMARY KEY,
                    portfolio_value_before REAL,
                    invested_value_before REAL,
                    cash_before REAL,
                    cash_after REAL,
                    bucket_size REAL,
                    target_positions INTEGER,
                    positions_before INTEGER,
                    positions_after INTEGER,
                    total_sell_gross REAL,
                    total_buy_gross REAL,
                    total_fees REAL,
                    executable_buys INTEGER,
                    executable_sells INTEGER,
                    skipped_trades INTEGER,
                    created_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE trade_plan_snapshots (
                    as_of_date DATE,
                    ticker TEXT,
                    action TEXT,
                    reason TEXT,
                    execution_order INTEGER,
                    source_rank INTEGER,
                    target_weight REAL,
                    current_shares REAL,
                    planned_shares REAL,
                    estimated_price REAL,
                    gross_amount REAL,
                    fee REAL,
                    net_amount REAL,
                    bucket_size REAL,
                    cash_before REAL,
                    cash_after REAL,
                    is_executable INTEGER,
                    skip_reason TEXT,
                    created_at DATETIME,
                    PRIMARY KEY (as_of_date, ticker)
                )
                """
            )
        )
    return engine
