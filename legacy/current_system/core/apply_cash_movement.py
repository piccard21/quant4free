import argparse
import logging
import subprocess
import sys
from datetime import datetime

from sqlalchemy import text

from shared.settings import engine


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# ARGUMENTE
# --------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Bucht manuelle Cash-Bewegungen: Einzahlung oder Auszahlung."
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=["deposit", "withdrawal"],
        help="deposit = Einzahlung, withdrawal = Auszahlung",
    )
    parser.add_argument(
        "--amount",
        required=True,
        type=float,
        help="Betrag der Cash-Bewegung. Immer positiv eingeben.",
    )
    parser.add_argument(
        "--as-of-date",
        required=False,
        default=None,
        help=(
            "Bezug zum Strategie-/Rebalance-Stichtag YYYY-MM-DD. "
            "Falls nicht gesetzt: letzter strategy_settings_snapshots-Stichtag."
        ),
    )
    parser.add_argument(
        "--booked-at",
        required=False,
        default=None,
        help="Buchungszeitpunkt YYYY-MM-DD HH:MM:SS. Standard: jetzt.",
    )
    parser.add_argument(
        "--notes",
        required=False,
        default=None,
        help="Optionale Notiz.",
    )
    parser.add_argument(
        "--skip-performance-refresh",
        action="store_true",
        help="Performance nach Buchung nicht neu berechnen.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validiert alles, schreibt aber nichts in die DB.",
    )
    return parser.parse_args()


# --------------------------------------------------
# HELPER
# --------------------------------------------------

def parse_booked_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now()

    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError(
            "Ungültiges Format für --booked-at. Erwartet: YYYY-MM-DD HH:MM:SS"
        ) from exc


def round_money(value: float) -> float:
    return round(float(value), 6)


def resolve_as_of_date(conn, value: str | None):
    if value:
        return value

    as_of_date = conn.execute(
        text("""
            SELECT MAX(as_of_date)
            FROM strategy_settings_snapshots
        """)
    ).scalar()

    if as_of_date is None:
        raise ValueError(
            "Kein strategy_settings_snapshots-Stichtag gefunden. "
            "Bitte --as-of-date explizit angeben, nachdem ein Rebalance-Snapshot existiert."
        )

    return str(as_of_date)


def assert_settings_snapshot_exists(conn, as_of_date: str) -> None:
    exists = conn.execute(
        text("""
            SELECT 1
            FROM strategy_settings_snapshots
            WHERE as_of_date = :as_of_date
            LIMIT 1
        """),
        {"as_of_date": as_of_date},
    ).scalar()

    if exists is None:
        raise ValueError(
            f"Kein strategy_settings_snapshots-Eintrag für as_of_date={as_of_date}. "
            "Cash-Ledger-Einträge müssen auf einen existierenden Snapshot-Stichtag zeigen."
        )


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


def load_latest_ledger_balance(conn):
    value = conn.execute(
        text("""
            SELECT balance_after
            FROM cash_ledger
            ORDER BY booked_at DESC, id DESC
            LIMIT 1
        """)
    ).scalar()

    if value is None:
        return None

    return float(value)


def validate_cash_consistency(current_cash: float, ledger_cash: float | None) -> None:
    if ledger_cash is None:
        return

    diff = round_money(current_cash - ledger_cash)
    if abs(diff) > 0.000001:
        raise ValueError(
            "Cash-Inkonsistenz erkannt: "
            f"portfolio_cash={current_cash:.6f}, cash_ledger={ledger_cash:.6f}, diff={diff:.6f}"
        )


def insert_cash_ledger_entry(
    conn,
    booked_at: datetime,
    as_of_date: str,
    entry_type: str,
    amount: float,
    balance_after: float,
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
                NULL,
                :entry_type,
                :amount,
                :balance_after,
                NULL,
                :notes,
                NOW()
            )
        """),
        {
            "booked_at": booked_at,
            "as_of_date": as_of_date,
            "entry_type": entry_type,
            "amount": amount,
            "balance_after": balance_after,
            "notes": notes,
        },
    )


def update_portfolio_cash(conn, new_balance: float, booked_at: datetime):
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
            "updated_at": booked_at,
        },
    )


def refresh_performance_snapshot(as_of_date: str) -> None:
    cmd = [
        "python",
        "-m",
        "research.build_performance",
        "--as-of-date",
        as_of_date,
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        logger.error("Performance-Refresh fehlgeschlagen.")
        sys.exit(1)


# --------------------------------------------------
# CORE
# --------------------------------------------------

def run(
    movement_type: str,
    amount: float,
    as_of_date: str | None,
    booked_at: datetime,
    notes: str | None,
    dry_run: bool = False,
    skip_performance_refresh: bool = False,
):
    logger.info("=== APPLY CASH MOVEMENT START ===")

    if amount <= 0:
        raise ValueError("--amount muss > 0 sein.")

    amount = round_money(amount)

    with engine.begin() as conn:
        resolved_as_of_date = resolve_as_of_date(conn, as_of_date)
        assert_settings_snapshot_exists(conn, resolved_as_of_date)

        current_cash = round_money(load_current_cash(conn))
        ledger_cash = load_latest_ledger_balance(conn)
        validate_cash_consistency(current_cash, ledger_cash)

        if movement_type == "deposit":
            signed_amount = amount
            new_balance = round_money(current_cash + amount)

        elif movement_type == "withdrawal":
            if amount > current_cash:
                raise ValueError(
                    f"Auszahlung nicht möglich. Gewünscht={amount:.2f}, "
                    f"verfügbar={current_cash:.2f}"
                )

            signed_amount = round_money(-amount)
            new_balance = round_money(current_cash - amount)

        else:
            raise ValueError(f"Unbekannter movement_type: {movement_type}")

        logger.info(
            "Validierung erfolgreich: type=%s | amount=%.6f | cash_before=%.6f | cash_after=%.6f | as_of_date=%s",
            movement_type,
            signed_amount,
            current_cash,
            new_balance,
            resolved_as_of_date,
        )

        if dry_run:
            logger.info("Dry-Run aktiv: keine DB-Schreibvorgänge ausgeführt.")
            logger.info("=== APPLY CASH MOVEMENT DONE ===")
            return

        insert_cash_ledger_entry(
            conn=conn,
            booked_at=booked_at,
            as_of_date=resolved_as_of_date,
            entry_type=movement_type,
            amount=signed_amount,
            balance_after=new_balance,
            notes=notes,
        )

        update_portfolio_cash(
            conn=conn,
            new_balance=new_balance,
            booked_at=booked_at,
        )

        logger.info(
            "Cash-Bewegung erfolgreich verbucht: type=%s | amount=%.6f | cash_after=%.6f",
            movement_type,
            signed_amount,
            new_balance,
        )

    if not skip_performance_refresh:
        refresh_performance_snapshot(resolved_as_of_date)

    logger.info("=== APPLY CASH MOVEMENT DONE ===")


if __name__ == "__main__":
    args = parse_args()
    run(
        movement_type=args.type,
        amount=args.amount,
        as_of_date=args.as_of_date,
        booked_at=parse_booked_at(args.booked_at),
        notes=args.notes,
        dry_run=args.dry_run,
        skip_performance_refresh=args.skip_performance_refresh,
    )
