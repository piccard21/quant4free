from datetime import date
import unittest

import pandas as pd

from evaluation import BacktestConfig, calculate_metrics, run_backtest
from strategies import StrategyContext, StrategyResult


class StaticStrategy:
    key = "static"
    version = "1.0"

    def run(self, context: StrategyContext) -> StrategyResult:
        return StrategyResult(
            strategy_key=self.key,
            strategy_version=self.version,
            as_of_date=context.as_of_date,
            rankings=pd.DataFrame(
                [
                    {
                        "ticker": "AAA",
                        "rank": 1,
                        "model_weight": 1.0,
                        "composite_score": 1.0,
                    }
                ]
            ),
        )


class BacktestTests(unittest.TestCase):
    def test_backtest_builds_equity_curve_trades_and_metrics(self):
        prices = pd.DataFrame(
            [
                {"ticker": "AAA", "date": date(2024, 1, 1), "close": 100},
                {"ticker": "AAA", "date": date(2024, 1, 2), "close": 110},
                {"ticker": "AAA", "date": date(2024, 1, 3), "close": 120},
            ]
        )
        benchmark = pd.DataFrame(
            [
                {"ticker": "SPY", "date": date(2024, 1, 1), "close": 200},
                {"ticker": "SPY", "date": date(2024, 1, 2), "close": 202},
                {"ticker": "SPY", "date": date(2024, 1, 3), "close": 204},
            ]
        )

        result = run_backtest(
            strategy=StaticStrategy(),
            config=BacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 3),
                initial_capital=1000,
                rebalance_days=30,
                lookback_days=1,
                transaction_cost_bps=0,
            ),
            universe=["AAA"],
            prices=prices,
            fundamentals=pd.DataFrame(
                columns=[
                    "ticker",
                    "report_date",
                    "net_income",
                    "free_cash_flow",
                    "total_debt",
                    "total_equity",
                ]
            ),
            market_caps=pd.DataFrame(columns=["ticker", "date", "market_cap"]),
            benchmark_prices=benchmark,
        )

        self.assertEqual(len(result.equity_curve), 3)
        self.assertEqual(len(result.trades), 1)
        self.assertAlmostEqual(
            result.equity_curve["portfolio_value"].iloc[-1],
            1200.0,
        )
        self.assertAlmostEqual(result.metrics["total_return"], 0.2)
        self.assertAlmostEqual(result.metrics["benchmark_return"], 0.02)
        self.assertAlmostEqual(result.metrics["outperformance"], 0.18)

    def test_metrics_include_max_drawdown(self):
        equity_curve = pd.DataFrame(
            {
                "portfolio_value": [100.0, 80.0, 120.0],
                "benchmark_value": [100.0, 100.0, 100.0],
                "daily_return": [None, -0.2, 0.5],
                "drawdown": [0.0, -0.2, 0.0],
            }
        )

        metrics = calculate_metrics(equity_curve)

        self.assertEqual(metrics["max_drawdown"], -0.2)


if __name__ == "__main__":
    unittest.main()
