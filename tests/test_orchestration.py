from datetime import date

import pandas as pd
import pytest

from cli.errors import CliUsageError
from cli.orchestration import StrategyRunConfig, run_strategy_snapshot
from data.models import Ticker


class FakeProvider:
    key = "fake"

    def __init__(self, benchmark_prices=None):
        self._benchmark_prices = benchmark_prices

    def list_tickers(self, active_only=False):
        return [
            Ticker("AAA", "AAA Inc", "Tech", True, None, None, None, None),
            Ticker("BBB", "BBB Inc", "Health", True, None, None, None, None),
        ]

    def load_prices(self, tickers=None, start_date=None, end_date=None):
        frame = pd.DataFrame(
            [
                _price("AAA", date(2024, 1, 1), 100),
                _price("AAA", date(2024, 1, 31), 130),
                _price("BBB", date(2024, 1, 1), 100),
                _price("BBB", date(2024, 1, 31), 110),
            ]
        )
        return _filter_frame(frame, tickers, start_date, end_date, "date")

    def load_fundamentals(
        self,
        tickers=None,
        report_type=None,
        start_date=None,
        end_date=None,
    ):
        frame = pd.DataFrame(
            [
                _fundamental("AAA", date(2023, 12, 31), 20, 18, 10, 100),
                _fundamental("BBB", date(2023, 12, 31), 10, 8, 30, 100),
            ]
        )
        return _filter_frame(frame, tickers, start_date, end_date, "report_date")

    def load_market_caps(self, tickers=None, start_date=None, end_date=None):
        frame = pd.DataFrame(
            [
                {"ticker": "AAA", "date": date(2024, 1, 31), "market_cap": 100},
                {"ticker": "BBB", "date": date(2024, 1, 31), "market_cap": 100},
            ]
        )
        return _filter_frame(frame, tickers, start_date, end_date, "date")

    def load_benchmark_prices(self, benchmark_ticker, start_date=None, end_date=None):
        if self._benchmark_prices is not None:
            return self._benchmark_prices
        frame = pd.DataFrame(
            [
                _price(benchmark_ticker, date(2024, 1, 1), 200),
                _price(benchmark_ticker, date(2024, 1, 31), 210),
            ]
        )
        return _filter_frame(frame, [benchmark_ticker], start_date, end_date, "date")


def test_strategy_snapshot_uses_latest_trading_date_and_model_portfolio():
    artifacts = run_strategy_snapshot(
        FakeProvider(),
        StrategyRunConfig(lookback_days=30, portfolio_size=1),
    )

    assert artifacts.as_of_date == date(2024, 1, 31)
    assert artifacts.benchmark_ticker == "SPY"
    assert len(artifacts.members) == 2
    assert list(artifacts.model_portfolio["ticker"]) == ["AAA"]


def test_strategy_snapshot_reports_missing_benchmark_as_operator_error():
    with pytest.raises(CliUsageError, match="benchmark price rows is empty"):
        run_strategy_snapshot(
            FakeProvider(benchmark_prices=pd.DataFrame()),
            StrategyRunConfig(lookback_days=30, portfolio_size=1),
        )


def _price(ticker, day, close):
    return {
        "ticker": ticker,
        "date": day,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1000,
    }


def _fundamental(
    ticker,
    report_date,
    net_income,
    free_cash_flow,
    total_debt,
    total_equity,
):
    return {
        "ticker": ticker,
        "report_date": report_date,
        "report_type": "ttm",
        "revenue": 100,
        "net_income": net_income,
        "ebit": net_income,
        "free_cash_flow": free_cash_flow,
        "total_debt": total_debt,
        "total_equity": total_equity,
        "cash_and_equivalents": 0,
    }


def _filter_frame(frame, tickers, start_date, end_date, date_column):
    result = frame.copy()
    if tickers is not None:
        result = result[result["ticker"].isin(tickers)]
    if start_date is not None:
        result = result[result[date_column] >= start_date]
    if end_date is not None:
        result = result[result[date_column] <= end_date]
    return result.reset_index(drop=True)
