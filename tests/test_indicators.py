from datetime import date
import unittest

import pandas as pd

from indicators import (
    EarningsYieldIndicator,
    MomentumReturnIndicator,
    RelativeStrengthIndicator,
    compute_indicators,
)


class IndicatorTests(unittest.TestCase):
    def test_momentum_uses_latest_prices_around_lookback(self):
        prices = pd.DataFrame(
            [
                {"ticker": "AAA", "date": date(2024, 1, 1), "close": 100},
                {"ticker": "AAA", "date": date(2024, 1, 31), "close": 125},
                {"ticker": "BBB", "date": date(2024, 1, 31), "close": 50},
            ]
        )

        result = MomentumReturnIndicator().compute(
            prices,
            as_of_date=date(2024, 1, 31),
            params={"lookback_days": 30},
        )

        values = result.values.set_index("ticker")
        self.assertEqual(values.loc["AAA", "momentum_return"], 0.25)
        self.assertTrue(pd.isna(values.loc["BBB", "momentum_return"]))

    def test_relative_strength_keeps_missing_momentum_as_nan(self):
        prices = pd.DataFrame(
            [
                {"ticker": "AAA", "date": date(2024, 1, 1), "close": 100},
                {"ticker": "AAA", "date": date(2024, 1, 31), "close": 125},
                {"ticker": "BBB", "date": date(2024, 1, 1), "close": 100},
                {"ticker": "BBB", "date": date(2024, 1, 31), "close": 110},
                {"ticker": "CCC", "date": date(2024, 1, 31), "close": 20},
            ]
        )

        result = RelativeStrengthIndicator().compute(
            prices,
            as_of_date=date(2024, 1, 31),
            params={"lookback_days": 30},
        )

        values = result.values.set_index("ticker")
        self.assertEqual(values.loc["AAA", "relative_strength"], 1.0)
        self.assertEqual(values.loc["BBB", "relative_strength"], 0.5)
        self.assertTrue(pd.isna(values.loc["CCC", "relative_strength"]))

    def test_value_indicator_preserves_missing_market_cap(self):
        fundamentals = pd.DataFrame(
            [
                {
                    "ticker": "AAA",
                    "report_date": date(2024, 1, 1),
                    "net_income": 10,
                    "free_cash_flow": 8,
                    "total_debt": 2,
                    "total_equity": 50,
                },
                {
                    "ticker": "BBB",
                    "report_date": date(2024, 1, 1),
                    "net_income": 7,
                    "free_cash_flow": 6,
                    "total_debt": 1,
                    "total_equity": 40,
                },
            ]
        )
        market_caps = pd.DataFrame(
            [{"ticker": "AAA", "date": date(2024, 1, 31), "market_cap": 100}]
        )

        result = EarningsYieldIndicator().compute(
            pd.DataFrame(),
            fundamentals=fundamentals,
            market_caps=market_caps,
            as_of_date=date(2024, 1, 31),
        )

        values = result.values.set_index("ticker")
        self.assertEqual(values.loc["AAA", "earnings_yield"], 0.1)
        self.assertTrue(pd.isna(values.loc["BBB", "earnings_yield"]))

    def test_value_indicator_accepts_absent_optional_inputs(self):
        result = EarningsYieldIndicator().compute(
            pd.DataFrame(),
            fundamentals=None,
            market_caps=None,
            as_of_date=date(2024, 1, 31),
        )

        self.assertEqual(
            list(result.values.columns),
            [
                "ticker",
                "as_of_date",
                "report_date",
                "market_cap_date",
                "earnings_yield",
            ],
        )
        self.assertTrue(result.values.empty)

    def test_engine_merges_selected_indicators(self):
        prices = pd.DataFrame(
            [
                {"ticker": "AAA", "date": date(2024, 1, 1), "close": 100},
                {"ticker": "AAA", "date": date(2024, 1, 31), "close": 125},
            ]
        )

        values = compute_indicators(
            [MomentumReturnIndicator(), RelativeStrengthIndicator()],
            prices,
            as_of_date=date(2024, 1, 31),
            params={
                "momentum_return": {"lookback_days": 30},
                "relative_strength": {"lookback_days": 30},
            },
        )

        self.assertEqual(
            list(values.columns),
            ["ticker", "momentum_return", "relative_strength"],
        )


if __name__ == "__main__":
    unittest.main()
