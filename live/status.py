from __future__ import annotations

from datetime import date
from math import isclose
from typing import Sequence

from .models import ExecutionGap, LivePortfolioStatus, PortfolioTarget, RealPosition


def build_live_status(
    model: Sequence[PortfolioTarget],
    shadow: Sequence[PortfolioTarget],
    real: Sequence[RealPosition],
    cash_balance: float,
    as_of_date: date | None = None,
    weight_tolerance: float = 0.001,
) -> LivePortfolioStatus:
    """Compare model, shadow, and real portfolio state.

    Model and shadow are target-weight snapshots. Real positions are valued with
    current_price when available and otherwise with their average buy price.
    """

    if weight_tolerance < 0:
        raise ValueError("weight_tolerance must not be negative")

    model_weights = _target_weights(model)
    shadow_weights = _target_weights(shadow)
    real_values = {position.ticker: position.market_value for position in real}
    real_shares = {position.ticker: float(position.shares) for position in real}

    invested_value = round(sum(real_values.values()), 6)
    total_value = round(invested_value + float(cash_balance), 6)
    real_weights = {
        ticker: (value / total_value if total_value > 0 else 0.0)
        for ticker, value in real_values.items()
    }

    tickers = sorted(set(model_weights) | set(shadow_weights) | set(real_weights))
    gaps = tuple(
        _build_gap(
            ticker=ticker,
            model_weight=model_weights.get(ticker, 0.0),
            shadow_weight=shadow_weights.get(ticker, 0.0),
            real_weight=real_weights.get(ticker, 0.0),
            real_value=real_values.get(ticker, 0.0),
            shares=real_shares.get(ticker, 0.0),
            weight_tolerance=weight_tolerance,
        )
        for ticker in tickers
    )

    resolved_date = as_of_date or _latest_target_date(shadow) or _latest_target_date(model)
    return LivePortfolioStatus(
        as_of_date=resolved_date,
        model_positions=sum(1 for target in model if target.target_weight > 0),
        shadow_positions=sum(1 for target in shadow if target.target_weight > 0),
        real_positions=sum(1 for position in real if position.shares > 0),
        cash_balance=round(float(cash_balance), 6),
        invested_value=invested_value,
        total_value=total_value,
        gaps=gaps,
    )


def _target_weights(targets: Sequence[PortfolioTarget]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for target in targets:
        ticker = target.ticker.strip().upper()
        weights[ticker] = weights.get(ticker, 0.0) + float(target.target_weight or 0.0)
    return weights


def _build_gap(
    ticker: str,
    model_weight: float,
    shadow_weight: float,
    real_weight: float,
    real_value: float,
    shares: float,
    weight_tolerance: float,
) -> ExecutionGap:
    weight_gap = round(shadow_weight - real_weight, 6)
    state = _classify_gap(
        model_weight=model_weight,
        shadow_weight=shadow_weight,
        real_weight=real_weight,
        weight_gap=weight_gap,
        weight_tolerance=weight_tolerance,
    )
    return ExecutionGap(
        ticker=ticker,
        model_weight=round(model_weight, 6),
        shadow_weight=round(shadow_weight, 6),
        real_weight=round(real_weight, 6),
        real_value=round(real_value, 6),
        state=state,
        weight_gap=weight_gap,
        shares=round(shares, 6),
    )


def _classify_gap(
    model_weight: float,
    shadow_weight: float,
    real_weight: float,
    weight_gap: float,
    weight_tolerance: float,
) -> str:
    has_model = model_weight > 0
    has_shadow = shadow_weight > 0
    has_real = real_weight > 0

    if has_model and not has_shadow:
        return "model_not_shadow"
    if has_shadow and not has_real:
        return "missing_in_real"
    if has_real and not has_shadow:
        return "extra_in_real"
    if has_shadow and has_real:
        if isclose(weight_gap, 0.0, rel_tol=0.0, abs_tol=weight_tolerance):
            return "aligned"
        if weight_gap > 0:
            return "underweight_real"
        return "overweight_real"
    return "aligned"


def _latest_target_date(targets: Sequence[PortfolioTarget]) -> date | None:
    dates = [target.as_of_date for target in targets if target.as_of_date is not None]
    return max(dates) if dates else None
