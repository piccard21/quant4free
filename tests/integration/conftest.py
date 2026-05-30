from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MysqlTestConfig:
    host: str
    user: str
    password: str
    database: str
    driver: str = "mysql+mysqlconnector"

    @property
    def admin_url(self) -> URL:
        return URL.create(
            drivername=self.driver,
            username=self.user,
            password=self.password,
            host=self.host,
        )

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername=self.driver,
            username=self.user,
            password=self.password,
            host=self.host,
            database=self.database,
        )


@pytest.fixture(scope="session")
def mysql_test_config() -> MysqlTestConfig:
    database = os.getenv("Q4F_TEST_DB_NAME", "quant4free_test")
    configured_db = os.getenv("DB_NAME", "stocks_db")
    if database == configured_db or "test" not in database.lower():
        raise RuntimeError(
            "Q4F_TEST_DB_NAME must be an isolated database containing 'test' "
            "and must not equal DB_NAME"
        )
    if not re.fullmatch(r"[A-Za-z0-9_]+", database):
        raise RuntimeError("Q4F_TEST_DB_NAME must contain only letters, digits, and underscores")

    return MysqlTestConfig(
        host=os.getenv("Q4F_TEST_DB_HOST", os.getenv("DB_HOST", "localhost")),
        user=os.getenv("Q4F_TEST_DB_USER", os.getenv("DB_USER", "root")),
        password=os.getenv(
            "Q4F_TEST_DB_PASSWORD",
            os.getenv("DB_PASSWORD", os.getenv("MYSQL_ROOT_PASSWORD", "mypassword")),
        ),
        database=database,
        driver=os.getenv("Q4F_TEST_DB_DRIVER", "mysql+mysqlconnector"),
    )


@pytest.fixture(scope="session")
def mysql_engine(mysql_test_config: MysqlTestConfig) -> Engine:
    admin_engine = create_engine(mysql_test_config.admin_url, future=True, pool_pre_ping=True)
    try:
        with admin_engine.begin() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text(f"DROP DATABASE IF EXISTS `{mysql_test_config.database}`"))
            conn.execute(
                text(
                    f"CREATE DATABASE `{mysql_test_config.database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
            )
    except SQLAlchemyError as exc:
        pytest.skip(f"MySQL integration database is not available: {exc}")
    finally:
        admin_engine.dispose()

    engine = create_engine(mysql_test_config.database_url, future=True, pool_pre_ping=True)
    try:
        _execute_sql_file(engine, REPO_ROOT / "fixtures/raw_market_data.sql")
        _execute_sql_file(engine, REPO_ROOT / "init.sql")
        yield engine
    finally:
        engine.dispose()
        admin_engine = create_engine(mysql_test_config.admin_url, future=True, pool_pre_ping=True)
        try:
            with admin_engine.begin() as conn:
                conn.execute(text(f"DROP DATABASE IF EXISTS `{mysql_test_config.database}`"))
        finally:
            admin_engine.dispose()


@pytest.fixture()
def mysql_cli_env(mysql_test_config: MysqlTestConfig) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DB_HOST": mysql_test_config.host,
            "DB_USER": mysql_test_config.user,
            "DB_PASSWORD": mysql_test_config.password,
            "DB_NAME": mysql_test_config.database,
            "MYSQL_ROOT_PASSWORD": mysql_test_config.password,
        }
    )
    return env


def _execute_sql_file(engine: Engine, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        for statement in _split_sql_statements(sql):
            conn.exec_driver_sql(statement)


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    escaped = False

    for char in sql:
        current.append(char)
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement[:-1].strip())
            current = []

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements
