from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import text

from data.models import DailyCandle, FinancialReport, MarketCapSnapshot, TickerUpsert
from data.repository import RawDataRepository
from live import CashMovementRequest, LiveExecutionService
from live.operations import (
    OperationalArtifacts,
    OperationalRepository,
    OperationalSettings,
    build_decision_log,
    build_rebalance_suggestions,
    build_trade_plan,
)


pytestmark = pytest.mark.integration


CANONICAL_TABLES = {
    "assets",
    "asset_provider_identifiers",
    "universes",
    "universe_members",
    "asset_price_bars",
    "asset_fundamental_reports",
    "asset_market_caps",
    "data_sync_runs",
    "strategy_instances",
    "strategy_config_snapshots",
    "portfolio_target_items",
    "live_rebalance_items",
    "live_decision_items",
    "live_trade_plans",
    "live_trade_plan_items",
    "live_trade_executions",
    "live_cash_ledger",
    "live_cash_balances",
    "live_positions",
    "performance_snapshots",
}


def test_mysql_schema_and_fixture_are_isolated_and_complete(mysql_engine):
    with mysql_engine.connect() as conn:
        tables = {
            row["TABLE_NAME"]
            for row in conn.execute(
                text(
                    """
                    SELECT TABLE_NAME
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                    """
                )
            ).mappings()
        }
        counts = {
            "assets": conn.execute(text("SELECT COUNT(*) FROM assets")).scalar_one(),
            "asset_provider_identifiers": conn.execute(
                text("SELECT COUNT(*) FROM asset_provider_identifiers")
            ).scalar_one(),
            "universes": conn.execute(text("SELECT COUNT(*) FROM universes")).scalar_one(),
            "universe_members": conn.execute(text("SELECT COUNT(*) FROM universe_members")).scalar_one(),
            "asset_price_bars": conn.execute(text("SELECT COUNT(*) FROM asset_price_bars")).scalar_one(),
            "asset_fundamental_reports": conn.execute(text("SELECT COUNT(*) FROM asset_fundamental_reports")).scalar_one(),
            "asset_market_caps": conn.execute(text("SELECT COUNT(*) FROM asset_market_caps")).scalar_one(),
            "strategy_instances": conn.execute(text("SELECT COUNT(*) FROM strategy_instances")).scalar_one(),
        }

    assert CANONICAL_TABLES <= tables
    assert counts["assets"] > 0
    assert counts["asset_provider_identifiers"] >= counts["assets"]
    assert counts["universes"] >= 3
    assert counts["universe_members"] >= counts["assets"]
    assert counts["asset_price_bars"] > 0
    assert counts["asset_fundamental_reports"] > 0
    assert counts["asset_market_caps"] > 0
    assert counts["strategy_instances"] == 1


def test_mysql_raw_repository_upserts_and_latest_queries(mysql_engine):
    repository = RawDataRepository(mysql_engine)
    sync_time = datetime(2026, 5, 30, 9, 0, 0)
    ticker = "T17A"

    assert repository.upsert_tickers([TickerUpsert(ticker, "AP17 Test Asset", "Tests")], sync_time) == 1
    assert repository.upsert_tickers([TickerUpsert(ticker, "AP17 Renamed Asset", "Quality")], sync_time) == 1
    repository.upsert_daily_candles(
        [
            DailyCandle(ticker, date(2026, 5, 28), Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10.5"), 1000),
            DailyCandle(ticker, date(2026, 5, 29), Decimal("11"), Decimal("12"), Decimal("10"), Decimal("11.5"), 1100),
        ]
    )
    repository.upsert_financial_reports(
        [
            FinancialReport(
                ticker=ticker,
                report_date=date(2026, 3, 31),
                report_type="ttm",
                revenue=100,
                net_income=10,
                ebit=9,
                free_cash_flow=8,
                total_debt=7,
                total_equity=6,
                cash_and_equivalents=5,
                source="pytest",
                imported_at=sync_time,
            )
        ]
    )
    repository.upsert_market_caps(
        [MarketCapSnapshot(ticker, date(2026, 5, 29), 123_456_789, sync_time)]
    )
    repository.mark_fundamental_updated(ticker, sync_time)

    asset = repository.get_ticker(ticker)
    current_members = repository.load_universe_members("sp500_active")
    identifiers = repository.list_provider_identifiers(
        provider_key="mysql_fixture",
        tickers=[ticker],
    )
    latest_candle = repository.latest_daily_candles([ticker], as_of_date=date(2026, 5, 30))[0]
    latest_report = repository.latest_financial_reports("ttm", [ticker], as_of_date=date(2026, 5, 30))[0]
    latest_market_cap = repository.latest_market_caps([ticker], as_of_date=date(2026, 5, 30))[0]

    assert asset is not None
    assert asset.name == "AP17 Renamed Asset"
    assert asset.asset_class == "equity"
    assert identifiers
    assert identifiers[0].provider_symbol == ticker
    assert ticker in {member.ticker for member in current_members}
    assert asset.sector == "Quality"
    assert asset.last_fundamental_update == sync_time
    assert latest_candle.date == date(2026, 5, 29)
    assert latest_candle.close == Decimal("11.5000")
    assert latest_report.revenue == 100
    assert latest_market_cap.market_cap == 123_456_789


def test_mysql_operational_persistence_cash_dry_run_and_cli(mysql_engine, mysql_cli_env):
    repository = OperationalRepository(mysql_engine)
    settings = _settings()
    as_of_date = date(2026, 5, 30)
    ticker = _first_fixture_ticker(mysql_engine)
    model = pd.DataFrame([_snapshot(ticker, 1, 1.0, as_of_date, snapshot_type="model")])
    shadow = pd.DataFrame([_snapshot(ticker, 1, 1.0, as_of_date, snapshot_type="shadow")])
    rankings = pd.DataFrame([_ranking(ticker, 1)])
    rebalance = build_rebalance_suggestions(
        shadow=shadow,
        real=pd.DataFrame(),
        rankings=rankings,
        as_of_date=as_of_date,
        settings=settings,
    )
    decision_log = build_decision_log(rebalance, rankings, settings)
    trade_plan, summary = build_trade_plan(
        as_of_date=as_of_date,
        rebalance=rebalance,
        real=pd.DataFrame(),
        prices=pd.DataFrame([{"ticker": ticker, "current_price": 100}]),
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

    with mysql_engine.begin() as conn:
        conn.execute(text("DELETE FROM live_cash_balances"))
        conn.execute(
            text(
                """
                INSERT INTO live_cash_balances (cash_balance, updated_at)
                VALUES (1000, :updated_at)
                """
            ),
            {"updated_at": datetime(2026, 5, 30, 9, 0, 0)},
        )

    repository.assert_artifacts_are_new(as_of_date)
    repository.save_artifacts(settings, artifacts)

    service = LiveExecutionService(mysql_engine)
    result = service.apply_cash_movement(
        CashMovementRequest(
            movement_type="deposit",
            amount=250,
            as_of_date=as_of_date,
            booked_at=datetime(2026, 5, 30, 10, 0, 0),
            dry_run=True,
        )
    )

    assert result.cash_before == 1000
    assert result.cash_after == 1250
    with mysql_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM portfolio_target_items")).scalar_one() == 2
        assert conn.execute(text("SELECT COUNT(*) FROM live_rebalance_items")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM live_decision_items")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM live_trade_plan_items")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM live_cash_ledger")).scalar_one() == 0

    cli_result = subprocess.run(
        [sys.executable, "-m", "cli.data_status", "--details"],
        check=True,
        env=mysql_cli_env,
        text=True,
        capture_output=True,
    )
    assert "ping=ok" in cli_result.stdout
    assert "assets rows=" in cli_result.stdout


def _settings(**overrides) -> OperationalSettings:
    values = {
        "strategy_version": "ap17-test",
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


def _first_fixture_ticker(mysql_engine) -> str:
    with mysql_engine.connect() as conn:
        return conn.execute(text("SELECT ticker FROM assets ORDER BY ticker LIMIT 1")).scalar_one()


def _snapshot(ticker, rank, target_weight, as_of_date, snapshot_type):
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
        "holding_start_date": None,
        "created_at": datetime(2026, 5, 30, 12, 0, 0),
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
        "buy_eligible": 1,
    }
