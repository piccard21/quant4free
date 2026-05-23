import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import create_engine, text


# --------------------------------------------------
# ZENTRALE DB-KONFIGURATION
# --------------------------------------------------
# Alle Skripte verwenden dieselbe Verbindung aus dieser Datei.
# Änderungen an Host/User/Passwort/DB-Namen müssen nur hier
# bzw. über die Environment-Variablen erfolgen.

DB_HOST = os.getenv("DB_HOST", "db")
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASSWORD", "password123")
DB_NAME = os.getenv("DB_NAME", "stocks_db")

DATABASE_URL = f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

engine = create_engine(DATABASE_URL)


# --------------------------------------------------
# ZENTRALE SYSTEMKONSTANTEN
# --------------------------------------------------
# Diese Werte sind bewusst NICHT in strategy_settings gespeichert,
# weil sie keine fachlichen Strategie-Regeln darstellen, sondern
# technische Defaults / Hilfsparameter für die Pipeline.

BENCHMARK_TICKER = "SPY"

# Preis-/Momentum-Helfer
RETURN_6M_LOOKBACK_DAYS = 126

# Preis-Sync (technische Laufzeitparameter)
INIT_HISTORY_DAYS = 548
DAILY_LOOKBACK_DAYS = 3
NEW_TICKER_FALLBACK_DAYS = 180
INIT_CHUNK_SIZE = 50
INIT_SLEEP_SECONDS = 2
DAILY_SLEEP_SECONDS = 0.05


# --------------------------------------------------
# SETTINGS MODELL
# --------------------------------------------------

@dataclass(frozen=True)
class StrategySettings:
    strategy_version: str

    value_weight: float
    quality_weight: float
    momentum_weight: float

    momentum_return_weight: float
    momentum_rel_strength_weight: float

    min_price: float
    min_market_cap: int

    sma_days: int
    return_lookback_days: int

    buy_rank_threshold: int
    sell_rank_threshold: int

    portfolio_size: int
    max_sector_positions: int

    min_holding_months: int
    max_trades_per_month: int

    daily_fundamental_limit: int
    fundamental_refresh_hours: int

    tax_rate: float

    # Variante C: begrenzt Funding-Sells beim Aufbau zusätzlicher Positionen.
    # Beispiel 0.20 = pro bestehender Position dürfen max. 20% des Positionswerts
    # als ADJUST_SELL verkauft werden, um neue BUYs zu finanzieren.
    max_funding_sell_pct: float


# --------------------------------------------------
# VALIDIERUNG
# --------------------------------------------------

def validate_settings(settings: StrategySettings) -> None:
    total_weight = (
        settings.value_weight
        + settings.quality_weight
        + settings.momentum_weight
    )

    if round(total_weight, 5) != 1.0:
        raise ValueError(
            f"Faktor-Gewichte müssen 1.0 ergeben, aktuell: {total_weight}"
        )

    momentum_sub_weight_total = (
        settings.momentum_return_weight
        + settings.momentum_rel_strength_weight
    )

    if round(momentum_sub_weight_total, 5) != 1.0:
        raise ValueError(
            "Momentum-Untergewichte müssen 1.0 ergeben, aktuell: "
            f"{momentum_sub_weight_total}"
        )

    if settings.momentum_return_weight < 0 or settings.momentum_rel_strength_weight < 0:
        raise ValueError("Momentum-Untergewichte dürfen nicht negativ sein")

    if settings.buy_rank_threshold >= settings.sell_rank_threshold:
        raise ValueError(
            "buy_rank_threshold muss kleiner sein als sell_rank_threshold"
        )

    if settings.portfolio_size <= 0:
        raise ValueError("portfolio_size muss > 0 sein")

    if settings.max_sector_positions <= 0:
        raise ValueError("max_sector_positions muss > 0 sein")

    if settings.sma_days <= 0:
        raise ValueError("sma_days muss > 0 sein")

    if settings.return_lookback_days <= 0:
        raise ValueError("return_lookback_days muss > 0 sein")

    if settings.min_price <= 0:
        raise ValueError("min_price muss > 0 sein")

    if settings.min_market_cap <= 0:
        raise ValueError("min_market_cap muss > 0 sein")

    if settings.min_holding_months < 0:
        raise ValueError("min_holding_months darf nicht negativ sein")

    if settings.max_trades_per_month <= 0:
        raise ValueError("max_trades_per_month muss > 0 sein")

    if settings.daily_fundamental_limit <= 0:
        raise ValueError("daily_fundamental_limit muss > 0 sein")

    if settings.fundamental_refresh_hours <= 0:
        raise ValueError("fundamental_refresh_hours muss > 0 sein")

    if settings.tax_rate < 0 or settings.tax_rate > 1:
        raise ValueError("tax_rate muss zwischen 0 und 1 liegen")

    if settings.max_funding_sell_pct < 0 or settings.max_funding_sell_pct > 1:
        raise ValueError("max_funding_sell_pct muss zwischen 0 und 1 liegen")


# --------------------------------------------------
# LOAD
# --------------------------------------------------

def load_settings() -> StrategySettings:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
                strategy_version,
                value_weight,
                quality_weight,
                momentum_weight,
                momentum_return_weight,
                momentum_rel_strength_weight,
                min_price,
                min_market_cap,
                sma_days,
                return_lookback_days,
                buy_rank_threshold,
                sell_rank_threshold,
                portfolio_size,
                max_sector_positions,
                min_holding_months,
                max_trades_per_month,
                daily_fundamental_limit,
                fundamental_refresh_hours,
                tax_rate,
                max_funding_sell_pct
            FROM strategy_settings
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
        """)).mappings().first()

    if row is None:
        raise ValueError("Keine aktive Konfiguration in strategy_settings gefunden.")

    settings = StrategySettings(
        strategy_version=str(row["strategy_version"]),
        value_weight=float(row["value_weight"]),
        quality_weight=float(row["quality_weight"]),
        momentum_weight=float(row["momentum_weight"]),
        momentum_return_weight=float(row["momentum_return_weight"]),
        momentum_rel_strength_weight=float(row["momentum_rel_strength_weight"]),
        min_price=float(row["min_price"]),
        min_market_cap=int(row["min_market_cap"]),
        sma_days=int(row["sma_days"]),
        return_lookback_days=int(row["return_lookback_days"]),
        buy_rank_threshold=int(row["buy_rank_threshold"]),
        sell_rank_threshold=int(row["sell_rank_threshold"]),
        portfolio_size=int(row["portfolio_size"]),
        max_sector_positions=int(row["max_sector_positions"]),
        min_holding_months=int(row["min_holding_months"]),
        max_trades_per_month=int(row["max_trades_per_month"]),
        daily_fundamental_limit=int(row["daily_fundamental_limit"]),
        fundamental_refresh_hours=int(row["fundamental_refresh_hours"]),
        tax_rate=float(row["tax_rate"]),
        max_funding_sell_pct=float(row.get("max_funding_sell_pct", 0.20)),
    )

    validate_settings(settings)
    return settings


# --------------------------------------------------
# SNAPSHOT
# --------------------------------------------------

def find_existing_snapshot_tables(as_of_date) -> list[str]:
    """Prüft, ob für einen Stichtag bereits eingefrorene Rebalance-Snapshots existieren."""
    tables_to_check = [
        "strategy_settings_snapshots",
        "rebalance_suggestions",
        "decision_log",
    ]

    existing_tables = []

    with engine.connect() as conn:
        for table_name in tables_to_check:
            query = text(f"SELECT 1 FROM {table_name} WHERE as_of_date = :as_of_date LIMIT 1")
            exists = conn.execute(query, {"as_of_date": as_of_date}).scalar()
            if exists is not None:
                existing_tables.append(table_name)

    return existing_tables



def save_settings_snapshot(as_of_date, settings: StrategySettings, conn=None) -> None:
    """
    Friert die aktuell verwendeten Settings für einen Stichtag ein.
    Bestehende Snapshots für denselben Stichtag dürfen NICHT überschrieben werden.
    """
    insert_sql = text("""
        INSERT INTO strategy_settings_snapshots (
            as_of_date,
            strategy_version,
            value_weight,
            quality_weight,
            momentum_weight,
            momentum_return_weight,
            momentum_rel_strength_weight,
            min_price,
            min_market_cap,
            sma_days,
            return_lookback_days,
            buy_rank_threshold,
            sell_rank_threshold,
            portfolio_size,
            max_sector_positions,
            min_holding_months,
            max_trades_per_month,
            daily_fundamental_limit,
            fundamental_refresh_hours,
            tax_rate,
            max_funding_sell_pct,
            created_at
        ) VALUES (
            :as_of_date,
            :strategy_version,
            :value_weight,
            :quality_weight,
            :momentum_weight,
            :momentum_return_weight,
            :momentum_rel_strength_weight,
            :min_price,
            :min_market_cap,
            :sma_days,
            :return_lookback_days,
            :buy_rank_threshold,
            :sell_rank_threshold,
            :portfolio_size,
            :max_sector_positions,
            :min_holding_months,
            :max_trades_per_month,
            :daily_fundamental_limit,
            :fundamental_refresh_hours,
            :tax_rate,
            :max_funding_sell_pct,
            :created_at
        )
    """)

    payload = {
        "as_of_date": as_of_date,
        "strategy_version": settings.strategy_version,
        "value_weight": settings.value_weight,
        "quality_weight": settings.quality_weight,
        "momentum_weight": settings.momentum_weight,
        "momentum_return_weight": settings.momentum_return_weight,
        "momentum_rel_strength_weight": settings.momentum_rel_strength_weight,
        "min_price": settings.min_price,
        "min_market_cap": settings.min_market_cap,
        "sma_days": settings.sma_days,
        "return_lookback_days": settings.return_lookback_days,
        "buy_rank_threshold": settings.buy_rank_threshold,
        "sell_rank_threshold": settings.sell_rank_threshold,
        "portfolio_size": settings.portfolio_size,
        "max_sector_positions": settings.max_sector_positions,
        "min_holding_months": settings.min_holding_months,
        "max_trades_per_month": settings.max_trades_per_month,
        "daily_fundamental_limit": settings.daily_fundamental_limit,
        "fundamental_refresh_hours": settings.fundamental_refresh_hours,
        "tax_rate": settings.tax_rate,
        "max_funding_sell_pct": settings.max_funding_sell_pct,
        "created_at": datetime.now(),
    }

    if conn is not None:
        conn.execute(insert_sql, payload)
        return

    with engine.begin() as managed_conn:
        managed_conn.execute(insert_sql, payload)


