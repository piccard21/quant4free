from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Optional, Protocol, Sequence

from .models import FinancialSyncPayload, ProviderIdentifier, TickerUpsert
from .repository import RawDataRepository
from .yahoo import (
    WikipediaSP500TickerSource,
    YFinanceFundamentalSource,
    YFinancePriceSource,
    normalize_yfinance_prices,
)


BENCHMARK_TICKER = "SPY"
YFINANCE_PROVIDER_KEY = "yfinance"
WIKIPEDIA_SP500_PROVIDER_KEY = "wikipedia_sp500"
INIT_HISTORY_DAYS = 548
DAILY_LOOKBACK_DAYS = 3
NEW_TICKER_FALLBACK_DAYS = 180


class TickerSource(Protocol):
    def list_tickers(self) -> list[TickerUpsert]:
        ...


class PriceSource(Protocol):
    def download_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ):
        ...


class FundamentalSource(Protocol):
    def load_fundamentals(
        self,
        ticker: str,
        imported_at: Optional[datetime] = None,
    ) -> FinancialSyncPayload:
        ...


@dataclass(frozen=True)
class PlannedPriceSync:
    ticker: str
    provider_key: str
    provider_symbol: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class PlannedFundamentalSync:
    ticker: str
    provider_key: str
    provider_symbol: str


@dataclass(frozen=True)
class PriceSyncResult:
    mode: str
    dry_run: bool
    ticker_upserts: int
    deactivated_tickers: int
    planned: tuple[PlannedPriceSync, ...]
    downloaded_tickers: int
    upserted_candles: int
    sync_run_id: Optional[int] = None
    membership_sync_run_id: Optional[int] = None


@dataclass(frozen=True)
class FundamentalSyncResult:
    mode: str
    dry_run: bool
    planned: tuple[PlannedFundamentalSync, ...]
    planned_tickers: tuple[str, ...]
    updated_tickers: int
    upserted_reports: int
    upserted_market_caps: int
    sync_run_id: Optional[int] = None


def calculate_price_start_date(
    mode: str,
    latest_date: Optional[date],
    today: date,
    init_history_days: int = INIT_HISTORY_DAYS,
    daily_lookback_days: int = DAILY_LOOKBACK_DAYS,
    new_ticker_fallback_days: int = NEW_TICKER_FALLBACK_DAYS,
) -> date:
    if mode == "init":
        return today - timedelta(days=init_history_days)
    if latest_date is not None:
        return latest_date - timedelta(days=daily_lookback_days)
    return today - timedelta(days=new_ticker_fallback_days)


class PriceSyncService:
    def __init__(
        self,
        repository: Optional[RawDataRepository] = None,
        ticker_source: Optional[TickerSource] = None,
        price_source: Optional[PriceSource] = None,
        provider_key: str = YFINANCE_PROVIDER_KEY,
    ) -> None:
        self.repository = repository or RawDataRepository()
        self.ticker_source = ticker_source or WikipediaSP500TickerSource()
        self.price_source = price_source or YFinancePriceSource()
        self.provider_key = provider_key

    def run(
        self,
        mode: str = "daily",
        tickers: Optional[Sequence[str]] = None,
        benchmark_ticker: str = BENCHMARK_TICKER,
        sync_tickers: bool = True,
        dry_run: bool = False,
        today: Optional[date] = None,
        now: Optional[datetime] = None,
    ) -> PriceSyncResult:
        if mode not in {"init", "daily"}:
            raise ValueError("mode must be 'init' or 'daily'")

        benchmark_ticker = benchmark_ticker.strip().upper()
        now = now or datetime.now()
        today = today or now.date()
        ticker_upserts = 0
        deactivated_tickers = 0
        membership_sync_run_id = None

        selected_tickers = _normalize_ticker_list(tickers)
        if selected_tickers is None:
            if sync_tickers and not dry_run:
                membership_sync_run_id = self.repository.start_data_sync_run(
                    sync_type="membership",
                    provider_key=WIKIPEDIA_SP500_PROVIDER_KEY,
                    source_role="membership",
                    mode=mode,
                    dry_run=False,
                    started_at=now,
                )
                try:
                    ticker_rows = self.ticker_source.list_tickers()
                    current_tickers = [row.ticker for row in ticker_rows]
                    deactivated_tickers = self.repository.deactivate_missing_active_tickers(
                        current_tickers,
                        sync_time=now,
                    )
                    ticker_upserts = self.repository.upsert_tickers(
                        ticker_rows,
                        sync_time=now,
                    )
                    self.repository.upsert_provider_identifiers(
                        _provider_identifiers_for_tickers(
                            ticker_rows,
                            provider_key=self.provider_key,
                            imported_at=now,
                        )
                    )
                    self.repository.finish_data_sync_run(
                        membership_sync_run_id,
                        planned_items=len(ticker_rows),
                        processed_items=len(ticker_rows),
                        upserted_rows=ticker_upserts,
                        ticker_upserts=ticker_upserts,
                        deactivated_tickers=deactivated_tickers,
                    )
                    selected_tickers = current_tickers
                except Exception as exc:
                    self.repository.fail_data_sync_run(
                        membership_sync_run_id,
                        error_message=_exception_message(exc),
                        ticker_upserts=ticker_upserts,
                        deactivated_tickers=deactivated_tickers,
                    )
                    raise
            else:
                selected_tickers = [
                    ticker.ticker
                    for ticker in self.repository.list_tickers(active_only=True)
                ]

        if not dry_run:
            self.repository.ensure_ticker(
                benchmark_ticker,
                name="SPDR S&P 500 ETF Trust",
                sector="Benchmark",
                is_active=False,
                sync_time=now,
            )
            self.repository.upsert_provider_identifiers(
                [
                    ProviderIdentifier(
                        ticker=benchmark_ticker,
                        provider_key=self.provider_key,
                        identifier_scheme="ticker",
                        provider_symbol=benchmark_ticker,
                        market="US",
                        quote_currency="USD",
                        is_primary=True,
                        imported_at=now,
                    )
                ]
            )
        symbols = _append_benchmark(selected_tickers, benchmark_ticker)
        provider_symbols = {
            mapping.ticker: mapping
            for mapping in self.repository.resolve_provider_symbols(
                provider_key=self.provider_key,
                tickers=symbols,
                fallback_to_ticker=True,
            )
        }
        planned = tuple(
            PlannedPriceSync(
                ticker=symbol,
                provider_key=self.provider_key,
                provider_symbol=provider_symbols[symbol].provider_symbol,
                start_date=calculate_price_start_date(
                    mode,
                    self.repository.latest_candle_date(symbol),
                    today,
                ),
                end_date=today,
            )
            for symbol in symbols
        )

        if dry_run:
            return PriceSyncResult(
                mode=mode,
                dry_run=True,
                ticker_upserts=ticker_upserts,
                deactivated_tickers=deactivated_tickers,
                planned=planned,
                downloaded_tickers=0,
                upserted_candles=0,
                sync_run_id=None,
                membership_sync_run_id=None,
            )

        sync_run_id = self.repository.start_data_sync_run(
            sync_type="prices",
            provider_key=self.provider_key,
            source_role="prices",
            mode=mode,
            dry_run=False,
            started_at=now,
            date_from=min((item.start_date for item in planned), default=None),
            date_to=max((item.end_date for item in planned), default=None),
            requested_tickers_count=len(symbols),
            planned_items=len(planned),
        )
        downloaded_tickers = 0
        upserted_candles = 0
        processed_tickers = 0
        try:
            for item in planned:
                raw_prices = self.price_source.download_prices(
                    item.provider_symbol,
                    item.start_date,
                    item.end_date,
                )
                processed_tickers += 1
                candles = normalize_yfinance_prices(
                    raw_prices,
                    item.provider_symbol,
                    output_ticker=item.ticker,
                )
                if candles:
                    downloaded_tickers += 1
                    upserted_candles += self.repository.upsert_daily_candles(candles)
        except Exception as exc:
            self.repository.fail_data_sync_run(
                sync_run_id,
                error_message=_exception_message(exc),
                planned_items=len(planned),
                processed_items=processed_tickers,
                upserted_rows=upserted_candles,
                upserted_candles=upserted_candles,
            )
            raise

        self.repository.finish_data_sync_run(
            sync_run_id,
            planned_items=len(planned),
            processed_items=processed_tickers,
            upserted_rows=upserted_candles,
            upserted_candles=upserted_candles,
        )

        return PriceSyncResult(
            mode=mode,
            dry_run=False,
            ticker_upserts=ticker_upserts,
            deactivated_tickers=deactivated_tickers,
            planned=planned,
            downloaded_tickers=downloaded_tickers,
            upserted_candles=upserted_candles,
            sync_run_id=sync_run_id,
            membership_sync_run_id=membership_sync_run_id,
        )


class FundamentalSyncService:
    def __init__(
        self,
        repository: Optional[RawDataRepository] = None,
        fundamental_source: Optional[FundamentalSource] = None,
        provider_key: str = YFINANCE_PROVIDER_KEY,
    ) -> None:
        self.repository = repository or RawDataRepository()
        self.fundamental_source = fundamental_source or YFinanceFundamentalSource()
        self.provider_key = provider_key

    def run(
        self,
        mode: str = "daily",
        tickers: Optional[Sequence[str]] = None,
        refresh_hours: int = 24,
        limit: int = 25,
        dry_run: bool = False,
        now: Optional[datetime] = None,
    ) -> FundamentalSyncResult:
        if mode not in {"init", "daily"}:
            raise ValueError("mode must be 'init' or 'daily'")

        now = now or datetime.now()
        planned = _normalize_ticker_list(tickers)
        if planned is None:
            planned = self.repository.select_tickers_for_fundamental_sync(
                mode=mode,
                refresh_hours=refresh_hours,
                limit=limit,
                now=now,
            )
        provider_symbols = {
            mapping.ticker: mapping
            for mapping in self.repository.resolve_provider_symbols(
                provider_key=self.provider_key,
                tickers=planned,
                fallback_to_ticker=True,
            )
        }
        planned_items = tuple(
            PlannedFundamentalSync(
                ticker=ticker,
                provider_key=self.provider_key,
                provider_symbol=provider_symbols[ticker].provider_symbol,
            )
            for ticker in planned
        )

        if dry_run:
            return FundamentalSyncResult(
                mode=mode,
                dry_run=True,
                planned=planned_items,
                planned_tickers=tuple(planned),
                updated_tickers=0,
                upserted_reports=0,
                upserted_market_caps=0,
                sync_run_id=None,
            )

        sync_run_id = self.repository.start_data_sync_run(
            sync_type="fundamentals",
            provider_key=self.provider_key,
            source_role="fundamentals",
            mode=mode,
            dry_run=False,
            started_at=now,
            requested_tickers_count=len(planned),
            planned_items=len(planned_items),
        )
        updated_tickers = 0
        upserted_reports = 0
        upserted_market_caps = 0
        processed_tickers = 0
        try:
            for item in planned_items:
                raw_payload = self.fundamental_source.load_fundamentals(
                    item.provider_symbol,
                    imported_at=now,
                )
                processed_tickers += 1
                payload = _payload_for_internal_ticker(raw_payload, item.ticker)
                reports = list(payload.reports)
                market_caps = [payload.market_cap] if payload.market_cap is not None else []
                if reports:
                    upserted_reports += self.repository.upsert_financial_reports(reports)
                if market_caps:
                    upserted_market_caps += self.repository.upsert_market_caps(market_caps)
                if reports or market_caps:
                    self.repository.mark_fundamental_updated(item.ticker, updated_at=now)
                    updated_tickers += 1
        except Exception as exc:
            self.repository.fail_data_sync_run(
                sync_run_id,
                error_message=_exception_message(exc),
                planned_items=len(planned_items),
                processed_items=processed_tickers,
                upserted_rows=upserted_reports + upserted_market_caps,
                updated_tickers=updated_tickers,
                upserted_reports=upserted_reports,
                upserted_market_caps=upserted_market_caps,
            )
            raise

        self.repository.finish_data_sync_run(
            sync_run_id,
            planned_items=len(planned_items),
            processed_items=processed_tickers,
            upserted_rows=upserted_reports + upserted_market_caps,
            updated_tickers=updated_tickers,
            upserted_reports=upserted_reports,
            upserted_market_caps=upserted_market_caps,
        )

        return FundamentalSyncResult(
            mode=mode,
            dry_run=False,
            planned=planned_items,
            planned_tickers=tuple(planned),
            updated_tickers=updated_tickers,
            upserted_reports=upserted_reports,
            upserted_market_caps=upserted_market_caps,
            sync_run_id=sync_run_id,
        )


def _normalize_ticker_list(tickers: Optional[Sequence[str]]) -> Optional[list[str]]:
    if tickers is None:
        return None
    return [ticker.strip().upper() for ticker in tickers if ticker.strip()]


def _append_benchmark(tickers: Sequence[str], benchmark_ticker: str) -> list[str]:
    symbols = list(dict.fromkeys(tickers))
    if benchmark_ticker and benchmark_ticker not in symbols:
        symbols.append(benchmark_ticker)
    return symbols


def _exception_message(exc: Exception) -> str:
    message = str(exc)
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__


def _provider_identifiers_for_tickers(
    tickers: Sequence[TickerUpsert],
    provider_key: str,
    imported_at: datetime,
) -> list[ProviderIdentifier]:
    return [
        ProviderIdentifier(
            ticker=ticker.ticker,
            provider_key=provider_key,
            identifier_scheme="ticker",
            provider_symbol=ticker.ticker,
            market=ticker.market,
            quote_currency=ticker.quote_currency,
            is_primary=ticker.primary_provider_key == provider_key,
            imported_at=imported_at,
        )
        for ticker in tickers
    ]


def _payload_for_internal_ticker(
    payload: FinancialSyncPayload,
    ticker: str,
) -> FinancialSyncPayload:
    return FinancialSyncPayload(
        reports=tuple(replace(report, ticker=ticker) for report in payload.reports),
        market_cap=(
            None
            if payload.market_cap is None
            else replace(payload.market_cap, ticker=ticker)
        ),
    )
