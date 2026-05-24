import os
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import URL


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    user: str
    password: str
    database: str
    driver: str = "mysql+mysqlconnector"

    @property
    def url(self) -> URL:
        return URL.create(
            drivername=self.driver,
            username=self.user,
            password=self.password,
            host=self.host,
            database=self.database,
        )


def load_database_config() -> DatabaseConfig:
    return DatabaseConfig(
        host=os.getenv("DB_HOST", "db"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv(
            "DB_PASSWORD",
            os.getenv("MYSQL_ROOT_PASSWORD", "password123"),
        ),
        database=os.getenv("DB_NAME", "stocks_db"),
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    config = load_database_config()
    return create_engine(config.url, pool_pre_ping=True, future=True)


@contextmanager
def connect() -> Iterator[Connection]:
    with get_engine().connect() as connection:
        yield connection


def ping_database() -> bool:
    with get_engine().connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1
