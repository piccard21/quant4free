from cli.errors import CliUsageError, format_cli_usage_error, format_database_error


class FakeDatabaseError(Exception):
    pass


def test_database_error_formats_mysql_missing_live_table_hint():
    message = (
        "(mysql.connector.errors.ProgrammingError) 1146 (42S02): "
        "Table 'stocks_db.portfolio_snapshots' doesn't exist"
    )

    formatted = format_database_error(FakeDatabaseError(message))

    assert "database_error=missing_table" in formatted
    assert "table=portfolio_snapshots" in formatted
    assert "fixtures/raw_market_data.sql intentionally does not contain live data" in formatted


def test_database_error_formats_sqlite_missing_raw_table_hint():
    formatted = format_database_error(FakeDatabaseError("no such table: tickers"))

    assert "database_error=missing_table" in formatted
    assert "table=tickers" in formatted
    assert "load fixtures/raw_market_data.sql" in formatted


def test_cli_usage_error_includes_hint():
    formatted = format_cli_usage_error(
        CliUsageError("strategy ranking rows is empty", hint="check fixture overlap")
    )

    assert formatted == (
        "cli_error=strategy ranking rows is empty\n"
        "hint=check fixture overlap"
    )
