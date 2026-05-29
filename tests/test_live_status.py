from datetime import date

from live import PortfolioTarget, RealPosition, build_live_status


def test_live_status_classifies_missing_and_extra_real_positions():
    as_of_date = date(2026, 5, 22)
    model = [
        PortfolioTarget("AAA", "model", as_of_date, 0.5, rank=1),
        PortfolioTarget("BBB", "model", as_of_date, 0.5, rank=2),
    ]
    shadow = [
        PortfolioTarget("AAA", "shadow", as_of_date, 0.5, rank=1),
        PortfolioTarget("BBB", "shadow", as_of_date, 0.5, rank=2),
    ]
    real = [
        RealPosition("AAA", shares=10, average_price=10, opened_at=as_of_date),
        RealPosition("CCC", shares=5, average_price=20, opened_at=as_of_date),
    ]

    status = build_live_status(model, shadow, real, cash_balance=0)

    states = {gap.ticker: gap.state for gap in status.gaps}
    assert states == {
        "AAA": "aligned",
        "BBB": "missing_in_real",
        "CCC": "extra_in_real",
    }
    assert status.model_positions == 2
    assert status.shadow_positions == 2
    assert status.real_positions == 2
    assert status.invested_value == 200
    assert status.total_value == 200
    assert len(status.actionable_gaps) == 2


def test_live_status_uses_cash_when_calculating_real_weights():
    as_of_date = date(2026, 5, 22)
    target = [PortfolioTarget("AAA", "shadow", as_of_date, 0.5, rank=1)]
    real = [RealPosition("AAA", shares=10, average_price=10, opened_at=as_of_date)]

    status = build_live_status(
        model=target,
        shadow=target,
        real=real,
        cash_balance=100,
        weight_tolerance=0.0,
    )

    gap = status.gaps[0]
    assert gap.ticker == "AAA"
    assert gap.real_weight == 0.5
    assert gap.weight_gap == 0.0
    assert gap.state == "aligned"


def test_live_status_flags_model_to_shadow_gap_before_real_gap():
    as_of_date = date(2026, 5, 22)
    model = [PortfolioTarget("AAA", "model", as_of_date, 1.0, rank=1)]

    status = build_live_status(
        model=model,
        shadow=[],
        real=[],
        cash_balance=100,
    )

    assert status.gaps[0].ticker == "AAA"
    assert status.gaps[0].state == "model_not_shadow"
