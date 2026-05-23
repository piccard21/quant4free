# cli/show_top_sector.py

import argparse
import pandas as pd
from sqlalchemy import text

from shared.settings import engine


def parse_args():
    parser = argparse.ArgumentParser(
        description="Zeigt die Top-Aktien je Sektor nach final_rank."
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--sector", default=None)
    parser.add_argument("--as-of-date", default=None)
    return parser.parse_args()


def resolve_as_of_date(cli_date):
    if cli_date:
        return cli_date

    with engine.connect() as conn:
        return conn.execute(
            text("SELECT MAX(as_of_date) FROM factor_scores")
        ).scalar()


def load_top_sector(as_of_date, limit, sector=None):
    sector_filter = ""
    params = {"as_of_date": as_of_date, "limit": limit}

    if sector:
        sector_filter = "AND sector = :sector"
        params["sector"] = sector

    sql = text(f"""
        WITH ranked AS (
            SELECT
                as_of_date,
                sector,
                ticker,
                final_rank,
                final_score,
                value_score,
                quality_score,
                momentum_score,
                trend_positive,
                buy_eligible,
                ROW_NUMBER() OVER (
                    PARTITION BY sector
                    ORDER BY final_rank ASC
                ) AS sector_pos
            FROM factor_scores
            WHERE as_of_date = :as_of_date
              {sector_filter}
        )
        SELECT
            sector,
            sector_pos,
            ticker,
            final_rank,
            ROUND(final_score, 2) AS final_score,
            ROUND(value_score, 2) AS value_score,
            ROUND(quality_score, 2) AS quality_score,
            ROUND(momentum_score, 2) AS momentum_score,
            trend_positive,
            buy_eligible
        FROM ranked
        WHERE sector_pos <= :limit
        ORDER BY sector, sector_pos
    """)

    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params=params)


def main():
    args = parse_args()
    as_of_date = resolve_as_of_date(args.as_of_date)

    if as_of_date is None:
        raise ValueError("Keine factor_scores vorhanden.")

    df = load_top_sector(
        as_of_date=as_of_date,
        limit=args.limit,
        sector=args.sector,
    )

    print()
    print("=" * 88)
    print(f"TOP {args.limit} JE SEKTOR | STICHTAG {as_of_date}")
    print("=" * 88)

    if df.empty:
        print("Keine Daten gefunden.")
        return

    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
