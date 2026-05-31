from datetime import date, datetime
from decimal import Decimal
import unittest

import pandas as pd
from sqlalchemy import create_engine, text

from data.models import (
    DailyCandle,
    FinancialReport,
    FinancialSyncPayload,
    MarketCapSnapshot,
    ProviderIdentifier,
    TickerUpsert,
    UniverseMemberUpsert,
)
from data.diagnostics import DataQualityDiagnostics, format_data_quality_report
from data.repository import RawDataRepository
from data.sync import (
    FundamentalSyncService,
    ProviderCircuitBreakerOpen,
    PriceSyncService,
    SyncRequestPolicy,
    calculate_price_start_date,
)
from data.yahoo import normalize_yfinance_prices, ttm_report_from_yfinance


class DataSyncTests(unittest.TestCase):
    def test_price_start_date_uses_init_incremental_and_new_ticker_rules(self):
        today = date(2026, 5, 29)

        self.assertEqual(
            calculate_price_start_date("init", date(2026, 5, 20), today),
            date(2024, 11, 27),
        )
        self.assertEqual(
            calculate_price_start_date("daily", date(2026, 5, 22), today),
            date(2026, 5, 19),
        )
        self.assertEqual(
            calculate_price_start_date("daily", None, today),
            date(2025, 11, 30),
        )

    def test_normalize_yfinance_prices_handles_multiindex_and_drops_adj_close(self):
        frame = pd.DataFrame(
            {
                ("AAA", "Open"): [10.0],
                ("AAA", "High"): [12.0],
                ("AAA", "Low"): [9.5],
                ("AAA", "Close"): [11.0],
                ("AAA", "Adj Close"): [10.8],
                ("AAA", "Volume"): [1000],
            },
            index=pd.DatetimeIndex(["2026-05-22"], name="Date"),
        )

        candles = normalize_yfinance_prices(frame, "AAA")

        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].ticker, "AAA")
        self.assertEqual(candles[0].date, date(2026, 5, 22))
        self.assertEqual(candles[0].close, Decimal("11.0"))
        self.assertEqual(candles[0].volume, 1000)

    def test_ttm_report_sums_quarters_and_uses_balance_sheet_latest_value(self):
        imported_at = datetime(2026, 5, 29, 12, 0)
        quarter_dates = pd.to_datetime(
            ["2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"]
        )
        income = pd.DataFrame(
            [[10, 20, 30, 40], [1, 2, 3, 4]],
            index=["Total Revenue", "Net Income"],
            columns=quarter_dates,
        )
        balance = pd.DataFrame(
            [[50], [70]],
            index=["Total Debt", "Stockholders Equity"],
            columns=[quarter_dates[0]],
        )
        cashflow = pd.DataFrame(
            [[5, 6, 7, 8]],
            index=["Free Cash Flow"],
            columns=quarter_dates,
        )

        report = ttm_report_from_yfinance(
            "AAA",
            quarterly_income=income,
            quarterly_balance=balance,
            quarterly_cashflow=cashflow,
            imported_at=imported_at,
        )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report.report_date, date(2026, 3, 31))
        self.assertEqual(report.revenue, 100)
        self.assertEqual(report.net_income, 10)
        self.assertEqual(report.free_cash_flow, 26)
        self.assertEqual(report.total_debt, 50)
        self.assertEqual(report.total_equity, 70)

    def test_repository_upserts_raw_sync_tables(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = RawDataRepository(engine)
        sync_time = datetime(2026, 5, 29, 12, 0)

        self.assertEqual(
            repository.upsert_tickers(
                [TickerUpsert("AAA", "Old Name", "Tech")],
                sync_time=sync_time,
            ),
            1,
        )
        repository.upsert_tickers(
            [TickerUpsert("AAA", "New Name", "Industrials")],
            sync_time=sync_time,
        )
        repository.upsert_daily_candles(
            [
                DailyCandle(
                    "AAA",
                    date(2026, 5, 22),
                    Decimal("10"),
                    Decimal("12"),
                    Decimal("9"),
                    Decimal("11"),
                    100,
                )
            ]
        )
        repository.upsert_daily_candles(
            [
                DailyCandle(
                    "AAA",
                    date(2026, 5, 22),
                    Decimal("10"),
                    Decimal("12"),
                    Decimal("9"),
                    Decimal("13"),
                    200,
                )
            ]
        )
        repository.upsert_financial_reports(
            [
                FinancialReport(
                    ticker="AAA",
                    report_date=date(2026, 3, 31),
                    report_type="ttm",
                    revenue=100,
                    net_income=10,
                    ebit=9,
                    free_cash_flow=8,
                    total_debt=7,
                    total_equity=6,
                    cash_and_equivalents=5,
                    source="test",
                    imported_at=sync_time,
                )
            ]
        )
        repository.upsert_market_caps(
            [
                MarketCapSnapshot(
                    ticker="AAA",
                    date=date(2026, 5, 29),
                    market_cap=123,
                    imported_at=sync_time,
                )
            ]
        )
        repository.mark_fundamental_updated("AAA", updated_at=sync_time)

        with engine.connect() as connection:
            ticker = connection.execute(
                text(
                    """
                    SELECT
                        name,
                        sector,
                        asset_class,
                        canonical_symbol,
                        display_symbol,
                        quote_currency,
                        primary_provider_key,
                        last_fundamental_update
                    FROM assets
                    """
                )
            ).mappings().one()
            provider_identifier_count = connection.execute(
                text("SELECT COUNT(*) FROM asset_provider_identifiers")
            ).scalar_one()
            universe_count = connection.execute(
                text("SELECT COUNT(*) FROM universes")
            ).scalar_one()
            universe_member_count = connection.execute(
                text("SELECT COUNT(*) FROM universe_members")
            ).scalar_one()
            candle = connection.execute(
                text("SELECT close, volume FROM asset_price_bars")
            ).mappings().one()
            report_count = connection.execute(
                text("SELECT COUNT(*) FROM asset_fundamental_reports")
            ).scalar_one()
            market_cap = connection.execute(
                text("SELECT market_cap FROM asset_market_caps")
            ).scalar_one()

        self.assertEqual(ticker["name"], "New Name")
        self.assertEqual(ticker["sector"], "Industrials")
        self.assertEqual(ticker["asset_class"], "equity")
        self.assertEqual(ticker["canonical_symbol"], "AAA")
        self.assertEqual(ticker["display_symbol"], "AAA")
        self.assertEqual(ticker["quote_currency"], "USD")
        self.assertEqual(ticker["primary_provider_key"], "mysql_fixture")
        self.assertIsNotNone(ticker["last_fundamental_update"])
        self.assertEqual(provider_identifier_count, 1)
        self.assertEqual(universe_count, 3)
        self.assertEqual(universe_member_count, 3)
        self.assertEqual(float(candle["close"]), 13.0)
        self.assertEqual(candle["volume"], 200)
        self.assertEqual(report_count, 1)
        self.assertEqual(market_cap, 123)

    def test_repository_reads_and_histories_universe_members(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = RawDataRepository(engine)

        repository.upsert_tickers(
            [
                TickerUpsert("AAA", "Asset AAA", "Tech"),
                TickerUpsert("BBB", "Asset BBB", "Health"),
            ],
            sync_time=datetime(2026, 5, 20, 12, 0),
        )
        repository.deactivate_missing_active_tickers(
            ["AAA"],
            sync_time=datetime(2026, 5, 25, 12, 0),
        )
        repository.upsert_universe_members(
            [
                UniverseMemberUpsert(
                    universe_key="sp500_active",
                    ticker="BBB",
                    valid_from=date(2026, 5, 28),
                    source_provider_key="pytest",
                    imported_at=datetime(2026, 5, 28, 12, 0),
                )
            ]
        )

        universes = repository.list_universes()
        current_members = repository.load_universe_members("sp500_active")
        historical_members = repository.load_universe_members(
            "sp500_active",
            as_of_date=date(2026, 5, 21),
        )

        self.assertEqual([universe.key for universe in universes], [
            "active_tickers",
            "all_tickers",
            "sp500_active",
        ])
        self.assertEqual([member.ticker for member in current_members], ["AAA", "BBB"])
        self.assertEqual(
            [member.ticker for member in historical_members],
            ["AAA", "BBB"],
        )

    def test_repository_reads_provider_identifiers_and_coverage(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = RawDataRepository(engine)

        repository.upsert_tickers([TickerUpsert("AAA", "Asset AAA", "Tech")])
        repository.upsert_provider_identifiers(
            [
                ProviderIdentifier(
                    ticker="AAA",
                    provider_key="yfinance",
                    identifier_scheme="ticker",
                    provider_symbol="AAA",
                    market="US",
                    quote_currency="USD",
                    is_primary=True,
                )
            ]
        )

        identifiers = repository.list_provider_identifiers(
            provider_key="yfinance",
            tickers=["AAA"],
        )
        coverage = repository.provider_identifier_coverage(
            source_role="prices",
            provider_key="yfinance",
            tickers=["AAA", "BBB"],
        )

        self.assertEqual(len(identifiers), 1)
        self.assertEqual(identifiers[0].provider_symbol, "AAA")
        self.assertEqual(coverage.covered_tickers, ("AAA",))
        self.assertEqual(coverage.missing_tickers, ("BBB",))

    def test_data_quality_diagnostics_report_missing_stale_and_identifier_gaps(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = RawDataRepository(engine)
        sync_time = datetime(2026, 5, 29, 12, 0)
        repository.upsert_tickers(
            [
                TickerUpsert("AAA", "Asset AAA", "Tech"),
                TickerUpsert("BBB", "Asset BBB", "Health"),
            ],
            sync_time=sync_time,
        )
        repository.ensure_ticker(
            "SPY",
            name="SPDR S&P 500 ETF Trust",
            sector="Benchmark",
            is_active=False,
            sync_time=sync_time,
        )
        repository.upsert_provider_identifiers(
            [
                ProviderIdentifier(
                    ticker="AAA",
                    provider_key="yfinance",
                    identifier_scheme="ticker",
                    provider_symbol="AAA",
                    is_primary=True,
                )
            ]
        )
        repository.upsert_daily_candles(
            [
                DailyCandle(
                    "AAA",
                    date(2026, 5, 29),
                    Decimal("10"),
                    Decimal("11"),
                    Decimal("9"),
                    Decimal("10.5"),
                    100,
                ),
                DailyCandle(
                    "SPY",
                    date(2026, 5, 20),
                    Decimal("20"),
                    Decimal("21"),
                    Decimal("19"),
                    Decimal("20.5"),
                    100,
                ),
            ]
        )
        repository.upsert_financial_reports(
            [
                FinancialReport(
                    ticker="AAA",
                    report_date=date(2026, 3, 31),
                    report_type="ttm",
                    revenue=100,
                    net_income=10,
                    ebit=9,
                    free_cash_flow=8,
                    total_debt=7,
                    total_equity=6,
                    cash_and_equivalents=5,
                    source="test",
                    imported_at=sync_time,
                )
            ]
        )
        repository.upsert_market_caps(
            [
                MarketCapSnapshot(
                    ticker="AAA",
                    date=date(2026, 5, 20),
                    market_cap=123,
                    imported_at=sync_time,
                )
            ]
        )

        run_id = repository.start_data_sync_run(
            sync_type="prices",
            provider_key="yfinance",
            source_role="prices",
            mode="daily",
            dry_run=False,
            started_at=datetime(2026, 5, 29, 10, 0),
        )
        repository.fail_data_sync_run(
            run_id,
            error_message="RuntimeError: provider unavailable",
            finished_at=datetime(2026, 5, 29, 10, 1),
        )

        report = DataQualityDiagnostics(engine).build_report(
            universe_key="sp500_active",
            benchmark_ticker="SPY",
            as_of_date=date(2026, 5, 31),
            price_stale_days=5,
            market_cap_stale_days=5,
            identifier_provider_key="yfinance",
            sync_provider_key="yfinance",
            now=datetime(2026, 5, 31, 12, 0),
        )
        lines = format_data_quality_report(report, sample_limit=5)

        self.assertEqual(report.status, "warning")
        self.assertEqual(report.prices.status, "missing_stale")
        self.assertEqual(report.prices.missing_tickers, ("BBB",))
        self.assertEqual(report.prices.stale_tickers, ("SPY",))
        self.assertEqual(report.fundamentals.status, "missing")
        self.assertEqual(report.fundamentals.missing_tickers, ("BBB",))
        self.assertEqual(report.market_caps.status, "missing_stale")
        self.assertEqual(report.provider_identifiers.status, "missing")
        self.assertIn("data_quality.prices status=missing_stale", lines[1])
        self.assertIn("data_quality.sync type=prices status=failed", "\n".join(lines))

    def test_price_sync_uses_provider_symbol_and_stores_internal_ticker(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = RawDataRepository(engine)
        repository.upsert_tickers([TickerUpsert("BRK-B", "Berkshire", "Financials")])
        repository.upsert_provider_identifiers(
            [
                ProviderIdentifier(
                    ticker="BRK-B",
                    provider_key="yfinance",
                    identifier_scheme="ticker",
                    provider_symbol="BRK.B",
                    is_primary=True,
                )
            ]
        )
        price_source = FakePriceSource()

        result = PriceSyncService(
            repository=repository,
            price_source=price_source,
        ).run(
            mode="daily",
            tickers=["BRK-B"],
            dry_run=False,
            today=date(2026, 5, 29),
            now=datetime(2026, 5, 29, 12, 0),
        )

        with engine.connect() as connection:
            candle_tickers = [
                row[0]
                for row in connection.execute(
                    text("SELECT ticker FROM asset_price_bars ORDER BY ticker")
                )
            ]

        self.assertIn("BRK.B", [call[0] for call in price_source.calls])
        self.assertIn("BRK-B", candle_tickers)
        self.assertEqual(result.planned[0].ticker, "BRK-B")
        self.assertEqual(result.planned[0].provider_symbol, "BRK.B")
        self.assertIsNotNone(result.sync_run_id)

        run = repository.list_data_sync_runs(limit=1)[0]
        self.assertEqual(run.sync_type, "prices")
        self.assertEqual(run.provider_key, "yfinance")
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.planned_items, 2)
        self.assertEqual(run.processed_items, 2)
        self.assertEqual(run.upserted_candles, 2)

    def test_price_sync_records_membership_audit_when_refreshing_tickers(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = RawDataRepository(engine)
        ticker_source = FakeTickerSource(
            [TickerUpsert("AAA", "Asset AAA", "Tech")]
        )
        price_source = FakePriceSource()

        result = PriceSyncService(
            repository=repository,
            ticker_source=ticker_source,
            price_source=price_source,
        ).run(
            mode="daily",
            dry_run=False,
            today=date(2026, 5, 29),
            now=datetime(2026, 5, 29, 12, 0),
        )

        runs = repository.list_data_sync_runs(limit=5)
        run_by_type = {run.sync_type: run for run in runs}

        self.assertIsNotNone(result.membership_sync_run_id)
        self.assertEqual(run_by_type["membership"].provider_key, "wikipedia_sp500")
        self.assertEqual(run_by_type["membership"].status, "ok")
        self.assertEqual(run_by_type["membership"].ticker_upserts, 1)
        self.assertEqual(run_by_type["prices"].status, "ok")

    def test_fundamental_sync_uses_provider_symbol_and_stores_internal_ticker(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = RawDataRepository(engine)
        repository.upsert_tickers([TickerUpsert("AAA", "Asset AAA", "Tech")])
        repository.upsert_provider_identifiers(
            [
                ProviderIdentifier(
                    ticker="AAA",
                    provider_key="yfinance",
                    identifier_scheme="ticker",
                    provider_symbol="AAA.DE",
                    is_primary=True,
                )
            ]
        )
        fundamental_source = FakeFundamentalSource()

        result = FundamentalSyncService(
            repository=repository,
            fundamental_source=fundamental_source,
        ).run(
            mode="daily",
            tickers=["AAA"],
            dry_run=False,
            now=datetime(2026, 5, 29, 12, 0),
        )

        with engine.connect() as connection:
            report_ticker = connection.execute(
                text("SELECT ticker FROM asset_fundamental_reports")
            ).scalar_one()
            market_cap_ticker = connection.execute(
                text("SELECT ticker FROM asset_market_caps")
            ).scalar_one()

        self.assertEqual(fundamental_source.calls, ["AAA.DE"])
        self.assertEqual(report_ticker, "AAA")
        self.assertEqual(market_cap_ticker, "AAA")
        self.assertEqual(result.planned[0].provider_symbol, "AAA.DE")
        self.assertIsNotNone(result.sync_run_id)

        run = repository.list_data_sync_runs(limit=1)[0]
        self.assertEqual(run.sync_type, "fundamentals")
        self.assertEqual(run.provider_key, "yfinance")
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.planned_items, 1)
        self.assertEqual(run.processed_items, 1)
        self.assertEqual(run.updated_tickers, 1)
        self.assertEqual(run.upserted_reports, 1)
        self.assertEqual(run.upserted_market_caps, 1)

    def test_price_sync_records_failed_audit_run(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = RawDataRepository(engine)
        repository.upsert_tickers([TickerUpsert("AAA", "Asset AAA", "Tech")])

        with self.assertRaises(RuntimeError):
            PriceSyncService(
                repository=repository,
                price_source=FailingPriceSource(),
            ).run(
                mode="daily",
                tickers=["AAA"],
                dry_run=False,
                today=date(2026, 5, 29),
                now=datetime(2026, 5, 29, 12, 0),
            )

        run = repository.list_data_sync_runs(limit=1)[0]
        self.assertEqual(run.sync_type, "prices")
        self.assertEqual(run.status, "failed")
        self.assertIn("RuntimeError: provider unavailable", run.error_message)

    def test_price_sync_records_failed_audit_for_setup_errors(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = FailingEnsureTickerRepository(engine)
        repository.upsert_tickers([TickerUpsert("AAA", "Asset AAA", "Tech")])

        with self.assertRaises(RuntimeError):
            PriceSyncService(repository=repository).run(
                mode="daily",
                tickers=["AAA"],
                dry_run=False,
                today=date(2026, 5, 29),
                now=datetime(2026, 5, 29, 12, 0),
            )

        run = repository.list_data_sync_runs(limit=1)[0]
        self.assertEqual(run.sync_type, "prices")
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.requested_tickers_count, 2)
        self.assertIn("RuntimeError: benchmark setup failed", run.error_message)

    def test_price_sync_retries_and_throttles_provider_requests(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = RawDataRepository(engine)
        repository.upsert_tickers(
            [
                TickerUpsert("AAA", "Asset AAA", "Tech"),
                TickerUpsert("BBB", "Asset BBB", "Tech"),
            ]
        )
        sleeps = []
        price_source = FlakyPriceSource(failures_before_success=1)

        result = PriceSyncService(
            repository=repository,
            price_source=price_source,
            request_policy=SyncRequestPolicy(
                batch_size=1,
                throttle_seconds=0.25,
                max_retries=1,
                backoff_seconds=0.5,
                circuit_breaker_failures=5,
            ),
            sleep_func=sleeps.append,
        ).run(
            mode="daily",
            tickers=["AAA", "BBB"],
            dry_run=False,
            today=date(2026, 5, 29),
            now=datetime(2026, 5, 29, 12, 0),
        )

        self.assertEqual(result.downloaded_tickers, 3)
        self.assertEqual(result.upserted_candles, 3)
        self.assertEqual(sleeps.count(0.5), 3)
        self.assertEqual(sleeps.count(0.25), 2)

    def test_price_sync_circuit_breaker_records_failed_audit_run(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = RawDataRepository(engine)
        repository.upsert_tickers([TickerUpsert("AAA", "Asset AAA", "Tech")])

        with self.assertRaises(ProviderCircuitBreakerOpen):
            PriceSyncService(
                repository=repository,
                price_source=FailingPriceSource(),
                request_policy=SyncRequestPolicy(
                    max_retries=4,
                    backoff_seconds=0,
                    circuit_breaker_failures=2,
                ),
                sleep_func=lambda seconds: None,
            ).run(
                mode="daily",
                tickers=["AAA"],
                dry_run=False,
                today=date(2026, 5, 29),
                now=datetime(2026, 5, 29, 12, 0),
            )

        run = repository.list_data_sync_runs(limit=1)[0]
        self.assertEqual(run.sync_type, "prices")
        self.assertEqual(run.status, "failed")
        self.assertIn("ProviderCircuitBreakerOpen", run.error_message)

    def test_fundamental_sync_records_failed_audit_for_selection_errors(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _create_raw_tables(engine)
        repository = FailingFundamentalSelectionRepository(engine)

        with self.assertRaises(RuntimeError):
            FundamentalSyncService(repository=repository).run(
                mode="daily",
                dry_run=False,
                now=datetime(2026, 5, 29, 12, 0),
            )

        run = repository.list_data_sync_runs(limit=1)[0]
        self.assertEqual(run.sync_type, "fundamentals")
        self.assertEqual(run.status, "failed")
        self.assertIn("RuntimeError: selection failed", run.error_message)


class FakePriceSource:
    def __init__(self) -> None:
        self.calls = []

    def download_prices(self, ticker: str, start_date: date, end_date: date):
        self.calls.append((ticker, start_date, end_date))
        return pd.DataFrame(
            {
                "Open": [10.0],
                "High": [11.0],
                "Low": [9.0],
                "Close": [10.5],
                "Volume": [1000],
            },
            index=pd.DatetimeIndex([end_date], name="Date"),
        )


class FailingPriceSource:
    def download_prices(self, ticker: str, start_date: date, end_date: date):
        raise RuntimeError("provider unavailable")


class FlakyPriceSource:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self.calls_by_ticker: dict[str, int] = {}

    def download_prices(self, ticker: str, start_date: date, end_date: date):
        self.calls_by_ticker[ticker] = self.calls_by_ticker.get(ticker, 0) + 1
        if self.calls_by_ticker[ticker] <= self.failures_before_success:
            raise RuntimeError("temporary provider failure")
        return pd.DataFrame(
            {
                "Open": [10.0],
                "High": [11.0],
                "Low": [9.0],
                "Close": [10.5],
                "Volume": [1000],
            },
            index=pd.DatetimeIndex([end_date], name="Date"),
        )


class FakeTickerSource:
    def __init__(self, tickers: list[TickerUpsert]) -> None:
        self.tickers = tickers

    def list_tickers(self) -> list[TickerUpsert]:
        return self.tickers


class FailingEnsureTickerRepository(RawDataRepository):
    def ensure_ticker(self, *args, **kwargs) -> None:
        raise RuntimeError("benchmark setup failed")


class FailingFundamentalSelectionRepository(RawDataRepository):
    def select_tickers_for_fundamental_sync(self, *args, **kwargs) -> list[str]:
        raise RuntimeError("selection failed")


class FakeFundamentalSource:
    def __init__(self) -> None:
        self.calls = []

    def load_fundamentals(
        self,
        ticker: str,
        imported_at: datetime | None = None,
    ) -> FinancialSyncPayload:
        self.calls.append(ticker)
        imported_at = imported_at or datetime(2026, 5, 29, 12, 0)
        return FinancialSyncPayload(
            reports=(
                FinancialReport(
                    ticker=ticker,
                    report_date=date(2026, 3, 31),
                    report_type="ttm",
                    revenue=100,
                    net_income=10,
                    ebit=9,
                    free_cash_flow=8,
                    total_debt=7,
                    total_equity=6,
                    cash_and_equivalents=5,
                    source="fake",
                    imported_at=imported_at,
                ),
            ),
            market_cap=MarketCapSnapshot(
                ticker=ticker,
                date=imported_at.date(),
                market_cap=123,
                imported_at=imported_at,
            ),
        )


def _create_raw_tables(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE assets (
                    ticker VARCHAR(32) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    sector VARCHAR(255),
                    asset_class VARCHAR(32) NOT NULL DEFAULT 'equity',
                    canonical_symbol VARCHAR(64),
                    display_symbol VARCHAR(64),
                    instrument_type VARCHAR(32) NOT NULL DEFAULT 'stock',
                    exchange_code VARCHAR(64),
                    market VARCHAR(64) DEFAULT 'US',
                    quote_currency CHAR(3) NOT NULL DEFAULT 'USD',
                    primary_provider_key VARCHAR(64) DEFAULT 'mysql_fixture',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    first_seen DATETIME,
                    last_seen DATETIME,
                    removed_at DATETIME,
                    last_fundamental_update DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE universes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    universe_key VARCHAR(100) NOT NULL UNIQUE,
                    name VARCHAR(255) NOT NULL,
                    description VARCHAR(500),
                    asset_classes VARCHAR(255) NOT NULL DEFAULT 'equity',
                    membership_source_role VARCHAR(64) NOT NULL DEFAULT 'membership',
                    membership_provider_key VARCHAR(64) NOT NULL DEFAULT 'mysql_fixture',
                    membership_rule VARCHAR(255) NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE universe_members (
                    universe_id INTEGER NOT NULL,
                    ticker VARCHAR(32) NOT NULL,
                    valid_from DATE NOT NULL,
                    valid_to DATE,
                    source_provider_key VARCHAR(64),
                    imported_at DATETIME,
                    PRIMARY KEY (universe_id, ticker, valid_from)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE asset_provider_identifiers (
                    ticker VARCHAR(32) NOT NULL,
                    provider_key VARCHAR(64) NOT NULL,
                    identifier_scheme VARCHAR(64) NOT NULL DEFAULT 'ticker',
                    provider_symbol VARCHAR(128) NOT NULL,
                    provider_asset_id VARCHAR(128),
                    exchange_code VARCHAR(64),
                    market VARCHAR(64),
                    quote_currency CHAR(3),
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    valid_from DATE,
                    valid_to DATE,
                    imported_at DATETIME,
                    PRIMARY KEY (
                        ticker,
                        provider_key,
                        identifier_scheme,
                        provider_symbol
                    )
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE asset_price_bars (
                    ticker VARCHAR(32) NOT NULL,
                    date DATE NOT NULL,
                    open NUMERIC,
                    high NUMERIC,
                    low NUMERIC,
                    close NUMERIC,
                    volume INTEGER,
                    PRIMARY KEY (ticker, date)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE asset_fundamental_reports (
                    ticker VARCHAR(32) NOT NULL,
                    report_date DATE NOT NULL,
                    report_type VARCHAR(20) NOT NULL,
                    revenue INTEGER,
                    net_income INTEGER,
                    ebit INTEGER,
                    free_cash_flow INTEGER,
                    total_debt INTEGER,
                    total_equity INTEGER,
                    cash_and_equivalents INTEGER,
                    source VARCHAR(50),
                    imported_at DATETIME,
                    PRIMARY KEY (ticker, report_date, report_type)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE asset_market_caps (
                    ticker VARCHAR(32) NOT NULL,
                    date DATE NOT NULL,
                    market_cap INTEGER,
                    imported_at DATETIME,
                    PRIMARY KEY (ticker, date)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE data_sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_type VARCHAR(32) NOT NULL,
                    provider_key VARCHAR(64),
                    source_role VARCHAR(64),
                    mode VARCHAR(32) NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'started',
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    started_at DATETIME NOT NULL,
                    finished_at DATETIME,
                    date_from DATE,
                    date_to DATE,
                    requested_tickers_count INTEGER,
                    planned_items INTEGER NOT NULL DEFAULT 0,
                    processed_items INTEGER NOT NULL DEFAULT 0,
                    upserted_rows INTEGER NOT NULL DEFAULT 0,
                    ticker_upserts INTEGER NOT NULL DEFAULT 0,
                    deactivated_tickers INTEGER NOT NULL DEFAULT 0,
                    upserted_candles INTEGER NOT NULL DEFAULT 0,
                    updated_tickers INTEGER NOT NULL DEFAULT 0,
                    upserted_reports INTEGER NOT NULL DEFAULT 0,
                    upserted_market_caps INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT
                )
                """
            )
        )


if __name__ == "__main__":
    unittest.main()
