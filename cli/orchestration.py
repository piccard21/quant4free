from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Mapping, Optional

from cli.errors import CliUsageError, require_non_empty

if TYPE_CHECKING:
    import pandas as pd

    from data.provider import DataProvider
    from strategies import StrategyResult


@dataclass(frozen=True)
class StrategyRunConfig:
    universe_key: str = "sp500_active"
    benchmark_key: str = "spy"
    as_of_date: Optional[date] = None
    lookback_days: int = 252
    portfolio_size: int = 7
    factor_weights: Mapping[str, float] | None = None


@dataclass(frozen=True)
class StrategyRunArtifacts:
    provider_key: str
    universe_key: str
    benchmark_key: str
    benchmark_ticker: str
    members: list[str]
    as_of_date: date
    load_start_date: date
    prices: "pd.DataFrame"
    fundamentals: "pd.DataFrame"
    market_caps: "pd.DataFrame"
    benchmark_prices: "pd.DataFrame"
    indicators: "pd.DataFrame"
    strategy_result: "StrategyResult"
    member_sectors: Mapping[str, str | None] | None = None

    @property
    def model_portfolio(self) -> "pd.DataFrame":
        return self.strategy_result.rankings[
            self.strategy_result.rankings["model_weight"] > 0
        ].copy()


def run_strategy_snapshot(
    provider: "DataProvider",
    config: StrategyRunConfig,
) -> StrategyRunArtifacts:
    from evaluation import create_benchmark
    from indicators import compute_indicators, create_indicators
    from shared import CapabilityValidationError, validate_strategy_run_capabilities
    from strategies import StrategyContext, create_default_strategy
    from universes import create_universe

    _validate_strategy_config(config)
    try:
        universe = create_universe(config.universe_key, provider)
        benchmark = create_benchmark(config.benchmark_key, provider)
        strategy = create_default_strategy(
            factor_weights=config.factor_weights,
            portfolio_size=config.portfolio_size,
        )
    except ValueError as exc:
        raise CliUsageError(
            str(exc),
            hint="use cli.framework_status --list-configs",
        ) from exc
    try:
        validate_strategy_run_capabilities(
            strategy_key=strategy.key,
            universe_key=universe.key,
            benchmark_key=benchmark.spec.key,
            provider_key=provider.key,
        )
    except CapabilityValidationError as exc:
        raise CliUsageError(
            str(exc),
            hint=(
                "verify universe, benchmark, strategy, and provider source "
                "bindings"
            ),
        ) from exc

    members = universe.load_members(config.as_of_date)
    member_sectors = {
        ticker.ticker.upper(): ticker.sector
        for ticker in provider.list_tickers(active_only=False)
    }
    require_non_empty(
        "universe members",
        len(members),
        hint="load raw data or choose another --universe",
    )

    as_of_date = config.as_of_date or latest_trading_date(provider, members)
    load_start_date = as_of_date - timedelta(days=config.lookback_days + 7)
    prices = provider.load_prices(
        members,
        start_date=load_start_date,
        end_date=as_of_date,
    )
    fundamentals = provider.load_fundamentals(
        members,
        report_type="ttm",
        end_date=as_of_date,
    )
    market_caps = provider.load_market_caps(members, end_date=as_of_date)
    benchmark_prices = benchmark.load_prices(
        start_date=load_start_date,
        end_date=as_of_date,
    )

    require_non_empty(
        "price rows",
        len(prices),
        hint="load fixtures/raw_market_data.sql and verify cli.data_status --details",
    )
    require_non_empty(
        "benchmark price rows",
        len(benchmark_prices),
        hint="verify the selected benchmark has asset_price_bars rows",
    )

    indicators = compute_indicators(
        create_indicators(),
        prices=prices,
        fundamentals=fundamentals,
        market_caps=market_caps,
        as_of_date=as_of_date,
        params={
            "momentum_return": {"lookback_days": config.lookback_days},
            "relative_strength": {"lookback_days": config.lookback_days},
        },
    )
    require_non_empty(
        "indicator rows",
        len(indicators),
        hint="verify prices, ttm fundamentals, and asset_market_caps rows overlap",
    )

    result = strategy.run(
        StrategyContext(
            as_of_date=as_of_date,
            universe=members,
            prices=prices,
            fundamentals=fundamentals,
            market_caps=market_caps,
            benchmark_prices=benchmark_prices,
            indicators={"default": indicators},
        )
    )
    require_non_empty(
        "strategy ranking rows",
        len(result.rankings),
        hint="verify indicator data covers enough universe members",
    )
    require_non_empty(
        "model portfolio rows",
        int((result.rankings["model_weight"] > 0).sum()),
        hint="verify the strategy has eligible ranked rows",
    )

    return StrategyRunArtifacts(
        provider_key=provider.key,
        universe_key=universe.key,
        benchmark_key=benchmark.spec.key,
        benchmark_ticker=benchmark.spec.ticker,
        members=members,
        as_of_date=as_of_date,
        load_start_date=load_start_date,
        prices=prices,
        fundamentals=fundamentals,
        market_caps=market_caps,
        benchmark_prices=benchmark_prices,
        indicators=indicators,
        strategy_result=result,
        member_sectors=member_sectors,
    )


def latest_trading_date(provider: "DataProvider", members: list[str]) -> date:
    prices = provider.load_prices()
    if prices.empty:
        prices = provider.load_prices(members)
    require_non_empty(
        "price rows",
        len(prices),
        hint="run cli.sync_prices or load fixtures/raw_market_data.sql",
    )
    return prices["date"].max()


def factor_weights_from_args(args) -> dict[str, float]:
    return {
        "value": args.value_weight,
        "quality": args.quality_weight,
        "momentum": args.momentum_weight,
    }


def print_strategy_summary(artifacts: StrategyRunArtifacts) -> None:
    result = artifacts.strategy_result
    print(
        "framework="
        f"provider:{artifacts.provider_key} "
        f"universe:{artifacts.universe_key} members:{len(artifacts.members)} "
        f"benchmark:{artifacts.benchmark_key} ticker:{artifacts.benchmark_ticker}"
    )
    print(
        "dates="
        f"as_of:{artifacts.as_of_date} "
        f"load_start:{artifacts.load_start_date}"
    )
    print(
        "strategy="
        f"{result.strategy_key} version:{result.strategy_version} "
        f"rows:{len(result.rankings)} "
        f"eligible:{result.diagnostics['eligible_rows']} "
        f"selected:{result.diagnostics['selected_rows']}"
    )


def print_model_portfolio(artifacts: StrategyRunArtifacts, limit: int) -> None:
    if limit <= 0:
        return
    model = artifacts.model_portfolio
    if model.empty:
        return
    columns = [
        "rank",
        "ticker",
        "model_weight",
        "composite_score",
        "value_score",
        "quality_score",
        "momentum_score",
    ]
    print("model_portfolio=")
    print(model[columns].head(limit).to_string(index=False))


def _validate_strategy_config(config: StrategyRunConfig) -> None:
    if config.lookback_days <= 0:
        raise CliUsageError("lookback days must be positive")
    if config.portfolio_size <= 0:
        raise CliUsageError("portfolio size must be positive")
