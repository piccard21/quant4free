from datetime import date
import unittest

import pandas as pd

from strategies import StrategyContext, ValueQualityMomentumStrategy


class ValueQualityMomentumStrategyTests(unittest.TestCase):
    def test_strategy_ranks_and_builds_equal_weight_model_portfolio(self):
        context = _context(
            pd.DataFrame(
                [
                    _indicator_row("AAA", 0.10, 0.08, 0.20, 0.20, 0.30, 1.0),
                    _indicator_row("BBB", 0.06, 0.05, 0.10, 0.10, 0.20, 0.5),
                    _indicator_row("CCC", 0.02, 0.01, 0.05, 0.60, 0.10, 0.25),
                ]
            )
        )
        strategy = ValueQualityMomentumStrategy(portfolio_size=2)

        result = strategy.run(context)

        self.assertEqual(list(result.rankings["ticker"].head(2)), ["AAA", "BBB"])
        self.assertEqual(result.rankings.loc[0, "rank"], 1)
        self.assertEqual(result.rankings.loc[1, "rank"], 2)
        self.assertEqual(result.rankings.loc[0, "model_weight"], 0.5)
        self.assertEqual(result.rankings.loc[1, "model_weight"], 0.5)
        self.assertEqual(result.rankings.loc[2, "model_weight"], 0.0)

    def test_weights_must_sum_to_one(self):
        with self.assertRaisesRegex(ValueError, "sum to 1.0"):
            ValueQualityMomentumStrategy(
                factor_weights={
                    "value": 0.5,
                    "quality": 0.3,
                    "momentum": 0.3,
                }
            )

    def test_weights_must_use_expected_keys(self):
        with self.assertRaisesRegex(ValueError, "factor_weights"):
            ValueQualityMomentumStrategy(
                factor_weights={
                    "value": 0.5,
                    "quality": 0.5,
                    "growth": 0.0,
                }
            )

    def test_missing_indicator_values_remain_unranked(self):
        context = _context(
            pd.DataFrame(
                [
                    _indicator_row("AAA", 0.10, 0.08, 0.20, 0.20, 0.30, 1.0),
                    _indicator_row("BBB", 0.06, None, 0.10, 0.10, 0.20, 0.5),
                ]
            )
        )

        result = ValueQualityMomentumStrategy(portfolio_size=2).run(context)
        values = result.rankings.set_index("ticker")

        self.assertTrue(pd.isna(values.loc["BBB", "composite_score"]))
        self.assertEqual(values.loc["BBB", "model_weight"], 0.0)


def _indicator_row(
    ticker,
    earnings_yield,
    free_cash_flow_yield,
    return_on_equity,
    debt_to_equity,
    momentum_return,
    relative_strength,
):
    return {
        "ticker": ticker,
        "earnings_yield": earnings_yield,
        "free_cash_flow_yield": free_cash_flow_yield,
        "return_on_equity": return_on_equity,
        "debt_to_equity": debt_to_equity,
        "momentum_return": momentum_return,
        "relative_strength": relative_strength,
    }


def _context(indicators):
    return StrategyContext(
        as_of_date=date(2024, 1, 31),
        universe=["AAA", "BBB", "CCC"],
        prices=pd.DataFrame(),
        fundamentals=pd.DataFrame(),
        market_caps=pd.DataFrame(),
        benchmark_prices=pd.DataFrame(),
        indicators={"default": indicators},
    )


if __name__ == "__main__":
    unittest.main()
