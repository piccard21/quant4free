import pytest

from shared.capabilities import (
    CapabilityValidationError,
    SOURCE_ROLE_FUNDAMENTALS,
    validate_indicator_run_capabilities,
    validate_live_capabilities,
    validate_strategy_run_capabilities,
)


def test_default_strategy_capability_check_accepts_current_path():
    report = validate_strategy_run_capabilities(
        strategy_key="value_quality_momentum",
        universe_key="sp500_active",
        benchmark_key="spy",
        provider_key="mysql_fixture",
    )

    assert report.strategy_key == "value_quality_momentum"
    assert report.universe_key == "sp500_active"
    assert report.benchmark_key == "spy"
    assert {item.capability_key for item in report.requirements} >= {
        "prices.daily_ohlcv",
        "fundamentals.equity_reports",
        "market_caps",
        "classification.equity_sector",
    }


def test_indicator_capability_check_accepts_subset_requirements():
    report = validate_indicator_run_capabilities(
        indicator_keys=["momentum_return", "relative_strength"],
        universe_key="sp500_active",
        provider_key="mysql_fixture",
    )

    assert [item.capability_key for item in report.requirements] == [
        "prices.daily_ohlcv"
    ]


def test_strategy_capability_check_rejects_equity_strategy_on_crypto_universe():
    with pytest.raises(CapabilityValidationError) as exc_info:
        validate_strategy_run_capabilities(
            strategy_key="value_quality_momentum",
            universe_key="crypto_top_liquid",
            benchmark_key="spy",
            provider_key="mysql_fixture",
        )

    message = str(exc_info.value)
    assert "strategy=value_quality_momentum cannot run with universe=crypto_top_liquid" in message
    assert "missing capability fundamentals.equity_reports" in message
    assert "asset_class=crypto" in message


def test_strategy_capability_check_rejects_provider_without_required_role():
    with pytest.raises(CapabilityValidationError) as exc_info:
        validate_strategy_run_capabilities(
            strategy_key="value_quality_momentum",
            universe_key="sp500_active",
            benchmark_key="spy",
            provider_key="mysql_fixture",
            source_bindings={SOURCE_ROLE_FUNDAMENTALS: "binance_spot"},
        )

    assert str(exc_info.value) == (
        "provider=binance_spot cannot satisfy source_role=fundamentals: "
        "missing capability fundamentals.equity_reports"
    )


def test_strategy_capability_check_rejects_missing_source_role():
    with pytest.raises(CapabilityValidationError) as exc_info:
        validate_strategy_run_capabilities(
            strategy_key="value_quality_momentum",
            universe_key="sp500_active",
            benchmark_key="spy",
            provider_key="mysql_fixture",
            source_bindings={SOURCE_ROLE_FUNDAMENTALS: None},
        )

    assert str(exc_info.value) == (
        "missing source binding for source_role=fundamentals: "
        "required capability fundamentals.equity_reports"
    )


def test_live_capability_check_declares_current_live_requirements():
    report = validate_live_capabilities(
        live_workflow_key="live_performance",
        benchmark_key="spy",
    )

    assert {item.capability_key for item in report.requirements} >= {
        "prices.daily_ohlcv",
        "live.cash",
        "live.positions",
    }
