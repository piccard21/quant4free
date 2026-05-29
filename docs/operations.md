# Operations Guide

Stand: AP15.

Der regulaere Betrieb nutzt nur noch die modularen CLIs und das kanonische
Schema aus `init.sql`. Legacy-CLIs sind kein Operator-Standardpfad mehr.

## Setup

Frische Datenbank mit kanonischem Schema:

```bash
./setup.sh init --start-capital 10000 --load-fixture
```

Ohne Fixture werden nur Schema, Default-Strategie und Cash angelegt:

```bash
./setup.sh init --start-capital 10000
```

Live-/Operational-State zuruecksetzen, Rohdaten behalten:

```bash
./setup.sh rebuild --start-capital 10000
```

## Status Und Smoke

```bash
docker compose run --rm app python -m cli.data_status --details
docker compose run --rm app python -m cli.operator_smoke --ranking-limit 5 --trade-limit 5
docker compose run --rm app python -m cli.live_status --all --limit 10
```

`cli.operator_smoke` prueft DB-Ping, kanonische Rohdatentabellen, Universum,
Benchmark, Strategie-Ranking und Benchmark-Backtest.

Frischer Client-Smoke gegen eine isolierte Testdatenbank:

```bash
scripts/client_smoke.sh --db-name ap15_client_smoke --mysql-root-password mypassword
```

Der Smoke legt nur die angegebene Testdatenbank neu an, laedt
`fixtures/raw_market_data.sql`, wendet `init.sql` an, setzt Startkapital und
Strategieparameter, laeuft `cli.operator_smoke`, persistiert
`cli.monthly_run --persist`, prueft `cli.live_status`, validiert Cash- und
Trade-Dry-Runs und bucht standardmaessig die erzeugten BUYs in dieser
isolierten Testdatenbank.

Ohne echte Trade-Buchungen:

```bash
scripts/client_smoke.sh --db-name ap15_client_smoke --skip-trade-execution
```

## Host Crontab

Der regulaere Cronpfad nutzt ausschliesslich die modularen CLIs. Legacy-CLIs
werden nicht als Cron-Fallback dokumentiert.

Log- und Lock-Verzeichnisse anlegen:

```bash
mkdir -p var/log var/lock
```

Daily-Run manuell mit Lock und Log testen:

```bash
flock -n var/lock/daily_run.lock scripts/cron_daily.sh >> var/log/daily_run.log 2>&1
```

Monthly-Run manuell mit Lock und Log testen:

```bash
flock -n var/lock/monthly_run.lock scripts/cron_monthly.sh >> var/log/monthly_run.log 2>&1
```

Parallelausfuehrung pruefen:

```bash
flock -n var/lock/daily_run.lock sleep 60 &
flock -n var/lock/daily_run.lock scripts/cron_daily.sh >> var/log/daily_run.log 2>&1
```

Der zweite Befehl muss sofort abbrechen, solange der erste Lock haelt.

Beispiel fuer `crontab -e` auf dem Host:

```cron
# Werktags nach US-Marktschluss, lokale Host-Zeitzone.
15 23 * * 1-5 cd /home/piccard/tmp/quant4free && mkdir -p var/log var/lock && flock -n var/lock/daily_run.lock scripts/cron_daily.sh >> var/log/daily_run.log 2>&1

# Monatlicher persistierter Rebalance-Lauf am zweiten Kalendertag.
30 8 2 * * cd /home/piccard/tmp/quant4free && mkdir -p var/log var/lock && flock -n var/lock/monthly_run.lock scripts/cron_monthly.sh >> var/log/monthly_run.log 2>&1
```

Die Skripte schreiben Start, Ende und Fehlerzeile in stdout/stderr; die
Crontab leitet beides in feste Logdateien um. Logs pruefen:

```bash
tail -n 100 var/log/daily_run.log
tail -n 100 var/log/monthly_run.log
```

## Daily Operations

Dry-Run ohne externe API-Calls:

```bash
docker compose run --rm app python -m cli.daily_run --dry-run-sync --model-limit 5
```

Regulaerer Daily-Run:

```bash
docker compose run --rm app python -m cli.daily_run
```

Gezielte Sync-Pruefung:

```bash
docker compose run --rm app python -m cli.sync_prices --dry-run --plan-limit 5
docker compose run --rm app python -m cli.sync_fundamentals --dry-run --plan-limit 5
docker compose run --rm app python -m cli.sync_data --dry-run
```

## Monthly Operations

Read-only Monthly-Run:

```bash
docker compose run --rm app python -m cli.monthly_run --model-limit 7
```

Persistierter Monthly-Run fuer Model, Shadow, Rebalance, Decision Items und
Trade Plan:

```bash
docker compose run --rm app python -m cli.monthly_run --persist --model-limit 7
```

Expliziter Stichtag:

```bash
docker compose run --rm app python -m cli.monthly_run --as-of-date 2026-05-22 --persist
```

Persistenz bricht kontrolliert ab, wenn fuer den Stichtag bereits eingefrorene
Artefakte existieren.

## Cash Movements

```bash
docker compose run --rm app python -m cli.live_cash --type deposit --amount 1000 --as-of-date 2026-05-22
docker compose run --rm app python -m cli.live_cash --type withdrawal --amount 250 --as-of-date 2026-05-22 --dry-run
```

Cash wird in `live_cash_ledger` gebucht und in `live_cash_balances`
fortgeschrieben.

## Trade Execution

BUY dry-run:

```bash
docker compose run --rm app python -m cli.live_trade --execution-type BUY --ticker AAPL --shares 1 --price 190 --fee 1 --as-of-date 2026-05-22 --dry-run
```

SELL erfassen:

```bash
docker compose run --rm app python -m cli.live_trade --execution-type SELL --ticker AAPL --shares 1 --price 200 --fee 1 --as-of-date 2026-05-22
```

Trade-Plan-Bezug validieren:

```bash
docker compose run --rm app python -m cli.live_trade --execution-type BUY --ticker AAPL --shares 1 --price 190 --fee 1 --as-of-date 2026-05-22 --trade-plan-action BUY --dry-run
```

## Canonical Tables

Rohdaten:

- `assets`
- `asset_price_bars`
- `asset_fundamental_reports`
- `asset_market_caps`

Live/Operations:

- `strategy_instances`
- `strategy_config_snapshots`
- `portfolio_target_items`
- `live_rebalance_items`
- `live_decision_items`
- `live_trade_plans`
- `live_trade_plan_items`
- `live_trade_executions`
- `live_cash_ledger`
- `live_cash_balances`
- `live_positions`

## Fehlerdiagnose

Bei fehlenden Rohdaten:

```bash
docker compose exec -T db sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < fixtures/raw_market_data.sql
docker compose exec -T db sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < init.sql
```

Danach erneut:

```bash
docker compose run --rm app python -m cli.data_status --details
docker compose run --rm app python -m cli.operator_smoke
```
