## Abstufungen: konservativ bis aggressiv

| Stufe                 | Ziel                                       | `portfolio_size` | `max_trades_per_month` | `max_sector_positions` | `min_holding_months` | `max_funding_sell_pct` |
| --------------------- | ------------------------------------------ | ---------------: | ---------------------: | ---------------------: | -------------------: | ---------------------: |
| **Konservativ**       | ruhig, wenig Turnover, stark regelgebunden |                5 |                      2 |                      2 |                    3 |                   0.20 |
| **Mittel / Balanced** | aktiver, aber noch kontrolliert            |                7 |                      4 |                      3 |                    2 |                   0.35 |
| **Aggressiv**         | schnelle Anpassung, mehr Rotation          |               10 |                   5–10 |                    3–4 |                  0–1 |              0.50–0.80 |

Für unseren Test haben wir **Mittel / Balanced** genommen.

---

## Rebuild-Befehl für „Mittel“

```bash
./setup.sh rebuild \
  --start-capital 10000 \
  --portfolio-size 7 \
  --max-trades-per-month 4 \
  --max-sector-positions 3 \
  --min-holding-months 2 \
  --max-funding-sell-pct 0.35
```

Falls dein Setup das Root-Passwort nicht aus `.env` liest:

```bash
./setup.sh rebuild \
  --start-capital 10000 \
  --portfolio-size 7 \
  --max-trades-per-month 4 \
  --max-sector-positions 3 \
  --min-holding-months 2 \
  --max-funding-sell-pct 0.35 \
  --mysql-root-password <pw>
```

---

## Käufe mit Dry-Run

Wir haben **NEM** und **ALL** weggelassen und stattdessen **EXPD, FSLR, EOG** ergänzt.

```bash
docker compose run --rm app python -m core.apply_trade_execution --as-of-date 2026-05-14 --ticker INCY --execution-type BUY --shares 12 --price 99.37 --fee 1.00 --dry-run

docker compose run --rm app python -m core.apply_trade_execution --as-of-date 2026-05-14 --ticker APA --execution-type BUY --shares 34 --price 36.62 --fee 1.00 --dry-run

docker compose run --rm app python -m core.apply_trade_execution --as-of-date 2026-05-14 --ticker CF --execution-type BUY --shares 9 --price 126.15 --fee 1.00 --dry-run

docker compose run --rm app python -m core.apply_trade_execution --as-of-date 2026-05-14 --ticker DVN --execution-type BUY --shares 26 --price 46.42 --fee 1.00 --dry-run

docker compose run --rm app python -m core.apply_trade_execution --as-of-date 2026-05-14 --ticker HST --execution-type BUY --shares 57 --price 21.74 --fee 1.00 --dry-run

docker compose run --rm app python -m core.apply_trade_execution --as-of-date 2026-05-14 --ticker EXPD --execution-type BUY --shares 8 --price 154.65 --fee 1.00 --dry-run

docker compose run --rm app python -m core.apply_trade_execution --as-of-date 2026-05-14 --ticker FSLR --execution-type BUY --shares 5 --price 237.40 --fee 1.00 --dry-run

docker compose run --rm app python -m core.apply_trade_execution --as-of-date 2026-05-14 --ticker EOG --execution-type BUY --shares 9 --price 133.55 --fee 1.00 --dry-run
```

Gesamter geplanter Cash-Bedarf inkl. Gebühren: **9.653,12**. Erwarteter Rest-Cash: **346,88**.

