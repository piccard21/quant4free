import argparse
import logging
from datetime import date, datetime

import pandas as pd
from sqlalchemy import text

from shared.settings import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SHADOW_START_CAPITAL = 10000.0
TRADE_FEE = 1.0


# --------------------------------------------------
# ARGUMENTE
# --------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--as-of-date",
        dest="as_of_date",
        help="Optionales Enddatum im Format YYYY-MM-DD",
    )
    parser.add_argument(
        "--mode",
        choices=["single", "backfill"],
        default="single",
        help="single = nur Enddatum berechnen, backfill = alle fehlenden Handelstage berechnen",
    )
    return parser.parse_args()


# --------------------------------------------------
# LOAD
# --------------------------------------------------

def load_existing_performance_pairs() -> set[tuple[date, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT as_of_date, portfolio_type
                FROM performance_snapshots
            """)
        ).fetchall()

    return {(row[0], str(row[1])) for row in rows}


def get_latest_market_date() -> date | None:
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT MAX(date)
                FROM daily_candles
            """)
        ).scalar()

    return result


def get_first_shadow_date() -> date | None:
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT MIN(as_of_date)
                FROM portfolio_snapshots
                WHERE snapshot_type = 'shadow'
            """)
        ).scalar()

    return result


def load_active_tax_rate() -> float:
    with engine.connect() as conn:
        value = conn.execute(
            text("""
                SELECT tax_rate
                FROM strategy_settings
                WHERE is_active = 1
                ORDER BY id DESC
                LIMIT 1
            """)
        ).scalar()

    return float(value) if value is not None else 0.26375


def load_shadow_tax_rates_upto(max_date: date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    as_of_date,
                    tax_rate
                FROM strategy_settings_snapshots
                WHERE as_of_date <= :max_date
                ORDER BY as_of_date
            """),
            conn,
            params={"max_date": max_date},
        )

    if not df.empty:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.date
        df["tax_rate"] = pd.to_numeric(df["tax_rate"], errors="coerce").fillna(load_active_tax_rate())

    return df


def load_trading_dates(start_date: date, end_date: date) -> list[date]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT date
                FROM daily_candles
                WHERE date BETWEEN :start_date AND :end_date
                ORDER BY date
            """),
            {"start_date": start_date, "end_date": end_date},
        ).fetchall()

    return [row[0] for row in rows]


def load_target_dates(as_of_date: str | None, mode: str) -> list[date]:
    if as_of_date:
        target = pd.to_datetime(as_of_date).date()
        return [target]

    latest_market_date = get_latest_market_date()
    if latest_market_date is None:
        return []

    if mode == "single":
        return [latest_market_date]

    first_shadow_date = get_first_shadow_date()
    if first_shadow_date is None:
        return []

    trading_dates = load_trading_dates(first_shadow_date, latest_market_date)
    existing_pairs = load_existing_performance_pairs()

    return [
        d for d in trading_dates
        if (d, "shadow") not in existing_pairs or (d, "real") not in existing_pairs
    ]


def load_existing_performance_before(min_target_date: date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    as_of_date,
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
                WHERE as_of_date < :min_target_date
                ORDER BY as_of_date, portfolio_type
            """),
            conn,
            params={"min_target_date": min_target_date},
        )

    if not df.empty:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.date

    return df


def load_shadow_snapshots_upto(max_date: date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    as_of_date,
                    ticker,
                    target_weight,
                    portfolio_rank
                FROM portfolio_snapshots
                WHERE snapshot_type = 'shadow'
                  AND as_of_date <= :max_date
                ORDER BY as_of_date, portfolio_rank, ticker
            """),
            conn,
            params={"max_date": max_date},
        )

    if not df.empty:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.date
        df["target_weight"] = pd.to_numeric(df["target_weight"], errors="coerce").fillna(0.0)

    return df


def load_trade_plan_snapshots_upto(max_date: date) -> pd.DataFrame:
    """Lädt eingefrorene Trade-Plan-Zeilen für Shadow-Ausführungen."""
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    as_of_date,
                    ticker,
                    action,
                    planned_shares,
                    estimated_price,
                    fee,
                    is_executable
                FROM trade_plan_snapshots
                WHERE as_of_date <= :max_date
                ORDER BY as_of_date, execution_order IS NULL, execution_order, ticker
            """),
            conn,
            params={"max_date": max_date},
        )

    if not df.empty:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.date
        df["planned_shares"] = pd.to_numeric(df["planned_shares"], errors="coerce")
        df["estimated_price"] = pd.to_numeric(df["estimated_price"], errors="coerce")
        df["fee"] = pd.to_numeric(df["fee"], errors="coerce").fillna(TRADE_FEE)
        df["is_executable"] = pd.to_numeric(df["is_executable"], errors="coerce").fillna(0).astype(int)

    return df


def load_price_history(min_date: date, max_date: date, tickers: list[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["ticker", "date", "close"])

    placeholders = ", ".join([f":t{i}" for i in range(len(tickers))])
    params = {"min_date": min_date, "max_date": max_date}
    for i, ticker in enumerate(sorted(tickers)):
        params[f"t{i}"] = ticker

    sql = text(f"""
        SELECT
            ticker,
            date,
            close
        FROM daily_candles
        WHERE date BETWEEN :min_date AND :max_date
          AND ticker IN ({placeholders})
        ORDER BY date, ticker
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["close"] = pd.to_numeric(df["close"], errors="coerce")

    return df


def load_trade_executions_upto(max_date: date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    as_of_date,
                    ticker,
                    execution_type,
                    executed_at,
                    shares,
                    price,
                    gross_amount,
                    fee,
                    net_amount,
                    status
                FROM trade_executions
                WHERE executed_at <= :target_end
                  AND status = 'executed'
                ORDER BY executed_at, id
            """),
            conn,
            params={"target_end": f"{max_date} 23:59:59"},
        )

    if not df.empty:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.date
        df["executed_at"] = pd.to_datetime(df["executed_at"])
        df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0.0)
        df["net_amount"] = pd.to_numeric(df["net_amount"], errors="coerce").fillna(0.0)

    return df


def load_cash_ledger_upto(max_date: date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    as_of_date,
                    booked_at,
                    ticker,
                    entry_type,
                    amount,
                    balance_after
                FROM cash_ledger
                WHERE booked_at <= :target_end
                ORDER BY booked_at, id
            """),
            conn,
            params={"target_end": f"{max_date} 23:59:59"},
        )

    if not df.empty:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.date
        df["booked_at"] = pd.to_datetime(df["booked_at"])
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        df["balance_after"] = pd.to_numeric(df["balance_after"], errors="coerce").fillna(0.0)

    return df


def load_cash_baseline_for_date(target_date: date) -> float:
    with engine.connect() as conn:
        ledger_balance = conn.execute(
            text("""
                SELECT balance_after
                FROM cash_ledger
                WHERE booked_at <= :target_end
                ORDER BY booked_at DESC, id DESC
                LIMIT 1
            """),
            {"target_end": f"{target_date} 23:59:59"},
        ).scalar()

        if ledger_balance is not None:
            return float(ledger_balance)

        portfolio_cash = conn.execute(
            text("""
                SELECT cash_balance
                FROM portfolio_cash
                WHERE updated_at <= :target_end
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            """),
            {"target_end": f"{target_date} 23:59:59"},
        ).scalar()

        if portfolio_cash is not None:
            return float(portfolio_cash)

        fallback = conn.execute(
            text("""
                SELECT cash_balance
                FROM portfolio_cash
                ORDER BY updated_at ASC, id ASC
                LIMIT 1
            """),
        ).scalar()

    return float(fallback or 0.0)


# --------------------------------------------------
# HELFER
# --------------------------------------------------

def build_price_matrix(price_history: pd.DataFrame) -> pd.DataFrame:
    if price_history.empty:
        return pd.DataFrame()

    matrix = price_history.pivot(index="date", columns="ticker", values="close").sort_index()
    matrix = matrix.ffill()
    return matrix


def build_shadow_rebalance_map(
    shadow_df: pd.DataFrame,
    shadow_tax_rates: pd.DataFrame,
    default_tax_rate: float,
) -> dict[date, dict]:
    rebalance_map: dict[date, dict] = {}

    if shadow_df.empty:
        return rebalance_map

    tax_rate_map: dict[date, float] = {}
    if not shadow_tax_rates.empty:
        tax_rate_map = {
            row["as_of_date"]: float(row["tax_rate"])
            for _, row in shadow_tax_rates.iterrows()
        }

    for as_of_date, group in shadow_df.groupby("as_of_date"):
        holdings = []
        for _, row in group.sort_values(["portfolio_rank", "ticker"]).iterrows():
            holdings.append({
                "ticker": row["ticker"],
                "target_weight": float(row["target_weight"]),
            })

        rebalance_map[as_of_date] = {
            "holdings": holdings,
            "tax_rate": float(tax_rate_map.get(as_of_date, default_tax_rate)),
        }

    return rebalance_map


def add_return_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.sort_values(["portfolio_type", "as_of_date"]).copy()
    df["daily_return"] = df.groupby("portfolio_type")["portfolio_value"].pct_change()

    def cumulative(series: pd.Series) -> pd.Series:
        if series.empty:
            return series
        return (series / series.iloc[0]) - 1

    def compute_drawdown(series: pd.Series) -> pd.Series:
        peak = series.cummax()
        return (series / peak) - 1

    df["cumulative_return"] = df.groupby("portfolio_type")["portfolio_value"].transform(cumulative)
    df["drawdown"] = df.groupby("portfolio_type")["portfolio_value"].transform(compute_drawdown)

    return df


def recompute_history_with_existing(new_df: pd.DataFrame, existing_df: pd.DataFrame) -> pd.DataFrame:
    if new_df.empty:
        return new_df

    if existing_df.empty:
        combined = new_df.copy()
    else:
        combined = pd.concat([existing_df, new_df], ignore_index=True)

    if combined.empty:
        return new_df

    combined = combined.sort_values(["portfolio_type", "as_of_date"]).copy()
    combined = combined.drop_duplicates(subset=["as_of_date", "portfolio_type"], keep="last")
    combined = add_return_columns(combined)

    new_keys = set(zip(new_df["as_of_date"], new_df["portfolio_type"]))
    mask = combined.apply(lambda r: (r["as_of_date"], r["portfolio_type"]) in new_keys, axis=1)
    return combined.loc[mask].copy()


# --------------------------------------------------
# SHADOW
# --------------------------------------------------

def simulate_shadow_performance(
    target_dates: list[date],
    shadow_df: pd.DataFrame,
    shadow_tax_rates: pd.DataFrame,
    default_tax_rate: float,
    trade_plan_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if shadow_df.empty or not target_dates:
        return pd.DataFrame()

    max_target_date = max(target_dates)
    shadow_tickers = sorted(shadow_df["ticker"].dropna().unique().tolist())

    price_history = load_price_history(date(2000, 1, 1), max_target_date, shadow_tickers)
    price_matrix = build_price_matrix(price_history)

    if price_matrix.empty:
        raise ValueError("Keine Preis-Historie für Shadow-Simulation gefunden.")

    rebalance_map = build_shadow_rebalance_map(
        shadow_df=shadow_df,
        shadow_tax_rates=shadow_tax_rates,
        default_tax_rate=default_tax_rate,
    )
    available_dates = list(price_matrix.index)

    def resolve_effective_trading_date(snapshot_date: date) -> date | None:
        eligible = [d for d in available_dates if d <= snapshot_date]
        if not eligible:
            return None
        return eligible[-1]

    effective_rebalance_map: dict[date, dict] = {}

    for snapshot_date, rebalance_payload in rebalance_map.items():
        effective_date = resolve_effective_trading_date(snapshot_date)
        if effective_date is None:
            continue
        effective_rebalance_map[effective_date] = {
            "snapshot_date": snapshot_date,
            "holdings": rebalance_payload["holdings"],
            "tax_rate": float(rebalance_payload["tax_rate"]),
        }

    trading_dates = [d for d in available_dates if d <= max_target_date]

    cash = float(SHADOW_START_CAPITAL)
    current_tax_rate = float(default_tax_rate)
    holdings: dict[str, dict[str, float]] = {}
    cumulative_realized_profit = 0.0
    cumulative_taxable_profit = 0.0
    cumulative_tax_paid = 0.0
    rows = []


    trade_plan_by_date = {}
    
    if trade_plan_df is not None and not trade_plan_df.empty:
        executable_rows = trade_plan_df[
            (trade_plan_df["is_executable"] == 1)
            & (trade_plan_df["planned_shares"].notna())
            & (trade_plan_df["estimated_price"].notna())
            & (trade_plan_df["planned_shares"] > 0)
            & (trade_plan_df["estimated_price"] > 0)
        ].copy()
    
        for snapshot_date, group in executable_rows.groupby("as_of_date"):
            effective_date = resolve_effective_trading_date(snapshot_date)
    
            if effective_date is None:
                logger.warning(
                    "Kein effektiver Handelstag für Trade-Plan-Snapshot %s gefunden. Trades werden übersprungen.",
                    snapshot_date,
                )
                continue
    
            if effective_date not in trade_plan_by_date:
                trade_plan_by_date[effective_date] = []
    
            trade_plan_by_date[effective_date].append(group.copy())
    
        trade_plan_by_date = {
            d: pd.concat(groups, ignore_index=True)
            for d, groups in trade_plan_by_date.items()
        }
    

    for current_date in trading_dates:
        current_prices = price_matrix.loc[current_date]

        if current_date in effective_rebalance_map:
            current_tax_rate = float(
                effective_rebalance_map[current_date].get("tax_rate", default_tax_rate)
            )

        if current_date in trade_plan_by_date:
            trades = trade_plan_by_date[current_date]
        
            for _, trade in trades.iterrows():
                ticker = trade["ticker"]
                action = str(trade["action"]).upper()
                shares = float(trade["planned_shares"])
                price = float(trade["estimated_price"])
                fee = float(trade["fee"] if pd.notna(trade["fee"]) else TRADE_FEE)
        
                if shares <= 0 or price <= 0:
                    continue
        
                if action in {"BUY", "ADJUST_BUY"}:
                    gross = shares * price
                    total_cost = gross + fee
        
                    if total_cost > cash:
                        continue
        
                    old = holdings.get(ticker)
        
                    if old is None:
                        holdings[ticker] = {
                            "shares": shares,
                            "cost_basis": price,
                        }
                    else:
                        old_shares = float(old["shares"])
                        old_cost = float(old["cost_basis"])
                        new_shares = old_shares + shares
                        new_cost = ((old_shares * old_cost) + (shares * price)) / new_shares
        
                        holdings[ticker] = {
                            "shares": new_shares,
                            "cost_basis": new_cost,
                        }
        
                    cash -= total_cost
        
                elif action in {"SELL", "ADJUST_SELL"}:
                    old = holdings.get(ticker)
                    if old is None:
                        continue
        
                    held_shares = float(old["shares"])
                    sell_shares = min(shares, held_shares)
                    cost_basis = float(old["cost_basis"])
        
                    gross = sell_shares * price
                    realized_profit = (price - cost_basis) * sell_shares
                    taxable_profit = max(realized_profit, 0.0)
                    tax_amount = taxable_profit * current_tax_rate
                    net = gross - fee - tax_amount
        
                    cash += net
                    cumulative_realized_profit += realized_profit
                    cumulative_taxable_profit += taxable_profit
                    cumulative_tax_paid += tax_amount
        
                    remaining = held_shares - sell_shares
                    if remaining > 0:
                        holdings[ticker] = {
                            "shares": remaining,
                            "cost_basis": cost_basis,
                        }
                    else:
                        holdings.pop(ticker, None)
    
        invested_value = 0.0
        priced_positions = 0
        missing_price_count = 0

        for ticker, position in holdings.items():
            shares = float(position["shares"])
            price = current_prices.get(ticker)

            if pd.isna(price) or float(price) <= 0:
                missing_price_count += 1
                continue

            invested_value += shares * float(price)
            priced_positions += 1

        portfolio_value = invested_value + cash

        rows.append({
            "as_of_date": current_date,
            "portfolio_type": "shadow",
            "portfolio_value": round(float(portfolio_value), 6),
            "invested_value": round(float(invested_value), 6),
            "cash_value": round(float(cash), 6),
            "position_count": int(len(holdings)),
            "priced_positions": int(priced_positions),
            "missing_price_count": int(missing_price_count),
            "realized_profit_total": round(float(cumulative_realized_profit), 6),
            "taxable_profit_total": round(float(cumulative_taxable_profit), 6),
            "tax_paid_total": round(float(cumulative_tax_paid), 6),
        })

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    final_rows = []
    for target_date in target_dates:
        eligible = result[result["as_of_date"] <= target_date].copy()
        if eligible.empty:
            continue

        latest_row = eligible.sort_values("as_of_date").iloc[-1].to_dict()
        latest_row["as_of_date"] = target_date
        final_rows.append(latest_row)

    return pd.DataFrame(final_rows)


# --------------------------------------------------
# REAL
# --------------------------------------------------

def build_real_performance(
    target_dates: list[date],
    trade_exec: pd.DataFrame,
    cash_ledger: pd.DataFrame,
    price_matrix: pd.DataFrame,
) -> pd.DataFrame:
    if not target_dates:
        return pd.DataFrame()

    rows = []
    available_price_dates = list(price_matrix.index) if not price_matrix.empty else []

    def resolve_effective_price_date(snapshot_date: date) -> date | None:
        if not available_price_dates:
            return None
        eligible = [d for d in available_price_dates if d <= snapshot_date]
        if not eligible:
            return None
        return eligible[-1]

    for target_date in target_dates:
        cash_value = load_cash_baseline_for_date(target_date)

        if not cash_ledger.empty:
            eligible_cash = cash_ledger[
                cash_ledger["booked_at"] <= pd.Timestamp(f"{target_date} 23:59:59")
            ].copy()
            if not eligible_cash.empty:
                cash_value = float(
                    eligible_cash.sort_values(["booked_at", "as_of_date"]).iloc[-1]["balance_after"]
                )

        holdings: dict[str, float] = {}

        if not trade_exec.empty:
            eligible_exec = trade_exec[
                trade_exec["executed_at"] <= pd.Timestamp(f"{target_date} 23:59:59")
            ].copy()
            eligible_exec = eligible_exec.sort_values(["executed_at", "as_of_date"])

            for _, row in eligible_exec.iterrows():
                ticker = row["ticker"]
                shares = float(row["shares"])

                if row["execution_type"] == "BUY":
                    holdings[ticker] = holdings.get(ticker, 0.0) + shares
                elif row["execution_type"] == "SELL":
                    holdings[ticker] = holdings.get(ticker, 0.0) - shares

        holdings = {ticker: shares for ticker, shares in holdings.items() if shares > 0}

        invested_value = 0.0
        priced_positions = 0
        missing_price_count = 0

        effective_price_date = resolve_effective_price_date(target_date)
        current_prices = (
            price_matrix.loc[effective_price_date]
            if effective_price_date is not None
            else pd.Series(dtype=float)
        )

        for ticker, shares in holdings.items():
            price = current_prices.get(ticker)

            if pd.isna(price) or float(price) <= 0:
                missing_price_count += 1
                continue

            invested_value += float(shares) * float(price)
            priced_positions += 1

        portfolio_value = invested_value + cash_value

        rows.append({
            "as_of_date": target_date,
            "portfolio_type": "real",
            "portfolio_value": round(float(portfolio_value), 6),
            "invested_value": round(float(invested_value), 6),
            "cash_value": round(float(cash_value), 6),
            "position_count": int(len(holdings)),
            "priced_positions": int(priced_positions),
            "missing_price_count": int(missing_price_count),
            "realized_profit_total": 0.0,
            "taxable_profit_total": 0.0,
            "tax_paid_total": 0.0,
        })

    return pd.DataFrame(rows)


# --------------------------------------------------
# SAVE
# --------------------------------------------------

def save_performance(rows: list[dict]) -> None:
    if not rows:
        logger.info("Keine Performance-Zeilen zu speichern.")
        return

    df = pd.DataFrame(rows).copy()
    df["created_at"] = datetime.now()

    cols = [
        "as_of_date",
        "portfolio_type",
        "portfolio_value",
        "invested_value",
        "cash_value",
        "position_count",
        "priced_positions",
        "missing_price_count",
        "realized_profit_total",
        "taxable_profit_total",
        "tax_paid_total",
        "daily_return",
        "cumulative_return",
        "drawdown",
        "created_at",
    ]

    for col in cols:
        if col not in df.columns:
            df[col] = None

    df = df[cols]
    df = df.astype(object)
    df = df.where(pd.notnull(df), None)

    target_keys = df[["as_of_date", "portfolio_type"]].drop_duplicates().values.tolist()

    delete_sql = text("""
        DELETE FROM performance_snapshots
        WHERE as_of_date = :as_of_date
          AND portfolio_type = :portfolio_type
    """)

    insert_sql = text("""
        INSERT INTO performance_snapshots (
            as_of_date,
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
            drawdown,
            created_at
        ) VALUES (
            :as_of_date,
            :portfolio_type,
            :portfolio_value,
            :invested_value,
            :cash_value,
            :position_count,
            :priced_positions,
            :missing_price_count,
            :realized_profit_total,
            :taxable_profit_total,
            :tax_paid_total,
            :daily_return,
            :cumulative_return,
            :drawdown,
            :created_at
        )
    """)

    records = df.to_dict(orient="records")

    with engine.begin() as conn:
        for as_of_date, portfolio_type in target_keys:
            conn.execute(
                delete_sql,
                {"as_of_date": as_of_date, "portfolio_type": portfolio_type},
            )
        conn.execute(insert_sql, records)


# --------------------------------------------------
# MARKET
# --------------------------------------------------
def build_benchmark_performance(target_dates: list[date]) -> pd.DataFrame:
    benchmark_ticker = "SPY"

    if not target_dates:
        return pd.DataFrame()

    start_date = get_first_shadow_date()
    if start_date is None:
        start_date = min(target_dates)

    end_date = max(target_dates)

    price_history = load_price_history(
        start_date,
        end_date,
        [benchmark_ticker],
    )

    if price_history.empty:
        return pd.DataFrame()

    price_history = price_history.sort_values("date").copy()
    price_history["close"] = pd.to_numeric(price_history["close"], errors="coerce")
    price_history = price_history.dropna(subset=["close"])

    if price_history.empty:
        return pd.DataFrame()

    start_price = float(price_history["close"].iloc[0])
    start_value = 10000.0

    rows = []

    for target_date in target_dates:
        eligible = price_history[price_history["date"] <= target_date].copy()
        if eligible.empty:
            continue

        price = float(eligible.sort_values("date").iloc[-1]["close"])
        value = start_value * (price / start_price)

        rows.append({
            "as_of_date": target_date,
            "portfolio_type": "benchmark",
            "portfolio_value": round(value, 6),
            "invested_value": round(value, 6),
            "cash_value": 0.0,
            "position_count": 1,
            "priced_positions": 1,
            "missing_price_count": 0,
            "realized_profit_total": 0.0,
            "taxable_profit_total": 0.0,
            "tax_paid_total": 0.0,
        })

    return pd.DataFrame(rows)

# --------------------------------------------------
# MAIN
# --------------------------------------------------

def run(as_of_date: str | None = None, mode: str = "single") -> None:
    logger.info("=== BUILD PERFORMANCE V2.3 START ===")

    target_dates = load_target_dates(as_of_date=as_of_date, mode=mode)

    if not target_dates:
        logger.info("Keine Ziel-Stichtage gefunden.")
        logger.info("=== BUILD PERFORMANCE V2.3 DONE ===")
        return

    logger.info("Ziel-Stichtage: %s", len(target_dates))
    logger.info("Erster Ziel-Stichtag: %s", min(target_dates))
    logger.info("Letzter Ziel-Stichtag: %s", max(target_dates))

    min_target_date = min(target_dates)
    max_target_date = max(target_dates)

    existing_perf = load_existing_performance_before(min_target_date)
    shadow_df = load_shadow_snapshots_upto(max_target_date)
    shadow_tax_rates = load_shadow_tax_rates_upto(max_target_date)
    active_tax_rate = load_active_tax_rate()
    trade_exec = load_trade_executions_upto(max_target_date)
    cash_ledger = load_cash_ledger_upto(max_target_date)
    trade_plan_df = load_trade_plan_snapshots_upto(max_target_date)

    all_tickers = sorted(
        set(shadow_df["ticker"].dropna().tolist()) |
        set(trade_exec["ticker"].dropna().tolist())
    )

    price_history = load_price_history(date(2000, 1, 1), max_target_date, all_tickers)
    price_matrix = build_price_matrix(price_history)

    logger.info("Bestehende Performance-Zeilen vor Zielbereich: %s", len(existing_perf))
    logger.info("Shadow-Historie Zeilen: %s", len(shadow_df))
    logger.info("Shadow-Tax-Snapshots: %s", len(shadow_tax_rates))
    logger.info("Trade-Executions: %s", len(trade_exec))
    logger.info("Cash-Ledger Zeilen: %s", len(cash_ledger))
    logger.info("Trade-Plan Zeilen: %s", len(trade_plan_df))
    logger.info("Preis-Historie Zeilen: %s", len(price_history))

    shadow_perf = simulate_shadow_performance(
        target_dates=target_dates,
        shadow_df=shadow_df,
        shadow_tax_rates=shadow_tax_rates,
        default_tax_rate=active_tax_rate,
        trade_plan_df=trade_plan_df,
    )
    real_perf = build_real_performance(target_dates, trade_exec, cash_ledger, price_matrix)

    benchmark_perf = build_benchmark_performance(target_dates)
    
    combined_new = pd.concat(
        [benchmark_perf, shadow_perf, real_perf],
        ignore_index=True
    )
    combined_new = recompute_history_with_existing(combined_new, existing_perf)

    if combined_new.empty:
        logger.info("Keine neuen Performance-Zeilen erzeugt.")
        logger.info("=== BUILD PERFORMANCE V2.3 DONE ===")
        return

    for portfolio_type in ["benchmark", "shadow", "real"]:
        subset = combined_new[combined_new["portfolio_type"] == portfolio_type].copy()
        if subset.empty:
            continue

        last_row = subset.sort_values("as_of_date").iloc[-1]
        logger.info(
            "%s zuletzt: date=%s | value=%.2f | invested=%.2f | cash=%.2f | daily=%s | cum=%.4f | dd=%.4f",
            portfolio_type.capitalize(),
            last_row["as_of_date"],
            float(last_row["portfolio_value"]),
            float(last_row["invested_value"]),
            float(last_row["cash_value"]),
            None if pd.isna(last_row["daily_return"]) else round(float(last_row["daily_return"]), 6),
            float(last_row["cumulative_return"]) if pd.notna(last_row["cumulative_return"]) else 0.0,
            float(last_row["drawdown"]) if pd.notna(last_row["drawdown"]) else 0.0,
        )

    save_performance(combined_new.to_dict(orient="records"))

    logger.info("Gespeicherte Performance-Zeilen: %s", len(combined_new))
    logger.info("=== BUILD PERFORMANCE V2.3 DONE ===")


if __name__ == "__main__":
    args = parse_args()
    run(as_of_date=args.as_of_date, mode=args.mode)



