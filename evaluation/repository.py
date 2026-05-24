from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

import pandas as pd
from sqlalchemy import Engine, text

from shared.db import get_engine

from .backtest import BacktestResult


@dataclass(frozen=True)
class StoredRun:
    run_id: int
    run_key: str


class EvaluationRepository:
    """Persistence for AP8 strategy evaluation runs."""

    def __init__(self, engine: Optional[Engine] = None) -> None:
        self.engine = engine or get_engine()

    def ensure_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS strategy_runs (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                run_key VARCHAR(64) NOT NULL UNIQUE,
                strategy_key VARCHAR(128) NOT NULL,
                strategy_version VARCHAR(64) NOT NULL,
                universe_key VARCHAR(128) NOT NULL,
                benchmark_key VARCHAR(128) NOT NULL,
                provider_key VARCHAR(128) NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                initial_capital DECIMAL(18, 4) NOT NULL,
                config_json TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS strategy_run_metrics (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                run_id BIGINT NOT NULL,
                metric_name VARCHAR(128) NOT NULL,
                metric_value DECIMAL(24, 10) NOT NULL,
                FOREIGN KEY (run_id) REFERENCES strategy_runs(id)
                    ON DELETE CASCADE,
                UNIQUE KEY uq_strategy_run_metric (run_id, metric_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS strategy_run_equity_curve (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                run_id BIGINT NOT NULL,
                date DATE NOT NULL,
                portfolio_value DECIMAL(18, 4) NOT NULL,
                cash DECIMAL(18, 4) NOT NULL,
                benchmark_value DECIMAL(18, 4) NOT NULL,
                daily_return DECIMAL(18, 10) NULL,
                benchmark_daily_return DECIMAL(18, 10) NULL,
                drawdown DECIMAL(18, 10) NULL,
                FOREIGN KEY (run_id) REFERENCES strategy_runs(id)
                    ON DELETE CASCADE,
                UNIQUE KEY uq_strategy_run_equity_date (run_id, date)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS strategy_run_trades (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                run_id BIGINT NOT NULL,
                trade_date DATE NOT NULL,
                ticker VARCHAR(16) NOT NULL,
                side VARCHAR(8) NOT NULL,
                shares DECIMAL(24, 10) NOT NULL,
                price DECIMAL(18, 6) NOT NULL,
                notional DECIMAL(18, 4) NOT NULL,
                fee DECIMAL(18, 4) NOT NULL,
                weight_before DECIMAL(18, 10) NOT NULL,
                weight_after DECIMAL(18, 10) NOT NULL,
                reason VARCHAR(64) NOT NULL,
                FOREIGN KEY (run_id) REFERENCES strategy_runs(id)
                    ON DELETE CASCADE,
                KEY idx_strategy_run_trades_run_date (run_id, trade_date)
            )
            """,
        ]
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def save_backtest_result(
        self,
        result: BacktestResult,
        *,
        universe_key: str,
        benchmark_key: str,
        provider_key: str,
        run_key: Optional[str] = None,
    ) -> StoredRun:
        run_key = run_key or uuid.uuid4().hex
        config = dict(result.config)
        initial_capital = float(config.get("initial_capital", 0.0))
        with self.engine.begin() as connection:
            insert_result = connection.execute(
                text(
                    """
                    INSERT INTO strategy_runs (
                        run_key,
                        strategy_key,
                        strategy_version,
                        universe_key,
                        benchmark_key,
                        provider_key,
                        start_date,
                        end_date,
                        initial_capital,
                        config_json,
                        created_at
                    )
                    VALUES (
                        :run_key,
                        :strategy_key,
                        :strategy_version,
                        :universe_key,
                        :benchmark_key,
                        :provider_key,
                        :start_date,
                        :end_date,
                        :initial_capital,
                        :config_json,
                        :created_at
                    )
                    """
                ),
                {
                    "run_key": run_key,
                    "strategy_key": result.strategy_key,
                    "strategy_version": result.strategy_version,
                    "universe_key": universe_key,
                    "benchmark_key": benchmark_key,
                    "provider_key": provider_key,
                    "start_date": result.start_date,
                    "end_date": result.end_date,
                    "initial_capital": initial_capital,
                    "config_json": json.dumps(config, sort_keys=True),
                    "created_at": datetime.utcnow(),
                },
            )
            run_id = int(insert_result.lastrowid)
            connection.execute(
                text(
                    """
                    INSERT INTO strategy_run_metrics (
                        run_id,
                        metric_name,
                        metric_value
                    )
                    VALUES (:run_id, :metric_name, :metric_value)
                    """
                ),
                [
                    {
                        "run_id": run_id,
                        "metric_name": name,
                        "metric_value": value,
                    }
                    for name, value in result.metrics.items()
                ],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO strategy_run_equity_curve (
                        run_id,
                        date,
                        portfolio_value,
                        cash,
                        benchmark_value,
                        daily_return,
                        benchmark_daily_return,
                        drawdown
                    )
                    VALUES (
                        :run_id,
                        :date,
                        :portfolio_value,
                        :cash,
                        :benchmark_value,
                        :daily_return,
                        :benchmark_daily_return,
                        :drawdown
                    )
                    """
                ),
                [
                    {
                        "run_id": run_id,
                        **_clean_mapping(row),
                    }
                    for row in result.equity_curve.to_dict("records")
                ],
            )
            if not result.trades.empty:
                connection.execute(
                    text(
                        """
                        INSERT INTO strategy_run_trades (
                            run_id,
                            trade_date,
                            ticker,
                            side,
                            shares,
                            price,
                            notional,
                            fee,
                            weight_before,
                            weight_after,
                            reason
                        )
                        VALUES (
                            :run_id,
                            :trade_date,
                            :ticker,
                            :side,
                            :shares,
                            :price,
                            :notional,
                            :fee,
                            :weight_before,
                            :weight_after,
                            :reason
                        )
                        """
                    ),
                    [
                        {
                            "run_id": run_id,
                            **_clean_mapping(row),
                        }
                        for row in result.trades.to_dict("records")
                    ],
                )
        return StoredRun(run_id=run_id, run_key=run_key)


def _clean_mapping(row: Mapping[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in row.items():
        if pd.isna(value):
            clean[key] = None
        else:
            clean[key] = value
    return clean
