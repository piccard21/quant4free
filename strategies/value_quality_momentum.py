from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose
from typing import Mapping

import pandas as pd

from .base import StrategyContext, StrategyResult


DEFAULT_FACTOR_WEIGHTS: dict[str, float] = {
    "value": 0.35,
    "quality": 0.30,
    "momentum": 0.35,
}

VALUE_INDICATORS = ("earnings_yield", "free_cash_flow_yield")
QUALITY_HIGH_INDICATORS = ("return_on_equity",)
QUALITY_LOW_INDICATORS = ("debt_to_equity",)
MOMENTUM_INDICATORS = ("momentum_return", "relative_strength")


@dataclass(frozen=True)
class ValueQualityMomentumStrategy:
    """First modular Value/Quality/Momentum ranking strategy."""

    factor_weights: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_FACTOR_WEIGHTS)
    )
    portfolio_size: int = 7
    key: str = "value_quality_momentum"
    version: str = "1.0"

    def __post_init__(self) -> None:
        _validate_factor_weights(self.factor_weights)
        if self.portfolio_size <= 0:
            raise ValueError("portfolio_size must be greater than 0")

    def run(self, context: StrategyContext) -> StrategyResult:
        indicators = _resolve_indicator_frame(context)
        _require_columns(
            indicators,
            {
                "ticker",
                *VALUE_INDICATORS,
                *QUALITY_HIGH_INDICATORS,
                *QUALITY_LOW_INDICATORS,
                *MOMENTUM_INDICATORS,
            },
        )

        rankings = indicators.copy()
        rankings = rankings[rankings["ticker"].isin(context.universe)].copy()
        rankings["value_score"] = _mean_columns(
            rankings,
            [_percentile_rank(rankings[column]) for column in VALUE_INDICATORS],
        )
        rankings["quality_score"] = _mean_columns(
            rankings,
            [
                *[
                    _percentile_rank(rankings[column])
                    for column in QUALITY_HIGH_INDICATORS
                ],
                *[
                    _percentile_rank(rankings[column], ascending=False)
                    for column in QUALITY_LOW_INDICATORS
                ],
            ],
        )
        rankings["momentum_score"] = _mean_columns(
            rankings,
            [_percentile_rank(rankings[column]) for column in MOMENTUM_INDICATORS],
        )
        rankings["composite_score"] = (
            rankings["value_score"] * self.factor_weights["value"]
            + rankings["quality_score"] * self.factor_weights["quality"]
            + rankings["momentum_score"] * self.factor_weights["momentum"]
        )
        rankings["rank"] = rankings["composite_score"].rank(
            method="first",
            ascending=False,
        )
        rankings["rank"] = rankings["rank"].astype("Int64")
        rankings = rankings.sort_values(
            ["composite_score", "ticker"],
            ascending=[False, True],
            na_position="last",
        ).reset_index(drop=True)
        rankings["model_weight"] = 0.0
        selected = rankings["rank"].le(self.portfolio_size)
        if selected.any():
            rankings.loc[selected, "model_weight"] = 1.0 / int(selected.sum())

        columns = [
            "ticker",
            "rank",
            "model_weight",
            "composite_score",
            "value_score",
            "quality_score",
            "momentum_score",
            *VALUE_INDICATORS,
            *QUALITY_HIGH_INDICATORS,
            *QUALITY_LOW_INDICATORS,
            *MOMENTUM_INDICATORS,
        ]
        return StrategyResult(
            strategy_key=self.key,
            strategy_version=self.version,
            as_of_date=context.as_of_date,
            rankings=rankings[columns],
            diagnostics={
                "portfolio_size": self.portfolio_size,
                "factor_weights": dict(self.factor_weights),
                "eligible_rows": int(rankings["composite_score"].notna().sum()),
                "selected_rows": int(selected.sum()),
            },
        )


def create_default_strategy(
    factor_weights: Mapping[str, float] | None = None,
    portfolio_size: int = 7,
) -> ValueQualityMomentumStrategy:
    return ValueQualityMomentumStrategy(
        factor_weights=factor_weights or DEFAULT_FACTOR_WEIGHTS,
        portfolio_size=portfolio_size,
    )


def _resolve_indicator_frame(context: StrategyContext) -> pd.DataFrame:
    if "default" in context.indicators:
        return context.indicators["default"]
    if len(context.indicators) == 1:
        return next(iter(context.indicators.values()))
    raise ValueError("context.indicators must contain a default indicator frame")


def _validate_factor_weights(weights: Mapping[str, float]) -> None:
    expected = set(DEFAULT_FACTOR_WEIGHTS)
    keys = set(weights)
    if keys != expected:
        missing = ", ".join(sorted(expected.difference(keys)))
        extra = ", ".join(sorted(keys.difference(expected)))
        details = []
        if missing:
            details.append(f"missing: {missing}")
        if extra:
            details.append(f"unknown: {extra}")
        raise ValueError(
            "factor_weights must contain value, quality, momentum "
            f"({'; '.join(details)})"
        )
    total = sum(float(value) for value in weights.values())
    if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("factor_weights must sum to 1.0")
    for key, value in weights.items():
        if float(value) < 0:
            raise ValueError(f"factor weight '{key}' must not be negative")


def _percentile_rank(values: pd.Series, ascending: bool = True) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.rank(pct=True, ascending=ascending)


def _mean_columns(frame: pd.DataFrame, columns: list[pd.Series]) -> pd.Series:
    if not columns:
        return pd.Series(pd.NA, index=frame.index, dtype="Float64")
    return pd.concat(columns, axis=1).mean(axis=1, skipna=False)


def _require_columns(frame: pd.DataFrame, columns: set[str]) -> None:
    missing = columns.difference(frame.columns)
    if missing:
        raise ValueError(
            "indicator frame missing required columns: "
            + ", ".join(sorted(missing))
        )
