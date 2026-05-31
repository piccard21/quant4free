from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional, Sequence

from sqlalchemy import Engine, bindparam, text

from shared.capabilities import SOURCE_ROLE_PRICES
from shared.db import get_engine

from .repository import RawDataRepository


DEFAULT_PRICE_STALE_DAYS = 5
DEFAULT_FUNDAMENTAL_STALE_DAYS = 550
DEFAULT_MARKET_CAP_STALE_DAYS = 10


@dataclass(frozen=True)
class FreshnessDiagnostic:
    key: str
    required_tickers: tuple[str, ...]
    covered_tickers: tuple[str, ...]
    missing_tickers: tuple[str, ...]
    stale_tickers: tuple[str, ...]
    latest_date: Optional[date]
    stale_before: date

    @property
    def status(self) -> str:
        if self.missing_tickers and self.stale_tickers:
            return "missing_stale"
        if self.missing_tickers:
            return "missing"
        if self.stale_tickers:
            return "stale"
        return "ok"


@dataclass(frozen=True)
class IdentifierDiagnostic:
    provider_key: str
    identifier_scheme: str
    required_tickers: tuple[str, ...]
    covered_tickers: tuple[str, ...]
    missing_tickers: tuple[str, ...]

    @property
    def status(self) -> str:
        return "missing" if self.missing_tickers else "ok"


@dataclass(frozen=True)
class SyncRunDiagnostic:
    sync_type: str
    status: str
    provider_key: Optional[str]
    source_role: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error_message: Optional[str]


@dataclass(frozen=True)
class DataQualityReport:
    universe_key: str
    as_of_date: date
    benchmark_ticker: str
    member_count: int
    prices: FreshnessDiagnostic
    fundamentals: FreshnessDiagnostic
    market_caps: FreshnessDiagnostic
    provider_identifiers: IdentifierDiagnostic
    sync_runs: tuple[SyncRunDiagnostic, ...]

    @property
    def status(self) -> str:
        raw_statuses = (
            self.prices.status,
            self.fundamentals.status,
            self.market_caps.status,
            self.provider_identifiers.status,
        )
        sync_statuses = {item.status for item in self.sync_runs}
        if any(status != "ok" for status in raw_statuses):
            return "warning"
        if sync_statuses.intersection({"failed", "stale_started"}):
            return "warning"
        return "ok"


class DataQualityDiagnostics:
    """Read-only raw-data freshness and coverage diagnostics."""

    def __init__(self, engine: Optional[Engine] = None) -> None:
        self.engine = engine or get_engine()
        self.repository = RawDataRepository(self.engine)

    def build_report(
        self,
        *,
        universe_key: str = "sp500_active",
        benchmark_ticker: str = "SPY",
        as_of_date: Optional[date] = None,
        price_stale_days: int = DEFAULT_PRICE_STALE_DAYS,
        fundamental_stale_days: int = DEFAULT_FUNDAMENTAL_STALE_DAYS,
        market_cap_stale_days: int = DEFAULT_MARKET_CAP_STALE_DAYS,
        identifier_provider_key: str = "mysql_fixture",
        identifier_scheme: str = "ticker",
        sync_provider_key: Optional[str] = None,
        stale_started_minutes: int = 120,
        now: Optional[datetime] = None,
    ) -> DataQualityReport:
        if price_stale_days < 0:
            raise ValueError("price_stale_days must be non-negative")
        if fundamental_stale_days < 0:
            raise ValueError("fundamental_stale_days must be non-negative")
        if market_cap_stale_days < 0:
            raise ValueError("market_cap_stale_days must be non-negative")
        if stale_started_minutes < 0:
            raise ValueError("stale_started_minutes must be non-negative")

        now = now or datetime.now()
        as_of_date = as_of_date or now.date()
        members = tuple(
            ticker.ticker.upper()
            for ticker in self.repository.load_universe_members(universe_key)
        )
        benchmark_ticker = benchmark_ticker.strip().upper()
        price_tickers = _unique(
            [*members, benchmark_ticker] if benchmark_ticker else members
        )
        identifier_tickers = price_tickers

        prices = self._freshness(
            key="prices",
            table_name="asset_price_bars",
            date_column="date",
            tickers=price_tickers,
            stale_before=as_of_date - timedelta(days=price_stale_days),
        )
        fundamentals = self._freshness(
            key="fundamentals",
            table_name="asset_fundamental_reports",
            date_column="report_date",
            tickers=members,
            stale_before=as_of_date - timedelta(days=fundamental_stale_days),
            extra_where="AND report_type = :report_type",
            extra_params={"report_type": "ttm"},
        )
        market_caps = self._freshness(
            key="market_caps",
            table_name="asset_market_caps",
            date_column="date",
            tickers=members,
            stale_before=as_of_date - timedelta(days=market_cap_stale_days),
        )
        identifier_coverage = self.repository.provider_identifier_coverage(
            source_role=SOURCE_ROLE_PRICES,
            provider_key=identifier_provider_key,
            identifier_scheme=identifier_scheme,
            tickers=identifier_tickers,
        )
        provider_identifiers = IdentifierDiagnostic(
            provider_key=identifier_provider_key,
            identifier_scheme=identifier_scheme,
            required_tickers=identifier_coverage.required_tickers,
            covered_tickers=identifier_coverage.covered_tickers,
            missing_tickers=identifier_coverage.missing_tickers,
        )
        sync_runs = self._latest_sync_runs(
            sync_provider_key=sync_provider_key,
            stale_started_at=now - timedelta(minutes=stale_started_minutes),
        )
        return DataQualityReport(
            universe_key=universe_key,
            as_of_date=as_of_date,
            benchmark_ticker=benchmark_ticker,
            member_count=len(members),
            prices=prices,
            fundamentals=fundamentals,
            market_caps=market_caps,
            provider_identifiers=provider_identifiers,
            sync_runs=sync_runs,
        )

    def _freshness(
        self,
        *,
        key: str,
        table_name: str,
        date_column: str,
        tickers: Sequence[str],
        stale_before: date,
        extra_where: str = "",
        extra_params: Optional[dict[str, Any]] = None,
    ) -> FreshnessDiagnostic:
        required = _unique(tickers)
        if not required:
            return FreshnessDiagnostic(
                key=key,
                required_tickers=(),
                covered_tickers=(),
                missing_tickers=(),
                stale_tickers=(),
                latest_date=None,
                stale_before=stale_before,
            )

        statement = text(
            f"""
            SELECT ticker, MAX({date_column}) AS latest_date
            FROM {table_name}
            WHERE ticker IN :tickers
            {extra_where}
            GROUP BY ticker
            """
        ).bindparams(bindparam("tickers", expanding=True))
        params: dict[str, Any] = {"tickers": list(required)}
        if extra_params:
            params.update(extra_params)
        with self.engine.connect() as connection:
            rows = list(connection.execute(statement, params).mappings())

        latest_by_ticker = {
            row["ticker"].upper(): _as_date(row["latest_date"])
            for row in rows
            if row["latest_date"] is not None
        }
        covered = tuple(sorted(latest_by_ticker))
        missing = tuple(
            ticker for ticker in required if ticker not in latest_by_ticker
        )
        stale = tuple(
            ticker
            for ticker, latest_date in latest_by_ticker.items()
            if latest_date < stale_before
        )
        latest_date = max(latest_by_ticker.values(), default=None)
        return FreshnessDiagnostic(
            key=key,
            required_tickers=required,
            covered_tickers=covered,
            missing_tickers=missing,
            stale_tickers=tuple(sorted(stale)),
            latest_date=latest_date,
            stale_before=stale_before,
        )

    def _latest_sync_runs(
        self,
        *,
        sync_provider_key: Optional[str],
        stale_started_at: datetime,
    ) -> tuple[SyncRunDiagnostic, ...]:
        sync_types = ("membership", "prices", "fundamentals")
        sql = """
            SELECT
                sync_type,
                provider_key,
                source_role,
                status,
                started_at,
                finished_at,
                error_message
            FROM data_sync_runs
            WHERE sync_type IN :sync_types
        """
        params: dict[str, Any] = {"sync_types": list(sync_types)}
        if sync_provider_key:
            sql += " AND provider_key = :provider_key"
            params["provider_key"] = sync_provider_key
        sql += " ORDER BY started_at DESC, id DESC"
        statement = text(sql).bindparams(bindparam("sync_types", expanding=True))
        with self.engine.connect() as connection:
            rows = list(connection.execute(statement, params).mappings())

        latest_by_type: dict[str, dict[str, Any]] = {}
        for row in rows:
            sync_type = row["sync_type"]
            if sync_type not in latest_by_type:
                latest_by_type[sync_type] = dict(row)

        diagnostics: list[SyncRunDiagnostic] = []
        for sync_type in sync_types:
            row = latest_by_type.get(sync_type)
            if row is None:
                diagnostics.append(
                    SyncRunDiagnostic(
                        sync_type=sync_type,
                        status="no_runs",
                        provider_key=sync_provider_key,
                        source_role=None,
                        started_at=None,
                        finished_at=None,
                        error_message=None,
                    )
                )
                continue
            status = row["status"]
            started_at = _as_datetime(row["started_at"])
            if (
                status == "started"
                and started_at is not None
                and started_at < stale_started_at
            ):
                status = "stale_started"
            diagnostics.append(
                SyncRunDiagnostic(
                    sync_type=sync_type,
                    status=status,
                    provider_key=row["provider_key"],
                    source_role=row["source_role"],
                    started_at=started_at,
                    finished_at=_as_datetime(row["finished_at"]),
                    error_message=row["error_message"],
                )
            )
        return tuple(diagnostics)


def format_data_quality_report(
    report: DataQualityReport,
    sample_limit: int = 10,
) -> list[str]:
    lines = [
        "data_quality "
        f"universe={report.universe_key} "
        f"as_of={report.as_of_date} "
        f"status={report.status} "
        f"members={report.member_count} "
        f"benchmark={report.benchmark_ticker}"
    ]
    for diagnostic in (report.prices, report.fundamentals, report.market_caps):
        lines.append(_format_freshness(diagnostic, sample_limit))
    lines.append(_format_identifiers(report.provider_identifiers, sample_limit))
    for sync_run in report.sync_runs:
        lines.append(_format_sync_run(sync_run))
    return lines


def _format_freshness(
    diagnostic: FreshnessDiagnostic,
    sample_limit: int,
) -> str:
    parts = [
        f"data_quality.{diagnostic.key}",
        f"status={diagnostic.status}",
        f"required={len(diagnostic.required_tickers)}",
        f"covered={len(diagnostic.covered_tickers)}",
        f"missing={len(diagnostic.missing_tickers)}",
        f"stale={len(diagnostic.stale_tickers)}",
        f"latest={diagnostic.latest_date}",
        f"stale_before={diagnostic.stale_before}",
    ]
    if diagnostic.missing_tickers:
        parts.append(
            f"missing_tickers={_sample(diagnostic.missing_tickers, sample_limit)}"
        )
    if diagnostic.stale_tickers:
        parts.append(
            f"stale_tickers={_sample(diagnostic.stale_tickers, sample_limit)}"
        )
    return " ".join(parts)


def _format_identifiers(
    diagnostic: IdentifierDiagnostic,
    sample_limit: int,
) -> str:
    parts = [
        "data_quality.provider_identifiers",
        f"status={diagnostic.status}",
        f"provider={diagnostic.provider_key}",
        f"scheme={diagnostic.identifier_scheme}",
        f"required={len(diagnostic.required_tickers)}",
        f"covered={len(diagnostic.covered_tickers)}",
        f"missing={len(diagnostic.missing_tickers)}",
    ]
    if diagnostic.missing_tickers:
        parts.append(
            f"missing_tickers={_sample(diagnostic.missing_tickers, sample_limit)}"
        )
    return " ".join(parts)


def _format_sync_run(diagnostic: SyncRunDiagnostic) -> str:
    parts = [
        "data_quality.sync",
        f"type={diagnostic.sync_type}",
        f"status={diagnostic.status}",
        f"provider={diagnostic.provider_key}",
    ]
    if diagnostic.source_role is not None:
        parts.append(f"source_role={diagnostic.source_role}")
    if diagnostic.started_at is not None:
        parts.append(f"started={diagnostic.started_at}")
    if diagnostic.finished_at is not None:
        parts.append(f"finished={diagnostic.finished_at}")
    if diagnostic.error_message:
        parts.append(f"error={diagnostic.error_message}")
    return " ".join(parts)


def _unique(tickers: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker)
    )


def _sample(values: Sequence[str], limit: int) -> str:
    limit = max(limit, 0)
    sample = list(values[:limit])
    suffix = ""
    if len(values) > limit:
        suffix = f",+{len(values) - limit}"
    if not sample:
        return suffix.lstrip(",")
    return ",".join(sample) + suffix


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise TypeError(f"cannot convert {value!r} to date")


def _as_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"cannot convert {value!r} to datetime")
