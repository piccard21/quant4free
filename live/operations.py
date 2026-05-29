from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional, Sequence

import pandas as pd
from sqlalchemy import Engine, bindparam, text

from shared.db import get_engine

if TYPE_CHECKING:
    from cli.orchestration import StrategyRunArtifacts


TRADE_FEE = 1.0
TRADE_BUCKET_THRESHOLD_PCT = 0.20
DEFAULT_MAX_FUNDING_SELL_PCT = 0.20


@dataclass(frozen=True)
class OperationalSettings:
    strategy_version: str
    value_weight: float
    quality_weight: float
    momentum_weight: float
    momentum_return_weight: float
    momentum_rel_strength_weight: float
    min_price: float
    min_market_cap: int
    sma_days: int
    return_lookback_days: int
    buy_rank_threshold: int
    sell_rank_threshold: int
    portfolio_size: int
    max_sector_positions: int
    min_holding_months: int
    max_trades_per_month: int
    daily_fundamental_limit: int
    fundamental_refresh_hours: int
    tax_rate: float
    max_funding_sell_pct: float


@dataclass(frozen=True)
class OperationalArtifacts:
    model: pd.DataFrame
    shadow: pd.DataFrame
    rebalance: pd.DataFrame
    decision_log: pd.DataFrame
    trade_plan: pd.DataFrame
    trade_plan_summary: dict[str, Any]


@dataclass(frozen=True)
class OperationalPersistenceResult:
    as_of_date: date
    model_rows: int
    shadow_rows: int
    rebalance_rows: int
    decision_rows: int
    trade_plan_rows: int
    executable_buys: int
    executable_sells: int
    skipped_trades: int
    dry_run: bool = False


class OperationalRepository:
    """Read/write canonical operational artifact tables."""

    def __init__(self, engine: Optional[Engine] = None) -> None:
        self.engine = engine or get_engine()

    def load_active_settings(self) -> OperationalSettings:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        strategy_version,
                        value_weight,
                        quality_weight,
                        momentum_weight,
                        momentum_return_weight,
                        momentum_rel_strength_weight,
                        min_price,
                        min_market_cap,
                        sma_days,
                        return_lookback_days,
                        buy_rank_threshold,
                        sell_rank_threshold,
                        portfolio_size,
                        max_sector_positions,
                        min_holding_months,
                        max_trades_per_month,
                        daily_fundamental_limit,
                        fundamental_refresh_hours,
                        tax_rate,
                        max_funding_sell_pct
                    FROM strategy_instances
                    WHERE is_active = 1
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()

        if row is None:
            raise ValueError("no active strategy_instances row found")
        settings = OperationalSettings(
            strategy_version=str(row["strategy_version"]),
            value_weight=float(row["value_weight"]),
            quality_weight=float(row["quality_weight"]),
            momentum_weight=float(row["momentum_weight"]),
            momentum_return_weight=float(row["momentum_return_weight"]),
            momentum_rel_strength_weight=float(row["momentum_rel_strength_weight"]),
            min_price=float(row["min_price"]),
            min_market_cap=int(row["min_market_cap"]),
            sma_days=int(row["sma_days"]),
            return_lookback_days=int(row["return_lookback_days"]),
            buy_rank_threshold=int(row["buy_rank_threshold"]),
            sell_rank_threshold=int(row["sell_rank_threshold"]),
            portfolio_size=int(row["portfolio_size"]),
            max_sector_positions=int(row["max_sector_positions"]),
            min_holding_months=int(row["min_holding_months"]),
            max_trades_per_month=int(row["max_trades_per_month"]),
            daily_fundamental_limit=int(row["daily_fundamental_limit"]),
            fundamental_refresh_hours=int(row["fundamental_refresh_hours"]),
            tax_rate=float(row["tax_rate"]),
            max_funding_sell_pct=float(
                row["max_funding_sell_pct"] or DEFAULT_MAX_FUNDING_SELL_PCT
            ),
        )
        validate_operational_settings(settings)
        return settings

    def load_previous_shadow(self, as_of_date: date) -> pd.DataFrame:
        with self.engine.connect() as conn:
            previous_date = conn.execute(
                text(
                    """
                    SELECT MAX(as_of_date)
                    FROM portfolio_target_items
                    WHERE snapshot_type = 'shadow'
                      AND as_of_date < :as_of_date
                    """
                ),
                {"as_of_date": as_of_date},
            ).scalar()
            if previous_date is None:
                return pd.DataFrame()
            return pd.read_sql(
                text(
                    """
                    SELECT
                        as_of_date,
                        ticker,
                        portfolio_rank,
                        source_rank,
                        sector,
                        target_weight,
                        final_score,
                        value_score,
                        quality_score,
                        momentum_score,
                        trend_positive,
                        buy_eligible,
                        holding_start_date
                    FROM portfolio_target_items
                    WHERE as_of_date = :as_of_date
                      AND snapshot_type = 'shadow'
                    ORDER BY portfolio_rank, ticker
                    """
                ),
                conn,
                params={"as_of_date": previous_date},
            )

    def load_real_positions(self) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(
                text(
                    """
                    SELECT ticker, shares, buy_price, opened_at, is_open
                    FROM live_positions
                    WHERE is_open = 1
                    ORDER BY opened_at, ticker
                    """
                ),
                conn,
            )

    def load_cash_balance(self) -> float:
        with self.engine.connect() as conn:
            value = conn.execute(
                text(
                    """
                    SELECT cash_balance
                    FROM live_cash_balances
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """
                )
            ).scalar()
        return float(value or 0.0)

    def load_latest_prices(
        self,
        tickers: Sequence[str],
        as_of_date: date,
    ) -> pd.DataFrame:
        normalized = sorted({str(ticker).upper() for ticker in tickers if ticker})
        if not normalized:
            return pd.DataFrame(columns=["ticker", "current_price"])
        sql = (
            text(
                """
                SELECT dc.ticker, dc.close AS current_price
                FROM asset_price_bars dc
                JOIN (
                    SELECT ticker, MAX(date) AS max_date
                    FROM asset_price_bars
                    WHERE date <= :as_of_date
                      AND ticker IN :tickers
                    GROUP BY ticker
                ) latest
                  ON latest.ticker = dc.ticker
                 AND latest.max_date = dc.date
                ORDER BY dc.ticker
                """
            )
            .bindparams(bindparam("tickers", expanding=True))
        )
        with self.engine.connect() as conn:
            return pd.read_sql(
                sql,
                conn,
                params={"tickers": normalized, "as_of_date": as_of_date},
            )

    def assert_artifacts_are_new(self, as_of_date: date) -> None:
        checks = {
            "portfolio_target_items.model": (
                """
                SELECT 1 FROM portfolio_target_items
                WHERE as_of_date = :as_of_date AND snapshot_type = 'model'
                LIMIT 1
                """
            ),
            "portfolio_target_items.shadow": (
                """
                SELECT 1 FROM portfolio_target_items
                WHERE as_of_date = :as_of_date AND snapshot_type = 'shadow'
                LIMIT 1
                """
            ),
            "strategy_config_snapshots": (
                "SELECT 1 FROM strategy_config_snapshots "
                "WHERE as_of_date = :as_of_date LIMIT 1"
            ),
            "live_rebalance_items": (
                "SELECT 1 FROM live_rebalance_items "
                "WHERE as_of_date = :as_of_date LIMIT 1"
            ),
            "live_decision_items": (
                "SELECT 1 FROM live_decision_items WHERE as_of_date = :as_of_date LIMIT 1"
            ),
            "live_trade_plans": (
                "SELECT 1 FROM live_trade_plans "
                "WHERE as_of_date = :as_of_date LIMIT 1"
            ),
            "live_trade_plan_items": (
                "SELECT 1 FROM live_trade_plan_items "
                "WHERE as_of_date = :as_of_date LIMIT 1"
            ),
        }
        existing = []
        with self.engine.connect() as conn:
            for name, sql in checks.items():
                if conn.execute(text(sql), {"as_of_date": as_of_date}).scalar() is not None:
                    existing.append(name)
        if existing:
            raise ValueError(
                f"operational artifacts already exist for {as_of_date}: "
                + ", ".join(existing)
            )

    def save_artifacts(
        self,
        settings: OperationalSettings,
        artifacts: OperationalArtifacts,
    ) -> None:
        as_of_date = artifacts.trade_plan_summary["as_of_date"]
        with self.engine.begin() as conn:
            _insert_rows(conn, "strategy_config_snapshots", [_settings_payload(as_of_date, settings)])
            _insert_rows(conn, "portfolio_target_items", artifacts.model)
            _insert_rows(conn, "portfolio_target_items", artifacts.shadow)
            _insert_rows(conn, "live_rebalance_items", artifacts.rebalance)
            _insert_rows(conn, "live_decision_items", artifacts.decision_log)
            _insert_rows(conn, "live_trade_plans", [artifacts.trade_plan_summary])
            _insert_rows(conn, "live_trade_plan_items", artifacts.trade_plan)


class OperationalPersistenceService:
    """Build and optionally persist monthly operational artifacts."""

    def __init__(self, repository: Optional[OperationalRepository] = None) -> None:
        self.repository = repository or OperationalRepository()

    def build(
        self,
        strategy_artifacts: StrategyRunArtifacts,
        settings: OperationalSettings | None = None,
    ) -> tuple[OperationalArtifacts, OperationalSettings]:
        resolved_settings = settings or self.repository.load_active_settings()
        as_of_date = strategy_artifacts.as_of_date
        model = build_model_snapshot(strategy_artifacts)
        previous_shadow = self.repository.load_previous_shadow(as_of_date)
        rankings = build_ranking_frame(strategy_artifacts)
        shadow = build_shadow_snapshot(
            model=model,
            previous=previous_shadow,
            rankings=rankings,
            as_of_date=as_of_date,
            settings=resolved_settings,
        )
        real = self.repository.load_real_positions()
        rebalance = build_rebalance_suggestions(
            shadow=shadow,
            real=real,
            rankings=rankings,
            as_of_date=as_of_date,
            settings=resolved_settings,
        )
        decision_log = build_decision_log(
            rebalance=rebalance,
            rankings=rankings,
            settings=resolved_settings,
        )
        tickers = _trade_price_tickers(rebalance, real)
        prices = self.repository.load_latest_prices(tickers, as_of_date)
        trade_plan, summary = build_trade_plan(
            as_of_date=as_of_date,
            rebalance=rebalance,
            real=real,
            prices=prices,
            cash_before=self.repository.load_cash_balance(),
            settings=resolved_settings,
        )
        return (
            OperationalArtifacts(
                model=model,
                shadow=shadow,
                rebalance=rebalance,
                decision_log=decision_log,
                trade_plan=trade_plan,
                trade_plan_summary=summary,
            ),
            resolved_settings,
        )

    def run(
        self,
        strategy_artifacts: StrategyRunArtifacts,
        persist: bool = False,
    ) -> OperationalPersistenceResult:
        operational_artifacts, settings = self.build(strategy_artifacts)
        if persist:
            self.repository.assert_artifacts_are_new(strategy_artifacts.as_of_date)
            self.repository.save_artifacts(settings, operational_artifacts)
        summary = operational_artifacts.trade_plan_summary
        return OperationalPersistenceResult(
            as_of_date=strategy_artifacts.as_of_date,
            model_rows=len(operational_artifacts.model),
            shadow_rows=len(operational_artifacts.shadow),
            rebalance_rows=len(operational_artifacts.rebalance),
            decision_rows=len(operational_artifacts.decision_log),
            trade_plan_rows=len(operational_artifacts.trade_plan),
            executable_buys=int(summary["executable_buys"]),
            executable_sells=int(summary["executable_sells"]),
            skipped_trades=int(summary["skipped_trades"]),
            dry_run=not persist,
        )


def validate_operational_settings(settings: OperationalSettings) -> None:
    if round(settings.value_weight + settings.quality_weight + settings.momentum_weight, 5) != 1.0:
        raise ValueError("factor weights must sum to 1.0")
    if settings.portfolio_size <= 0:
        raise ValueError("portfolio_size must be positive")
    if settings.max_sector_positions <= 0:
        raise ValueError("max_sector_positions must be positive")
    if settings.min_holding_months < 0:
        raise ValueError("min_holding_months must not be negative")
    if settings.max_trades_per_month <= 0:
        raise ValueError("max_trades_per_month must be positive")
    if not 0 <= settings.tax_rate <= 1:
        raise ValueError("tax_rate must be between 0 and 1")
    if not 0 <= settings.max_funding_sell_pct <= 1:
        raise ValueError("max_funding_sell_pct must be between 0 and 1")


def build_model_snapshot(artifacts: StrategyRunArtifacts) -> pd.DataFrame:
    model = artifacts.model_portfolio.copy()
    sectors = {
        item.ticker.upper(): item.sector
        for item in artifacts.strategy_result.rankings.itertuples()
        if hasattr(item, "sector")
    }
    if not sectors:
        sectors = _sector_map_from_provider_members(artifacts)

    rows = []
    for _, row in model.sort_values(["rank", "ticker"]).iterrows():
        ticker = str(row["ticker"]).upper()
        rows.append(
            {
                "as_of_date": artifacts.as_of_date,
                "snapshot_type": "model",
                "ticker": ticker,
                "portfolio_rank": _optional_int(row["rank"]),
                "source_rank": _optional_int(row["rank"]),
                "sector": sectors.get(ticker),
                "target_weight": _optional_float(row["model_weight"]),
                "final_score": _optional_float(row["composite_score"]),
                "value_score": _optional_float(row["value_score"]),
                "quality_score": _optional_float(row["quality_score"]),
                "momentum_score": _optional_float(row["momentum_score"]),
                "trend_positive": 1,
                "buy_eligible": 1,
                "holding_start_date": None,
                "created_at": datetime.now(),
            }
        )
    return pd.DataFrame(rows)


def build_ranking_frame(artifacts: StrategyRunArtifacts) -> pd.DataFrame:
    rankings = artifacts.strategy_result.rankings.copy()
    sectors = _sector_map_from_provider_members(artifacts)
    rankings["ticker"] = rankings["ticker"].astype(str).str.upper()
    rankings["source_rank"] = rankings["rank"]
    rankings["final_score"] = rankings["composite_score"]
    rankings["sector"] = rankings["ticker"].map(sectors)
    rankings["trend_positive"] = 1
    rankings["buy_eligible"] = rankings["model_weight"].gt(0).astype(int)
    return rankings


def build_shadow_snapshot(
    model: pd.DataFrame,
    previous: pd.DataFrame,
    rankings: pd.DataFrame,
    as_of_date: date,
    settings: OperationalSettings,
) -> pd.DataFrame:
    if model.empty and previous.empty:
        return pd.DataFrame()

    model = _normalize_snapshot_frame(model)
    previous = _normalize_snapshot_frame(previous)
    rankings = _normalize_ranking_frame(rankings)
    as_of_ts = pd.to_datetime(as_of_date)
    min_hold_days = int(settings.min_holding_months * 30)
    configured_max_changes = int(settings.max_trades_per_month)
    portfolio_size = int(settings.portfolio_size)
    previous_position_count = int(len(previous))
    missing_positions = max(0, portfolio_size - previous_position_count)
    max_changes = max(configured_max_changes, missing_positions)

    model_tickers = set(model["ticker"].tolist()) if not model.empty else set()
    previous_tickers = set(previous["ticker"].tolist()) if not previous.empty else set()

    keep = set()
    sell_candidates = []
    for _, row in previous.iterrows():
        ticker = row["ticker"]
        holding_start = row.get("holding_start_date")
        if pd.isna(holding_start):
            holding_start = row["as_of_date"]
        holding_days = int((as_of_ts - pd.to_datetime(holding_start)).days)
        if ticker in model_tickers or holding_days < min_hold_days:
            keep.add(ticker)
        else:
            sell_candidates.append(ticker)

    buy_candidates = [
        row["ticker"]
        for _, row in model.sort_values(["portfolio_rank", "ticker"]).iterrows()
        if row["ticker"] not in previous_tickers
    ]

    used_changes = 0
    executed_sells = set()
    for ticker in sell_candidates:
        if used_changes >= max_changes:
            keep.add(ticker)
            continue
        executed_sells.add(ticker)
        used_changes += 1

    current = (previous_tickers - executed_sells) | keep
    if len(current) > portfolio_size:
        rank_map = {
            row["ticker"]: _optional_int(row.get("source_rank")) or 999999
            for _, row in rankings.iterrows()
        }
        ordered = sorted(
            current,
            key=lambda ticker: (
                0 if ticker in model_tickers else 1,
                rank_map.get(ticker, 999999),
                ticker,
            ),
        )
        current = set(ordered[:portfolio_size])

    for ticker in buy_candidates:
        if used_changes >= max_changes:
            continue
        if len(current) >= portfolio_size:
            continue
        current.add(ticker)
        used_changes += 1

    previous_map = previous.set_index("ticker").to_dict(orient="index") if not previous.empty else {}
    model_map = model.set_index("ticker").to_dict(orient="index") if not model.empty else {}
    ranking_map = rankings.set_index("ticker").to_dict(orient="index") if not rankings.empty else {}
    ordered_model = [ticker for ticker in model["ticker"].tolist() if ticker in current]
    ordered_other = sorted([ticker for ticker in current if ticker not in set(ordered_model)])

    rows = []
    for ticker in ordered_model + ordered_other:
        base = dict(ranking_map.get(ticker) or model_map.get(ticker) or previous_map[ticker])
        holding_start = (
            previous_map[ticker].get("holding_start_date")
            if ticker in previous_map
            else as_of_date
        )
        if pd.isna(holding_start):
            holding_start = previous_map[ticker].get("as_of_date")
        rows.append(
            {
                "as_of_date": as_of_date,
                "snapshot_type": "shadow",
                "ticker": ticker,
                "portfolio_rank": len(rows) + 1,
                "source_rank": _optional_int(base.get("source_rank") or base.get("rank")),
                "sector": _optional_string(base.get("sector")),
                "target_weight": 1.0 / max(1, len(current)),
                "final_score": _optional_float(base.get("final_score") or base.get("composite_score")),
                "value_score": _optional_float(base.get("value_score")),
                "quality_score": _optional_float(base.get("quality_score")),
                "momentum_score": _optional_float(base.get("momentum_score")),
                "trend_positive": _optional_int(base.get("trend_positive")) or 0,
                "buy_eligible": _optional_int(base.get("buy_eligible")) or 0,
                "holding_start_date": pd.to_datetime(holding_start).date(),
                "created_at": datetime.now(),
            }
        )
    return pd.DataFrame(rows)


def build_rebalance_suggestions(
    shadow: pd.DataFrame,
    real: pd.DataFrame,
    rankings: pd.DataFrame,
    as_of_date: date,
    settings: OperationalSettings,
) -> pd.DataFrame:
    shadow = _normalize_snapshot_frame(shadow)
    real = _normalize_real_frame(real)
    rankings = _normalize_ranking_frame(rankings)
    shadow_tickers = set(shadow["ticker"].tolist()) if not shadow.empty else set()
    real_tickers = set(real["ticker"].tolist()) if not real.empty else set()
    ranking_map = rankings.set_index("ticker").to_dict(orient="index") if not rankings.empty else {}
    as_of_ts = pd.to_datetime(as_of_date)
    min_hold_days = int(settings.min_holding_months * 30)
    max_changes = max(
        int(settings.max_trades_per_month),
        max(0, int(settings.portfolio_size) - int(len(real))),
    )
    rows = []

    for _, row in shadow.iterrows():
        ticker = row["ticker"]
        sector = _optional_string(row.get("sector")) or _optional_string(ranking_map.get(ticker, {}).get("sector")) or "UNKNOWN"
        if ticker in real_tickers:
            real_row = real.loc[real["ticker"] == ticker].iloc[0]
            opened_at = real_row["opened_at"]
            holding_days = int((as_of_ts - pd.to_datetime(opened_at)).days) if pd.notna(opened_at) else None
            rows.append(
                _rebalance_row(
                    as_of_date,
                    ticker,
                    sector,
                    "HOLD",
                    "already_in_real_portfolio",
                    row.get("source_rank"),
                    row.get("target_weight"),
                    real_row.get("shares"),
                    opened_at,
                    holding_days,
                    1,
                )
            )
        else:
            rows.append(
                _rebalance_row(
                    as_of_date,
                    ticker,
                    sector,
                    "BUY",
                    "in_shadow_not_in_real",
                    row.get("source_rank"),
                    row.get("target_weight"),
                    None,
                    None,
                    None,
                    1,
                )
            )

    for _, row in real.iterrows():
        ticker = row["ticker"]
        if ticker in shadow_tickers:
            continue
        opened_at = row["opened_at"]
        holding_days = int((as_of_ts - pd.to_datetime(opened_at)).days) if pd.notna(opened_at) else None
        min_hold_ok = 1 if holding_days is None or holding_days >= min_hold_days else 0
        ranking = ranking_map.get(ticker, {})
        rows.append(
            _rebalance_row(
                as_of_date,
                ticker,
                _optional_string(ranking.get("sector")) or "UNKNOWN",
                "SELL" if min_hold_ok else "HOLD",
                "in_real_not_in_shadow" if min_hold_ok else "min_hold_not_reached",
                ranking.get("source_rank"),
                None,
                row.get("shares"),
                opened_at,
                holding_days,
                min_hold_ok,
            )
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    used_changes = 0
    for idx in result.loc[result["action"] == "SELL"].index:
        if used_changes < max_changes:
            used_changes += 1
        else:
            result.loc[idx, "action"] = "HOLD"
            result.loc[idx, "reason"] = "turnover_limit_reached"

    buy_candidates = result.loc[result["action"] == "BUY"].sort_values(
        ["source_rank", "ticker"],
        na_position="last",
    )
    for idx in buy_candidates.index:
        if used_changes < max_changes:
            used_changes += 1
        else:
            result.loc[idx, "action"] = "HOLD"
            result.loc[idx, "reason"] = "turnover_limit_reached"

    result["sort_key"] = result["action"].map({"SELL": 1, "BUY": 2, "HOLD": 3}).fillna(99)
    return result.sort_values(["sort_key", "source_rank", "ticker"], na_position="last").drop(columns=["sort_key"]).reset_index(drop=True)


def build_decision_log(
    rebalance: pd.DataFrame,
    rankings: pd.DataFrame,
    settings: OperationalSettings,
) -> pd.DataFrame:
    if rebalance.empty:
        return pd.DataFrame()
    rankings = _normalize_ranking_frame(rankings)
    score_cols = [
        "ticker",
        "source_rank",
        "final_score",
        "value_score",
        "quality_score",
        "momentum_score",
        "trend_positive",
    ]
    merged = rebalance.merge(
        rankings[score_cols].drop_duplicates("ticker"),
        on="ticker",
        how="left",
        suffixes=("", "_score"),
    )
    if "source_rank_score" in merged.columns:
        merged["source_rank"] = merged["source_rank"].fillna(merged["source_rank_score"])
    rows = []
    for _, row in merged.iterrows():
        rows.append(
            {
                "as_of_date": row["as_of_date"],
                "ticker": row["ticker"],
                "action": row["action"],
                "reason": row["reason"],
                "source_rank": _optional_int(row.get("source_rank")),
                "final_score": _optional_float(row.get("final_score")),
                "value_score": _optional_float(row.get("value_score")),
                "quality_score": _optional_float(row.get("quality_score")),
                "momentum_score": _optional_float(row.get("momentum_score")),
                "trend_positive": _optional_int(row.get("trend_positive")) or 0,
                "holding_days": _optional_int(row.get("holding_days")),
                "min_hold_ok": _optional_int(row.get("min_hold_ok")) or 1,
                "strategy_version": settings.strategy_version,
                "created_at": datetime.now(),
            }
        )
    return pd.DataFrame(rows)


def build_trade_plan(
    as_of_date: date,
    rebalance: pd.DataFrame,
    real: pd.DataFrame,
    prices: pd.DataFrame,
    cash_before: float,
    settings: OperationalSettings,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rebalance = rebalance.copy()
    real = _normalize_real_frame(real)
    prices = _normalize_prices_frame(prices)
    shares_state, price_map = _build_trade_maps(real, prices)
    portfolio_value, invested_value = _compute_portfolio_values(real, prices, cash_before)
    portfolio_size = int(settings.portfolio_size)
    position_change_limit = max(
        int(settings.max_trades_per_month),
        max(0, portfolio_size - len(real)),
    )
    max_funding_sell_pct = max(0.0, min(1.0, float(settings.max_funding_sell_pct)))
    bucket_size = portfolio_value / float(portfolio_size)

    cash = _round_money(cash_before)
    execution_order = 1
    used_position_changes = 0
    used_funding_value_by_ticker: dict[str, float] = {}
    rows = []

    for _, row in rebalance.loc[rebalance["action"] == "SELL"].iterrows():
        ticker = row["ticker"]
        price = float(price_map.get(ticker, 0.0) or 0.0)
        current_shares = float(shares_state.get(ticker, 0.0) or 0.0)
        if used_position_changes >= position_change_limit:
            rows.append(_trade_row(as_of_date, ticker, "SELL", row["reason"], None, row, current_shares, None, price or None, None, 0.0, None, bucket_size, cash, cash, 0, "position_change_limit_reached"))
            continue
        if current_shares <= 0 or price <= 0:
            rows.append(_trade_row(as_of_date, ticker, "SELL", row["reason"], None, row, current_shares or None, None, price or None, None, 0.0, None, bucket_size, cash, cash, 0, "price_or_shares_missing"))
            continue
        gross_amount = _round_money(current_shares * price)
        net_amount = _round_money(gross_amount - TRADE_FEE)
        cash_after = _round_money(cash + net_amount)
        rows.append(_trade_row(as_of_date, ticker, "SELL", row["reason"], execution_order, row, current_shares, current_shares, price, gross_amount, TRADE_FEE, net_amount, bucket_size, cash, cash_after, 1, None))
        shares_state[ticker] = 0.0
        cash = cash_after
        execution_order += 1
        used_position_changes += 1

    buy_rows = rebalance.loc[rebalance["action"] == "BUY"].sort_values(
        ["source_rank", "ticker"],
        na_position="last",
    )
    for _, row in buy_rows.iterrows():
        ticker = row["ticker"]
        price = float(price_map.get(ticker, 0.0) or 0.0)
        if used_position_changes >= position_change_limit:
            rows.append(_trade_row(as_of_date, ticker, "BUY", row["reason"], None, row, None, None, price or None, None, 0.0, None, bucket_size, cash, cash, 0, "position_change_limit_reached"))
            continue
        if price <= 0:
            rows.append(_trade_row(as_of_date, ticker, "BUY", row["reason"], None, row, None, None, None, None, 0.0, None, bucket_size, cash, cash, 0, "price_missing"))
            continue

        planned_shares = int((bucket_size - TRADE_FEE) // price)
        gross_amount = _round_money(planned_shares * price) if planned_shares > 0 else 0.0
        buy_cash_needed = _round_money(gross_amount + TRADE_FEE) if planned_shares > 0 else 0.0
        if planned_shares <= 0:
            rows.append(_trade_row(as_of_date, ticker, "BUY", row["reason"], None, row, None, None, price, None, 0.0, None, bucket_size, cash, cash, 0, "shares_zero_after_rounding"))
            continue

        funding_rows = []
        if cash < buy_cash_needed:
            ok, funding_rows, _funded_cash = _simulate_funding_for_buy(
                buy_required_cash=buy_cash_needed,
                current_cash=cash,
                funding_candidates=_build_funding_candidates(
                    rebalance,
                    shares_state,
                    price_map,
                    bucket_size,
                    max_funding_sell_pct,
                    {ticker},
                ),
                shares_state=shares_state,
                used_funding_value_by_ticker=used_funding_value_by_ticker,
                max_funding_sell_pct=max_funding_sell_pct,
                bucket_size=bucket_size,
            )
            if not ok:
                rows.append(_trade_row(as_of_date, ticker, "BUY", row["reason"], None, row, None, planned_shares, price, gross_amount, TRADE_FEE, buy_cash_needed, bucket_size, cash, cash, 0, "insufficient_cash_after_limited_funding"))
                continue

        for funding in funding_rows:
            cash_after_funding = _round_money(cash + funding["net_amount"])
            rows.append(
                _trade_row(
                    as_of_date,
                    funding["ticker"],
                    "ADJUST_SELL",
                    "funding_new_buy_limited_pct",
                    execution_order,
                    funding,
                    funding["current_shares"],
                    funding["planned_shares"],
                    funding["price"],
                    funding["gross_amount"],
                    TRADE_FEE,
                    funding["net_amount"],
                    bucket_size,
                    cash,
                    cash_after_funding,
                    1,
                    None,
                )
            )
            shares_state[funding["ticker"]] = _round_money(shares_state.get(funding["ticker"], 0.0) - funding["planned_shares"])
            used_funding_value_by_ticker[funding["ticker"]] = _round_money(
                used_funding_value_by_ticker.get(funding["ticker"], 0.0) + funding["gross_amount"]
            )
            cash = cash_after_funding
            execution_order += 1

        if cash < buy_cash_needed:
            rows.append(_trade_row(as_of_date, ticker, "BUY", row["reason"], None, row, None, planned_shares, price, gross_amount, TRADE_FEE, buy_cash_needed, bucket_size, cash, cash, 0, "insufficient_cash_after_funding_guard"))
            continue

        cash_after_buy = _round_money(cash - buy_cash_needed)
        rows.append(_trade_row(as_of_date, ticker, "BUY", row["reason"], execution_order, row, None, planned_shares, price, gross_amount, TRADE_FEE, buy_cash_needed, bucket_size, cash, cash_after_buy, 1, None))
        cash = cash_after_buy
        execution_order += 1
        used_position_changes += 1

    planned_tickers = {row["ticker"] for row in rows}
    for _, row in rebalance.iterrows():
        ticker = row["ticker"]
        if ticker in planned_tickers:
            continue
        rows.append(
            _trade_row(
                as_of_date,
                ticker,
                "HOLD",
                row["reason"],
                None,
                row,
                shares_state.get(ticker),
                None,
                price_map.get(ticker),
                None,
                0.0,
                None,
                bucket_size,
                cash,
                cash,
                0,
                row["reason"],
            )
        )

    rows = _aggregate_funding_rows(rows)
    trade_df = pd.DataFrame(rows)
    if trade_df.empty:
        trade_df = pd.DataFrame(columns=_trade_columns())
    dupes = trade_df[trade_df.duplicated(subset=["as_of_date", "ticker"], keep=False)]
    if not dupes.empty:
        raise ValueError("duplicate trade-plan rows found: " + ", ".join(sorted(dupes["ticker"].astype(str).unique())))
    executable_buys = int(((trade_df["action"].isin(["BUY", "ADJUST_BUY"])) & (trade_df["is_executable"] == 1)).sum())
    executable_sells = int(((trade_df["action"].isin(["SELL", "ADJUST_SELL"])) & (trade_df["is_executable"] == 1)).sum())
    skipped_trades = int(((trade_df["action"] != "HOLD") & (trade_df["is_executable"] == 0)).sum())
    positions_before = int(len(real))
    positions_after = positions_before - int(((trade_df["action"] == "SELL") & (trade_df["is_executable"] == 1)).sum()) + int(((trade_df["action"] == "BUY") & (trade_df["is_executable"] == 1)).sum())
    summary = {
        "as_of_date": as_of_date,
        "portfolio_value_before": float(portfolio_value),
        "invested_value_before": float(invested_value),
        "cash_before": float(cash_before),
        "cash_after": float(cash),
        "bucket_size": float(bucket_size),
        "target_positions": int(settings.portfolio_size),
        "positions_before": positions_before,
        "positions_after": positions_after,
        "total_sell_gross": float(trade_df.loc[(trade_df["action"].isin(["SELL", "ADJUST_SELL"])) & (trade_df["is_executable"] == 1), "gross_amount"].fillna(0.0).sum()),
        "total_buy_gross": float(trade_df.loc[(trade_df["action"].isin(["BUY", "ADJUST_BUY"])) & (trade_df["is_executable"] == 1), "gross_amount"].fillna(0.0).sum()),
        "total_fees": float(trade_df.loc[trade_df["is_executable"] == 1, "fee"].fillna(0.0).sum()),
        "executable_buys": executable_buys,
        "executable_sells": executable_sells,
        "skipped_trades": skipped_trades,
        "created_at": datetime.now(),
    }
    trade_df["created_at"] = datetime.now()
    executable = trade_df[(trade_df["is_executable"] == 1) & trade_df["execution_order"].notna()].sort_values(["execution_order", "ticker"])
    for order, idx in enumerate(executable.index, start=1):
        trade_df.loc[idx, "execution_order"] = order
    return trade_df.sort_values(["execution_order", "source_rank", "ticker"], na_position="last").reset_index(drop=True), summary


def _sector_map_from_provider_members(artifacts: StrategyRunArtifacts) -> dict[str, str | None]:
    member_sectors = getattr(artifacts, "member_sectors", None)
    if member_sectors:
        return {
            str(ticker).upper(): sector
            for ticker, sector in member_sectors.items()
        }
    result: dict[str, str | None] = {}
    for ticker in artifacts.members:
        result[str(ticker).upper()] = None
    return result


def _normalize_snapshot_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return result
    result["ticker"] = result["ticker"].astype(str).str.upper()
    return result


def _normalize_ranking_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return result
    result["ticker"] = result["ticker"].astype(str).str.upper()
    if "source_rank" not in result.columns and "rank" in result.columns:
        result["source_rank"] = result["rank"]
    if "final_score" not in result.columns and "composite_score" in result.columns:
        result["final_score"] = result["composite_score"]
    return result


def _normalize_real_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return result
    result["ticker"] = result["ticker"].astype(str).str.upper()
    result["shares"] = pd.to_numeric(result["shares"], errors="coerce").fillna(0.0)
    if "opened_at" in result.columns:
        result["opened_at"] = pd.to_datetime(result["opened_at"])
    return result


def _normalize_prices_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return pd.DataFrame(columns=["ticker", "current_price"])
    result["ticker"] = result["ticker"].astype(str).str.upper()
    if "current_price" not in result.columns and "close" in result.columns:
        result["current_price"] = result["close"]
    result["current_price"] = pd.to_numeric(result["current_price"], errors="coerce")
    return result[["ticker", "current_price"]]


def _rebalance_row(
    as_of_date: date,
    ticker: str,
    sector: str,
    action: str,
    reason: str,
    source_rank,
    target_weight,
    current_shares,
    opened_at,
    holding_days,
    min_hold_ok,
) -> dict[str, Any]:
    opened_date = pd.to_datetime(opened_at).date() if pd.notna(opened_at) else None
    return {
        "as_of_date": as_of_date,
        "ticker": ticker,
        "sector": sector,
        "action": action,
        "reason": reason,
        "source_rank": _optional_int(source_rank),
        "target_weight": _optional_float(target_weight),
        "current_shares": _optional_float(current_shares),
        "opened_at": opened_date,
        "holding_days": _optional_int(holding_days),
        "min_hold_ok": _optional_int(min_hold_ok) or 0,
        "created_at": datetime.now(),
    }


def _build_trade_maps(real: pd.DataFrame, prices: pd.DataFrame) -> tuple[dict[str, float], dict[str, float]]:
    shares_map = real.set_index("ticker")["shares"].astype(float).to_dict() if not real.empty else {}
    price_map = prices.set_index("ticker")["current_price"].astype(float).to_dict() if not prices.empty else {}
    return shares_map, price_map


def _compute_portfolio_values(real: pd.DataFrame, prices: pd.DataFrame, cash_before: float) -> tuple[float, float]:
    if real.empty:
        invested_value = 0.0
    else:
        merged = real.merge(prices, on="ticker", how="left")
        merged["current_price"] = pd.to_numeric(merged["current_price"], errors="coerce").fillna(0.0)
        invested_value = float((merged["shares"] * merged["current_price"]).sum())
    return invested_value + float(cash_before), invested_value


def _trade_row(
    as_of_date,
    ticker,
    action,
    reason,
    execution_order,
    row,
    current_shares,
    planned_shares,
    estimated_price,
    gross_amount,
    fee,
    net_amount,
    bucket_size,
    cash_before,
    cash_after,
    is_executable,
    skip_reason,
) -> dict[str, Any]:
    return {
        "as_of_date": as_of_date,
        "ticker": ticker,
        "action": action,
        "reason": reason,
        "execution_order": execution_order,
        "source_rank": _optional_int(row.get("source_rank")),
        "target_weight": _optional_float(row.get("target_weight")),
        "current_shares": _optional_float(current_shares),
        "planned_shares": _optional_float(planned_shares),
        "estimated_price": _optional_float(estimated_price),
        "gross_amount": _optional_float(gross_amount),
        "fee": _optional_float(fee) or 0.0,
        "net_amount": _optional_float(net_amount),
        "bucket_size": _optional_float(bucket_size),
        "cash_before": _optional_float(cash_before),
        "cash_after": _optional_float(cash_after),
        "is_executable": int(is_executable),
        "skip_reason": skip_reason,
    }


def _build_funding_candidates(
    rebalance: pd.DataFrame,
    shares_state: dict[str, float],
    price_map: dict[str, float],
    bucket_size: float,
    max_funding_sell_pct: float,
    exclude_tickers: set[str],
) -> list[dict[str, Any]]:
    rebalance_map = rebalance.set_index("ticker").to_dict(orient="index") if not rebalance.empty else {}
    rows = []
    for ticker, shares in shares_state.items():
        if ticker in exclude_tickers:
            continue
        price = float(price_map.get(ticker, 0.0) or 0.0)
        if shares <= 0 or price <= 0:
            continue
        current_value = shares * price
        excess_value = current_value - bucket_size
        if excess_value <= 0:
            continue
        sell_value_cap = min(excess_value, current_value * max_funding_sell_pct)
        max_shares = int(sell_value_cap // price)
        if max_shares <= 0:
            continue
        meta = rebalance_map.get(ticker, {})
        rows.append(
            {
                "ticker": ticker,
                "price": price,
                "max_shares": max_shares,
                "source_rank": _optional_int(meta.get("source_rank")),
                "target_weight": _optional_float(meta.get("target_weight")),
                "current_shares": float(shares),
            }
        )
    return sorted(rows, key=lambda item: (item["source_rank"] is None, item["source_rank"], item["ticker"]))


def _simulate_funding_for_buy(
    buy_required_cash: float,
    current_cash: float,
    funding_candidates: list[dict[str, Any]],
    shares_state: dict[str, float],
    used_funding_value_by_ticker: dict[str, float],
    max_funding_sell_pct: float,
    bucket_size: float,
) -> tuple[bool, list[dict[str, Any]], float]:
    simulated_cash = float(current_cash)
    simulated_rows = []
    if simulated_cash >= buy_required_cash:
        return True, [], simulated_cash
    for item in funding_candidates:
        ticker = item["ticker"]
        price = float(item["price"])
        available_shares = float(shares_state.get(ticker, 0.0) or 0.0)
        if available_shares <= 0 or price <= 0:
            continue
        current_value = available_shares * price
        excess_value = max(0.0, current_value - bucket_size)
        remaining_value_limit = max(
            0.0,
            current_value * max_funding_sell_pct - used_funding_value_by_ticker.get(ticker, 0.0),
        )
        sell_value_cap = min(excess_value, remaining_value_limit)
        missing_cash = buy_required_cash - simulated_cash
        if missing_cash <= 0:
            break
        target_sell_value = min(sell_value_cap, missing_cash + TRADE_FEE)
        planned_shares = int(target_sell_value / price)
        if planned_shares * price < target_sell_value:
            planned_shares += 1
        planned_shares = min(planned_shares, int(available_shares))
        if planned_shares <= 0:
            continue
        gross_amount = _round_money(planned_shares * price)
        net_amount = _round_money(gross_amount - TRADE_FEE)
        if net_amount <= 0:
            continue
        simulated_rows.append(
            {
                "ticker": ticker,
                "price": price,
                "planned_shares": planned_shares,
                "gross_amount": gross_amount,
                "net_amount": net_amount,
                "source_rank": item["source_rank"],
                "target_weight": item["target_weight"],
                "current_shares": available_shares,
            }
        )
        simulated_cash = _round_money(simulated_cash + net_amount)
        if simulated_cash >= buy_required_cash:
            return True, simulated_rows, simulated_cash
    return False, [], current_cash


def _aggregate_funding_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregated_rows = []
    funding_by_ticker = {}
    for row in rows:
        key = (row["as_of_date"], row["ticker"])
        if row["action"] != "ADJUST_SELL":
            aggregated_rows.append(row)
            continue
        if key not in funding_by_ticker:
            funding_by_ticker[key] = dict(row)
            continue
        existing = funding_by_ticker[key]
        existing["planned_shares"] = _round_money((existing["planned_shares"] or 0.0) + (row["planned_shares"] or 0.0))
        existing["gross_amount"] = _round_money((existing["gross_amount"] or 0.0) + (row["gross_amount"] or 0.0))
        existing["fee"] = _round_money((existing["fee"] or 0.0) + (row["fee"] or 0.0))
        existing["net_amount"] = _round_money((existing["net_amount"] or 0.0) + (row["net_amount"] or 0.0))
        existing["cash_after"] = row["cash_after"]
        existing["execution_order"] = min(existing["execution_order"], row["execution_order"])
        existing["reason"] = "funding_new_buy_limited_pct_aggregated"
    aggregated_rows.extend(funding_by_ticker.values())
    return aggregated_rows


def _trade_price_tickers(rebalance: pd.DataFrame, real: pd.DataFrame) -> list[str]:
    values = []
    if not rebalance.empty:
        values.extend(rebalance["ticker"].tolist())
    if not real.empty:
        values.extend(real["ticker"].tolist())
    return sorted({str(value).upper() for value in values if value})


def _insert_rows(conn, table_name: str, rows) -> None:
    if isinstance(rows, pd.DataFrame):
        records = rows.to_dict(orient="records")
    else:
        records = list(rows)
    records = [_clean_record(record) for record in records]
    if not records:
        return
    columns = list(records[0].keys())
    sql = text(
        f"INSERT INTO {table_name} ("
        + ", ".join(columns)
        + ") VALUES ("
        + ", ".join(f":{column}" for column in columns)
        + ")"
    )
    conn.execute(sql, records)


def _settings_payload(as_of_date: date, settings: OperationalSettings) -> dict[str, Any]:
    return {
        "as_of_date": as_of_date,
        "strategy_version": settings.strategy_version,
        "value_weight": settings.value_weight,
        "quality_weight": settings.quality_weight,
        "momentum_weight": settings.momentum_weight,
        "momentum_return_weight": settings.momentum_return_weight,
        "momentum_rel_strength_weight": settings.momentum_rel_strength_weight,
        "min_price": settings.min_price,
        "min_market_cap": settings.min_market_cap,
        "sma_days": settings.sma_days,
        "return_lookback_days": settings.return_lookback_days,
        "buy_rank_threshold": settings.buy_rank_threshold,
        "sell_rank_threshold": settings.sell_rank_threshold,
        "portfolio_size": settings.portfolio_size,
        "max_sector_positions": settings.max_sector_positions,
        "min_holding_months": settings.min_holding_months,
        "max_trades_per_month": settings.max_trades_per_month,
        "daily_fundamental_limit": settings.daily_fundamental_limit,
        "fundamental_refresh_hours": settings.fundamental_refresh_hours,
        "tax_rate": settings.tax_rate,
        "max_funding_sell_pct": settings.max_funding_sell_pct,
        "created_at": datetime.now(),
    }


def _trade_columns() -> list[str]:
    return [
        "as_of_date",
        "ticker",
        "action",
        "reason",
        "execution_order",
        "source_rank",
        "target_weight",
        "current_shares",
        "planned_shares",
        "estimated_price",
        "gross_amount",
        "fee",
        "net_amount",
        "bucket_size",
        "cash_before",
        "cash_after",
        "is_executable",
        "skip_reason",
    ]


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    cleaned = {}
    for key, value in record.items():
        if pd.isna(value):
            cleaned[key] = None
        elif isinstance(value, pd.Timestamp):
            cleaned[key] = value.to_pydatetime()
        elif hasattr(value, "item"):
            cleaned[key] = value.item()
        else:
            cleaned[key] = value
    return cleaned


def _optional_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _optional_int(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _optional_string(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)


def _round_money(value: float) -> float:
    return round(float(value), 6)
