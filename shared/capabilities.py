from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


CAPABILITY_UNIVERSE_MEMBERSHIP = "universe.membership"
CAPABILITY_PRICES_DAILY_OHLCV = "prices.daily_ohlcv"
CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS = "fundamentals.equity_reports"
CAPABILITY_MARKET_CAPS = "market_caps"
CAPABILITY_CLASSIFICATION_EQUITY_SECTOR = "classification.equity_sector"
CAPABILITY_LIVE_CASH = "live.cash"
CAPABILITY_LIVE_POSITIONS = "live.positions"

SOURCE_ROLE_MEMBERSHIP = "membership"
SOURCE_ROLE_PRICES = "prices"
SOURCE_ROLE_FUNDAMENTALS = "fundamentals"
SOURCE_ROLE_MARKET_CAPS = "market_caps"
SOURCE_ROLE_CLASSIFICATION = "classification"
SOURCE_ROLE_BENCHMARK_PRICES = "benchmark_prices"
SOURCE_ROLE_LIVE_CASH = "live_cash"
SOURCE_ROLE_LIVE_POSITIONS = "live_positions"

ASSET_CLASS_EQUITY = "equity"
ASSET_CLASS_ETF = "etf"
ASSET_CLASS_CRYPTO = "crypto"


@dataclass(frozen=True)
class CapabilityDefinition:
    key: str
    description: str


@dataclass(frozen=True)
class Requirement:
    capability_key: str
    source_role: str
    required_by: str


@dataclass(frozen=True)
class UniverseCapabilityProfile:
    universe_key: str
    asset_classes: tuple[str, ...]
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class ProviderCapability:
    provider_key: str
    source_role: str
    capability_key: str
    asset_classes: tuple[str, ...]
    granularity: str
    required_fields: tuple[str, ...]


@dataclass(frozen=True)
class AssetMetadata:
    ticker: str
    asset_class: str
    canonical_symbol: str | None = None
    display_symbol: str | None = None
    quote_currency: str | None = None


@dataclass(frozen=True)
class ProviderIdentifierCoverage:
    source_role: str
    provider_key: str
    identifier_scheme: str
    required_tickers: tuple[str, ...]
    covered_tickers: tuple[str, ...]

    @property
    def missing_tickers(self) -> tuple[str, ...]:
        covered = {ticker.upper() for ticker in self.covered_tickers}
        return tuple(
            ticker
            for ticker in self.required_tickers
            if ticker.upper() not in covered
        )


@dataclass(frozen=True)
class SourceBinding:
    source_role: str
    provider_key: str


@dataclass(frozen=True)
class CapabilityCheckReport:
    strategy_key: str | None
    universe_key: str | None
    benchmark_key: str | None
    provider_bindings: tuple[SourceBinding, ...]
    requirements: tuple[Requirement, ...]


class CapabilityValidationError(ValueError):
    """Raised when a run configuration violates capability/provider rules."""


CAPABILITY_DEFINITIONS: dict[str, CapabilityDefinition] = {
    CAPABILITY_UNIVERSE_MEMBERSHIP: CapabilityDefinition(
        key=CAPABILITY_UNIVERSE_MEMBERSHIP,
        description="Universe membership for a configured asset selection.",
    ),
    CAPABILITY_PRICES_DAILY_OHLCV: CapabilityDefinition(
        key=CAPABILITY_PRICES_DAILY_OHLCV,
        description="Daily open, high, low, close, and volume price bars.",
    ),
    CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS: CapabilityDefinition(
        key=CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS,
        description="Equity financial reports used by value and quality factors.",
    ),
    CAPABILITY_MARKET_CAPS: CapabilityDefinition(
        key=CAPABILITY_MARKET_CAPS,
        description="Point-in-time market-cap snapshots.",
    ),
    CAPABILITY_CLASSIFICATION_EQUITY_SECTOR: CapabilityDefinition(
        key=CAPABILITY_CLASSIFICATION_EQUITY_SECTOR,
        description="Equity sector classification.",
    ),
    CAPABILITY_LIVE_CASH: CapabilityDefinition(
        key=CAPABILITY_LIVE_CASH,
        description="Operational cash ledger and balances.",
    ),
    CAPABILITY_LIVE_POSITIONS: CapabilityDefinition(
        key=CAPABILITY_LIVE_POSITIONS,
        description="Operational real portfolio positions.",
    ),
}


UNIVERSE_CAPABILITIES: dict[str, UniverseCapabilityProfile] = {
    "sp500_active": UniverseCapabilityProfile(
        universe_key="sp500_active",
        asset_classes=(ASSET_CLASS_EQUITY,),
        capabilities=(
            CAPABILITY_UNIVERSE_MEMBERSHIP,
            CAPABILITY_PRICES_DAILY_OHLCV,
            CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS,
            CAPABILITY_MARKET_CAPS,
            CAPABILITY_CLASSIFICATION_EQUITY_SECTOR,
        ),
    ),
    "active_tickers": UniverseCapabilityProfile(
        universe_key="active_tickers",
        asset_classes=(ASSET_CLASS_EQUITY,),
        capabilities=(
            CAPABILITY_UNIVERSE_MEMBERSHIP,
            CAPABILITY_PRICES_DAILY_OHLCV,
            CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS,
            CAPABILITY_MARKET_CAPS,
            CAPABILITY_CLASSIFICATION_EQUITY_SECTOR,
        ),
    ),
    "all_tickers": UniverseCapabilityProfile(
        universe_key="all_tickers",
        asset_classes=(ASSET_CLASS_EQUITY,),
        capabilities=(
            CAPABILITY_UNIVERSE_MEMBERSHIP,
            CAPABILITY_PRICES_DAILY_OHLCV,
            CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS,
            CAPABILITY_MARKET_CAPS,
            CAPABILITY_CLASSIFICATION_EQUITY_SECTOR,
        ),
    ),
    "crypto_top_liquid": UniverseCapabilityProfile(
        universe_key="crypto_top_liquid",
        asset_classes=(ASSET_CLASS_CRYPTO,),
        capabilities=(
            CAPABILITY_UNIVERSE_MEMBERSHIP,
            CAPABILITY_PRICES_DAILY_OHLCV,
            CAPABILITY_MARKET_CAPS,
        ),
    ),
}


INDICATOR_REQUIREMENTS: dict[str, tuple[Requirement, ...]] = {
    "momentum_return": (
        Requirement(
            CAPABILITY_PRICES_DAILY_OHLCV,
            SOURCE_ROLE_PRICES,
            "indicator=momentum_return",
        ),
    ),
    "relative_strength": (
        Requirement(
            CAPABILITY_PRICES_DAILY_OHLCV,
            SOURCE_ROLE_PRICES,
            "indicator=relative_strength",
        ),
    ),
    "earnings_yield": (
        Requirement(
            CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS,
            SOURCE_ROLE_FUNDAMENTALS,
            "indicator=earnings_yield",
        ),
        Requirement(
            CAPABILITY_MARKET_CAPS,
            SOURCE_ROLE_MARKET_CAPS,
            "indicator=earnings_yield",
        ),
    ),
    "free_cash_flow_yield": (
        Requirement(
            CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS,
            SOURCE_ROLE_FUNDAMENTALS,
            "indicator=free_cash_flow_yield",
        ),
        Requirement(
            CAPABILITY_MARKET_CAPS,
            SOURCE_ROLE_MARKET_CAPS,
            "indicator=free_cash_flow_yield",
        ),
    ),
    "return_on_equity": (
        Requirement(
            CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS,
            SOURCE_ROLE_FUNDAMENTALS,
            "indicator=return_on_equity",
        ),
    ),
    "debt_to_equity": (
        Requirement(
            CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS,
            SOURCE_ROLE_FUNDAMENTALS,
            "indicator=debt_to_equity",
        ),
    ),
}

STRATEGY_INDICATORS: dict[str, tuple[str, ...]] = {
    "value_quality_momentum": tuple(INDICATOR_REQUIREMENTS),
}

STRATEGY_REQUIREMENTS: dict[str, tuple[Requirement, ...]] = {
    "value_quality_momentum": (
        Requirement(
            CAPABILITY_CLASSIFICATION_EQUITY_SECTOR,
            SOURCE_ROLE_CLASSIFICATION,
            "strategy=value_quality_momentum",
        ),
    ),
}

BENCHMARK_REQUIREMENTS: dict[str, tuple[Requirement, ...]] = {
    "spy": (
        Requirement(
            CAPABILITY_PRICES_DAILY_OHLCV,
            SOURCE_ROLE_BENCHMARK_PRICES,
            "benchmark=spy",
        ),
    ),
    "qqq": (
        Requirement(
            CAPABILITY_PRICES_DAILY_OHLCV,
            SOURCE_ROLE_BENCHMARK_PRICES,
            "benchmark=qqq",
        ),
    ),
    "iwm": (
        Requirement(
            CAPABILITY_PRICES_DAILY_OHLCV,
            SOURCE_ROLE_BENCHMARK_PRICES,
            "benchmark=iwm",
        ),
    ),
}

LIVE_REQUIREMENTS: dict[str, tuple[Requirement, ...]] = {
    "live_cash": (
        Requirement(CAPABILITY_LIVE_CASH, SOURCE_ROLE_LIVE_CASH, "live=live_cash"),
    ),
    "live_status": (
        Requirement(CAPABILITY_PRICES_DAILY_OHLCV, SOURCE_ROLE_PRICES, "live=live_status"),
        Requirement(CAPABILITY_LIVE_CASH, SOURCE_ROLE_LIVE_CASH, "live=live_status"),
        Requirement(
            CAPABILITY_LIVE_POSITIONS,
            SOURCE_ROLE_LIVE_POSITIONS,
            "live=live_status",
        ),
    ),
    "live_performance": (
        Requirement(
            CAPABILITY_PRICES_DAILY_OHLCV,
            SOURCE_ROLE_BENCHMARK_PRICES,
            "live=live_performance",
        ),
        Requirement(CAPABILITY_LIVE_CASH, SOURCE_ROLE_LIVE_CASH, "live=live_performance"),
        Requirement(
            CAPABILITY_LIVE_POSITIONS,
            SOURCE_ROLE_LIVE_POSITIONS,
            "live=live_performance",
        ),
    ),
    "live_trade": (
        Requirement(CAPABILITY_PRICES_DAILY_OHLCV, SOURCE_ROLE_PRICES, "live=live_trade"),
        Requirement(CAPABILITY_LIVE_CASH, SOURCE_ROLE_LIVE_CASH, "live=live_trade"),
        Requirement(
            CAPABILITY_LIVE_POSITIONS,
            SOURCE_ROLE_LIVE_POSITIONS,
            "live=live_trade",
        ),
    ),
}


DEFAULT_SOURCE_BINDINGS: tuple[SourceBinding, ...] = (
    SourceBinding(SOURCE_ROLE_MEMBERSHIP, "mysql_fixture"),
    SourceBinding(SOURCE_ROLE_PRICES, "mysql_fixture"),
    SourceBinding(SOURCE_ROLE_FUNDAMENTALS, "mysql_fixture"),
    SourceBinding(SOURCE_ROLE_MARKET_CAPS, "mysql_fixture"),
    SourceBinding(SOURCE_ROLE_CLASSIFICATION, "mysql_fixture"),
    SourceBinding(SOURCE_ROLE_BENCHMARK_PRICES, "mysql_fixture"),
    SourceBinding(SOURCE_ROLE_LIVE_CASH, "mysql_fixture"),
    SourceBinding(SOURCE_ROLE_LIVE_POSITIONS, "mysql_fixture"),
)


PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = (
    ProviderCapability(
        "mysql_fixture",
        SOURCE_ROLE_MEMBERSHIP,
        CAPABILITY_UNIVERSE_MEMBERSHIP,
        (ASSET_CLASS_EQUITY,),
        "snapshot",
        ("ticker", "is_active"),
    ),
    ProviderCapability(
        "mysql_fixture",
        SOURCE_ROLE_PRICES,
        CAPABILITY_PRICES_DAILY_OHLCV,
        (ASSET_CLASS_EQUITY, ASSET_CLASS_ETF),
        "daily",
        ("ticker", "date", "open", "high", "low", "close", "volume"),
    ),
    ProviderCapability(
        "mysql_fixture",
        SOURCE_ROLE_FUNDAMENTALS,
        CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS,
        (ASSET_CLASS_EQUITY,),
        "ttm",
        (
            "ticker",
            "report_date",
            "net_income",
            "free_cash_flow",
            "total_debt",
            "total_equity",
        ),
    ),
    ProviderCapability(
        "mysql_fixture",
        SOURCE_ROLE_MARKET_CAPS,
        CAPABILITY_MARKET_CAPS,
        (ASSET_CLASS_EQUITY,),
        "snapshot",
        ("ticker", "date", "market_cap"),
    ),
    ProviderCapability(
        "mysql_fixture",
        SOURCE_ROLE_CLASSIFICATION,
        CAPABILITY_CLASSIFICATION_EQUITY_SECTOR,
        (ASSET_CLASS_EQUITY,),
        "snapshot",
        ("ticker", "sector"),
    ),
    ProviderCapability(
        "mysql_fixture",
        SOURCE_ROLE_BENCHMARK_PRICES,
        CAPABILITY_PRICES_DAILY_OHLCV,
        (ASSET_CLASS_EQUITY, ASSET_CLASS_ETF),
        "daily",
        ("ticker", "date", "open", "high", "low", "close", "volume"),
    ),
    ProviderCapability(
        "mysql_fixture",
        SOURCE_ROLE_LIVE_CASH,
        CAPABILITY_LIVE_CASH,
        (ASSET_CLASS_EQUITY,),
        "ledger",
        ("currency", "balance"),
    ),
    ProviderCapability(
        "mysql_fixture",
        SOURCE_ROLE_LIVE_POSITIONS,
        CAPABILITY_LIVE_POSITIONS,
        (ASSET_CLASS_EQUITY,),
        "snapshot",
        ("ticker", "quantity"),
    ),
    ProviderCapability(
        "wikipedia_sp500",
        SOURCE_ROLE_MEMBERSHIP,
        CAPABILITY_UNIVERSE_MEMBERSHIP,
        (ASSET_CLASS_EQUITY,),
        "snapshot",
        ("ticker", "is_active"),
    ),
    ProviderCapability(
        "wikipedia_sp500",
        SOURCE_ROLE_CLASSIFICATION,
        CAPABILITY_CLASSIFICATION_EQUITY_SECTOR,
        (ASSET_CLASS_EQUITY,),
        "snapshot",
        ("ticker", "sector"),
    ),
    ProviderCapability(
        "yfinance",
        SOURCE_ROLE_PRICES,
        CAPABILITY_PRICES_DAILY_OHLCV,
        (ASSET_CLASS_EQUITY, ASSET_CLASS_ETF),
        "daily",
        ("ticker", "date", "open", "high", "low", "close", "volume"),
    ),
    ProviderCapability(
        "yfinance",
        SOURCE_ROLE_BENCHMARK_PRICES,
        CAPABILITY_PRICES_DAILY_OHLCV,
        (ASSET_CLASS_EQUITY, ASSET_CLASS_ETF),
        "daily",
        ("ticker", "date", "open", "high", "low", "close", "volume"),
    ),
    ProviderCapability(
        "yfinance",
        SOURCE_ROLE_FUNDAMENTALS,
        CAPABILITY_FUNDAMENTALS_EQUITY_REPORTS,
        (ASSET_CLASS_EQUITY,),
        "ttm",
        (
            "ticker",
            "report_date",
            "net_income",
            "free_cash_flow",
            "total_debt",
            "total_equity",
        ),
    ),
    ProviderCapability(
        "yfinance",
        SOURCE_ROLE_MARKET_CAPS,
        CAPABILITY_MARKET_CAPS,
        (ASSET_CLASS_EQUITY,),
        "snapshot",
        ("ticker", "date", "market_cap"),
    ),
    ProviderCapability(
        "binance_spot",
        SOURCE_ROLE_MEMBERSHIP,
        CAPABILITY_UNIVERSE_MEMBERSHIP,
        (ASSET_CLASS_CRYPTO,),
        "snapshot",
        ("ticker", "is_active"),
    ),
    ProviderCapability(
        "binance_spot",
        SOURCE_ROLE_PRICES,
        CAPABILITY_PRICES_DAILY_OHLCV,
        (ASSET_CLASS_CRYPTO,),
        "daily",
        ("ticker", "date", "open", "high", "low", "close", "volume"),
    ),
    ProviderCapability(
        "binance_spot",
        SOURCE_ROLE_BENCHMARK_PRICES,
        CAPABILITY_PRICES_DAILY_OHLCV,
        (ASSET_CLASS_CRYPTO,),
        "daily",
        ("ticker", "date", "open", "high", "low", "close", "volume"),
    ),
)


def default_source_bindings(provider_key: str = "mysql_fixture") -> dict[str, str]:
    return {binding.source_role: provider_key for binding in DEFAULT_SOURCE_BINDINGS}


def validate_strategy_run_capabilities(
    *,
    strategy_key: str = "value_quality_momentum",
    universe_key: str = "sp500_active",
    benchmark_key: str = "spy",
    provider_key: str = "mysql_fixture",
    source_bindings: Mapping[str, str | None] | None = None,
    asset_metadata: Sequence[AssetMetadata] | None = None,
    provider_identifier_coverage: Sequence[ProviderIdentifierCoverage] | None = None,
) -> CapabilityCheckReport:
    requirements = [
        *requirements_for_strategy(strategy_key),
        *requirements_for_benchmark(benchmark_key),
    ]
    return validate_capabilities(
        strategy_key=strategy_key,
        universe_key=universe_key,
        benchmark_key=benchmark_key,
        provider_key=provider_key,
        requirements=requirements,
        source_bindings=source_bindings,
        asset_metadata=asset_metadata,
        provider_identifier_coverage=provider_identifier_coverage,
    )


def validate_indicator_run_capabilities(
    *,
    indicator_keys: Sequence[str],
    universe_key: str = "sp500_active",
    provider_key: str = "mysql_fixture",
    source_bindings: Mapping[str, str | None] | None = None,
    asset_metadata: Sequence[AssetMetadata] | None = None,
    provider_identifier_coverage: Sequence[ProviderIdentifierCoverage] | None = None,
) -> CapabilityCheckReport:
    requirements = _unique_requirements(
        requirement
        for indicator_key in indicator_keys
        for requirement in requirements_for_indicator(indicator_key)
    )
    return validate_capabilities(
        strategy_key=None,
        universe_key=universe_key,
        benchmark_key=None,
        provider_key=provider_key,
        requirements=requirements,
        source_bindings=source_bindings,
        asset_metadata=asset_metadata,
        provider_identifier_coverage=provider_identifier_coverage,
    )


def validate_live_capabilities(
    *,
    live_workflow_key: str,
    benchmark_key: str | None = None,
    provider_key: str = "mysql_fixture",
    source_bindings: Mapping[str, str | None] | None = None,
    asset_metadata: Sequence[AssetMetadata] | None = None,
    provider_identifier_coverage: Sequence[ProviderIdentifierCoverage] | None = None,
) -> CapabilityCheckReport:
    requirements = [*requirements_for_live_workflow(live_workflow_key)]
    if benchmark_key is not None:
        requirements.extend(requirements_for_benchmark(benchmark_key))
    return validate_capabilities(
        strategy_key=None,
        universe_key=None,
        benchmark_key=benchmark_key,
        provider_key=provider_key,
        requirements=requirements,
        source_bindings=source_bindings,
        asset_metadata=asset_metadata,
        provider_identifier_coverage=provider_identifier_coverage,
    )


def validate_capabilities(
    *,
    strategy_key: str | None,
    universe_key: str | None,
    benchmark_key: str | None,
    provider_key: str,
    requirements: Sequence[Requirement],
    source_bindings: Mapping[str, str | None] | None = None,
    asset_metadata: Sequence[AssetMetadata] | None = None,
    provider_identifier_coverage: Sequence[ProviderIdentifierCoverage] | None = None,
) -> CapabilityCheckReport:
    bindings = _resolve_source_bindings(provider_key, source_bindings)
    universe_profile = _universe_profile(universe_key) if universe_key else None
    asset_classes = _asset_classes_from_metadata(
        universe_profile,
        asset_metadata,
    )

    if universe_profile is not None:
        _validate_universe_capabilities(
            strategy_key,
            universe_profile,
            requirements,
        )

    for requirement in requirements:
        bound_provider = bindings.get(requirement.source_role)
        if bound_provider is None:
            raise CapabilityValidationError(
                f"missing source binding for source_role={requirement.source_role}: "
                f"required capability {requirement.capability_key}"
            )
        if not _provider_satisfies(
            provider_key=bound_provider,
            source_role=requirement.source_role,
            capability_key=requirement.capability_key,
            asset_classes=asset_classes,
        ):
            raise CapabilityValidationError(
                f"provider={bound_provider} cannot satisfy "
                f"source_role={requirement.source_role}: "
                f"missing capability {requirement.capability_key}"
            )
    _validate_provider_identifier_coverage(
        requirements,
        bindings,
        provider_identifier_coverage,
    )

    return CapabilityCheckReport(
        strategy_key=strategy_key,
        universe_key=universe_key,
        benchmark_key=benchmark_key,
        provider_bindings=tuple(
            SourceBinding(role, key) for role, key in sorted(bindings.items())
        ),
        requirements=tuple(requirements),
    )


def requirements_for_strategy(strategy_key: str) -> tuple[Requirement, ...]:
    if strategy_key not in STRATEGY_INDICATORS:
        available = ", ".join(sorted(STRATEGY_INDICATORS))
        raise CapabilityValidationError(
            f"unknown strategy '{strategy_key}'; available: {available}"
        )
    indicator_requirements = _unique_requirements(
        requirement
        for indicator_key in STRATEGY_INDICATORS[strategy_key]
        for requirement in requirements_for_indicator(indicator_key)
    )
    return _unique_requirements(
        [*indicator_requirements, *STRATEGY_REQUIREMENTS.get(strategy_key, ())]
    )


def requirements_for_indicator(indicator_key: str) -> tuple[Requirement, ...]:
    try:
        return INDICATOR_REQUIREMENTS[indicator_key]
    except KeyError as exc:
        available = ", ".join(sorted(INDICATOR_REQUIREMENTS))
        raise CapabilityValidationError(
            f"unknown indicator '{indicator_key}'; available: {available}"
        ) from exc


def requirements_for_benchmark(benchmark_key: str) -> tuple[Requirement, ...]:
    try:
        return BENCHMARK_REQUIREMENTS[benchmark_key]
    except KeyError as exc:
        available = ", ".join(sorted(BENCHMARK_REQUIREMENTS))
        raise CapabilityValidationError(
            f"unknown benchmark '{benchmark_key}'; available: {available}"
        ) from exc


def requirements_for_live_workflow(live_workflow_key: str) -> tuple[Requirement, ...]:
    try:
        return LIVE_REQUIREMENTS[live_workflow_key]
    except KeyError as exc:
        available = ", ".join(sorted(LIVE_REQUIREMENTS))
        raise CapabilityValidationError(
            f"unknown live workflow '{live_workflow_key}'; available: {available}"
        ) from exc


def _resolve_source_bindings(
    provider_key: str,
    source_bindings: Mapping[str, str | None] | None,
) -> dict[str, str | None]:
    bindings = default_source_bindings(provider_key)
    if source_bindings:
        bindings.update(source_bindings)
    return bindings


def _universe_profile(universe_key: str | None) -> UniverseCapabilityProfile:
    try:
        return UNIVERSE_CAPABILITIES[universe_key or ""]
    except KeyError as exc:
        available = ", ".join(sorted(UNIVERSE_CAPABILITIES))
        raise CapabilityValidationError(
            f"unknown universe '{universe_key}'; available: {available}"
        ) from exc


def _validate_universe_capabilities(
    strategy_key: str | None,
    universe_profile: UniverseCapabilityProfile,
    requirements: Sequence[Requirement],
) -> None:
    available = set(universe_profile.capabilities)
    for requirement in requirements:
        if requirement.capability_key not in available:
            asset_classes = ", ".join(universe_profile.asset_classes)
            prefix = (
                f"strategy={strategy_key} cannot run with "
                if strategy_key is not None
                else "capability check failed for "
            )
            raise CapabilityValidationError(
                f"{prefix}universe={universe_profile.universe_key}: "
                f"missing capability {requirement.capability_key} "
                f"for asset_class={asset_classes}"
            )


def _asset_classes_from_metadata(
    universe_profile: UniverseCapabilityProfile | None,
    asset_metadata: Sequence[AssetMetadata] | None,
) -> tuple[str, ...]:
    if not asset_metadata:
        if universe_profile is not None:
            return universe_profile.asset_classes
        return (ASSET_CLASS_EQUITY,)

    asset_classes = tuple(
        sorted({item.asset_class for item in asset_metadata if item.asset_class})
    )
    if not asset_classes:
        if universe_profile is not None:
            return universe_profile.asset_classes
        return (ASSET_CLASS_EQUITY,)

    if universe_profile is not None:
        allowed = set(universe_profile.asset_classes)
        unexpected = [
            item
            for item in asset_metadata
            if item.asset_class and item.asset_class not in allowed
        ]
        if unexpected:
            sample = unexpected[0]
            raise CapabilityValidationError(
                f"universe={universe_profile.universe_key} asset metadata "
                f"contains unsupported asset_class={sample.asset_class} "
                f"for ticker={sample.ticker}"
            )
    return asset_classes


def _validate_provider_identifier_coverage(
    requirements: Sequence[Requirement],
    bindings: Mapping[str, str | None],
    provider_identifier_coverage: Sequence[ProviderIdentifierCoverage] | None,
) -> None:
    if not provider_identifier_coverage:
        return
    coverage_by_role_provider = {
        (coverage.source_role, coverage.provider_key): coverage
        for coverage in provider_identifier_coverage
    }
    for requirement in requirements:
        bound_provider = bindings.get(requirement.source_role)
        if bound_provider is None:
            continue
        coverage = coverage_by_role_provider.get(
            (requirement.source_role, bound_provider)
        )
        if coverage is None:
            continue
        missing = coverage.missing_tickers
        if missing:
            sample = ", ".join(missing[:5])
            suffix = "" if len(missing) <= 5 else f", +{len(missing) - 5} more"
            raise CapabilityValidationError(
                f"provider={bound_provider} missing provider identifier mapping "
                f"for source_role={requirement.source_role} "
                f"identifier_scheme={coverage.identifier_scheme}: "
                f"tickers={sample}{suffix}"
            )


def _provider_satisfies(
    *,
    provider_key: str,
    source_role: str,
    capability_key: str,
    asset_classes: Sequence[str],
) -> bool:
    for capability in PROVIDER_CAPABILITIES:
        if capability.provider_key != provider_key:
            continue
        if capability.source_role != source_role:
            continue
        if capability.capability_key != capability_key:
            continue
        if set(asset_classes).issubset(capability.asset_classes):
            return True
    return False


def _unique_requirements(requirements: Iterable[Requirement]) -> tuple[Requirement, ...]:
    unique: dict[tuple[str, str], Requirement] = {}
    for requirement in requirements:
        unique[(requirement.capability_key, requirement.source_role)] = requirement
    return tuple(unique.values())
