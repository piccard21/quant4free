__all__ = [
    "DailyCandle",
    "DataProvider",
    "FinancialSyncPayload",
    "FinancialReport",
    "FixtureDataProvider",
    "MarketCapSnapshot",
    "PriceSyncService",
    "RawDataRepository",
    "Ticker",
    "TickerUpsert",
    "UniverseMemberUpsert",
    "UniverseRecord",
    "FundamentalSyncService",
    "latest_daily_candles",
    "latest_financial_reports",
    "latest_market_caps",
    "load_daily_candles",
    "load_financial_reports",
    "load_market_caps",
    "load_tickers",
]


def __getattr__(name: str):
    if name in {
        "DailyCandle",
        "FinancialSyncPayload",
        "FinancialReport",
        "MarketCapSnapshot",
        "Ticker",
        "TickerUpsert",
        "UniverseMemberUpsert",
        "UniverseRecord",
    }:
        from . import models

        return getattr(models, name)

    if name in {"FundamentalSyncService", "PriceSyncService"}:
        from . import sync

        return getattr(sync, name)

    if name in {"DataProvider", "FixtureDataProvider"}:
        from . import provider

        return getattr(provider, name)

    if name in {
        "RawDataRepository",
        "latest_daily_candles",
        "latest_financial_reports",
        "latest_market_caps",
        "load_daily_candles",
        "load_financial_reports",
        "load_market_caps",
        "load_tickers",
    }:
        from . import repository

        return getattr(repository, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
