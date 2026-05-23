import argparse
import logging
from typing import Any

import pandas as pd
from sqlalchemy import text

from shared.settings import engine, load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

OK = "OK"
WARN = "WARN"
ERROR = "ERROR"


# --------------------------------------------------
# ARGUMENTE
# --------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Zeigt den aktuellen Status des Quant-Portfolio-Systems an."
    )
    parser.add_argument(
        "--as-of-date",
        dest="as_of_date",
        help="Optionaler Stichtag im Format YYYY-MM-DD. Standard: letzter verfügbarer Performance-Tag, sonst letzter Portfolio-Stichtag.",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Zusätzliche Details zu Portfolio, Rebalance, Trade Plan und Positionen anzeigen.",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Nur technische Konsistenz und System-Health anzeigen.",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


# --------------------------------------------------
# FORMAT
# --------------------------------------------------

def fmt_money(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:.2f}%"


def value_or_dash(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"
    return str(value)


def print_section(title: str) -> None:
    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


def print_header(as_of_date, overall_status: str, performance_date, shadow_snapshot_date, rebalance_snapshot_date, trade_plan_snapshot_date) -> None:
    print("\n" + "=" * 88)
    print(f"QUANT STATUS | {as_of_date} | GESAMTSTATUS: {overall_status}")
    print("=" * 88)
    print(f"Performance-Tag          : {performance_date if performance_date is not None else '-'}")
    print(f"Tradable-Shadow-Snapshot : {shadow_snapshot_date if shadow_snapshot_date is not None else '-'}")
    print(f"Rebalance-Snapshot       : {rebalance_snapshot_date if rebalance_snapshot_date is not None else '-'}")
    print(f"Trade-Plan-Snapshot      : {trade_plan_snapshot_date if trade_plan_snapshot_date is not None else '-'}")


def print_status_line(label: str, status: str, detail: str) -> None:
    print(f"[{status:<5}] {label:<24} {detail}")


def status_rank(status: str) -> int:
    return {OK: 0, WARN: 1, ERROR: 2}.get(status, 2)


def merge_status(current: str, new: str) -> str:
    return new if status_rank(new) > status_rank(current) else current


def get_overall_status(check_groups: list[tuple[str, str, list[tuple[str, str, str]]]]) -> str:
    overall = OK
    for _, group_status, _ in check_groups:
        overall = merge_status(overall, group_status)
    return overall


# --------------------------------------------------
# STICHTAGE
# --------------------------------------------------
def resolve_performance_date(as_of_date):
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT MAX(as_of_date)
                FROM performance_snapshots
                WHERE as_of_date <= :d
            """),
            {"d": as_of_date},
        ).scalar()

def get_latest_performance_date():
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT MAX(as_of_date) FROM performance_snapshots")
        ).scalar()


def get_latest_portfolio_date():
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT MAX(as_of_date)
                FROM trade_plan_summary
            """)
        ).scalar()


def get_latest_shadow_date():
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT MAX(as_of_date)
                FROM portfolio_snapshots
                WHERE snapshot_type = 'shadow'
            """)
        ).scalar()


def get_latest_factor_scores_date():
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT MAX(as_of_date) FROM factor_scores")
        ).scalar()


def resolve_as_of_date(cli_value: str | None):
    if cli_value:
        return cli_value

    candidates = [
        get_latest_portfolio_date(),
        get_latest_shadow_date(),
        get_latest_factor_scores_date(),
        get_latest_performance_date(),
    ]
    candidates = [d for d in candidates if d is not None]

    if not candidates:
        return None

    return max(candidates)


def resolve_model_snapshot_date(as_of_date):
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT MAX(as_of_date)
                FROM portfolio_snapshots
                WHERE snapshot_type = 'model'
                  AND as_of_date <= :d
            """),
            {"d": as_of_date},
        ).scalar()


def resolve_shadow_snapshot_date(as_of_date):
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT MAX(as_of_date)
                FROM portfolio_snapshots
                WHERE snapshot_type = 'shadow'
                  AND as_of_date <= :d
            """),
            {"d": as_of_date},
        ).scalar()


def resolve_rebalance_snapshot_date(as_of_date):
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT MAX(as_of_date)
                FROM rebalance_suggestions
                WHERE as_of_date <= :d
            """),
            {"d": as_of_date},
        ).scalar()


def resolve_trade_plan_snapshot_date(as_of_date):
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT MAX(as_of_date)
                FROM trade_plan_summary
                WHERE as_of_date <= :d
            """),
            {"d": as_of_date},
        ).scalar()


# --------------------------------------------------
# COUNTS / OVERVIEW
# --------------------------------------------------

def load_counts() -> dict[str, int]:
    tables = [
        "tickers",
        "daily_candles",
        "financial_reports",
        "market_cap_snapshots",
        "factor_metrics",
        "factor_scores",
        "portfolio_snapshots",
        "rebalance_suggestions",
        "decision_log",
        "trade_plan_summary",
        "trade_plan_snapshots",
        "trade_executions",
        "cash_ledger",
        "performance_snapshots",
        "portfolio_positions",
        "portfolio_cash",
    ]

    result: dict[str, int] = {}
    with engine.connect() as conn:
        for table in tables:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            result[table] = int(cnt or 0)
    return result


# --------------------------------------------------
# CASH / REAL / EXECUTIONS
# --------------------------------------------------

def load_cash_status(as_of_date) -> dict[str, Any]:
    with engine.connect() as conn:
        portfolio_cash = conn.execute(
            text("""
                SELECT cash_balance, updated_at
                FROM portfolio_cash
                WHERE updated_at <= :target_end
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            """),
            {"target_end": f"{as_of_date} 23:59:59"},
        ).mappings().first()

        if portfolio_cash is None:
            portfolio_cash = conn.execute(
                text("""
                    SELECT cash_balance, updated_at
                    FROM portfolio_cash
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                """)
            ).mappings().first()

        ledger_cash = conn.execute(
            text("""
                SELECT balance_after, booked_at
                FROM cash_ledger
                WHERE booked_at <= :target_end
                ORDER BY booked_at DESC, id DESC
                LIMIT 1
            """),
            {"target_end": f"{as_of_date} 23:59:59"},
        ).mappings().first()

    return {
        "portfolio_cash": None if portfolio_cash is None else portfolio_cash["cash_balance"],
        "portfolio_cash_updated_at": None if portfolio_cash is None else portfolio_cash["updated_at"],
        "ledger_cash": None if ledger_cash is None else ledger_cash["balance_after"],
        "ledger_cash_booked_at": None if ledger_cash is None else ledger_cash["booked_at"],
    }


def load_real_positions(as_of_date) -> pd.DataFrame:
    sql = text("""
        SELECT
            p.ticker,
            p.shares,
            p.buy_price,
            p.opened_at,
            p.is_open
        FROM portfolio_positions p
        WHERE p.is_open = 1
          AND p.opened_at <= :target_end
          AND (
                p.closed_at IS NULL
                OR p.closed_at > :target_date
              )
        ORDER BY p.opened_at ASC, p.ticker ASC
    """)

    with engine.connect() as conn:
        df = pd.read_sql(
            sql,
            conn,
            params={
                "target_end": f"{as_of_date} 23:59:59",
                "target_date": as_of_date,
            },
        )
    return df


def load_execution_status(as_of_date) -> dict[str, Any]:
    with engine.connect() as conn:
        executed = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM trade_executions
                WHERE status = 'executed'
                  AND executed_at <= :target_end
            """),
            {"target_end": f"{as_of_date} 23:59:59"},
        ).scalar()

        latest_execution = conn.execute(
            text("""
                SELECT
                    as_of_date,
                    ticker,
                    execution_type,
                    executed_at,
                    shares,
                    price,
                    net_amount,
                    realized_profit,
                    tax_amount
                FROM trade_executions
                WHERE status = 'executed'
                  AND executed_at <= :target_end
                ORDER BY executed_at DESC, id DESC
                LIMIT 1
            """),
            {"target_end": f"{as_of_date} 23:59:59"},
        ).mappings().first()

    return {
        "executed": int(executed or 0),
        "latest_execution": None if latest_execution is None else dict(latest_execution),
    }


def load_tax_status(as_of_date) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT
                    COUNT(*) AS executed_count,
                    COALESCE(SUM(CASE WHEN execution_type = 'SELL' THEN 1 ELSE 0 END), 0) AS sell_count,
                    COALESCE(SUM(CASE WHEN realized_profit IS NOT NULL THEN realized_profit ELSE 0 END), 0) AS realized_profit_total,
                    COALESCE(SUM(CASE WHEN realized_profit > 0 THEN realized_profit ELSE 0 END), 0) AS taxable_profit_total,
                    COALESCE(SUM(CASE WHEN tax_amount IS NOT NULL THEN tax_amount ELSE 0 END), 0) AS tax_paid_total
                FROM trade_executions
                WHERE status = 'executed'
                  AND executed_at <= :target_end
            """),
            {"target_end": f"{as_of_date} 23:59:59"},
        ).mappings().first()

    realized_profit_total = float(row["realized_profit_total"] or 0.0)
    taxable_profit_total = float(row["taxable_profit_total"] or 0.0)
    tax_paid_total = float(row["tax_paid_total"] or 0.0)

    effective_tax_rate = None
    if taxable_profit_total > 0:
        effective_tax_rate = tax_paid_total / taxable_profit_total

    return {
        "executed_count": int(row["executed_count"] or 0),
        "sell_count": int(row["sell_count"] or 0),
        "realized_profit_total": realized_profit_total,
        "taxable_profit_total": taxable_profit_total,
        "tax_paid_total": tax_paid_total,
        "effective_tax_rate": effective_tax_rate,
    }


# --------------------------------------------------
# SNAPSHOT-WELT
# --------------------------------------------------

def load_snapshot_presence(as_of_date) -> dict[str, int]:
    shadow_date = resolve_shadow_snapshot_date(as_of_date)
    rebalance_date = resolve_rebalance_snapshot_date(as_of_date)
    trade_plan_date = resolve_trade_plan_snapshot_date(as_of_date)

    result = {
        "factor_metrics": 0,
        "factor_scores": 0,
        "portfolio_shadow": 0,
        "rebalance": 0,
        "decision_log": 0,
        "trade_plan_summary": 0,
        "trade_plan": 0,
        "performance": 0,
    }

    with engine.connect() as conn:
        result["factor_metrics"] = int(
            conn.execute(
                text("SELECT COUNT(*) FROM factor_metrics WHERE as_of_date = :d"),
                {"d": as_of_date},
            ).scalar() or 0
        )
        result["factor_scores"] = int(
            conn.execute(
                text("SELECT COUNT(*) FROM factor_scores WHERE as_of_date = :d"),
                {"d": as_of_date},
            ).scalar() or 0
        )

        if shadow_date is not None:
            result["portfolio_shadow"] = int(
                conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM portfolio_snapshots
                        WHERE as_of_date = :d
                          AND snapshot_type = 'shadow'
                    """),
                    {"d": shadow_date},
                ).scalar() or 0
            )
        if rebalance_date is not None:
            result["rebalance"] = int(
                conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM rebalance_suggestions
                        WHERE as_of_date = :d
                    """),
                    {"d": rebalance_date},
                ).scalar() or 0
            )
            result["decision_log"] = int(
                conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM decision_log
                        WHERE as_of_date = :d
                    """),
                    {"d": rebalance_date},
                ).scalar() or 0
            )

        if trade_plan_date is not None:
            result["trade_plan_summary"] = int(
                conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM trade_plan_summary
                        WHERE as_of_date = :d
                    """),
                    {"d": trade_plan_date},
                ).scalar() or 0
            )
            result["trade_plan"] = int(
                conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM trade_plan_snapshots
                        WHERE as_of_date = :d
                    """),
                    {"d": trade_plan_date},
                ).scalar() or 0
            )

        performance_date = resolve_performance_date(as_of_date)
        if performance_date is not None:
            result["performance"] = int(
                conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM performance_snapshots
                        WHERE as_of_date = :d
                    """),
                    {"d": performance_date},
                ).scalar() or 0
            )

    return result

def load_model_portfolio(as_of_date) -> tuple[pd.DataFrame, Any]:
    snapshot_date = resolve_model_snapshot_date(as_of_date)
    if snapshot_date is None:
        return pd.DataFrame(), None

    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    portfolio_rank,
                    ticker,
                    sector,
                    source_rank,
                    final_score,
                    value_score,
                    quality_score,
                    momentum_score,
                    trend_positive,
                    target_weight
                FROM portfolio_snapshots
                WHERE as_of_date = :d
                  AND snapshot_type = 'model'
                ORDER BY portfolio_rank, ticker
            """),
            conn,
            params={"d": snapshot_date},
        )
    return df, snapshot_date

def load_shadow_portfolio(as_of_date) -> tuple[pd.DataFrame, Any]:
    snapshot_date = resolve_shadow_snapshot_date(as_of_date)
    if snapshot_date is None:
        return pd.DataFrame(), None

    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    portfolio_rank,
                    ticker,
                    sector,
                    source_rank,
                    final_score,
                    value_score,
                    quality_score,
                    momentum_score,
                    trend_positive,
                    target_weight,
                    holding_start_date
                FROM portfolio_snapshots
                WHERE as_of_date = :d
                  AND snapshot_type = 'shadow'
                ORDER BY portfolio_rank, ticker
            """),
            conn,
            params={"d": snapshot_date},
        )
    return df, snapshot_date


def load_rebalance(as_of_date) -> tuple[pd.DataFrame, Any]:
    snapshot_date = resolve_rebalance_snapshot_date(as_of_date)
    if snapshot_date is None:
        return pd.DataFrame(), None

    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    ticker,
                    sector,
                    action,
                    reason,
                    source_rank,
                    holding_days,
                    min_hold_ok,
                    current_shares
                FROM rebalance_suggestions
                WHERE as_of_date = :d
                ORDER BY
                    CASE action
                        WHEN 'SELL' THEN 1
                        WHEN 'BUY' THEN 2
                        ELSE 3
                    END,
                    source_rank,
                    ticker
            """),
            conn,
            params={"d": snapshot_date},
        )
    return df, snapshot_date


def load_cash_movements(as_of_date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    booked_at,
                    as_of_date,
                    entry_type,
                    amount,
                    balance_after,
                    notes
                FROM cash_ledger
                WHERE as_of_date = :d
                  AND entry_type IN ('deposit', 'withdrawal', 'correction')
                ORDER BY booked_at ASC, id ASC
            """),
            conn,
            params={"d": as_of_date},
        )

    if not df.empty:
        df["booked_at"] = pd.to_datetime(df["booked_at"])
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        df["balance_after"] = pd.to_numeric(df["balance_after"], errors="coerce").fillna(0.0)

    return df


def load_trade_plan(as_of_date) -> tuple[pd.DataFrame, dict[str, Any] | None, Any]:
    snapshot_date = resolve_trade_plan_snapshot_date(as_of_date)
    if snapshot_date is None:
        return pd.DataFrame(), None, None

    with engine.connect() as conn:
        trade_df = pd.read_sql(
            text("""
                SELECT
                    tps.ticker,
                    tps.action,
                    tps.execution_order,
                    tps.planned_shares,
                    tps.estimated_price,
                    tps.gross_amount,
                    tps.fee,
                    tps.net_amount,
                    tps.cash_before,
                    tps.cash_after,
                    tps.is_executable,
                    tps.skip_reason,
                    te.id AS trade_execution_id,
                    te.executed_at
                FROM trade_plan_snapshots tps
                LEFT JOIN trade_executions te
                  ON te.as_of_date = tps.as_of_date
                 AND te.ticker = tps.ticker
                 AND te.trade_plan_execution_order = tps.execution_order
                 AND te.status = 'executed'
                WHERE tps.as_of_date = :d
                ORDER BY tps.execution_order IS NULL, tps.execution_order, tps.ticker
            """),
            conn,
            params={"d": snapshot_date},
        )

        row = conn.execute(
            text("""
                SELECT *
                FROM trade_plan_summary
                WHERE as_of_date = :d
                LIMIT 1
            """),
            {"d": snapshot_date},
        ).mappings().first()

    return trade_df, (None if row is None else dict(row)), snapshot_date


# --------------------------------------------------
# PERFORMANCE
# --------------------------------------------------

def load_performance(as_of_date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    portfolio_type,
                    portfolio_value,
                    invested_value,
                    cash_value,
                    position_count,
                    priced_positions,
                    missing_price_count,
                    realized_profit_total,
                    taxable_profit_total,
                    tax_paid_total,
                    daily_return,
                    cumulative_return,
                    drawdown
                FROM performance_snapshots
                WHERE as_of_date = :d
                ORDER BY portfolio_type
            """),
            conn,
            params={"d": as_of_date},
        )
    return df


# --------------------------------------------------
# CHECKS
# --------------------------------------------------

def evaluate_snapshot_checks(snapshot_presence: dict[str, int]) -> tuple[str, list[tuple[str, str, str]]]:
    overall = OK
    lines: list[tuple[str, str, str]] = []

    required = [
        "factor_metrics",
        "factor_scores",
        "portfolio_shadow",
    ]
    optional = [
        "rebalance",
        "decision_log",
        "trade_plan_summary",
        "trade_plan",
        "performance",
    ]

    for key in required:
        count = snapshot_presence.get(key, 0)
        status = OK if count > 0 else ERROR
        overall = merge_status(overall, status)
    
        label = "portfolio_tradable_shadow" if key == "portfolio_shadow" else key
    
        lines.append((status, label, f"rows={count}"))
    
    for key in optional:
        count = snapshot_presence.get(key, 0)
        status = OK if count > 0 else WARN
        overall = merge_status(overall, status)
    
        label = "portfolio_tradable_shadow" if key == "portfolio_shadow" else key
    
        lines.append((status, label, f"rows={count}"))

    return overall, lines


def evaluate_cash_checks(cash_status: dict[str, Any]) -> tuple[str, list[tuple[str, str, str]]]:
    overall = OK
    lines: list[tuple[str, str, str]] = []

    portfolio_cash = cash_status["portfolio_cash"]
    ledger_cash = cash_status["ledger_cash"]

    if portfolio_cash is None:
        status = ERROR
        overall = merge_status(overall, status)
        lines.append((status, "portfolio_cash", "kein Eintrag vorhanden"))
    else:
        lines.append((OK, "portfolio_cash", f"cash={fmt_money(portfolio_cash)}"))

    if ledger_cash is None:
        status = WARN
        overall = merge_status(overall, status)
        lines.append((status, "cash_ledger", "noch keine Ledger-Buchungen"))
    else:
        lines.append((OK, "cash_ledger", f"cash={fmt_money(ledger_cash)}"))

    if portfolio_cash is not None and ledger_cash is not None:
        diff = float(portfolio_cash) - float(ledger_cash)
        status = OK if abs(diff) < 1e-6 else ERROR
        overall = merge_status(overall, status)
        lines.append((status, "cash_consistency", f"Differenz={fmt_money(diff)}"))

    return overall, lines


def evaluate_performance_checks(perf_df: pd.DataFrame) -> tuple[str, list[tuple[str, str, str]]]:
    overall = OK
    lines: list[tuple[str, str, str]] = []

    if perf_df.empty:
        status = WARN
        overall = merge_status(overall, status)
        lines.append((status, "performance", "keine Performance-Snapshots"))
        return overall, lines

    types = set(perf_df["portfolio_type"].astype(str).tolist())
    if {"shadow", "real"}.issubset(types):
        status = OK
        detail = "tradable shadow + real vorhanden"
    else:
        status = WARN
        detail = f"vorhanden={', '.join(sorted(types))}"
    overall = merge_status(overall, status)
    lines.append((status, "portfolio_types", detail))

    missing_prices = int(pd.to_numeric(perf_df["missing_price_count"], errors="coerce").fillna(0).sum())
    status = OK if missing_prices == 0 else WARN
    overall = merge_status(overall, status)
    lines.append((status, "missing_prices", f"sum={missing_prices}"))

    non_positive = int((pd.to_numeric(perf_df["portfolio_value"], errors="coerce").fillna(0) <= 0).sum())
    status = OK if non_positive == 0 else ERROR
    overall = merge_status(overall, status)
    lines.append((status, "portfolio_values", f"non_positive={non_positive}"))

    return overall, lines


def evaluate_live_checks(real_df: pd.DataFrame, shadow_df: pd.DataFrame, exec_status: dict[str, Any], perf_df: pd.DataFrame) -> tuple[str, list[tuple[str, str, str]]]:
    overall = OK
    lines: list[tuple[str, str, str]] = []

    lines.append((OK if len(real_df) > 0 else WARN, "real_positions", f"count={len(real_df)}"))
    lines.append((OK if len(shadow_df) > 0 else WARN, "tradable_shadow_positions", f"count={len(shadow_df)}"))
    lines.append((OK, "executions_upto_day", f"count={exec_status['executed']}"))

    latest_execution = exec_status.get("latest_execution")
    if latest_execution is None:
        status = WARN
        detail = "keine Execution vorhanden"
    else:
        status = OK
        detail = f"{latest_execution['ticker']} {latest_execution['execution_type']} @ {latest_execution['executed_at']}"
    overall = merge_status(overall, status)
    lines.append((status, "latest_execution", detail))

    perf_status, perf_lines = evaluate_performance_checks(perf_df)
    overall = merge_status(overall, perf_status)
    for item in perf_lines:
        lines.append(item)

    return overall, lines


# --------------------------------------------------
# OUTPUT
# --------------------------------------------------

def print_settings() -> None:
    settings = load_settings()
    print_section("AKTIVE SETTINGS")
    print(f"Strategie-Version        : {settings.strategy_version}")
    print(f"Faktor-Gewichte          : Value={settings.value_weight:.2f} | Quality={settings.quality_weight:.2f} | Momentum={settings.momentum_weight:.2f}")
    print(f"Momentum-Untergewichte   : Return={settings.momentum_return_weight:.2f} | RelStrength={settings.momentum_rel_strength_weight:.2f}")
    print(f"Universum-Filter         : Preis > {settings.min_price:.2f} | Market Cap > {settings.min_market_cap}")
    print(f"Trend / Momentum         : SMA={settings.sma_days} | Lookback={settings.return_lookback_days}")
    print(f"Ranks                    : BUY <= {settings.buy_rank_threshold} | SELL > {settings.sell_rank_threshold}")
    print(f"Portfolio                : Größe={settings.portfolio_size} | max/Sektor={settings.max_sector_positions}")
    print(f"Turnover                 : MinHold={settings.min_holding_months} Monate | max Trades/Monat={settings.max_trades_per_month}")
    print(f"Funding-Sells            : max {settings.max_funding_sell_pct:.0%} je bestehender Position")
    print(f"Steuer                   : tax_rate={settings.tax_rate:.5f}")
    print(f"Fundamentals Daily       : Limit={settings.daily_fundamental_limit} | Refresh={settings.fundamental_refresh_hours}h")


def print_overview(
    as_of_date,
    model_df: pd.DataFrame,
    real_df: pd.DataFrame,
    shadow_df: pd.DataFrame,
    shadow_snapshot_date,
    rebalance_snapshot_date,
    trade_plan_snapshot_date,
    performance_date,
) -> None:
    print_section("ÜBERSICHT")
    print(f"Stichtag                 : {as_of_date}")
    print(f"Performance-Tag          : {performance_date if performance_date is not None else '-'}")
    print(f"Tradable-Shadow-Snapshot : {shadow_snapshot_date if shadow_snapshot_date is not None else '-'}")
    print(f"Rebalance-Snapshot       : {rebalance_snapshot_date if rebalance_snapshot_date is not None else '-'}")
    print(f"Trade-Plan-Snapshot      : {trade_plan_snapshot_date if trade_plan_snapshot_date is not None else '-'}")
    print(f"Model Positionen         : {len(model_df)}")
    print(f"Tradable Shadow Pos.     : {len(shadow_df)}")
    print(f"Offene Real-Positionen   : {len(real_df)}")

    # Transparenz für die neue Auffüll-Logik:
    # Wenn das reale Portfolio kleiner als die Zielgröße ist, wird das effektive
    # Positionswechsel-Limit erhöht, damit fehlende Positionen aufgebaut werden
    # können. Sobald die Zielgröße erreicht ist, gilt wieder max_trades_per_month.
    settings = load_settings()
    missing_positions = max(0, int(settings.portfolio_size) - len(real_df))
    effective_limit = max(int(settings.max_trades_per_month), missing_positions)
    print(f"Fehlende Real-Positionen : {missing_positions}")
    print(f"Effektives Trade-Limit   : {effective_limit} (max({settings.max_trades_per_month}, {missing_positions}))")

def print_health_dashboard(check_groups: list[tuple[str, str, list[tuple[str, str, str]]]]) -> None:
    print_section("SYSTEM HEALTH")
    print(f"Gesamtstatus             : {get_overall_status(check_groups)}")

    print("\nGruppen:")
    for group_name, group_status, _ in check_groups:
        print_status_line(group_name, group_status, "")

    print("\nChecks:")
    for group_name, _, lines in check_groups:
        print(f"\n{group_name}")
        for line_status, label, detail in lines:
            print_status_line(label, line_status, detail)


def print_table_counts(counts: dict[str, int]) -> None:
    print_section("TABELLEN")
    for key, value in counts.items():
        print(f"{key:<24} {value:>10}")


def print_snapshot_status(as_of_date, snapshot_presence: dict[str, int]) -> None:
    print_section(f"SNAPSHOTS BIS {as_of_date}")
    for key, value in snapshot_presence.items():
        status = "OK" if value > 0 else "FEHLT"
        print(f"{status:<6} {key:<22} {value:>6}")


# --------------------------------------------------
# NICHT AUFGENOMMENE KANDIDATEN
# --------------------------------------------------

def explain_not_selected_reason(reason: Any) -> str:
    mapping = {
        "portfolio_full": "Portfolio voll",
        "sector_limit_reached": "Sektorlimit",
        "rank_above_buy_threshold": "Rank zu schwach",
        "trend_negative": "Trend negativ",
        "missing_price": "Preis fehlt",
        "price_below_min": "Preis zu niedrig",
        "missing_market_cap": "Market Cap fehlt",
        "market_cap_too_small": "Market Cap zu klein",
        "missing_ebit": "EBIT fehlt",
        "invalid_ebit": "EBIT ungültig",
        "missing_equity": "Equity fehlt",
        "invalid_equity": "Equity ungültig",
        "missing_200dma": "200DMA fehlt",
        "missing_12m_return": "12M Return fehlt",
        "missing_6m_return": "6M Return fehlt",
        "not_selected_unknown": "Nicht aufgenommen",
    }
    if reason is None or pd.isna(reason):
        return "-"
    return mapping.get(str(reason), str(reason))


def derive_candidate_reasons(scored_df: pd.DataFrame, selected_tickers: set[str], settings) -> pd.DataFrame:
    if scored_df.empty:
        return scored_df

    df = scored_df.copy()
    df["final_rank"] = pd.to_numeric(df["final_rank"], errors="coerce")
    df["buy_eligible"] = pd.to_numeric(df["buy_eligible"], errors="coerce").fillna(0).astype(int)
    df["trend_positive"] = pd.to_numeric(df["trend_positive"], errors="coerce").fillna(0).astype(int)
    df = df.sort_values(["final_rank", "ticker"], na_position="last").copy()

    selected_count = 0
    sector_counts: dict[str, int] = {}
    reasons: dict[str, str] = {}

    for _, row in df.iterrows():
        ticker = str(row["ticker"])
        sector = str(row.get("sector") or "")
        is_selected = ticker in selected_tickers

        if is_selected:
            selected_count += 1
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            continue

        if int(row.get("buy_eligible") or 0) == 1:
            if sector_counts.get(sector, 0) >= int(settings.max_sector_positions):
                reasons[ticker] = "sector_limit_reached"
            elif selected_count >= int(settings.portfolio_size):
                reasons[ticker] = "portfolio_full"
            else:
                reasons[ticker] = "not_selected_unknown"
            continue

        if int(row.get("trend_positive") or 0) == 0:
            reasons[ticker] = "trend_negative"
        else:
            reasons[ticker] = "rank_above_buy_threshold"

    df["not_selected_reason"] = df["ticker"].astype(str).map(reasons)
    return df


def load_not_selected_candidates(as_of_date, shadow_snapshot_date=None, limit: int = 10) -> pd.DataFrame:
    settings = load_settings()

    if shadow_snapshot_date is None:
        shadow_snapshot_date = resolve_shadow_snapshot_date(as_of_date)

    with engine.connect() as conn:
        selected = pd.read_sql(
            text("""
                SELECT ticker
                FROM portfolio_snapshots
                WHERE as_of_date = :d
                  AND snapshot_type = 'shadow'
            """),
            conn,
            params={"d": shadow_snapshot_date},
        ) if shadow_snapshot_date is not None else pd.DataFrame(columns=["ticker"])

        scored = pd.read_sql(
            text("""
                SELECT
                    fs.ticker,
                    fs.sector,
                    fs.final_rank,
                    fs.final_score,
                    fs.trend_positive,
                    fs.buy_eligible,
                    fm.current_price,
                    fm.sma_200,
                    fm.is_valid,
                    fm.exclusion_reason
                FROM factor_scores fs
                LEFT JOIN factor_metrics fm
                  ON fm.as_of_date = fs.as_of_date
                 AND fm.ticker = fs.ticker
                WHERE fs.as_of_date = :d
                ORDER BY fs.final_rank ASC, fs.ticker ASC
            """),
            conn,
            params={"d": as_of_date},
        )

        invalid = pd.read_sql(
            text("""
                SELECT
                    fm.ticker,
                    fm.sector,
                    NULL AS final_rank,
                    NULL AS final_score,
                    fm.trend_positive,
                    0 AS buy_eligible,
                    fm.current_price,
                    fm.sma_200,
                    fm.is_valid,
                    fm.exclusion_reason
                FROM factor_metrics fm
                LEFT JOIN factor_scores fs
                  ON fs.as_of_date = fm.as_of_date
                 AND fs.ticker = fm.ticker
                WHERE fm.as_of_date = :d
                  AND fm.is_valid = 0
                  AND fs.ticker IS NULL
                ORDER BY fm.ticker ASC
                LIMIT 20
            """),
            conn,
            params={"d": as_of_date},
        )

    selected_tickers = set(selected["ticker"].astype(str).tolist()) if not selected.empty else set()

    scored = scored[~scored["ticker"].astype(str).isin(selected_tickers)].copy()
    scored = derive_candidate_reasons(scored, selected_tickers, settings)
    # Sector aus scored übernehmen
    scored["sector"] = scored["ticker"].map(scored.set_index("ticker")["sector"])
    
    # Optional auch für invalid Kandidaten:
    if not invalid.empty:
        invalid["sector"] = invalid["ticker"].map(scored.set_index("ticker")["sector"])

    if not invalid.empty:
        invalid["not_selected_reason"] = invalid["exclusion_reason"]

    #result = pd.concat([scored, invalid], ignore_index=True) if not invalid.empty else scored
    if not invalid.empty:
        invalid = invalid.loc[:, invalid.notna().any()]
        result = pd.concat([scored, invalid], ignore_index=True)
    else:
        result = scored

    if result.empty:
        return result

    result["reason_text"] = result["not_selected_reason"].apply(explain_not_selected_reason)
    result["final_rank_sort"] = pd.to_numeric(result["final_rank"], errors="coerce").fillna(999999)
    result = result.sort_values(["final_rank_sort", "ticker"]).head(limit).copy()
    result = result.drop(columns=["final_rank_sort"], errors="ignore")
    return result


def print_not_selected_candidates(df: pd.DataFrame, as_of_date, shadow_snapshot_date) -> None:
    title = f"TOP BUY CANDIDATES NOT SELECTED BIS {as_of_date}"
    if shadow_snapshot_date is not None:
        title += f" (TRADABLE SHADOW SNAPSHOT {shadow_snapshot_date})"
    print_section(title)

    if df is None or df.empty:
        print("Keine nicht aufgenommenen Kandidaten gefunden.")
        return

    print("Top-Kandidaten außerhalb des Tradable Shadow Portfolios.")

    display = df.copy()
    cols = [
        "ticker",
        "sector",
        "final_rank",
        "final_score",
        "trend_positive",
        "buy_eligible",
        "current_price",
        "sma_200",
        "reason_text",
    ]
    for col in cols:
        if col not in display.columns:
            display[col] = None
    display = display[cols].copy()

    for col in ["final_score", "current_price", "sma_200"]:
        display[col] = pd.to_numeric(display[col], errors="coerce").map(
            lambda x: "-" if pd.isna(x) else f"{float(x):.2f}".replace(".", ",")
        )

    display["final_rank"] = pd.to_numeric(display["final_rank"], errors="coerce").map(
        lambda x: "-" if pd.isna(x) else str(int(x))
    )
    display["trend_positive"] = pd.to_numeric(display["trend_positive"], errors="coerce").fillna(0).astype(int)
    display["buy_eligible"] = pd.to_numeric(display["buy_eligible"], errors="coerce").fillna(0).astype(int)

    display = display.rename(columns={
        "ticker": "Ticker",
        "sector": "Sektor",
        "final_rank": "Rank",
        "reason_text": "Grund",
    })

    compact_cols = ["Ticker", "Sektor", "Rank", "Grund"]
    for col in compact_cols:
        if col not in display.columns:
            display[col] = "-"

    print(display[compact_cols].to_string(index=False))

def print_cash_status(cash_status: dict[str, Any]) -> None:
    print_section("CASH-STATUS")
    print(f"portfolio_cash           : {fmt_money(cash_status['portfolio_cash'])}")
    print(f"portfolio_cash updated   : {value_or_dash(cash_status['portfolio_cash_updated_at'])}")
    print(f"cash_ledger              : {fmt_money(cash_status['ledger_cash'])}")
    print(f"ledger booked_at         : {value_or_dash(cash_status['ledger_cash_booked_at'])}")

    p = cash_status["portfolio_cash"]
    l = cash_status["ledger_cash"]
    if p is not None and l is not None:
        diff = float(p) - float(l)
        print(f"Differenz                : {fmt_money(diff)}")
        print(f"Konsistenz               : {'OK' if abs(diff) < 1e-6 else 'WARNUNG'}")


def print_cash_movements(df: pd.DataFrame, as_of_date) -> None:
    print_section(f"CASH-BEWEGUNGEN ZUM SNAPSHOT {as_of_date}")

    if df is None or df.empty:
        print("Keine Einzahlungen, Auszahlungen oder Cash-Korrekturen gefunden.")
        return

    deposits = float(df.loc[df["entry_type"] == "deposit", "amount"].sum())
    withdrawals = float(df.loc[df["entry_type"] == "withdrawal", "amount"].sum())
    corrections = float(df.loc[df["entry_type"] == "correction", "amount"].sum())
    net = deposits + withdrawals + corrections

    print(f"Einzahlungen             : {fmt_money(deposits)}")
    print(f"Auszahlungen             : {fmt_money(withdrawals)}")
    print(f"Korrekturen              : {fmt_money(corrections)}")
    print(f"Netto Cash Movement      : {fmt_money(net)}")

    latest_balance = df.sort_values("booked_at").iloc[-1]["balance_after"]
    print(f"Cash nach letzter Buchung: {fmt_money(latest_balance)}")

    print("\nDetails:")

    display = df.copy()
    display["booked_at"] = display["booked_at"].astype(str)
    display["amount"] = display["amount"].apply(fmt_money)
    display["balance_after"] = display["balance_after"].apply(fmt_money)

    cols = [
        "booked_at",
        "entry_type",
        "amount",
        "balance_after",
        "notes",
    ]
    cols = [c for c in cols if c in display.columns]

    print(display[cols].to_string(index=False))

def print_execution_status(exec_status: dict[str, Any]) -> None:
    print_section("EXECUTION-STATUS BIS STICHTAG")
    print(f"Erfasste Executions      : {exec_status['executed']}")
    latest_execution = exec_status.get("latest_execution")
    if latest_execution is None:
        print("Letzte Execution         : -")
        return

    print(
        "Letzte Execution         : "
        f"{latest_execution['ticker']} {latest_execution['execution_type']} | "
        f"{latest_execution['shares']} @ {fmt_money(latest_execution['price'])} | "
        f"{latest_execution['executed_at']}"
    )
    print(f"Trade-Plan-Stichtag      : {latest_execution['as_of_date']}")
    print(f"Net Amount               : {fmt_money(latest_execution['net_amount'])}")
    print(f"Realized Profit          : {fmt_money(latest_execution.get('realized_profit'))}")
    print(f"Tax Amount               : {fmt_money(latest_execution.get('tax_amount'))}")


def print_tax_summary(tax_status: dict[str, Any]) -> None:
    print_section("TAX SUMMARY BIS STICHTAG")
    print(f"Executions               : {value_or_dash(tax_status.get('executed_count'))}")
    print(f"SELL Trades              : {value_or_dash(tax_status.get('sell_count'))}")
    print(f"Realized Profit Total    : {fmt_money(tax_status.get('realized_profit_total'))}")
    print(f"Taxable Profit Total     : {fmt_money(tax_status.get('taxable_profit_total'))}")
    print(f"Taxes Paid Total         : {fmt_money(tax_status.get('tax_paid_total'))}")
    print(f"Effective Tax Rate       : {fmt_pct(tax_status.get('effective_tax_rate'))}")


def print_performance(perf_df: pd.DataFrame, title: str = "PERFORMANCE") -> None:
    print_section(title)
    print("Hinweis: TRADABLE SHADOW EXECUTED zeigt die finanzierbar simulierte Shadow-Umsetzung, nicht zwingend alle Zielpositionen des Shadow-Snapshots.")
    if perf_df.empty:
        print("Keine Performance-Snapshots vorhanden.")
        return

    for _, row in perf_df.iterrows():
        portfolio_label = str(row["portfolio_type"]).upper()
        if str(row["portfolio_type"]).lower() == "shadow":
            portfolio_label = "TRADABLE SHADOW EXECUTED"
        
        print(f"{portfolio_label}")
        print(f"  Portfolio Value        : {fmt_money(row['portfolio_value'])}")
        print(f"  Invested               : {fmt_money(row['invested_value'])}")
        print(f"  Cash                   : {fmt_money(row['cash_value'])}")
        print(f"  Position Count         : {value_or_dash(row['position_count'])}")
        print(f"  Priced Positions       : {value_or_dash(row['priced_positions'])}")
        print(f"  Missing Prices         : {value_or_dash(row['missing_price_count'])}")
        if str(row['portfolio_type']).lower() == "shadow":
            effective_shadow_tax_rate = None
            taxable_profit_total = row.get('taxable_profit_total')
            tax_paid_total = row.get('tax_paid_total')
            if taxable_profit_total is not None and not pd.isna(taxable_profit_total) and float(taxable_profit_total) > 0:
                effective_shadow_tax_rate = float(tax_paid_total) / float(taxable_profit_total)
            print(f"  Tradable Shadow Realized Profit : {fmt_money(row.get('realized_profit_total'))}")
            print(f"  Tradable Shadow Taxable Profit  : {fmt_money(row.get('taxable_profit_total'))}")
            print(f"  Tradable Shadow Taxes Paid      : {fmt_money(row.get('tax_paid_total'))}")
            print(f"  Tradable Shadow Tax Rate        : {fmt_pct(effective_shadow_tax_rate)}")
        print(f"  Daily Return           : {fmt_pct(row['daily_return'])}")
        print(f"  Cumulative Return      : {fmt_pct(row['cumulative_return'])}")
        print(f"  Drawdown               : {fmt_pct(row['drawdown'])}")
        print()


def print_real_positions(real_df: pd.DataFrame, as_of_date) -> None:
    print_section(f"REALE POSITIONEN BIS {as_of_date}")
    print(f"Anzahl offene Positionen : {len(real_df)}")
    if real_df.empty:
        return
    print(real_df.to_string(index=False))

def print_model(model_df: pd.DataFrame, model_snapshot_date) -> None:
    title = "MODEL PORTFOLIO"
    if model_snapshot_date is not None:
        title += f" (SNAPSHOT {model_snapshot_date})"

    print_section(title)
    print(f"Anzahl Model-Positionen  : {len(model_df)}")

    if model_df.empty:
        return

    display = model_df.copy()
    display["target_weight"] = display["target_weight"].apply(lambda x: fmt_pct(x))

    print(display.to_string(index=False))

def print_shadow(shadow_df: pd.DataFrame, shadow_snapshot_date) -> None:
    title = "TRADABLE SHADOW PORTFOLIO"
    if shadow_snapshot_date is not None:
        title += f" (SNAPSHOT {shadow_snapshot_date})"
    print_section(title)
    print(f"Anzahl Tradable-Shadow-Positionen : {len(shadow_df)}")
    if shadow_df.empty:
        return
    display = shadow_df.copy()
    display["target_weight"] = display["target_weight"].apply(lambda x: fmt_pct(x))
    print(display.to_string(index=False))


def print_model_signals_vs_tradable_shadow(
    model_df: pd.DataFrame,
    shadow_df: pd.DataFrame,
    as_of_date,
) -> None:
    print_section("MODEL SIGNALS VS TRADABLE SHADOW")

    if model_df.empty or shadow_df.empty:
        print("Keine vollständigen Model-/Tradable-Shadow-Daten vorhanden.")
        return

    model_tickers = set(model_df["ticker"].astype(str).tolist())
    shadow_tickers = set(shadow_df["ticker"].astype(str).tolist())

    buy_signals = sorted(model_tickers - shadow_tickers)
    sell_signals = sorted(shadow_tickers - model_tickers)

    if not buy_signals and not sell_signals:
        print("Keine Abweichungen: Model und Tradable Shadow sind identisch.")
        return

    if sell_signals:
        print("\nSELL SIGNALS / NOCH BLOCKIERT")
        display = shadow_df[shadow_df["ticker"].astype(str).isin(sell_signals)].copy()

        if "holding_start_date" in display.columns:
            display["holding_days"] = (
                pd.to_datetime(as_of_date) - pd.to_datetime(display["holding_start_date"])
            ).dt.days

        display["blocked_reason"] = "Mindesthaltedauer / Turnover"

        cols = ["ticker", "source_rank", "final_score"]
        if "holding_days" in display.columns:
            cols.append("holding_days")
        cols.append("blocked_reason")

        display = display[cols].rename(columns={
            "ticker": "Ticker",
            "source_rank": "Rank",
            "final_score": "Score",
            "holding_days": "Haltedauer",
            "blocked_reason": "Grund",
        })

        display["Rank"] = pd.to_numeric(display["Rank"], errors="coerce").map(
            lambda x: "-" if pd.isna(x) else f"#{int(x)}"
        )
        display["Score"] = pd.to_numeric(display["Score"], errors="coerce").map(
            lambda x: "-" if pd.isna(x) else f"{float(x):.2f}"
        )

        print(display.to_string(index=False))
    else:
        print("\nSELL SIGNALS / NOCH BLOCKIERT")
        print("Keine")

    if buy_signals:
        print("\nBUY SIGNALS / NOCH BLOCKIERT")
        display = model_df[model_df["ticker"].astype(str).isin(buy_signals)].copy()
        display["blocked_reason"] = "Mindesthaltedauer / Turnover"

        cols = ["ticker", "source_rank", "final_score", "blocked_reason"]
        display = display[cols].rename(columns={
            "ticker": "Ticker",
            "source_rank": "Rank",
            "final_score": "Score",
            "blocked_reason": "Grund",
        })

        display["Rank"] = pd.to_numeric(display["Rank"], errors="coerce").map(
            lambda x: "-" if pd.isna(x) else f"#{int(x)}"
        )
        display["Score"] = pd.to_numeric(display["Score"], errors="coerce").map(
            lambda x: "-" if pd.isna(x) else f"{float(x):.2f}"
        )

        print(display.to_string(index=False))
    else:
        print("\nBUY SIGNALS / NOCH BLOCKIERT")
        print("Keine")

    print("\nInterpretation:")
    print("Das reine Model will diese Änderungen.")
    print("Tradable Shadow setzt sie erst um, wenn Halte-/Turnover-Regeln es erlauben.")


def print_model_changes_vs_tradable_shadow(model_df: pd.DataFrame, shadow_df: pd.DataFrame, as_of_date) -> None:
    # Deprecated: combined into print_model_signals_vs_tradable_shadow.
    return

def print_shadow_vs_real(shadow_df: pd.DataFrame, real_df: pd.DataFrame) -> None:
    print_section("TRADABLE SHADOW VS REAL")

    if shadow_df.empty and real_df.empty:
        print("Keine Shadow- oder Real-Daten vorhanden.")
        return

    shadow_tickers = set(shadow_df["ticker"].astype(str).tolist()) if not shadow_df.empty else set()
    real_tickers = set(real_df["ticker"].astype(str).tolist()) if not real_df.empty else set()

    only_shadow = sorted(shadow_tickers - real_tickers)
    only_real = sorted(real_tickers - shadow_tickers)

    if not only_shadow and not only_real:
        print("Tradable Shadow und Real Portfolio sind identisch.")
        return

    if only_shadow:
        print("\nNur im Tradable Shadow:")
        display = shadow_df[shadow_df["ticker"].isin(only_shadow)].copy()
        cols = ["portfolio_rank", "ticker", "sector", "source_rank", "final_score"]
        if "holding_start_date" in display.columns:
            cols.append("holding_start_date")
        print(display[cols].to_string(index=False))

    if only_real:
        print("\nNur im Real Portfolio:")
        display = real_df[real_df["ticker"].isin(only_real)].copy()
        cols = ["ticker", "shares", "buy_price", "opened_at"]
        print(display[cols].to_string(index=False))

    print("\nInterpretation:")
    print("Tradable Shadow = regelkonforme Modellumsetzung.")
    print("Real Portfolio = tatsächlich verbuchte Broker-Trades.")



def print_rebalance(rebalance_df: pd.DataFrame, rebalance_snapshot_date) -> None:
    title = "EXECUTABLE REBALANCE"
    if rebalance_snapshot_date is not None:
        title += f" (SNAPSHOT {rebalance_snapshot_date})"
    print_section(title)

    if rebalance_df.empty:
        print("Keine Rebalance-Daten vorhanden.")
        return

    actionable = rebalance_df[
        rebalance_df["action"].astype(str).str.upper().isin(["BUY", "SELL"])
    ].copy()

    sell_count = int((actionable["action"].astype(str).str.upper() == "SELL").sum())
    buy_count = int((actionable["action"].astype(str).str.upper() == "BUY").sum())

    print(f"SELL                     {sell_count}")
    print(f"BUY                      {buy_count}")

    if actionable.empty:
        print("\nKeine regelkonformen Änderungen.")
        return

    print("\nDetails:")
    cols = [
        "ticker",
        "sector",
        "action",
        "reason",
        "source_rank",
        "holding_days",
        "min_hold_ok",
        "current_shares",
    ]
    cols = [c for c in cols if c in actionable.columns]
    display_df = actionable[cols].copy()

    for col in ["source_rank", "holding_days", "min_hold_ok"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: "-" if pd.isna(x) else int(x)
            )

    if "current_shares" in display_df.columns:
        display_df["current_shares"] = display_df["current_shares"].apply(
            lambda x: "-" if pd.isna(x) else float(x)
        )

    print(display_df.to_string(index=False))


def print_trade_plan(trade_df: pd.DataFrame, summary: dict[str, Any] | None, trade_plan_snapshot_date) -> None:
    title = "TRADE PLAN"
    if trade_plan_snapshot_date is not None:
        title += f" (SNAPSHOT {trade_plan_snapshot_date})"
    print_section(title)

    if trade_df.empty:
        if summary is not None:
            print(f"Portfolio vor Trades     : {fmt_money(summary.get('portfolio_value_before'))}")
            print(f"Cash vor/nach Trades     : {fmt_money(summary.get('cash_before'))} -> {fmt_money(summary.get('cash_after'))}")
            print(f"Bucket Size              : {fmt_money(summary.get('bucket_size'))}")
            print(f"Ausführbare Käufe        : 0")
            print(f"Echte Positionsverkäufe  : 0")
            print(f"Funding-Teilverkäufe     : 0")
            print(f"Total Fees               : {fmt_money(summary.get('total_fees'))}")
        print("\nKeine Trade-Plan-Daten vorhanden.")
        return

    executable = trade_df[
        pd.to_numeric(trade_df["is_executable"], errors="coerce").fillna(0).astype(int) == 1
    ].copy()

    if executable.empty:
        if summary is not None:
            print(f"Portfolio vor Trades     : {fmt_money(summary.get('portfolio_value_before'))}")
            print(f"Cash vor/nach Trades     : {fmt_money(summary.get('cash_before'))} -> {fmt_money(summary.get('cash_after'))}")
            print(f"Bucket Size              : {fmt_money(summary.get('bucket_size'))}")
            print(f"Ausführbare Käufe        : 0")
            print(f"Echte Positionsverkäufe  : 0")
            print(f"Funding-Teilverkäufe     : 0")
            print(f"Total Fees               : {fmt_money(summary.get('total_fees'))}")
        print("\nKeine ausführbaren Trades.")
        return

    if "trade_execution_id" in executable.columns:
        executable["is_executed"] = executable["trade_execution_id"].notna()
    else:
        executable["is_executed"] = False

    open_executable = executable[
        executable["is_executed"] == False
    ].copy()

    executed = executable[
        executable["is_executed"] == True
    ].copy()

    buy_count = int((open_executable["action"] == "BUY").sum()) if not open_executable.empty else 0
    adjust_buy_count = int((open_executable["action"] == "ADJUST_BUY").sum()) if not open_executable.empty else 0
    sell_count = int((open_executable["action"] == "SELL").sum()) if not open_executable.empty else 0
    adjust_sell_count = int((open_executable["action"] == "ADJUST_SELL").sum()) if not open_executable.empty else 0

    executed_count = len(executed)

    if summary is not None:
        print(f"Portfolio vor Trades     : {fmt_money(summary.get('portfolio_value_before'))}")
        print(f"Cash vor/nach Trades     : {fmt_money(summary.get('cash_before'))} -> {fmt_money(summary.get('cash_after'))}")
        print(f"Bucket Size              : {fmt_money(summary.get('bucket_size'))}")
        print(f"Offene ausführbare Käufe : {buy_count + adjust_buy_count}")
        print(f"Offene echte Verkäufe    : {sell_count}")
        print(f"Offene Funding-Verkäufe  : {adjust_sell_count}")
        print(f"Bereits ausgeführt       : {executed_count}")
        print(f"Total Fees geplant       : {fmt_money(summary.get('total_fees'))}")

    if adjust_sell_count > 0:
        print()
        print("Hinweis: ADJUST_SELLs sind Teilverkäufe bestehender Positionen zur Finanzierung neuer BUYs.")
        print("Sie sind keine Sell-Signale und schließen keine Position.")

    action_cols = [
        "execution_order",
        "action",
        "ticker",
        "planned_shares",
        "estimated_price",
        "gross_amount",
        "fee",
        "net_amount",
        "cash_after",
    ]

    money_cols = [
        "estimated_price",
        "gross_amount",
        "fee",
        "net_amount",
        "cash_after",
    ]

    if open_executable.empty:
        print("\nNÄCHSTE AKTIONEN: keine offenen ausführbaren Trades")
    else:
        print("\nNÄCHSTE AKTIONEN:")

        open_cols = [c for c in action_cols if c in open_executable.columns]
        display = open_executable[open_cols].copy()

        for col in money_cols:
            if col in display.columns:
                display[col] = display[col].apply(fmt_money)

        if "planned_shares" in display.columns:
            display["planned_shares"] = display["planned_shares"].apply(
                lambda x: "-" if pd.isna(x) else int(x)
            )

        if "execution_order" in display.columns:
            display["execution_order"] = display["execution_order"].apply(
                lambda x: "-" if pd.isna(x) else int(x)
            )

        print(display.to_string(index=False))

    if not executed.empty:
        print("\nBEREITS AUSGEFÜHRT:")

        executed_cols = [
            "execution_order",
            "action",
            "ticker",
            "planned_shares",
            "estimated_price",
            "gross_amount",
            "fee",
            "net_amount",
            "executed_at",
        ]
        executed_cols = [c for c in executed_cols if c in executed.columns]

        display = executed[executed_cols].copy()

        for col in ["estimated_price", "gross_amount", "fee", "net_amount"]:
            if col in display.columns:
                display[col] = display[col].apply(fmt_money)

        if "planned_shares" in display.columns:
            display["planned_shares"] = display["planned_shares"].apply(
                lambda x: "-" if pd.isna(x) else int(x)
            )

        if "execution_order" in display.columns:
            display["execution_order"] = display["execution_order"].apply(
                lambda x: "-" if pd.isna(x) else int(x)
            )

        print(display.to_string(index=False))


def get_perf_row(perf_df: pd.DataFrame, portfolio_type: str):
    if perf_df is None or perf_df.empty:
        return None
    match = perf_df[perf_df["portfolio_type"].astype(str).str.lower() == portfolio_type.lower()]
    if match.empty:
        return None
    return match.iloc[0]


def fmt_money_eur(value: Any, decimals: int = 0) -> str:
    if value is None or pd.isna(value):
        return "-"
    formatted = f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"


def fmt_signed_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:+.2f}%"


def print_kv(label: str, value: Any) -> None:
    print(f"{label:<24}: {value}")


def get_dashboard_critical(rebalance_df: pd.DataFrame, real_df: pd.DataFrame, as_of_date, limit: int = 6) -> list[str]:
    critical: list[str] = []

    if rebalance_df is not None and not rebalance_df.empty:
        for _, row in rebalance_df.iterrows():
            action = str(row.get("action", "")).upper()
            ticker = str(row.get("ticker", ""))
            reason = str(row.get("reason", ""))
            if action == "SELL":
                if "not_in_shadow" in reason:
                    critical.append(f"{ticker} nicht mehr im Tradable Shadow")
                else:
                    critical.append(f"{ticker} SELL Signal")
            elif action == "HOLD" and reason == "min_hold_not_reached":
                critical.append(f"{ticker} Verkauf blockiert: Mindesthaltedauer")

    if real_df is not None and not real_df.empty:
        tickers = sorted(real_df["ticker"].dropna().astype(str).unique().tolist())
        if tickers:
            placeholders = ", ".join([f":t{i}" for i in range(len(tickers))])
            params = {"d": as_of_date}
            for i, ticker in enumerate(tickers):
                params[f"t{i}"] = ticker
            try:
                with engine.connect() as conn:
                    rows = conn.execute(
                        text(f"""
                            SELECT ticker, final_rank, trend_positive
                            FROM factor_scores
                            WHERE as_of_date = :d
                              AND ticker IN ({placeholders})
                        """),
                        params,
                    ).mappings().fetchall()
                settings = load_settings()
                for row in rows:
                    ticker = row["ticker"]
                    rank = row["final_rank"]
                    trend = int(row["trend_positive"] or 0)
                    if trend == 0:
                        critical.append(f"{ticker} unter 200DMA")
                    elif rank is not None and int(rank) > settings.sell_rank_threshold:
                        critical.append(f"{ticker} Rank > {settings.sell_rank_threshold}")
            except Exception as exc:
                logger.warning("Kritisch-Block konnte nicht vollständig geladen werden: %s", exc)

    deduped = []
    seen = set()
    for item in critical:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped[:limit]


def get_top_candidates_for_dashboard(as_of_date, shadow_snapshot_date, limit: int = 5) -> pd.DataFrame:
    df = load_not_selected_candidates(as_of_date, shadow_snapshot_date, limit=40)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["final_rank_num"] = pd.to_numeric(df["final_rank"], errors="coerce")
    df = df[df["final_rank_num"].notna()].copy()
    if df.empty:
        return df
    df = df.sort_values(["final_rank_num", "ticker"]).head(limit)
    return df


def print_dashboard_actions(trade_df: pd.DataFrame) -> None:
    print("\nREBALANCE VORSCHLÄGE")
    if trade_df is None or trade_df.empty:
        print("Keine Trade-Plan-Daten vorhanden")
        return

    executable = trade_df[
        pd.to_numeric(trade_df["is_executable"], errors="coerce").fillna(0).astype(int) == 1
    ].copy()
    if executable.empty:
        print("Keine Änderungen erforderlich")
        return

    executable = executable.sort_values(["execution_order", "ticker"], na_position="last")
    for _, row in executable.iterrows():
        action = str(row.get("action", "")).upper()
        ticker = str(row.get("ticker", ""))
        shares = row.get("planned_shares")
        prefix = "Funding" if action == "ADJUST_SELL" else ""
        action_label = f"{prefix} {action}".strip()
        if pd.isna(shares):
            print(f"{action_label:<18} {ticker}")
        else:
            print(f"{action_label:<18} {ticker} ({int(float(shares))} Shares)")


def print_dashboard_positions(real_df: pd.DataFrame, shadow_df: pd.DataFrame) -> None:
    print("\nAKTUELLE POSITIONEN")

    real_tickers = []
    shadow_tickers = []

    if real_df is not None and not real_df.empty:
        real_tickers = sorted(real_df["ticker"].dropna().astype(str).unique().tolist())

    if shadow_df is not None and not shadow_df.empty:
        shadow_tickers = sorted(shadow_df["ticker"].dropna().astype(str).unique().tolist())

    print(
        "Real             : "
        + (" | ".join(real_tickers) if real_tickers else "keine offenen Positionen")
    )
    print(
        "Tradable Shadow  : "
        + (" | ".join(shadow_tickers) if shadow_tickers else "keine Positionen")
    )

    real_set = set(real_tickers)
    shadow_set = set(shadow_tickers)

    only_real = sorted(real_set - shadow_set)
    only_shadow = sorted(shadow_set - real_set)
    shared = sorted(real_set & shadow_set)

    print("\nALIGNMENT")
    print("Only Real        : " + (" | ".join(only_real) if only_real else "-") )
    print("Only Shadow      : " + (" | ".join(only_shadow) if only_shadow else "-") )
    print("Shared           : " + (" | ".join(shared) if shared else "-") )


def print_dashboard(
    as_of_date,
    overall_status: str,
    settings,
    cash_status: dict[str, Any],
    cash_movements_df: pd.DataFrame,
    perf_df: pd.DataFrame,
    real_df: pd.DataFrame,
    shadow_df: pd.DataFrame,
    rebalance_df: pd.DataFrame,
    trade_df: pd.DataFrame,
    shadow_snapshot_date,
) -> None:
    print("\n" + "=" * 88)
    print(f"QUANT DASHBOARD | {as_of_date}")
    print("=" * 88)

    real = get_perf_row(perf_df, "real")
    shadow = get_perf_row(perf_df, "shadow")
    benchmark = get_perf_row(perf_df, "benchmark")

    print("\nSYSTEM")
    print_kv("Status", overall_status)
    print_kv("Strategie", settings.strategy_version)
    print_kv("Snapshot", shadow_snapshot_date if shadow_snapshot_date is not None else "-")

    print("\nPORTFOLIO")
    print_kv("Real Value", fmt_money_eur(None if real is None else real.get("portfolio_value")))
    print_kv("Tradable Shadow Executed", fmt_money_eur(None if shadow is None else shadow.get("portfolio_value")))
    print_kv("Benchmark", fmt_money_eur(None if benchmark is None else benchmark.get("portfolio_value")))
    print_kv("Cash", fmt_money_eur(cash_status.get("portfolio_cash")))
    
    cash_movement_net = 0.0
    if cash_movements_df is not None and not cash_movements_df.empty:
        cash_movement_net = float(cash_movements_df["amount"].sum())
    
    print_kv("Cash Movements", fmt_money_eur(cash_movement_net))
    print_kv("Open Positions", len(real_df))

    print("\nPERFORMANCE")
    print_kv("Real Return", fmt_signed_pct(None if real is None else real.get("cumulative_return")))
    print_kv("Shadow Executed Return", fmt_signed_pct(None if shadow is None else shadow.get("cumulative_return")))
    print_kv("Benchmark Return", fmt_signed_pct(None if benchmark is None else benchmark.get("cumulative_return")))

    print("\nEXECUTION GAP")
    real_return = None if real is None else real.get("cumulative_return")
    shadow_return = None if shadow is None else shadow.get("cumulative_return")
    benchmark_return = None if benchmark is None else benchmark.get("cumulative_return")
    print_kv("Real vs Shadow Executed", fmt_signed_pct(None if real_return is None or shadow_return is None else float(real_return) - float(shadow_return)))
    print_kv("Real vs Benchmark", fmt_signed_pct(None if real_return is None or benchmark_return is None else float(real_return) - float(benchmark_return)))

    print_dashboard_actions(trade_df)

    print("\nKRITISCH")
    critical = get_dashboard_critical(rebalance_df, real_df, as_of_date)
    if critical:
        for item in critical:
            print(item)
    else:
        print("Keine kritischen Signale")

    print_dashboard_positions(real_df, shadow_df)

    print("\nTOP KANDIDATEN NICHT IM TRADABLE SHADOW")
    candidates = get_top_candidates_for_dashboard(as_of_date, shadow_snapshot_date, limit=5)
    if candidates.empty:
        print("Keine Kandidaten gefunden")
    else:
        for _, row in candidates.iterrows():
            ticker = str(row.get("ticker"))
            rank = row.get("final_rank")
            reason = row.get("reason_text")
            rank_text = "-" if pd.isna(rank) else f"#{int(float(rank))}"
            if reason is None or pd.isna(reason):
                print(f"{ticker} ({rank_text})")
            else:
                print(f"{ticker} ({rank_text}) - {reason}")

    print("\nTURNOVER")
    executable_position_changes = 0
    if trade_df is not None and not trade_df.empty:
        executable_mask = pd.to_numeric(trade_df["is_executable"], errors="coerce").fillna(0).astype(int) == 1
        action_mask = trade_df["action"].astype(str).str.upper().isin(["BUY", "SELL"])
        executable_position_changes = int((executable_mask & action_mask).sum())

    missing_positions = max(0, int(settings.portfolio_size) - len(real_df))
    effective_limit = max(int(settings.max_trades_per_month), missing_positions)
    remaining = max(effective_limit - executable_position_changes, 0)
    print_kv("Positionswechsel", f"{executable_position_changes} / {effective_limit}")
    print_kv("Verbleibend", remaining)
    print_kv("Hinweis", "ADJUST_SELL/Funding zählt nicht als Positionswechsel")


def print_health_only(
    as_of_date,
    overall_status: str,
    performance_date,
    shadow_snapshot_date,
    rebalance_snapshot_date,
    trade_plan_snapshot_date,
    check_groups,
    counts: dict[str, int],
    snapshot_presence: dict[str, int],
) -> None:
    print("\n" + "=" * 88)
    print(f"QUANT HEALTH CHECK | {as_of_date} | STATUS: {overall_status}")
    print("=" * 88)
    print(f"Performance-Tag          : {performance_date if performance_date is not None else '-'}")
    print(f"Tradable-Shadow-Snapshot : {shadow_snapshot_date if shadow_snapshot_date is not None else '-'}")
    print(f"Rebalance-Snapshot       : {rebalance_snapshot_date if rebalance_snapshot_date is not None else '-'}")
    print(f"Trade-Plan-Snapshot      : {trade_plan_snapshot_date if trade_plan_snapshot_date is not None else '-'}")
    print_health_dashboard(check_groups)
    print_snapshot_status(as_of_date, snapshot_presence)
    print_table_counts(counts)


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def run(as_of_date: str | None = None, details: bool = False, brief: bool = False, health: bool = False) -> None:
    logger.info("=== SHOW STATUS START ===")

    as_of_date = resolve_as_of_date(as_of_date)
    if as_of_date is None:
        raise ValueError("Kein verfügbarer Stichtag gefunden.")

    logger.info("Aktiver Stichtag: %s", as_of_date)

    settings = load_settings()
    performance_date = resolve_performance_date(as_of_date)

    cash_status = load_cash_status(as_of_date)
    cash_movements_df = load_cash_movements(as_of_date)
    real_df = load_real_positions(as_of_date)
    exec_status = load_execution_status(as_of_date)
    tax_status = load_tax_status(as_of_date)
    cash_movements_df = load_cash_movements(as_of_date)
    perf_df = load_performance(performance_date) if performance_date is not None else pd.DataFrame()

    model_df, model_snapshot_date = load_model_portfolio(as_of_date)
    shadow_df, shadow_snapshot_date = load_shadow_portfolio(as_of_date)
    rebalance_df, rebalance_snapshot_date = load_rebalance(as_of_date)
    trade_df, summary, trade_plan_snapshot_date = load_trade_plan(as_of_date)
    snapshot_presence = load_snapshot_presence(as_of_date)

    check_groups = [
        ("Snapshots", *evaluate_snapshot_checks(snapshot_presence)),
        ("Cash", *evaluate_cash_checks(cash_status)),
        ("Live Compare", *evaluate_live_checks(real_df, shadow_df, exec_status, perf_df)),
    ]
    overall_status = get_overall_status(check_groups)

    if health:
        counts = load_counts()
        print_health_only(
            as_of_date=as_of_date,
            overall_status=overall_status,
            performance_date=performance_date,
            shadow_snapshot_date=shadow_snapshot_date,
            rebalance_snapshot_date=rebalance_snapshot_date,
            trade_plan_snapshot_date=trade_plan_snapshot_date,
            check_groups=check_groups,
            counts=counts,
            snapshot_presence=snapshot_presence,
        )
    elif details:
        print_header(
            as_of_date,
            overall_status,
            performance_date,
            shadow_snapshot_date,
            rebalance_snapshot_date,
            trade_plan_snapshot_date,
        )
        print_settings()
        print_overview(
            as_of_date,
            model_df,
            real_df,
            shadow_df,
            shadow_snapshot_date,
            rebalance_snapshot_date,
            trade_plan_snapshot_date,
            performance_date,
        )
        print_health_dashboard(check_groups)
        not_selected_df = load_not_selected_candidates(as_of_date, shadow_snapshot_date)
        print_not_selected_candidates(not_selected_df, as_of_date, shadow_snapshot_date)
        print_cash_status(cash_status)
        print_cash_movements(cash_movements_df, as_of_date)
        print_execution_status(exec_status)
        print_tax_summary(tax_status)
        print_performance(perf_df, title=f"PERFORMANCE FÜR {as_of_date}")
        #print_tracking_summary(perf_df)
        print_model(model_df, model_snapshot_date)
        print_shadow(shadow_df, shadow_snapshot_date)
        print_real_positions(real_df, as_of_date)
        print_model_signals_vs_tradable_shadow(model_df, shadow_df, as_of_date)
        print_shadow_vs_real(shadow_df, real_df)
        print_rebalance(rebalance_df, rebalance_snapshot_date)
        print_trade_plan(trade_df, summary, trade_plan_snapshot_date)
    else:
        # Default und alter --brief-Modus: operatives Dashboard.
        print_dashboard(
            as_of_date=as_of_date,
            overall_status=overall_status,
            settings=settings,
            cash_status=cash_status,
            cash_movements_df=cash_movements_df,
            perf_df=perf_df,
            real_df=real_df,
            shadow_df=shadow_df,
            rebalance_df=rebalance_df,
            trade_df=trade_df,
            shadow_snapshot_date=shadow_snapshot_date,
        )

    logger.info("\n=== SHOW STATUS DONE ===")


if __name__ == "__main__":
    args = parse_args()
    run(as_of_date=args.as_of_date, details=args.details, brief=args.brief, health=args.health)




