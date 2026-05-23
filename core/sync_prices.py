import argparse
import io
import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.dialects.mysql import insert

from shared.settings import (
    engine,
    load_settings,
    BENCHMARK_TICKER,
    INIT_HISTORY_DAYS,
    DAILY_LOOKBACK_DAYS,
    NEW_TICKER_FALLBACK_DAYS,
    INIT_CHUNK_SIZE,
    INIT_SLEEP_SECONDS,
    DAILY_SLEEP_SECONDS,
)


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# ARGUMENTE
# --------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["init", "daily"],
        default="daily",
        help="init = Initial Load (~18 Monate), daily = inkrementelles Update"
    )
    return parser.parse_args()


# --------------------------------------------------
# HELPER
# --------------------------------------------------

def chunked(items, size):
    """Teilt eine Liste in Chunks fester Größe."""
    for i in range(0, len(items), size):
        yield items[i:i + size]


def sync_tickers_with_wikipedia():
    """Gleicht die Wikipedia-Liste mit der lokalen Ticker-Tabelle ab."""
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        table = pd.read_html(io.StringIO(response.text))
        df_wiki = table[0].copy()

        df_wiki = df_wiki[['Symbol', 'Security', 'GICS Sector']]
        df_wiki.columns = ['ticker', 'name', 'sector']
        df_wiki['ticker'] = df_wiki['ticker'].str.replace('.', '-', regex=False)

        current_wiki_tickers = df_wiki['ticker'].tolist()
        now = datetime.now()

        with engine.begin() as conn:
            ticker_placeholder = ", ".join([f"'{t}'" for t in current_wiki_tickers])
            sql_deactivate = text(f"""
                UPDATE tickers
                SET is_active = 0, removed_at = :now
                WHERE ticker NOT IN ({ticker_placeholder}) AND is_active = 1
            """)
            conn.execute(sql_deactivate, {"now": now})

            for _, row in df_wiki.iterrows():
                stmt = text("""
                    INSERT INTO tickers (ticker, name, sector, is_active, first_seen, last_seen, removed_at)
                    VALUES (:t, :n, :s, 1, :now, :now, NULL)
                    ON DUPLICATE KEY UPDATE
                        name = :n,
                        sector = :s,
                        is_active = 1,
                        last_seen = :now,
                        removed_at = NULL
                """)
                conn.execute(stmt, {
                    "t": row["ticker"],
                    "n": row["name"],
                    "s": row["sector"],
                    "now": now
                })

        logger.info("Ticker-Sync: %s Ticker aktuell im System.", len(current_wiki_tickers))
        return current_wiki_tickers

    except Exception as e:
        logger.error("Fehler bei Ticker-Sync: %s", e)
        return []


def upsert_candles(table, conn, keys, data_iter):
    """Sorgt für sauberes Update der Kerzen ohne Duplikate."""
    data = [dict(zip(keys, row)) for row in data_iter]
    if not data:
        return

    stmt = insert(table.table).values(data)
    update_dict = {c.name: c for c in stmt.inserted if c.name not in ["ticker", "date"]}
    conn.execute(stmt.on_duplicate_key_update(update_dict))


def normalize_single_ticker_df(df, ticker):
    """Normalisiert yfinance-Output für einen einzelnen Ticker."""
    if df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]

    if "adj_close" in df.columns:
        df = df.drop(columns=["adj_close"])

    if "date" not in df.columns:
        logger.warning("%s: Keine 'date'-Spalte im Download gefunden.", ticker)
        return pd.DataFrame()

    expected_cols = ["date", "open", "high", "low", "close", "volume"]
    missing_cols = [col for col in expected_cols if col not in df.columns]
    if missing_cols:
        logger.warning("%s: Fehlende Spalten: %s", ticker, missing_cols)
        return pd.DataFrame()

    df = df[expected_cols].copy()
    df["ticker"] = ticker
    return df


def save_price_df(df):
    """Speichert normalisierte Price-Daten in die DB."""
    if df.empty:
        return

    with engine.begin() as conn:
        df.to_sql(
            "daily_candles",
            conn,
            if_exists="append",
            index=False,
            method=upsert_candles
        )


def ensure_benchmark_ticker_exists():
    """Legt den Benchmark-Ticker in tickers an, damit FK in daily_candles funktioniert."""
    now = datetime.now()

    with engine.begin() as conn:
        stmt = text("""
            INSERT INTO tickers (ticker, name, sector, is_active, first_seen, last_seen, removed_at)
            VALUES (:ticker, :name, :sector, 0, :now, :now, NULL)
            ON DUPLICATE KEY UPDATE
                name = :name,
                sector = :sector,
                last_seen = :now
        """)
        conn.execute(stmt, {
            "ticker": BENCHMARK_TICKER,
            "name": "SPDR S&P 500 ETF Trust",
            "sector": "Benchmark",
            "now": now,
        })


def fetch_and_save_benchmark(mode="daily"):
    """Lädt Benchmark-Preise separat und speichert sie in daily_candles."""
    ensure_benchmark_ticker_exists()

    start_date = datetime.now() - timedelta(days=730)
    end_date = datetime.now()

    try:
        df = yf.download(
            BENCHMARK_TICKER,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False
        )

        normalized_df = normalize_single_ticker_df(df, BENCHMARK_TICKER)
        if not normalized_df.empty:
            save_price_df(normalized_df)
            logger.info("Benchmark %s erfolgreich gespeichert.", BENCHMARK_TICKER)
        else:
            logger.warning("Benchmark %s: keine Daten erhalten.", BENCHMARK_TICKER)

    except Exception as e:
        logger.error("Fehler beim Benchmark-Download %s: %s", BENCHMARK_TICKER, e)


def get_start_date(conn, ticker, mode):
    """Bestimmt Startdatum abhängig vom Modus."""
    now = datetime.now()

    if mode == "init":
        return now - timedelta(days=INIT_HISTORY_DAYS)

    result = conn.execute(
        text("SELECT MAX(date) FROM daily_candles WHERE ticker = :t"),
        {"t": ticker}
    ).scalar()

    if result:
        return result - timedelta(days=DAILY_LOOKBACK_DAYS)

    logger.info("%s: keine Daten vorhanden → fallback %s Tage", ticker, NEW_TICKER_FALLBACK_DAYS)
    return now - timedelta(days=NEW_TICKER_FALLBACK_DAYS)


def fetch_and_save_prices_daily(active_tickers):
    """Daily-Modus: inkrementell pro Ticker."""
    updated_count = 0

    for i, ticker in enumerate(active_tickers, start=1):
        try:
            with engine.connect() as conn:
                start_date = get_start_date(conn, ticker, mode="daily")

            end_date = datetime.now()

            df = yf.download(
                ticker,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False
            )

            normalized_df = normalize_single_ticker_df(df, ticker)
            if not normalized_df.empty:
                save_price_df(normalized_df)
                updated_count += 1

            if i % 100 == 0 or i == len(active_tickers):
                logger.info("Fortschritt DAILY: %s/%s", i, len(active_tickers))

            time.sleep(DAILY_SLEEP_SECONDS)

        except Exception as e:
            logger.error("Fehler bei DAILY Preis-Download für %s: %s", ticker, e)

    return updated_count


def fetch_and_save_prices_init(active_tickers):
    """Init-Modus: Chunk-Download mit mehreren Tickern pro Request."""
    start_date = (datetime.now() - timedelta(days=INIT_HISTORY_DAYS)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    updated_tickers = 0
    total_chunks = (len(active_tickers) + INIT_CHUNK_SIZE - 1) // INIT_CHUNK_SIZE

    for chunk_index, ticker_chunk in enumerate(chunked(active_tickers, INIT_CHUNK_SIZE), start=1):
        ticker_string = " ".join(ticker_chunk)

        try:
            logger.info(
                "INIT Chunk %s/%s: %s Ticker von %s bis %s",
                chunk_index,
                total_chunks,
                len(ticker_chunk),
                ticker_chunk[0],
                ticker_chunk[-1],
            )

            df = yf.download(
                ticker_string,
                start=start_date,
                end=end_date,
                interval="1d",
                progress=False,
                auto_adjust=False,
                group_by="ticker",
                threads=False
            )

            if df.empty:
                logger.warning("INIT Chunk %s: Keine Daten zurückbekommen.", chunk_index)
                time.sleep(INIT_SLEEP_SECONDS)
                continue

            if isinstance(df.columns, pd.MultiIndex):
                for ticker in ticker_chunk:
                    try:
                        if ticker not in df.columns.get_level_values(0):
                            logger.warning("%s: im Chunk nicht geliefert.", ticker)
                            continue

                        ticker_df = df[ticker].copy()
                        normalized_df = normalize_single_ticker_df(ticker_df, ticker)

                        if not normalized_df.empty:
                            save_price_df(normalized_df)
                            updated_tickers += 1

                    except Exception as inner_e:
                        logger.error(
                            "Fehler bei Verarbeitung von %s im INIT-Chunk: %s",
                            ticker,
                            inner_e,
                        )

            else:
                if len(ticker_chunk) == 1:
                    ticker = ticker_chunk[0]
                    normalized_df = normalize_single_ticker_df(df.copy(), ticker)
                    if not normalized_df.empty:
                        save_price_df(normalized_df)
                        updated_tickers += 1
                else:
                    logger.warning(
                        "INIT Chunk %s: Unerwartete Spaltenstruktur ohne MultiIndex bei mehreren Tickern.",
                        chunk_index,
                    )

            logger.info(
                "INIT Fortschritt: Chunk %s/%s abgeschlossen | Ticker mit Daten bisher: %s",
                chunk_index,
                total_chunks,
                updated_tickers,
            )

            time.sleep(INIT_SLEEP_SECONDS)

        except Exception as e:
            logger.error("Fehler bei INIT Chunk %s: %s", chunk_index, e)

    return updated_tickers


def fetch_and_save_prices(mode="daily"):
    """Holt die Kurse für alle aktiven Ticker plus Benchmark."""
    logger.info("Starte Preis-Sync im Modus: %s", mode.upper())

    settings = load_settings()
    logger.info(
        "Verwende Settings: version=%s | benchmark=%s",
        settings.strategy_version,
        BENCHMARK_TICKER,
    )

    start_time = time.time()
    active_tickers = sync_tickers_with_wikipedia()

    if not active_tickers:
        logger.warning("Keine aktiven Ticker gefunden. Abbruch.")
        return

    fetch_and_save_benchmark(mode=mode)

    if mode == "init":
        updated_count = fetch_and_save_prices_init(active_tickers)
    else:
        updated_count = fetch_and_save_prices_daily(active_tickers)

    duration = (time.time() - start_time) / 60
    logger.info("Preis-Sync fertig! Dauer: %.2fmin | Updates: %s", duration, updated_count)


if __name__ == "__main__":
    args = parse_args()
    fetch_and_save_prices(mode=args.mode)
