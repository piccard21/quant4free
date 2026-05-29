from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Engine, text

from shared.db import get_engine

from .models import PortfolioTarget, RealPosition


class LivePortfolioRepository:
    """Read legacy-compatible live portfolio tables for AP9 workflows."""

    def __init__(self, engine: Optional[Engine] = None) -> None:
        self.engine = engine or get_engine()

    def latest_snapshot_date(self, snapshot_type: str) -> date | None:
        with self.engine.connect() as conn:
            return conn.execute(
                text(
                    """
                    SELECT MAX(as_of_date)
                    FROM portfolio_snapshots
                    WHERE snapshot_type = :snapshot_type
                    """
                ),
                {"snapshot_type": snapshot_type},
            ).scalar()

    def load_targets(
        self,
        snapshot_type: str,
        as_of_date: date | None = None,
    ) -> list[PortfolioTarget]:
        resolved_date = as_of_date or self.latest_snapshot_date(snapshot_type)
        if resolved_date is None:
            return []

        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        as_of_date,
                        ticker,
                        portfolio_rank,
                        source_rank,
                        sector,
                        target_weight
                    FROM portfolio_snapshots
                    WHERE as_of_date = :as_of_date
                      AND snapshot_type = :snapshot_type
                    ORDER BY portfolio_rank, ticker
                    """
                ),
                {"as_of_date": resolved_date, "snapshot_type": snapshot_type},
            ).mappings()
            return [
                PortfolioTarget(
                    ticker=str(row["ticker"]).upper(),
                    source=snapshot_type,
                    as_of_date=row["as_of_date"],
                    target_weight=_float(row["target_weight"]),
                    rank=row["portfolio_rank"] or row["source_rank"],
                    sector=row["sector"],
                )
                for row in rows
            ]

    def load_real_positions(self, as_of_date: date | None = None) -> list[RealPosition]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        p.ticker,
                        p.shares,
                        p.buy_price,
                        p.opened_at,
                        latest_price.current_price
                    FROM portfolio_positions p
                    LEFT JOIN (
                        SELECT fm.ticker, fm.current_price
                        FROM factor_metrics fm
                        JOIN (
                            SELECT ticker, MAX(as_of_date) AS max_as_of_date
                            FROM factor_metrics
                            WHERE (:as_of_date IS NULL OR as_of_date <= :as_of_date)
                            GROUP BY ticker
                        ) latest
                            ON latest.ticker = fm.ticker
                           AND latest.max_as_of_date = fm.as_of_date
                    ) latest_price
                        ON latest_price.ticker = p.ticker
                    WHERE p.is_open = 1
                    ORDER BY p.opened_at, p.ticker
                    """
                ),
                {"as_of_date": as_of_date},
            ).mappings()
            return [
                RealPosition(
                    ticker=str(row["ticker"]).upper(),
                    shares=_float(row["shares"]),
                    average_price=_float(row["buy_price"]),
                    opened_at=row["opened_at"],
                    current_price=_optional_float(row["current_price"]),
                )
                for row in rows
            ]

    def load_cash_balance(self) -> float:
        with self.engine.connect() as conn:
            value = conn.execute(
                text(
                    """
                    SELECT cash_balance
                    FROM portfolio_cash
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """
                )
            ).scalar()
        return _float(value)


def _float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _optional_float(value) -> float | None:
    if value is None:
        return None
    return _float(value)
