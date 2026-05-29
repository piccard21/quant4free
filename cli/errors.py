from __future__ import annotations

import re
from collections.abc import Callable
from typing import NoReturn


RAW_TABLES = {
    "tickers",
    "daily_candles",
    "financial_reports",
    "market_cap_snapshots",
}

LIVE_TABLES = {
    "cash_ledger",
    "factor_metrics",
    "portfolio_cash",
    "portfolio_positions",
    "portfolio_snapshots",
    "strategy_settings",
    "strategy_settings_snapshots",
    "trade_executions",
    "trade_plan_snapshots",
}


class CliUsageError(Exception):
    """Expected operator-facing CLI error with an optional remediation hint."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


def run_cli(command: Callable[[], None]) -> None:
    """Run a CLI command and turn expected failures into concise messages."""

    try:
        command()
    except SystemExit:
        raise
    except ModuleNotFoundError as exc:
        _exit(
            f"missing Python dependency: {exc.name}; "
            "install requirements with .venv/bin/python -m pip install -r requirements.txt"
        )
    except CliUsageError as exc:
        _exit(format_cli_usage_error(exc))
    except Exception as exc:
        if _is_database_exception(exc):
            _exit(format_database_error(exc))
        raise


def format_cli_usage_error(exc: CliUsageError) -> str:
    lines = [f"cli_error={exc}"]
    if exc.hint:
        lines.append(f"hint={exc.hint}")
    return "\n".join(lines)


def format_database_error(exc: BaseException) -> str:
    message = _primary_message(exc)
    missing_table = _missing_table_name(message)
    if missing_table:
        lines = [
            "database_error=missing_table",
            f"table={missing_table}",
            f"message=required database table is missing: {missing_table}",
            f"hint={_missing_table_hint(missing_table)}",
        ]
        return "\n".join(lines)

    if "Unknown database" in message:
        return "\n".join(
            [
                "database_error=unknown_database",
                f"message={message}",
                "hint=create the configured database or check DB_NAME in .env",
            ]
        )

    if "Access denied" in message:
        return "\n".join(
            [
                "database_error=access_denied",
                f"message={message}",
                "hint=check DB_USER and DB_PASSWORD in .env",
            ]
        )

    if "Can't connect" in message or "Connection refused" in message:
        return "\n".join(
            [
                "database_error=connection_failed",
                f"message={message}",
                "hint=start MySQL with docker compose up -d db and check DB_HOST",
            ]
        )

    return "\n".join(
        [
            "database_error=query_failed",
            f"message={message}",
            "hint=run cli.data_status --details first to verify raw fixture availability",
        ]
    )


def require_non_empty(name: str, count: int, hint: str | None = None) -> None:
    if count <= 0:
        raise CliUsageError(f"{name} is empty", hint=hint)


def _is_database_exception(exc: BaseException) -> bool:
    database_error_names = {
        "DatabaseError",
        "DataError",
        "InterfaceError",
        "OperationalError",
        "ProgrammingError",
    }
    current: BaseException | None = exc
    while current is not None:
        if current.__class__.__name__ in database_error_names:
            return True
        current = current.__cause__ or current.__context__
    return False


def _primary_message(exc: BaseException) -> str:
    message = str(exc).strip()
    if "\n[SQL:" in message:
        message = message.split("\n[SQL:", 1)[0]
    return " ".join(message.split())


def _missing_table_name(message: str) -> str | None:
    mysql_match = re.search(r"Table '([^']+)' doesn't exist", message)
    if mysql_match:
        return mysql_match.group(1).split(".")[-1]

    sqlite_match = re.search(r"no such table:\s*([A-Za-z0-9_]+)", message)
    if sqlite_match:
        return sqlite_match.group(1)

    return None


def _missing_table_hint(table_name: str) -> str:
    if table_name in RAW_TABLES:
        return (
            "load fixtures/raw_market_data.sql into the configured database, "
            "then rerun cli.data_status --details"
        )
    if table_name in LIVE_TABLES:
        return (
            "load init.sql or run the legacy setup path to create live tables; "
            "fixtures/raw_market_data.sql intentionally does not contain live data"
        )
    return "check init.sql and the configured database schema"


def _exit(message: str) -> NoReturn:
    raise SystemExit(message)
