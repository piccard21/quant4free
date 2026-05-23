
import argparse
import logging
import subprocess
import sys
from datetime import datetime

from sqlalchemy import text

from shared.settings import engine


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# ARGUMENTE
# --------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of-date", required=True, help="Stichtag des Trade-Plans, Format YYYY-MM-DD")
    parser.add_argument("--ticker", required=True, help="Ticker, z. B. AAPL")
    parser.add_argument("--execution-type", required=True, choices=["BUY", "SELL"], help="Echte Ausführung: BUY oder SELL")
    parser.add_argument("--shares", required=True, type=float, help="Ausgeführte Stückzahl")
    parser.add_argument("--price", required=True, type=float, help="Ausführungspreis je Aktie")
    parser.add_argument("--fee", required=False, type=float, default=1.0, help="Gebühr des Trades")
    parser.add_argument("--executed-at", required=False, help="Zeitpunkt der Ausführung, Format YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--trade-plan-action", required=False, default=None, help="Originale Aktion aus trade_plan_snapshots")
    parser.add_argument("--broker", required=False, default=None, help="Optionaler Broker")
    parser.add_argument("--notes", required=False, default=None, help="Optionale Notiz")
    parser.add_argument(
        "--skip-performance-refresh",
        action="store_true",
        help="Performance nach erfolgreicher Verbuchung NICHT automatisch neu berechnen",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validiert alles, schreibt aber nichts in die DB"
    )
    return parser.parse_args()


# --------------------------------------------------
# HELPER
# --------------------------------------------------

def parse_executed_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now()

    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError(
            "Ungültiges Format für --executed-at. Erwartet: YYYY-MM-DD HH:MM:SS"
        ) from exc


def round_money(value: float) -> float:
    return round(float(value), 6)


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def normalize_trade_plan_action(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    return cleaned if cleaned else None


# --------------------------------------------------
# LOAD
# --------------------------------------------------

def load_trade_plan_row(conn, as_of_date: str, ticker: str):
    return conn.execute(
        text("""
            SELECT
                as_of_date,
                ticker,
                action,
                execution_order,
                planned_shares,
                estimated_price,
                is_executable,
                skip_reason
            FROM trade_plan_snapshots
            WHERE as_of_date = :as_of_date
              AND ticker = :ticker
            LIMIT 1
        """),
        {"as_of_date": as_of_date, "ticker": ticker},
    ).mappings().first()


def load_ticker_exists(conn, ticker: str) -> bool:
    row = conn.execute(
        text("""
            SELECT 1
            FROM tickers
            WHERE ticker = :ticker
            LIMIT 1
        """),
        {"ticker": ticker},
    ).scalar()
    return row is not None


def load_current_cash(conn) -> float:
    value = conn.execute(
        text("""
            SELECT cash_balance
            FROM portfolio_cash
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
        """)
    ).scalar()

    if value is None:
        raise ValueError("Kein Eintrag in portfolio_cash gefunden.")

    return float(value)


def load_open_position(conn, ticker: str):
    return conn.execute(
        text("""
            SELECT
                position_id,
                ticker,
                shares,
                buy_price,
                opened_at,
                is_open
            FROM portfolio_positions
            WHERE ticker = :ticker
              AND is_open = 1
            ORDER BY opened_at ASC, position_id ASC
            LIMIT 1
        """),
        {"ticker": ticker},
    ).mappings().first()


def load_latest_cash_ledger_balance(conn):
    row = conn.execute(
        text("""
            SELECT balance_after
            FROM cash_ledger
            ORDER BY booked_at DESC, id DESC
            LIMIT 1
        """)
    ).scalar()

    if row is None:
        return None

    return float(row)


def load_existing_execution_duplicate(
    conn,
    ticker: str,
    executed_at: datetime,
    shares: float,
    price: float,
):
    return conn.execute(
        text("""
            SELECT id
            FROM trade_executions
            WHERE ticker = :ticker
              AND executed_at = :executed_at
              AND shares = :shares
              AND price = :price
              AND status = 'executed'
            LIMIT 1
        """),
        {
            "ticker": ticker,
            "executed_at": executed_at,
            "shares": shares,
            "price": price,
        },
    ).scalar()


def load_existing_execution_by_plan(
    conn,
    as_of_date: str,
    ticker: str,
    execution_order: int,
):
    return conn.execute(
        text("""
            SELECT id
            FROM trade_executions
            WHERE as_of_date = :as_of_date
              AND ticker = :ticker
              AND trade_plan_execution_order = :execution_order
              AND status = 'executed'
            LIMIT 1
        """),
        {
            "as_of_date": as_of_date,
            "ticker": ticker,
            "execution_order": execution_order,
        },
    ).scalar()


def load_tax_rate(conn, as_of_date: str) -> float:
    snapshot_value = conn.execute(
        text("""
            SELECT tax_rate
            FROM strategy_settings_snapshots
            WHERE as_of_date = :as_of_date
            LIMIT 1
        """),
        {"as_of_date": as_of_date},
    ).scalar()

    if snapshot_value is not None:
        return float(snapshot_value)

    active_value = conn.execute(
        text("""
            SELECT tax_rate
            FROM strategy_settings
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
        """)
    ).scalar()

    if active_value is not None:
        return float(active_value)

    return 0.26375


# --------------------------------------------------
# VALIDIERUNG
# --------------------------------------------------

def validate_inputs(
    conn,
    as_of_date: str,
    ticker: str,
    execution_type: str,
    shares: float,
    price: float,
    fee: float,
    executed_at: datetime,
    trade_plan_action: str | None,
    dry_run: bool = False,
):
    if not load_ticker_exists(conn, ticker):
        raise ValueError(f"Ticker {ticker} existiert nicht in tickers.")

    if shares <= 0:
        raise ValueError("Shares müssen > 0 sein.")

    if price <= 0:
        raise ValueError("Price muss > 0 sein.")

    if fee < 0:
        raise ValueError("Fee darf nicht negativ sein.")

    trade_plan_row = load_trade_plan_row(conn, as_of_date, ticker)
    requested_plan_action = normalize_trade_plan_action(trade_plan_action)

    # Doppelerfassung immer verhindern
    existing_duplicate = load_existing_execution_duplicate(
        conn,
        ticker=ticker,
        executed_at=executed_at,
        shares=shares,
        price=price,
    )
    if existing_duplicate is not None:
        message = f"Mögliche Doppelerfassung erkannt: trade_executions.id={existing_duplicate}"
        if dry_run:
            logger.warning("%s Dry-Run läuft trotzdem weiter.", message)
        else:
            raise ValueError(message)

    if trade_plan_row is None:
        if requested_plan_action is not None:
            raise ValueError(
                f"--trade-plan-action ({requested_plan_action}) gesetzt, aber kein Trade-Plan-Eintrag "
                f"für {ticker} am Stichtag {as_of_date} gefunden."
            )
        return None

    action = str(trade_plan_row["action"]).upper()
    is_executable = int(trade_plan_row["is_executable"] or 0)

    if requested_plan_action is not None and requested_plan_action != action:
        raise ValueError(
            f"--trade-plan-action ({requested_plan_action}) passt nicht zur tatsächlichen "
            f"Trade-Plan-Aktion ({action}) für {ticker}."
        )

    # Nur wenn der Nutzer explizit planbezogen arbeitet ODER die Richtung zum Plan passt,
    # wird der Trade als planbezogene Ausführung streng validiert.
    plan_matches_execution = (
        (execution_type == "BUY" and action in {"BUY", "ADJUST_BUY"})
        or (execution_type == "SELL" and action in {"SELL", "ADJUST_SELL"})
    )
    enforce_plan = requested_plan_action is not None or plan_matches_execution

    if not enforce_plan:
        logger.info(
            "Off-Plan-Trade erkannt: ticker=%s | execution_type=%s | trade_plan_action=%s",
            ticker,
            execution_type,
            action,
        )
        return None

    if is_executable != 1:
        raise ValueError(
            f"Trade-Plan-Eintrag für {ticker} am Stichtag {as_of_date} ist nicht ausführbar "
            f"(skip_reason={trade_plan_row['skip_reason']})."
        )

    execution_order = trade_plan_row["execution_order"]
    if execution_order is not None:
        existing_by_plan = load_existing_execution_by_plan(
            conn,
            as_of_date=as_of_date,
            ticker=ticker,
            execution_order=execution_order,
        )

        if existing_by_plan is not None:
            message = (
                f"Trade für {ticker} (execution_order={execution_order}) wurde bereits verbucht "
                f"(trade_execution_id={existing_by_plan})."
            )
            if dry_run:
                logger.warning("%s Dry-Run läuft trotzdem weiter.", message)
            else:
                raise ValueError(message)

    if execution_type == "BUY" and action not in {"BUY", "ADJUST_BUY"}:
        raise ValueError(
            f"Execution-Typ BUY passt nicht zur Trade-Plan-Aktion {action} für {ticker}."
        )

    if execution_type == "SELL" and action not in {"SELL", "ADJUST_SELL"}:
        raise ValueError(
            f"Execution-Typ SELL passt nicht zur Trade-Plan-Aktion {action} für {ticker}."
        )

    return trade_plan_row


def validate_buy(conn, ticker: str, shares: float, price: float, fee: float):
    current_cash = load_current_cash(conn)
    gross_amount = round_money(shares * price)
    total_cash_needed = round_money(gross_amount + fee)

    if total_cash_needed > current_cash:
        raise ValueError(
            f"Nicht genug Cash für BUY in {ticker}. "
            f"Bedarf={total_cash_needed:.2f}, verfügbar={current_cash:.6f}"
        )

    return current_cash, gross_amount, total_cash_needed


def validate_sell(conn, ticker: str, shares: float, price: float, fee: float):
    position = load_open_position(conn, ticker)
    if position is None:
        raise ValueError(f"Keine offene Position für SELL von {ticker} gefunden.")

    open_shares = float(position["shares"])
    if shares > open_shares:
        raise ValueError(
            f"SELL Shares größer als offene Position in {ticker}. "
            f"Offen={open_shares:.6f}, SELL={shares:.6f}"
        )

    gross_amount = round_money(shares * price)
    net_cash_increase = round_money(gross_amount - fee)

    return position, gross_amount, net_cash_increase


# --------------------------------------------------
# WRITE HELPERS
# --------------------------------------------------

def insert_trade_execution(
    conn,
    as_of_date: str,
    ticker: str,
    execution_type: str,
    trade_plan_action: str | None,
    executed_at: datetime,
    shares: float,
    price: float,
    gross_amount: float,
    fee: float,
    net_amount: float,
    realized_profit: float | None,
    tax_amount: float,
    trade_plan_execution_order,
    broker: str | None,
    notes: str | None,
):
    conn.execute(
        text("""
            INSERT INTO trade_executions (
                as_of_date,
                ticker,
                execution_type,
                trade_plan_action,
                executed_at,
                shares,
                price,
                gross_amount,
                fee,
                net_amount,
                realized_profit,
                tax_amount,
                trade_plan_execution_order,
                broker,
                notes,
                status,
                created_at
            ) VALUES (
                :as_of_date,
                :ticker,
                :execution_type,
                :trade_plan_action,
                :executed_at,
                :shares,
                :price,
                :gross_amount,
                :fee,
                :net_amount,
                :realized_profit,
                :tax_amount,
                :trade_plan_execution_order,
                :broker,
                :notes,
                'executed',
                NOW()
            )
        """),
        {
            "as_of_date": as_of_date,
            "ticker": ticker,
            "execution_type": execution_type,
            "trade_plan_action": trade_plan_action,
            "executed_at": executed_at,
            "shares": shares,
            "price": price,
            "gross_amount": gross_amount,
            "fee": fee,
            "net_amount": net_amount,
            "realized_profit": realized_profit,
            "tax_amount": tax_amount,
            "trade_plan_execution_order": trade_plan_execution_order,
            "broker": broker,
            "notes": notes,
        },
    )

    trade_execution_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    return int(trade_execution_id)


def insert_cash_ledger_entry(
    conn,
    booked_at: datetime,
    as_of_date: str,
    ticker: str | None,
    entry_type: str,
    amount: float,
    balance_after: float,
    trade_execution_id: int | None,
    notes: str | None,
):
    conn.execute(
        text("""
            INSERT INTO cash_ledger (
                booked_at,
                as_of_date,
                ticker,
                entry_type,
                amount,
                balance_after,
                trade_execution_id,
                notes,
                created_at
            ) VALUES (
                :booked_at,
                :as_of_date,
                :ticker,
                :entry_type,
                :amount,
                :balance_after,
                :trade_execution_id,
                :notes,
                NOW()
            )
        """),
        {
            "booked_at": booked_at,
            "as_of_date": as_of_date,
            "ticker": ticker,
            "entry_type": entry_type,
            "amount": amount,
            "balance_after": balance_after,
            "trade_execution_id": trade_execution_id,
            "notes": notes,
        },
    )


def update_portfolio_cash(conn, new_balance: float, executed_at: datetime):
    conn.execute(
        text("""
            INSERT INTO portfolio_cash (
                cash_balance,
                updated_at
            ) VALUES (
                :cash_balance,
                :updated_at
            )
        """),
        {
            "cash_balance": new_balance,
            "updated_at": executed_at,
        },
    )


def apply_buy_execution(conn, ticker: str, shares: float, price: float, executed_at: datetime):
    existing_position = load_open_position(conn, ticker)

    if existing_position is None:
        conn.execute(
            text("""
                INSERT INTO portfolio_positions (
                    ticker,
                    shares,
                    buy_price,
                    opened_at,
                    is_open,
                    closed_at,
                    notes,
                    created_at,
                    updated_at
                ) VALUES (
                    :ticker,
                    :shares,
                    :buy_price,
                    :opened_at,
                    1,
                    NULL,
                    :notes,
                    NOW(),
                    NOW()
                )
            """),
            {
                "ticker": ticker,
                "shares": shares,
                "buy_price": price,
                "opened_at": executed_at.date(),
                "notes": "Created by apply_trade_execution.py",
            },
        )
        return

    old_shares = float(existing_position["shares"])
    old_buy_price = float(existing_position["buy_price"])

    new_total_shares = round(old_shares + shares, 6)
    new_avg_price = round_money(
        ((old_shares * old_buy_price) + (shares * price)) / new_total_shares
    )

    conn.execute(
        text("""
            UPDATE portfolio_positions
            SET
                shares = :shares,
                buy_price = :buy_price,
                updated_at = NOW()
            WHERE position_id = :position_id
        """),
        {
            "shares": new_total_shares,
            "buy_price": new_avg_price,
            "position_id": existing_position["position_id"],
        },
    )


def apply_sell_execution(conn, ticker: str, shares: float, executed_at: datetime):
    position = load_open_position(conn, ticker)
    if position is None:
        raise ValueError(f"Keine offene Position für SELL von {ticker} gefunden.")

    old_shares = float(position["shares"])
    remaining_shares = round(old_shares - shares, 6)

    if remaining_shares < 0:
        raise ValueError(
            f"Negative Restposition für {ticker} erkannt: {remaining_shares}"
        )

    if remaining_shares == 0:
        conn.execute(
            text("""
                UPDATE portfolio_positions
                SET
                    shares = 0,
                    is_open = 0,
                    closed_at = :closed_at,
                    updated_at = NOW()
                WHERE position_id = :position_id
            """),
            {
                "closed_at": executed_at.date(),
                "position_id": position["position_id"],
            },
        )
        return

    conn.execute(
        text("""
            UPDATE portfolio_positions
            SET
                shares = :shares,
                updated_at = NOW()
            WHERE position_id = :position_id
        """),
        {
            "shares": remaining_shares,
            "position_id": position["position_id"],
        },
    )


def refresh_performance_snapshot(as_of_date: str) -> None:
    commands = [
        ["python", "-m", "cli.research_main", "performance", "--as-of-date", as_of_date],
        ["python", "-m", "research_main", "performance", "--as-of-date", as_of_date],
        ["python", "-m", "research.build_performance", "--as-of-date", as_of_date],
        ["python", "build_performance.py", "--as-of-date", as_of_date],
    ]

    for cmd in commands:
        try:
            logger.info("Aktualisiere Performance automatisch: %s", " ".join(cmd))
            result = subprocess.run(cmd, check=False)
            if result.returncode == 0:
                logger.info("Performance für %s erfolgreich aktualisiert.", as_of_date)
                return
        except FileNotFoundError:
            continue

    raise RuntimeError(
        f"Trade wurde verbucht, aber die automatische Performance-Aktualisierung für {as_of_date} ist fehlgeschlagen."
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def run(
    as_of_date: str,
    ticker: str,
    execution_type: str,
    shares: float,
    price: float,
    fee: float,
    executed_at: datetime,
    trade_plan_action: str | None,
    broker: str | None,
    notes: str | None,
    dry_run: bool,
    skip_performance_refresh: bool,
):
    ticker = normalize_ticker(ticker)
    execution_type = execution_type.strip().upper()
    trade_plan_action = normalize_trade_plan_action(trade_plan_action)
    shares = round(float(shares), 6)
    price = round_money(price)
    fee = round_money(fee)

    logger.info("=== APPLY TRADE EXECUTION START ===")
    logger.info(
        "Input: as_of_date=%s | ticker=%s | execution_type=%s | shares=%.6f | price=%.6f | fee=%.6f | executed_at=%s | dry_run=%s",
        as_of_date,
        ticker,
        execution_type,
        shares,
        price,
        fee,
        executed_at,
        dry_run,
    )

    with engine.begin() as conn:
        trade_plan_row = validate_inputs(
            conn=conn,
            as_of_date=as_of_date,
            ticker=ticker,
            execution_type=execution_type,
            shares=shares,
            price=price,
            fee=fee,
            executed_at=executed_at,
            trade_plan_action=trade_plan_action,
            dry_run=dry_run,
        )

        if trade_plan_row is None:
            trade_plan_action_db = trade_plan_action
            trade_plan_execution_order = None
            effective_notes = notes or "manual off-plan trade"
        else:
            trade_plan_action_db = str(trade_plan_row["action"]).upper()
            trade_plan_execution_order = trade_plan_row["execution_order"]
            effective_notes = notes

        current_cash = load_current_cash(conn)
        latest_ledger_balance = load_latest_cash_ledger_balance(conn)

        if latest_ledger_balance is not None and abs(latest_ledger_balance - current_cash) > 0.000001:
            raise ValueError(
                f"Inkonsistenz zwischen portfolio_cash ({current_cash:.6f}) und cash_ledger ({latest_ledger_balance:.6f})."
            )

        realized_profit = None
        tax_amount = 0.0
        tax_rate = load_tax_rate(conn, as_of_date)

        if execution_type == "BUY":
            current_cash, gross_amount, _ = validate_buy(
                conn, ticker, shares, price, fee
            )
            net_amount = round_money(-(gross_amount + fee))
            new_cash_balance_before_tax = round_money(current_cash + net_amount)
            new_cash_balance = new_cash_balance_before_tax

        elif execution_type == "SELL":
            position, gross_amount, net_cash_increase = validate_sell(
                conn, ticker, shares, price, fee
            )
            buy_price = round_money(float(position["buy_price"]))
            realized_profit = round_money((price - buy_price) * shares)
            tax_amount = round_money(max(realized_profit, 0.0) * tax_rate)
            net_amount = round_money(net_cash_increase)
            new_cash_balance_before_tax = round_money(current_cash + net_amount)
            new_cash_balance = round_money(new_cash_balance_before_tax - tax_amount)

        else:
            raise ValueError(f"Unbekannter execution_type: {execution_type}")

        if new_cash_balance < -0.000001:
            raise ValueError(
                f"Negativer Cash nach Verbuchung erkannt: {new_cash_balance:.6f}"
            )

        logger.info(
            "Validierung erfolgreich: gross_amount=%.6f | net_amount=%.6f | realized_profit=%s | tax_amount=%.6f | cash_before=%.6f | cash_after=%.6f",
            gross_amount,
            net_amount,
            "-" if realized_profit is None else f"{realized_profit:.6f}",
            tax_amount,
            current_cash,
            new_cash_balance,
        )

        if dry_run:
            logger.info("Dry-Run aktiv: keine DB-Schreibvorgänge ausgeführt.")
            logger.info("=== APPLY TRADE EXECUTION DONE ===")
            return

        if execution_type == "BUY":
            apply_buy_execution(conn, ticker, shares, price, executed_at)
            cash_entry_type = "trade_buy"
        else:
            apply_sell_execution(conn, ticker, shares, executed_at)
            cash_entry_type = "trade_sell"

        trade_execution_id = insert_trade_execution(
            conn=conn,
            as_of_date=as_of_date,
            ticker=ticker,
            execution_type=execution_type,
            trade_plan_action=trade_plan_action_db,
            executed_at=executed_at,
            shares=shares,
            price=price,
            gross_amount=gross_amount,
            fee=fee,
            net_amount=net_amount,
            realized_profit=realized_profit,
            tax_amount=tax_amount,
            trade_plan_execution_order=trade_plan_execution_order,
            broker=broker,
            notes=effective_notes,
        )

        insert_cash_ledger_entry(
            conn=conn,
            booked_at=executed_at,
            as_of_date=as_of_date,
            ticker=ticker,
            entry_type=cash_entry_type,
            amount=net_amount,
            balance_after=new_cash_balance_before_tax,
            trade_execution_id=trade_execution_id,
            notes=effective_notes,
        )

        if tax_amount > 0:
            insert_cash_ledger_entry(
                conn=conn,
                booked_at=executed_at,
                as_of_date=as_of_date,
                ticker=ticker,
                entry_type="tax_payment",
                amount=round_money(-tax_amount),
                balance_after=new_cash_balance,
                trade_execution_id=trade_execution_id,
                notes=effective_notes,
            )

        update_portfolio_cash(conn, new_balance=new_cash_balance, executed_at=executed_at)

        logger.info(
            "Trade erfolgreich verbucht: trade_execution_id=%s | ticker=%s | execution_type=%s | tax_amount=%.6f | cash_after=%.6f",
            trade_execution_id,
            ticker,
            execution_type,
            tax_amount,
            new_cash_balance,
        )

    if not skip_performance_refresh:
        refresh_performance_snapshot(as_of_date)

    logger.info("=== APPLY TRADE EXECUTION DONE ===")


if __name__ == "__main__":
    args = parse_args()
    run(
        as_of_date=args.as_of_date,
        ticker=args.ticker,
        execution_type=args.execution_type,
        shares=args.shares,
        price=args.price,
        fee=args.fee,
        executed_at=parse_executed_at(args.executed_at),
        trade_plan_action=args.trade_plan_action,
        broker=args.broker,
        notes=args.notes,
        dry_run=args.dry_run,
        skip_performance_refresh=args.skip_performance_refresh,
    )


