from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from math import sqrt
from typing import Any, Mapping, Optional, Sequence

import pandas as pd

from indicators import compute_indicators, create_indicators
from strategies import Strategy, StrategyContext


@dataclass(frozen=True)
class BacktestConfig:
    start_date: date
    end_date: date
    initial_capital: float = 10000.0
    rebalance_days: int = 21
    lookback_days: int = 252
    transaction_cost_bps: float = 10.0
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestTrade:
    trade_date: date
    ticker: str
    side: str
    shares: float
    price: float
    notional: float
    fee: float
    weight_before: float
    weight_after: float
    reason: str = "rebalance"


@dataclass(frozen=True)
class BacktestResult:
    strategy_key: str
    strategy_version: str
    start_date: date
    end_date: date
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: Mapping[str, float]
    config: Mapping[str, Any]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


def run_backtest(
    *,
    strategy: Strategy,
    config: BacktestConfig,
    universe: Sequence[str],
    prices: pd.DataFrame,
    fundamentals: pd.DataFrame,
    market_caps: pd.DataFrame,
    benchmark_prices: pd.DataFrame,
) -> BacktestResult:
    _validate_config(config)
    close_prices = _close_price_pivot(prices, config.start_date, config.end_date)
    if close_prices.empty:
        raise ValueError("no price data available for backtest date range")
    benchmark_close = _benchmark_close_series(
        benchmark_prices,
        config.start_date,
        config.end_date,
    )
    if benchmark_close.empty:
        raise ValueError("no benchmark data available for backtest date range")

    trading_dates = list(close_prices.index)
    rebalance_dates = set(_rebalance_dates(trading_dates, config.rebalance_days))
    cash = float(config.initial_capital)
    positions: dict[str, float] = {}
    trade_rows: list[BacktestTrade] = []
    equity_rows: list[dict[str, Any]] = []
    benchmark_start = float(benchmark_close.iloc[0])
    previous_value: Optional[float] = None
    previous_benchmark_value: Optional[float] = None

    for current_date in trading_dates:
        prices_today = close_prices.loc[current_date].dropna()
        value_before = _portfolio_value(cash, positions, prices_today)
        if current_date in rebalance_dates:
            target_weights = _target_weights_for_date(
                strategy=strategy,
                as_of_date=current_date,
                universe=universe,
                prices=prices,
                fundamentals=fundamentals,
                market_caps=market_caps,
                benchmark_prices=benchmark_prices,
                lookback_days=config.lookback_days,
            )
            cash, positions, trades = _rebalance(
                current_date=current_date,
                cash=cash,
                positions=positions,
                prices_today=prices_today,
                target_weights=target_weights,
                transaction_cost_bps=config.transaction_cost_bps,
            )
            trade_rows.extend(trades)

        portfolio_value = _portfolio_value(cash, positions, prices_today)
        benchmark_price = _last_price_on_or_before(benchmark_close, current_date)
        benchmark_value = (
            float(config.initial_capital) * float(benchmark_price) / benchmark_start
        )
        daily_return = (
            None
            if previous_value is None or previous_value == 0
            else (portfolio_value / previous_value) - 1
        )
        benchmark_daily_return = (
            None
            if previous_benchmark_value is None or previous_benchmark_value == 0
            else (benchmark_value / previous_benchmark_value) - 1
        )
        equity_rows.append(
            {
                "date": current_date,
                "portfolio_value": portfolio_value,
                "cash": cash,
                "benchmark_value": benchmark_value,
                "daily_return": daily_return,
                "benchmark_daily_return": benchmark_daily_return,
            }
        )
        previous_value = portfolio_value
        previous_benchmark_value = benchmark_value

    equity_curve = pd.DataFrame(equity_rows)
    equity_curve["drawdown"] = _drawdown(equity_curve["portfolio_value"])
    trades = pd.DataFrame([trade.__dict__ for trade in trade_rows])
    metrics = calculate_metrics(equity_curve)
    return BacktestResult(
        strategy_key=strategy.key,
        strategy_version=strategy.version,
        start_date=config.start_date,
        end_date=config.end_date,
        equity_curve=equity_curve,
        trades=trades,
        metrics=metrics,
        config={
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
            "initial_capital": config.initial_capital,
            "rebalance_days": config.rebalance_days,
            "lookback_days": config.lookback_days,
            "transaction_cost_bps": config.transaction_cost_bps,
            "params": dict(config.params),
        },
        diagnostics={
            "trading_days": len(trading_dates),
            "rebalance_count": len(rebalance_dates),
            "trade_count": len(trade_rows),
        },
    )


def calculate_metrics(equity_curve: pd.DataFrame) -> dict[str, float]:
    if equity_curve.empty:
        return {
            "total_return": 0.0,
            "benchmark_return": 0.0,
            "outperformance": 0.0,
            "volatility": 0.0,
            "max_drawdown": 0.0,
        }
    start_value = float(equity_curve["portfolio_value"].iloc[0])
    end_value = float(equity_curve["portfolio_value"].iloc[-1])
    benchmark_start = float(equity_curve["benchmark_value"].iloc[0])
    benchmark_end = float(equity_curve["benchmark_value"].iloc[-1])
    total_return = (end_value / start_value) - 1 if start_value else 0.0
    benchmark_return = (
        (benchmark_end / benchmark_start) - 1 if benchmark_start else 0.0
    )
    returns = pd.to_numeric(equity_curve["daily_return"], errors="coerce").dropna()
    volatility = float(returns.std(ddof=0) * sqrt(252)) if not returns.empty else 0.0
    max_drawdown = float(equity_curve["drawdown"].min())
    return {
        "total_return": float(total_return),
        "benchmark_return": float(benchmark_return),
        "outperformance": float(total_return - benchmark_return),
        "volatility": volatility,
        "max_drawdown": max_drawdown,
    }


def _target_weights_for_date(
    *,
    strategy: Strategy,
    as_of_date: date,
    universe: Sequence[str],
    prices: pd.DataFrame,
    fundamentals: pd.DataFrame,
    market_caps: pd.DataFrame,
    benchmark_prices: pd.DataFrame,
    lookback_days: int,
) -> dict[str, float]:
    indicator_start = as_of_date - timedelta(days=lookback_days + 7)
    indicator_prices = _date_window(prices, indicator_start, as_of_date, "date")
    indicator_fundamentals = _date_window(
        fundamentals,
        None,
        as_of_date,
        "report_date",
    )
    indicator_market_caps = _date_window(market_caps, None, as_of_date, "date")
    indicator_benchmark_prices = _date_window(
        benchmark_prices,
        indicator_start,
        as_of_date,
        "date",
    )
    indicators = compute_indicators(
        create_indicators(),
        prices=indicator_prices,
        fundamentals=indicator_fundamentals,
        market_caps=indicator_market_caps,
        as_of_date=as_of_date,
        params={
            "momentum_return": {"lookback_days": lookback_days},
            "relative_strength": {"lookback_days": lookback_days},
        },
    )
    result = strategy.run(
        StrategyContext(
            as_of_date=as_of_date,
            universe=universe,
            prices=indicator_prices,
            fundamentals=indicator_fundamentals,
            market_caps=indicator_market_caps,
            benchmark_prices=indicator_benchmark_prices,
            indicators={"default": indicators},
        )
    )
    selected = result.rankings[result.rankings["model_weight"] > 0]
    return {
        str(row.ticker): float(row.model_weight)
        for row in selected.itertuples(index=False)
    }


def _rebalance(
    *,
    current_date: date,
    cash: float,
    positions: dict[str, float],
    prices_today: pd.Series,
    target_weights: Mapping[str, float],
    transaction_cost_bps: float,
) -> tuple[float, dict[str, float], list[BacktestTrade]]:
    portfolio_value = _portfolio_value(cash, positions, prices_today)
    trades: list[BacktestTrade] = []
    next_positions = dict(positions)
    cost_rate = float(transaction_cost_bps) / 10000.0
    investable_value = portfolio_value * (1.0 - cost_rate)
    tradable = {
        ticker: weight
        for ticker, weight in target_weights.items()
        if ticker in prices_today.index and pd.notna(prices_today[ticker])
    }
    target_tickers = set(tradable)
    current_tickers = set(next_positions)
    for ticker in sorted(current_tickers.union(target_tickers)):
        price = float(prices_today[ticker]) if ticker in prices_today.index else None
        if price is None or price <= 0:
            continue
        current_shares = float(next_positions.get(ticker, 0.0))
        target_value = investable_value * float(tradable.get(ticker, 0.0))
        target_shares = target_value / price
        delta_shares = target_shares - current_shares
        if abs(delta_shares) < 1e-9:
            continue
        notional = delta_shares * price
        fee = abs(notional) * cost_rate
        weight_before = (
            (current_shares * price) / portfolio_value if portfolio_value else 0.0
        )
        cash -= notional + fee
        next_positions[ticker] = target_shares
        if abs(next_positions[ticker]) < 1e-9:
            next_positions.pop(ticker, None)
        value_after = _portfolio_value(cash, next_positions, prices_today)
        weight_after = (
            (next_positions.get(ticker, 0.0) * price) / value_after
            if value_after
            else 0.0
        )
        trades.append(
            BacktestTrade(
                trade_date=current_date,
                ticker=ticker,
                side="BUY" if delta_shares > 0 else "SELL",
                shares=abs(delta_shares),
                price=price,
                notional=abs(notional),
                fee=fee,
                weight_before=weight_before,
                weight_after=weight_after,
            )
        )
    return cash, next_positions, trades


def _close_price_pivot(
    prices: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    _require_columns(prices, {"ticker", "date", "close"}, "prices")
    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    frame = frame[(frame["date"] >= start_date) & (frame["date"] <= end_date)]
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.pivot_table(index="date", columns="ticker", values="close").sort_index()


def _benchmark_close_series(
    benchmark_prices: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> pd.Series:
    _require_columns(benchmark_prices, {"date", "close"}, "benchmark_prices")
    frame = benchmark_prices.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    frame = frame[(frame["date"] >= start_date) & (frame["date"] <= end_date)]
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    series = frame.sort_values("date").dropna(subset=["close"]).set_index("date")[
        "close"
    ]
    return series[~series.index.duplicated(keep="last")]


def _date_window(
    frame: pd.DataFrame,
    start_date: Optional[date],
    end_date: date,
    date_column: str,
) -> pd.DataFrame:
    if frame.empty or date_column not in frame.columns:
        return frame.copy()
    values = frame.copy()
    values[date_column] = pd.to_datetime(values[date_column]).dt.date
    if start_date is not None:
        values = values[values[date_column] >= start_date]
    return values[values[date_column] <= end_date]


def _portfolio_value(cash: float, positions: Mapping[str, float], prices: pd.Series) -> float:
    value = float(cash)
    for ticker, shares in positions.items():
        if ticker in prices.index and pd.notna(prices[ticker]):
            value += float(shares) * float(prices[ticker])
    return value


def _rebalance_dates(trading_dates: Sequence[date], rebalance_days: int) -> list[date]:
    dates: list[date] = []
    next_rebalance: Optional[date] = None
    for current_date in trading_dates:
        if next_rebalance is None or current_date >= next_rebalance:
            dates.append(current_date)
            next_rebalance = current_date + timedelta(days=rebalance_days)
    return dates


def _last_price_on_or_before(series: pd.Series, current_date: date) -> float:
    values = series[series.index <= current_date]
    if values.empty:
        raise ValueError(f"benchmark has no close price on or before {current_date}")
    return float(values.iloc[-1])


def _drawdown(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    high_watermark = numeric.cummax()
    return (numeric / high_watermark) - 1


def _validate_config(config: BacktestConfig) -> None:
    if config.start_date > config.end_date:
        raise ValueError("start_date must be on or before end_date")
    if config.initial_capital <= 0:
        raise ValueError("initial_capital must be greater than 0")
    if config.rebalance_days <= 0:
        raise ValueError("rebalance_days must be greater than 0")
    if config.lookback_days <= 0:
        raise ValueError("lookback_days must be greater than 0")
    if config.transaction_cost_bps < 0:
        raise ValueError("transaction_cost_bps must not be negative")


def _require_columns(frame: pd.DataFrame, columns: set[str], name: str) -> None:
    missing = columns.difference(frame.columns)
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(sorted(missing))}")
