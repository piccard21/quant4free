import argparse
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import text

from shared.settings import engine, load_settings


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# KONSTANTEN
# --------------------------------------------------

TRADE_FEE = 1.0
THRESHOLD_PCT = 0.20  # 20% vom Bucket für klassische spätere Bucket-Abweichungen
DEFAULT_MAX_FUNDING_SELL_PCT = 0.20


# --------------------------------------------------
# ARGUMENTE / LOAD
# --------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--as-of-date",
        dest="as_of_date",
        help="Optionaler Stichtag im Format YYYY-MM-DD. Standard: MAX(as_of_date) aus rebalance_suggestions",
    )
    return parser.parse_args()


def get_latest_as_of_date():
    with engine.connect() as conn:
        as_of_date = conn.execute(
            text("SELECT MAX(as_of_date) FROM rebalance_suggestions")
        ).scalar()

    if as_of_date is None:
        raise ValueError("Keine Rebalance-Vorschläge gefunden.")

    return as_of_date


def resolve_as_of_date(cli_value: str | None):
    return cli_value if cli_value else get_latest_as_of_date()


def assert_trade_plan_snapshot_is_new(as_of_date) -> None:
    tables_to_check = [
        "trade_plan_summary",
        "trade_plan_snapshots",
    ]

    existing_tables = []

    with engine.connect() as conn:
        for table_name in tables_to_check:
            exists = conn.execute(
                text(f"SELECT 1 FROM {table_name} WHERE as_of_date = :as_of_date LIMIT 1"),
                {"as_of_date": as_of_date},
            ).scalar()
            if exists is not None:
                existing_tables.append(table_name)

    if existing_tables:
        joined = ", ".join(existing_tables)
        raise ValueError(
            f"Für den Stichtag {as_of_date} existieren bereits eingefrorene Trade-Plan-Snapshots in: {joined}. "
            "Der Lauf wird abgebrochen, damit keine Snapshots überschrieben werden."
        )


def load_rebalance(as_of_date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    as_of_date,
                    ticker,
                    action,
                    reason,
                    source_rank,
                    target_weight,
                    current_shares,
                    holding_days,
                    min_hold_ok
                FROM rebalance_suggestions
                WHERE as_of_date = :as_of_date
                ORDER BY
                    CASE action
                        WHEN 'SELL' THEN 1
                        WHEN 'BUY'  THEN 2
                        ELSE 3
                    END,
                    source_rank,
                    ticker
            """),
            conn,
            params={"as_of_date": as_of_date},
        )
    return df


def load_real_positions() -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    ticker,
                    shares,
                    buy_price,
                    opened_at
                FROM portfolio_positions
                WHERE is_open = 1
                ORDER BY opened_at ASC, ticker ASC
            """),
            conn,
        )

    if not df.empty:
        df["opened_at"] = pd.to_datetime(df["opened_at"])

    return df


def load_prices(as_of_date) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("""
                SELECT
                    ticker,
                    current_price
                FROM factor_metrics
                WHERE as_of_date = :as_of_date
            """),
            conn,
            params={"as_of_date": as_of_date},
        )
    return df


def load_cash_balance() -> float:
    with engine.connect() as conn:
        cash = conn.execute(
            text("SELECT cash_balance FROM portfolio_cash ORDER BY id DESC LIMIT 1")
        ).scalar()

    return float(cash or 0.0)


# --------------------------------------------------
# HELPER
# --------------------------------------------------

def round_money(value: float) -> float:
    return round(float(value), 6)


def get_max_funding_sell_pct(settings) -> float:
    """
    Variante C: begrenztes Funding aus bestehenden Positionen.

    Das Setting max_funding_sell_pct ist bewusst defensiv:
    - 0.20 bedeutet: maximal ca. 20% des aktuellen Positionswerts dürfen
      je Trade-Plan-Lauf zur Finanzierung neuer Positionen verkauft werden.
    - Falls die DB/Migration noch nicht vorhanden ist, fällt der Code auf 20% zurück,
      damit alte Installationen nicht hart brechen.
    """
    value = getattr(settings, "max_funding_sell_pct", DEFAULT_MAX_FUNDING_SELL_PCT)
    value = float(value if value is not None else DEFAULT_MAX_FUNDING_SELL_PCT)
    return max(0.0, min(1.0, value))


def build_maps(real: pd.DataFrame, prices: pd.DataFrame):
    shares_map = {}
    if not real.empty:
        shares_map = real.set_index("ticker")["shares"].astype(float).to_dict()

    price_map = {}
    if not prices.empty:
        price_map = prices.set_index("ticker")["current_price"].astype(float).to_dict()

    return shares_map, price_map


def compute_portfolio_values(real: pd.DataFrame, prices: pd.DataFrame, cash_before: float):
    if real.empty:
        invested_value = 0.0
    else:
        df = real.merge(prices, on="ticker", how="left")
        df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0.0)
        df["current_price"] = pd.to_numeric(df["current_price"], errors="coerce").fillna(0.0)
        df["position_value"] = df["shares"] * df["current_price"]
        invested_value = float(df["position_value"].sum())

    portfolio_value = invested_value + float(cash_before)
    return portfolio_value, invested_value


def make_trade_row(
    as_of_date,
    ticker,
    action,
    reason,
    execution_order,
    source_rank,
    target_weight,
    current_shares,
    planned_shares,
    estimated_price,
    gross_amount,
    fee,
    net_amount,
    bucket_size,
    cash_before,
    cash_after,
    is_executable,
    skip_reason,
):
    return {
        "as_of_date": as_of_date,
        "ticker": ticker,
        "action": action,
        "reason": reason,
        "execution_order": execution_order,
        "source_rank": source_rank,
        "target_weight": target_weight,
        "current_shares": current_shares,
        "planned_shares": planned_shares,
        "estimated_price": estimated_price,
        "gross_amount": gross_amount,
        "fee": fee,
        "net_amount": net_amount,
        "bucket_size": bucket_size,
        "cash_before": cash_before,
        "cash_after": cash_after,
        "is_executable": is_executable,
        "skip_reason": skip_reason,
    }


def build_funding_candidates(
    rebalance: pd.DataFrame,
    shares_state: dict[str, float],
    price_map: dict[str, float],
    bucket_size: float,
    max_funding_sell_pct: float,
    exclude_tickers: set[str],
) -> list[dict]:
    """
    Ermittelt bestehende Positionen, aus denen Cash für neue BUYs gewonnen werden darf.

    Wichtig für Variante C:
    - Funding-Sells sind KEINE eigenständige Rebalance-Entscheidung.
    - Sie dienen ausschließlich dazu, einen konkreten neuen BUY zu finanzieren.
    - Sie dürfen nur bis max_funding_sell_pct des aktuellen Positionswerts gehen.
    - Zusätzlich verkaufen wir nicht unter die neue Bucket-Größe, damit alte Positionen
      nicht aggressiv leerverkauft oder übermäßig verkleinert werden.
    """
    rows = []
    rebalance_map = rebalance.set_index("ticker").to_dict(orient="index") if not rebalance.empty else {}

    for ticker, shares in shares_state.items():
        if ticker in exclude_tickers:
            continue

        price = float(price_map.get(ticker, 0.0) or 0.0)
        shares = float(shares or 0.0)
        if shares <= 0 or price <= 0:
            continue

        current_value = shares * price
        excess_value = current_value - bucket_size
        if excess_value <= 0:
            continue

        limited_value = current_value * max_funding_sell_pct
        sell_value_cap = min(excess_value, limited_value)
        max_shares = int(sell_value_cap // price)

        if max_shares <= 0:
            continue

        meta = rebalance_map.get(ticker, {})
        rows.append({
            "ticker": ticker,
            "price": price,
            "max_shares": max_shares,
            "source_rank": None if pd.isna(meta.get("source_rank")) else int(meta.get("source_rank")),
            "target_weight": None if pd.isna(meta.get("target_weight")) else meta.get("target_weight"),
            "current_shares": shares,
        })

    return sorted(rows, key=lambda x: (x["source_rank"] is None, x["source_rank"], x["ticker"]))


def simulate_funding_for_buy(
    as_of_date,
    buy_required_cash: float,
    current_cash: float,
    funding_candidates: list[dict],
    shares_state: dict[str, float],
    used_funding_value_by_ticker: dict[str, float],
    max_funding_sell_pct: float,
    bucket_size: float,
) -> tuple[bool, list[dict], float]:
    """
    Simuliert Funding-Sells für EINEN konkreten BUY.

    Die Funktion gibt nur dann Funding-Zeilen zurück, wenn der BUY danach wirklich
    ausführbar ist. Dadurch entstehen keine verwaisten ADJUST_SELLs mehr.
    """
    simulated_cash = float(current_cash)
    simulated_rows = []

    if simulated_cash >= buy_required_cash:
        return True, [], simulated_cash

    for item in funding_candidates:
        ticker = item["ticker"]
        price = float(item["price"])
        available_shares = float(shares_state.get(ticker, 0.0) or 0.0)

        if available_shares <= 0 or price <= 0:
            continue

        current_value = available_shares * price
        excess_value = max(0.0, current_value - bucket_size)
        already_funded_value = float(used_funding_value_by_ticker.get(ticker, 0.0))

        # Monatslimit je Position: z. B. 20% des aktuellen Positionswerts.
        monthly_value_limit = current_value * max_funding_sell_pct
        remaining_value_limit = max(0.0, monthly_value_limit - already_funded_value)
        sell_value_cap = min(excess_value, remaining_value_limit)

        missing_cash = buy_required_cash - simulated_cash
        if missing_cash <= 0:
            break

        # Wir verkaufen nur so viel wie für den nächsten konkreten BUY nötig ist.
        #
        # WICHTIG:
        # Früher wurde hier per Floor-Division gearbeitet:
        #
        #   planned_shares = int(target_sell_value // price)
        #
        # Dadurch konnte der Funding-Mechanismus knapp unter dem benötigten
        # Cashbetrag hängen bleiben und der BUY wurde trotz ausreichend
        # möglicher Funding-Kandidaten verworfen.
        #
        # Deshalb verwenden wir jetzt eine "aufrundende" Berechnung:
        # Sobald ein Funding-Sell prinzipiell erlaubt ist, wird genügend
        # Stückzahl verkauft, damit der BUY danach tatsächlich ausführbar ist.
        target_sell_value = min(sell_value_cap, missing_cash + TRADE_FEE)

        planned_shares = int(target_sell_value / price)
        if (planned_shares * price) < target_sell_value:
            planned_shares += 1

        if planned_shares <= 0:
            continue

        planned_shares = min(planned_shares, int(available_shares))
        gross_amount = round_money(planned_shares * price)
        net_amount = round_money(gross_amount - TRADE_FEE)
        if net_amount <= 0:
            continue

        simulated_rows.append({
            "ticker": ticker,
            "price": price,
            "planned_shares": planned_shares,
            "gross_amount": gross_amount,
            "net_amount": net_amount,
            "source_rank": item["source_rank"],
            "target_weight": item["target_weight"],
            "current_shares": available_shares,
        })
        simulated_cash = round_money(simulated_cash + net_amount)

        if simulated_cash >= buy_required_cash:
            return True, simulated_rows, simulated_cash

    return False, [], current_cash


# --------------------------------------------------
# CORE
# --------------------------------------------------

def build_trade_plan(as_of_date, rebalance, real, prices, cash_before, settings):
    shares_map, price_map = build_maps(real, prices)
    portfolio_value, invested_value = compute_portfolio_values(real, prices, cash_before)

    portfolio_size = int(settings.portfolio_size)
    configured_max_trades = int(settings.max_trades_per_month)
    real_position_count = len(real)
    missing_positions = max(0, portfolio_size - real_position_count)

    # Positionswechsel-Limit:
    # BUY/SELL neuer bzw. entfernter Positionen zählen gegen das Limit.
    # Funding-ADJUST_SELLs zählen nicht als Positionswechsel, weil sie nur
    # bestehende Positionen verkleinern und keine Position schließen.
    position_change_limit = max(configured_max_trades, missing_positions)

    max_funding_sell_pct = get_max_funding_sell_pct(settings)
    bucket_size = portfolio_value / float(portfolio_size)
    threshold = bucket_size * THRESHOLD_PCT

    logger.info(
        "Portfolio=%.2f | investiert=%.2f | Cash=%.2f | Bucket=%.2f | Threshold=%.2f | "
        "position_change_limit=%s | max_funding_sell_pct=%.2f",
        portfolio_value,
        invested_value,
        cash_before,
        bucket_size,
        threshold,
        position_change_limit,
        max_funding_sell_pct,
    )

    cash = round_money(cash_before)
    execution_order = 1
    used_position_changes = 0
    rows = []

    shares_state = {ticker: float(shares) for ticker, shares in shares_map.items()}
    used_funding_value_by_ticker: dict[str, float] = {}

    # 1) Echte SELLs aus Rebalance. Diese schließen Positionen und zählen daher
    #    gegen das Positionswechsel-Limit.
    sell_rows = rebalance.loc[rebalance["action"] == "SELL"].copy()
    for _, row in sell_rows.iterrows():
        ticker = row["ticker"]
        price = float(price_map.get(ticker, 0.0) or 0.0)
        current_shares = float(shares_state.get(ticker, 0.0) or 0.0)

        if used_position_changes >= position_change_limit:
            rows.append(make_trade_row(
                as_of_date, ticker, "SELL", row["reason"], None,
                None if pd.isna(row["source_rank"]) else int(row["source_rank"]),
                None if pd.isna(row["target_weight"]) else float(row["target_weight"]),
                current_shares if current_shares > 0 else None, None, price if price > 0 else None,
                None, 0.0, None, bucket_size, cash, cash, 0, "position_change_limit_reached",
            ))
            continue

        if current_shares <= 0 or price <= 0:
            rows.append(make_trade_row(
                as_of_date, ticker, "SELL", row["reason"], None,
                None if pd.isna(row["source_rank"]) else int(row["source_rank"]),
                None if pd.isna(row["target_weight"]) else float(row["target_weight"]),
                current_shares if current_shares > 0 else None, None, price if price > 0 else None,
                None, 0.0, None, bucket_size, cash, cash, 0, "price_or_shares_missing",
            ))
            continue

        gross_amount = round_money(current_shares * price)
        net_amount = round_money(gross_amount - TRADE_FEE)
        cash_after = round_money(cash + net_amount)

        rows.append(make_trade_row(
            as_of_date, ticker, "SELL", row["reason"], execution_order,
            None if pd.isna(row["source_rank"]) else int(row["source_rank"]),
            None if pd.isna(row["target_weight"]) else float(row["target_weight"]),
            current_shares, current_shares, price, gross_amount, TRADE_FEE, net_amount,
            bucket_size, cash, cash_after, 1, None,
        ))
        shares_state[ticker] = 0.0
        cash = cash_after
        execution_order += 1
        used_position_changes += 1

    # 2) Neue BUYs. Falls Cash nicht reicht, werden begrenzte Funding-Sells
    #    simuliert und nur zusammen mit dem BUY gespeichert.
    buy_rows = rebalance.loc[rebalance["action"] == "BUY"].copy()
    buy_rows = buy_rows.sort_values(["source_rank", "ticker"], na_position="last")

    for _, row in buy_rows.iterrows():
        ticker = row["ticker"]
        price = float(price_map.get(ticker, 0.0) or 0.0)

        if used_position_changes >= position_change_limit:
            rows.append(make_trade_row(
                as_of_date, ticker, "BUY", row["reason"], None,
                None if pd.isna(row["source_rank"]) else int(row["source_rank"]),
                None if pd.isna(row["target_weight"]) else float(row["target_weight"]),
                None, None, price if price > 0 else None, None, 0.0, None,
                bucket_size, cash, cash, 0, "position_change_limit_reached",
            ))
            continue

        if price <= 0:
            rows.append(make_trade_row(
                as_of_date, ticker, "BUY", row["reason"], None,
                None if pd.isna(row["source_rank"]) else int(row["source_rank"]),
                None if pd.isna(row["target_weight"]) else float(row["target_weight"]),
                None, None, None, None, 0.0, None, bucket_size, cash, cash, 0, "price_missing",
            ))
            continue

        planned_shares = int((bucket_size - TRADE_FEE) // price)
        gross_amount = round_money(planned_shares * price) if planned_shares > 0 else 0.0
        buy_cash_needed = round_money(gross_amount + TRADE_FEE) if planned_shares > 0 else 0.0

        if planned_shares <= 0:
            rows.append(make_trade_row(
                as_of_date, ticker, "BUY", row["reason"], None,
                None if pd.isna(row["source_rank"]) else int(row["source_rank"]),
                None if pd.isna(row["target_weight"]) else float(row["target_weight"]),
                None, None, price, None, 0.0, None, bucket_size, cash, cash, 0, "shares_zero_after_rounding",
            ))
            continue

        funding_rows = []
        if cash < buy_cash_needed:
            funding_candidates = build_funding_candidates(
                rebalance=rebalance,
                shares_state=shares_state,
                price_map=price_map,
                bucket_size=bucket_size,
                max_funding_sell_pct=max_funding_sell_pct,
                exclude_tickers={ticker},
            )
            ok, funding_rows, funded_cash = simulate_funding_for_buy(
                as_of_date=as_of_date,
                buy_required_cash=buy_cash_needed,
                current_cash=cash,
                funding_candidates=funding_candidates,
                shares_state=shares_state,
                used_funding_value_by_ticker=used_funding_value_by_ticker,
                max_funding_sell_pct=max_funding_sell_pct,
                bucket_size=bucket_size,
            )
            if not ok:
                rows.append(make_trade_row(
                    as_of_date, ticker, "BUY", row["reason"], None,
                    None if pd.isna(row["source_rank"]) else int(row["source_rank"]),
                    None if pd.isna(row["target_weight"]) else float(row["target_weight"]),
                    None, planned_shares, price, gross_amount, TRADE_FEE, buy_cash_needed,
                    bucket_size, cash, cash, 0, "insufficient_cash_after_limited_funding",
                ))
                continue

        # Funding-Sells committen: erst jetzt, weil sicher ein BUY folgt.
        for f in funding_rows:
            cash_after_funding = round_money(cash + f["net_amount"])
            rows.append(make_trade_row(
                as_of_date=as_of_date,
                ticker=f["ticker"],
                action="ADJUST_SELL",
                reason="funding_new_buy_limited_pct",
                execution_order=execution_order,
                source_rank=f["source_rank"],
                target_weight=f["target_weight"],
                current_shares=f["current_shares"],
                planned_shares=f["planned_shares"],
                estimated_price=f["price"],
                gross_amount=f["gross_amount"],
                fee=TRADE_FEE,
                net_amount=f["net_amount"],
                bucket_size=bucket_size,
                cash_before=cash,
                cash_after=cash_after_funding,
                is_executable=1,
                skip_reason=None,
            ))
            shares_state[f["ticker"]] = round_money(shares_state.get(f["ticker"], 0.0) - f["planned_shares"])
            used_funding_value_by_ticker[f["ticker"]] = round_money(
                used_funding_value_by_ticker.get(f["ticker"], 0.0) + f["gross_amount"]
            )
            cash = cash_after_funding
            execution_order += 1

        if cash < buy_cash_needed:
            # Safety Guard: sollte durch Simulation nicht eintreten.
            rows.append(make_trade_row(
                as_of_date, ticker, "BUY", row["reason"], None,
                None if pd.isna(row["source_rank"]) else int(row["source_rank"]),
                None if pd.isna(row["target_weight"]) else float(row["target_weight"]),
                None, planned_shares, price, gross_amount, TRADE_FEE, buy_cash_needed,
                bucket_size, cash, cash, 0, "insufficient_cash_after_funding_guard",
            ))
            continue

        cash_after_buy = round_money(cash - buy_cash_needed)
        rows.append(make_trade_row(
            as_of_date=as_of_date,
            ticker=ticker,
            action="BUY",
            reason=row["reason"],
            execution_order=execution_order,
            source_rank=None if pd.isna(row["source_rank"]) else int(row["source_rank"]),
            target_weight=None if pd.isna(row["target_weight"]) else float(row["target_weight"]),
            current_shares=None,
            planned_shares=planned_shares,
            estimated_price=price,
            gross_amount=gross_amount,
            fee=TRADE_FEE,
            net_amount=buy_cash_needed,
            bucket_size=bucket_size,
            cash_before=cash,
            cash_after=cash_after_buy,
            is_executable=1,
            skip_reason=None,
        ))
        cash = cash_after_buy
        execution_order += 1
        used_position_changes += 1

    # 3) HOLD-/Skip-Zeilen für Rebalance-Ticker ohne ausführbare Zeile.
    #    Wenn ein Ticker nur als Funding-ADJUST_SELL vorkommt, bekommt er keine
    #    zusätzliche HOLD-Zeile, weil pro as_of_date/ticker nur eine Snapshot-Zeile erlaubt ist.
    planned_tickers = {r["ticker"] for r in rows}

    for _, row in rebalance.iterrows():
        ticker = row["ticker"]
        if ticker in planned_tickers:
            continue

        price = float(price_map[ticker]) if ticker in price_map else None
        current_shares = float(shares_state[ticker]) if ticker in shares_state else None

        rows.append(make_trade_row(
            as_of_date=as_of_date,
            ticker=ticker,
            action="HOLD",
            reason=row["reason"],
            execution_order=None,
            source_rank=None if pd.isna(row["source_rank"]) else int(row["source_rank"]),
            target_weight=None if pd.isna(row["target_weight"]) else float(row["target_weight"]),
            current_shares=current_shares,
            planned_shares=None,
            estimated_price=price,
            gross_amount=None,
            fee=0.0,
            net_amount=None,
            bucket_size=bucket_size,
            cash_before=cash,
            cash_after=cash,
            is_executable=0,
            skip_reason=row["reason"],
        ))


    # 3b) Funding-ADJUST_SELLs je Ticker aggregieren.
    #
    # Die Tabelle trade_plan_snapshots erlaubt nur eine Zeile pro
    # (as_of_date, ticker). Ein Ticker kann aber in der Funding-Simulation
    # mehrfach als Cash-Quelle für mehrere BUYs verwendet werden.
    #
    # Deshalb aggregieren wir mehrere ADJUST_SELL-Zeilen desselben Tickers
    # zu einer einzigen Zeile.
    aggregated_rows = []
    funding_by_ticker = {}

    for row in rows:
        key = (row["as_of_date"], row["ticker"])

        if row["action"] != "ADJUST_SELL":
            aggregated_rows.append(row)
            continue

        if key not in funding_by_ticker:
            funding_by_ticker[key] = dict(row)
            continue

        existing = funding_by_ticker[key]

        existing["planned_shares"] = round_money(
            float(existing["planned_shares"] or 0.0)
            + float(row["planned_shares"] or 0.0)
        )
        existing["gross_amount"] = round_money(
            float(existing["gross_amount"] or 0.0)
            + float(row["gross_amount"] or 0.0)
        )
        existing["fee"] = round_money(
            float(existing["fee"] or 0.0)
            + float(row["fee"] or 0.0)
        )
        existing["net_amount"] = round_money(
            float(existing["net_amount"] or 0.0)
            + float(row["net_amount"] or 0.0)
        )

        existing["cash_after"] = row["cash_after"]
        existing["execution_order"] = min(
            existing["execution_order"],
            row["execution_order"],
        )

        existing["reason"] = "funding_new_buy_limited_pct_aggregated"

    aggregated_rows.extend(funding_by_ticker.values())
    rows = aggregated_rows


    # 3c) Execution Order nach Aggregation normalisieren.
    #
    # Durch Aggregation mehrerer ADJUST_SELL-Zeilen können Lücken entstehen,
    # z. B. 1, 2, 3, 5, 6, 7. Für die UI und manuelle Umsetzung ist eine
    # saubere Reihenfolge besser.
    executable_rows = [
        row for row in rows
        if row.get("is_executable") == 1
        and row.get("execution_order") is not None
    ]

    executable_rows = sorted(
        executable_rows,
        key=lambda row: (
            float(row.get("execution_order") or 999999),
            str(row.get("ticker") or ""),
        )
    )

    for i, row in enumerate(executable_rows, start=1):
        row["execution_order"] = i


    trade_df = pd.DataFrame(rows)

    if trade_df.empty:
        trade_df = pd.DataFrame(columns=[
            "as_of_date", "ticker", "action", "reason", "execution_order",
            "source_rank", "target_weight", "current_shares", "planned_shares",
            "estimated_price", "gross_amount", "fee", "net_amount", "bucket_size",
            "cash_before", "cash_after", "is_executable", "skip_reason",
        ])

    dupes = trade_df[trade_df.duplicated(subset=["as_of_date", "ticker"], keep=False)]
    if not dupes.empty:
        raise ValueError(
            "Doppelte Trade-Plan-Zeilen gefunden:\n"
            + dupes.sort_values(["ticker", "execution_order"], na_position="last").to_string(index=False)
        )

    executable_buys = int(((trade_df["action"].isin(["BUY", "ADJUST_BUY"])) & (trade_df["is_executable"] == 1)).sum())
    executable_sells = int(((trade_df["action"].isin(["SELL", "ADJUST_SELL"])) & (trade_df["is_executable"] == 1)).sum())
    skipped_trades = int(((trade_df["action"] != "HOLD") & (trade_df["is_executable"] == 0)).sum())

    positions_before = int(len(real))
    full_position_sells = int(((trade_df["action"] == "SELL") & (trade_df["is_executable"] == 1)).sum())
    new_position_buys = int(((trade_df["action"] == "BUY") & (trade_df["is_executable"] == 1)).sum())
    positions_after = positions_before - full_position_sells + new_position_buys

    summary = {
        "as_of_date": as_of_date,
        "portfolio_value_before": float(portfolio_value),
        "invested_value_before": float(invested_value),
        "cash_before": float(cash_before),
        "cash_after": float(cash),
        "bucket_size": float(bucket_size),
        "target_positions": int(settings.portfolio_size),
        "positions_before": positions_before,
        "positions_after": positions_after,
        "total_sell_gross": float(trade_df.loc[(trade_df["action"].isin(["SELL", "ADJUST_SELL"])) & (trade_df["is_executable"] == 1), "gross_amount"].fillna(0.0).sum()),
        "total_buy_gross": float(trade_df.loc[(trade_df["action"].isin(["BUY", "ADJUST_BUY"])) & (trade_df["is_executable"] == 1), "gross_amount"].fillna(0.0).sum()),
        "total_fees": float(trade_df.loc[trade_df["is_executable"] == 1, "fee"].fillna(0.0).sum()),
        "executable_buys": executable_buys,
        "executable_sells": executable_sells,
        "skipped_trades": skipped_trades,
        "created_at": datetime.now(),
    }

    trade_df["created_at"] = datetime.now()

    # Reihenfolge in der Anzeige: tatsächliche Ausführungsreihenfolge zuerst.
    trade_df = trade_df.sort_values(
        ["execution_order", "source_rank", "ticker"],
        na_position="last"
    ).reset_index(drop=True)

    return trade_df, summary


# --------------------------------------------------
# SAVE
# --------------------------------------------------

def save_trade_plan(trade_df: pd.DataFrame, summary: dict) -> None:
    trade_df = trade_df.copy()
    trade_df = trade_df.astype(object)
    trade_df = trade_df.where(pd.notnull(trade_df), None)

    summary_df = pd.DataFrame([summary]).astype(object)
    summary_df = summary_df.where(pd.notnull(summary_df), None)

    with engine.begin() as conn:
        summary_df.to_sql(
            "trade_plan_summary",
            conn,
            if_exists="append",
            index=False,
            method="multi",
        )
        trade_df.to_sql(
            "trade_plan_snapshots",
            conn,
            if_exists="append",
            index=False,
            method="multi",
        )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def run(as_of_date: str | None = None):
    logger.info("=== BUILD TRADE PLAN V3.1 START ===")

    settings = load_settings()
    as_of_date = resolve_as_of_date(as_of_date)
    assert_trade_plan_snapshot_is_new(as_of_date)

    rebalance = load_rebalance(as_of_date)
    real = load_real_positions()
    prices = load_prices(as_of_date)
    cash_before = load_cash_balance()

    logger.info("Stichtag: %s", as_of_date)
    logger.info("Rebalance-Vorschläge: %s", len(rebalance))
    logger.info("Reale offene Positionen: %s", len(real))
    logger.info("Preiszeilen: %s", len(prices))
    logger.info("Verfügbarer Cash: %.2f", cash_before)

    trade_df, summary = build_trade_plan(as_of_date, rebalance, real, prices, cash_before, settings)

    logger.info(
        "Trade-Plan Summary: portfolio_before=%.2f | bucket=%.2f | cash_before=%.2f | cash_after=%.2f | exec_sells=%s | exec_buys=%s | skipped=%s",
        summary["portfolio_value_before"],
        summary["bucket_size"],
        summary["cash_before"],
        summary["cash_after"],
        summary["executable_sells"],
        summary["executable_buys"],
        summary["skipped_trades"],
    )

    if not trade_df.empty:
        logger.info(
            "\n%s",
            trade_df[[
                "ticker", "action", "reason", "execution_order", "planned_shares",
                "estimated_price", "cash_before", "cash_after", "is_executable", "skip_reason",
            ]].to_string(index=False)
        )

    save_trade_plan(trade_df, summary)

    logger.info("Trade-Plan Summary und Trade-Plan Snapshot unveränderlich gespeichert für %s", as_of_date)
    logger.info("=== BUILD TRADE PLAN V3.1 DONE ===")


if __name__ == "__main__":
    args = parse_args()
    run(as_of_date=args.as_of_date)

