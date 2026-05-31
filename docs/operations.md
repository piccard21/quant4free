# Operations Guide

Stand: AP17.

Der regulaere Betrieb nutzt nur noch die modularen CLIs und das kanonische
Schema aus `init.sql`. Legacy-CLIs sind kein Operator-Standardpfad mehr.

## Day-to-day Einstieg

Dieses Kapitel ist der kuerzeste Einstieg fuer den regulaeren Betrieb.

Merkkarte:

- `Status = jetzt`
- `Performance = Verlauf`
- `Monthly = offizieller Rebalance-Stand`

Die operative Pipeline ist:

```text
neue Marktdaten holen
-> taeglichen Strategie-Stand berechnen
-> monatlich neue Zielportfolios und Trade-Plan erzeugen
-> Ist-Zustand gegen Shadow/Model pruefen
-> Kaeufe/Verkaeufe manuell buchen
-> Real Portfolio gegen Shadow und Benchmark vergleichen
```

Die drei Portfolio-Sichten sind:

- `Model`: das reine Strategie-Ergebnis fuer den Stichtag.
- `Shadow`: das tradierbare Zielportfolio nach Halte- und Trade-Regeln.
- `Real`: das tatsaechlich manuell gebuchte Portfolio.

Fuer den Alltag sind diese Befehle die wichtigsten:

- `python -m cli.daily_run`
  Holt neue Daten und berechnet den aktuellen Strategie-Stand fuer den Tag.
- `python -m cli.monthly_run --persist`
  Friert zum Monatslauf Model, Shadow, Rebalance, Decisions und Trade-Plan ein.
- `python -m cli.live_status --all --limit 10`
  Zeigt, wo Real gegen Shadow/Model abweicht.
- `python -m cli.live_performance --curve-limit 5`
  Zeigt Real vs. Shadow vs. Benchmark ueber die Zeit.
- `python -m cli.live_cash --type deposit|withdrawal ...`
  Bucht Ein- oder Auszahlungen.
- `python -m cli.live_trade ...`
  Bucht einen manuellen Kauf oder Verkauf.

Wenn nur ein schneller Tagesablauf noetig ist, ist die Reihenfolge meist:

1. `python -m cli.daily_run`
2. `python -m cli.live_status --limit 10`
3. Falls Monatsanfang oder Rebalance-Tag: `python -m cli.monthly_run --persist`
4. Danach geplante Trades mit `python -m cli.live_trade ...` buchen
5. Zum Schluss `python -m cli.live_performance --curve-limit 5`

## Was Daily Und Monthly Machen

`daily_run` ist der Tageslauf:

- aktualisiert Rohdaten ueber den modularen Sync
- berechnet Indikatoren neu
- laesst die Strategie gegen den neuesten Handelstag laufen
- zeigt das aktuelle Model Portfolio
- ist der passende manuelle Befehl, wenn man denselben Ablauf wie den Daily-Cron starten will

`monthly_run` ist der Monatslauf:

- nutzt den neuesten verfuegbaren Handelstag oder `--as-of-date`
- erzeugt das Model Portfolio fuer den Monatsstichtag
- erzeugt das tradierbare Shadow Portfolio
- erzeugt Rebalance- und Decision-Artefakte
- erzeugt den Trade-Plan fuer manuelle Ausfuehrung
- schreibt diese Artefakte nur mit `--persist` dauerhaft in die Datenbank

Merksatz:

- `daily_run` beantwortet: "Wie sieht die Strategie heute aus?"
- `monthly_run --persist` beantwortet: "Was ist mein offizieller Monatsstand und was soll ich handeln?"

## Wichtigste Befehle

### Daten holen

Regulaerer Tagesbefehl:

```bash
docker compose run --rm app python -m cli.daily_run
```

Nur pruefen, was synchronisiert wuerde:

```bash
docker compose run --rm app python -m cli.daily_run --dry-run-sync --model-limit 5
docker compose run --rm app python -m cli.sync_data --dry-run
```

Gezielt nur Preise oder Fundamentals pruefen:

```bash
docker compose run --rm app python -m cli.sync_prices --dry-run --plan-limit 5
docker compose run --rm app python -m cli.sync_fundamentals --dry-run --plan-limit 5
```

### Aktuellen Stand sehen

Kurzstatus der Portfolios:

```bash
docker compose run --rm app python -m cli.live_status --limit 10
```

Voller Status inklusive ausgerichteter Zeilen:

```bash
docker compose run --rm app python -m cli.live_status --all --limit 10
```

Portfolio gegen Markt vergleichen:

```bash
docker compose run --rm app python -m cli.live_performance --curve-limit 5
```

Wenn nur ein kompakter Systemcheck noetig ist:

```bash
docker compose run --rm app python -m cli.operator_smoke --ranking-limit 5 --trade-limit 5
```

### Monatsstand erzeugen

Nur ansehen, noch nichts schreiben:

```bash
docker compose run --rm app python -m cli.monthly_run --model-limit 7
```

Offiziellen Monatsstand mit Trade-Plan schreiben:

```bash
docker compose run --rm app python -m cli.monthly_run --persist --model-limit 7
```

### Kauf, Verkauf, Cash

Cash einzahlen:

```bash
docker compose run --rm app python -m cli.live_cash --type deposit --amount 1000 --as-of-date 2026-05-22
```

Cash-Abgang als Test:

```bash
docker compose run --rm app python -m cli.live_cash --type withdrawal --amount 250 --as-of-date 2026-05-22 --dry-run
```

Kauf oder Verkauf manuell buchen:

```bash
docker compose run --rm app python -m cli.live_trade --help
```

Der normale Weg ist:

1. `monthly_run --persist` erzeugt den Trade-Plan
2. `live_status` zeigt die Luecken zwischen Shadow und Real
3. `live_trade` bucht die manuelle Umsetzung
4. `live_performance` zeigt danach den Vergleich gegen Shadow und Benchmark

## Status-System

`cli.live_status` ist der schnellste Befehl fuer den operativen Ist-Zustand.

Er zeigt:

- wie viele Positionen in `Model`, `Shadow` und `Real` liegen
- wie viel Cash im Real Portfolio vorhanden ist
- investierten und gesamten Portfoliowert
- welche Titel im Real Portfolio fehlen, zusaetzlich vorhanden sind oder vom Shadow abweichen

Praktische Kurzform:

```bash
docker compose run --rm app python -m cli.live_status --limit 10
```

Wenn nur die Problemstellen wichtig sind, reicht diese Kurzform meist aus.

## Setup

Frische Datenbank mit kanonischem Schema:

```bash
./setup.sh init --start-capital 10000 --load-fixture
```

`setup.sh init` loescht das Docker-DB-Volume und initialisiert MySQL neu. Das
ist der regulaere Weg, wenn sich `MYSQL_ROOT_PASSWORD` in `.env` geaendert hat
und das neue Passwort auch in der laufenden Datenbank aktiv werden soll.

Ohne Fixture werden nur Schema, Default-Strategie und Cash angelegt:

```bash
./setup.sh init --start-capital 10000
```

Live-/Operational-State zuruecksetzen, Rohdaten behalten:

```bash
./setup.sh rebuild --start-capital 10000
```

`setup.sh rebuild` setzt kein MySQL-Root-Passwort zurueck und baut die
Datenbank nicht neu auf.

## Status Und Smoke

Automatisierter Entwicklungscheck:

```bash
scripts/dev_check.sh
```

Der schnelle Default laeuft im Docker-App-Container und prueft `compileall`
sowie die schnelle Pytest-Suite ohne DB-Integration. Die DB-Integrationstests
laufen gegen den isolierten Compose-Service `db_test`:

```bash
scripts/db_integration_tests.sh
```

Der Runner verwendet standardmaessig `quant4free_test` auf `db_test`, laedt
Fixture und Schema pro Testsession neu und loescht nur diese Testdatenbank.
Die normale Entwicklungsdatenbank `db` wird nicht beruehrt.

Der isolierte End-to-End-Smoke nutzt ebenfalls eine eigene Testdatenbank:

```bash
scripts/dev_check.sh --smoke
```

Echte Smoke-Trade-Buchungen nur in der isolierten Testdatenbank:

```bash
scripts/dev_check.sh --smoke --execute-smoke-trades
```

```bash
docker compose run --rm app python -m cli.data_status --details
docker compose run --rm app python -m cli.operator_smoke --ranking-limit 5 --trade-limit 5
docker compose run --rm app python -m cli.live_status --all --limit 10
docker compose run --rm app python -m cli.live_performance --curve-limit 5
```

`cli.operator_smoke` prueft DB-Ping, kanonische Rohdatentabellen, Universum,
Benchmark, AP20-Capability-/Provider-Bindings, Strategie-Ranking und
Benchmark-Backtest.

Mit der AP15-Fixture und den Default-Parametern aus der README sind im
Live-Status als Fixture-Beispiel diese fehlenden Real-Positionen bzw.
Kaufkandidaten zu erwarten:

```text
APA
CB
CF
INCY
NEM
TRV
```

Diese Liste ist nur ein reproduzierbares Testsignal fuer die Fixture. Sie ist
keine aktuelle Anlageempfehlung und kann sich mit anderer Fixture, anderem
Stichtag oder anderen Strategieparametern aendern.

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

## Performance

AP16 stellt den operativen Performance-Report als read-only CLI bereit:

```bash
docker compose run --rm app python -m cli.live_performance --curve-limit 10
```

Der Report vergleicht Real Portfolio, Shadow Portfolio und Benchmark. Der
Benchmark wird ueber `--benchmark` gewaehlt und ist standardmaessig `spy`. Wenn
kein Zeitraum angegeben wird, endet der Report am letzten verfuegbaren
Benchmark-Preis und startet 365 Tage davor:

```bash
docker compose run --rm app python -m cli.live_performance --benchmark spy --start-date 2026-01-02 --end-date 2026-05-22
```

Real wird aus `live_positions`, `live_cash_balances` und historischen
`asset_price_bars` bewertet. Shadow wird als target-weight Portfolio aus den
persistierten `portfolio_target_items` mit `snapshot_type='shadow'`
fortgeschrieben. Der Benchmark wird auf denselben Startwert normalisiert. Die
Option `--base-value` setzt optional die gemeinsame Normierungsbasis aller
Wertreihen. Die CLI gibt Rendite, Benchmark-Rendite, Outperformance,
Max Drawdown, Diagnosezaehler und den Tail der Wertreihe aus.

## Operator Shortcuts

Wer die langen Docker-Befehle nicht jedes Mal tippen will, kann sich lokal
diese Shell-Shortcuts setzen:

```bash
alias qrun='docker compose run --rm app python -m'
alias qdaily='docker compose run --rm app python -m cli.daily_run'
alias qmonth='docker compose run --rm app python -m cli.monthly_run'
alias qstatus='docker compose run --rm app python -m cli.live_status --limit 10'
alias qperf='docker compose run --rm app python -m cli.live_performance --curve-limit 5'
```

Dann werden die wichtigsten Alltagsbefehle kurz:

```bash
qdaily
qstatus
qmonth --persist --model-limit 7
qperf
qrun cli.live_cash --type deposit --amount 1000 --as-of-date 2026-05-22
```

## Best Practices

- Vor manuellen Trades immer zuerst `cli.monthly_run --persist` und danach `cli.live_status` laufen lassen.
- `cli.live_trade` moeglichst mit Werten aus `live_trade_plan_items` fuettern statt freie Zahlen zu raten.
- Nach Cash-Buchungen oder Trades den Ist-Zustand direkt mit `cli.live_status --limit 10` pruefen.
- Fuer den Marktvergleich `cli.live_performance` als Abschlussbefehl verwenden.
- Fuer den regulaeren Betrieb dieselben Befehle wie im Cronpfad nutzen, damit manueller Lauf und Scheduler nicht auseinanderlaufen.

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

Der folgende Bash-Block liest automatisch die erste ausfuehrbare BUY-Zeile aus
`live_trade_plan_items` und speichert `as_of_date`, `ticker`, `planned_shares`,
`estimated_price` und `fee` in Shell-Variablen. Diese Variablen werden danach
im `cli.live_trade --dry-run` verwendet.

```bash
read -r TRADE_AS_OF_DATE TRADE_TICKER TRADE_SHARES TRADE_PRICE TRADE_FEE < <(
  docker compose exec -T db sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -B -N -e "
    SELECT as_of_date, ticker, planned_shares, estimated_price, fee
    FROM live_trade_plan_items
    WHERE action = '\''BUY'\'' AND is_executable = 1
    ORDER BY as_of_date DESC, execution_order, ticker
    LIMIT 1;
  "'
)

docker compose run --rm app python -m cli.live_trade \
  --execution-type BUY \
  --ticker "${TRADE_TICKER}" \
  --shares "${TRADE_SHARES}" \
  --price "${TRADE_PRICE}" \
  --fee "${TRADE_FEE}" \
  --as-of-date "${TRADE_AS_OF_DATE}" \
  --trade-plan-action BUY \
  --dry-run
```

Die Werte fuer `shares`, `price`, `fee` und `as-of-date` aus dem persistierten
Trade-Plan nehmen:

```sql
SELECT as_of_date, execution_order, action, ticker, planned_shares, estimated_price, fee, is_executable
FROM live_trade_plan_items
WHERE action = 'BUY'
ORDER BY as_of_date DESC, execution_order, ticker;
```

SELL erfassen, wenn vorher eine reale Position gebucht wurde:

```bash
docker compose run --rm app python -m cli.live_trade --execution-type SELL --ticker "${TRADE_TICKER}" --shares 1 --price 200 --fee 1 --as-of-date "${TRADE_AS_OF_DATE}"
```

## Canonical Tables

Rohdaten:

- `assets`
- `asset_provider_identifiers`
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
