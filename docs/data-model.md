# Datenmodell-Plan

Stand: AP3 abgeschlossen.

Dieses Dokument beschreibt den Zielzustand des neuen modularen Quant-Frameworks. Es ist noch keine Migration des produktiven Legacy-Schemas. `init.sql` bleibt vorerst kompatibel zum eingefrorenen Legacy-System. Die bereinigte Framework-Fixture liegt in `fixtures/raw_market_data.sql`.

## Leitlinien

- Rohdaten bleiben dauerhaft gespeichert und werden nicht aus Strategie-Runs abgeleitet.
- Fachliche Konfiguration wird versioniert gespeichert, nicht in `.env`.
- Evaluation und Live-Betrieb werden getrennt modelliert.
- Billig reproduzierbare Zwischenwerte werden nicht dauerhaft gespeichert.
- Audit-relevante Entscheidungen, Trades, Cash-Bewegungen und Run-Konfigurationen werden eingefroren.
- Die erste Umsetzung bleibt auf MySQL und SQLAlchemy-nahe SQL-Zugriffe ausgerichtet.

## Aktueller Legacy-Bestand

`init.sql` beschreibt den legacy-kompatiblen Gesamtbestand. Der entfernte
Full-Dump `stocks_db.sql` enthielt dieselben 18 Tabellen und wurde durch die
bereinigte Rohdaten-Fixture `fixtures/raw_market_data.sql` ersetzt:

| Bereich | Tabellen | Bewertung |
|---|---|---|
| Rohdaten | `tickers`, `daily_candles`, `financial_reports`, `market_cap_snapshots` | Bleiben Kernbestand des neuen Systems. |
| Berechnete Faktoren | `factor_metrics`, `factor_scores` | Im neuen System zunaechst reproduzierbar berechnen; Speicherung nur optional fuer Run-Audit oder Performance. |
| Legacy-Settings | `strategy_settings`, `strategy_settings_snapshots` | Wird durch versionierte `strategy_instances` ersetzt. Legacy bleibt bis zur Migration erhalten. |
| Legacy-Model/Shadow | `portfolio_snapshots`, `rebalance_suggestions`, `decision_log`, `trade_plan_summary`, `trade_plan_snapshots` | Wird in Evaluation-Run-Tabellen und Live-Entscheidungstabellen aufgeteilt. |
| Real Portfolio | `portfolio_positions`, `portfolio_cash`, `trade_executions`, `cash_ledger` | Bleibt fachlich wichtig, wird spaeter portfolio- und tenant-faehig erweitert. |
| Research | `performance_snapshots` | Wird durch kompakte Run-Metriken und Equity-Curves ersetzt. |

## Zielbereiche

### 1. Stammdaten und Rohdaten

Bestehende Tabellen:

```text
tickers
daily_candles
financial_reports
market_cap_snapshots
```

Diese Tabellen bleiben die erste Datenbasis. Sie werden spaeter nur vorsichtig erweitert, z. B. um Provider-Metadaten, ohne die Fixture-Nutzbarkeit von `fixtures/raw_market_data.sql` zu brechen.

Offene Entscheidung fuer spaeter:

- Ob `tickers.is_active` als Legacy-S&P-500-Hilfsspalte erhalten bleibt oder vollstaendig durch `universe_members` ersetzt wird.

### 2. Mandanten, Portfolios und Kataloge

Neue Katalog- und Konfigurationstabellen:

```text
tenants
portfolios
universes
universe_members
data_providers
provider_configs
benchmarks
strategy_instances
```

Minimaler Zweck:

| Tabelle | Zweck |
|---|---|
| `tenants` | Spaetere Mandantenfaehigkeit; initial genau ein Default-Tenant. |
| `portfolios` | Fachlicher Container fuer Strategie, Benchmark, Live-Bestand und Runs. |
| `universes` | Katalog auswählbarer Anlageuniversen, z. B. `sp500`. |
| `universe_members` | Historisierte Mitgliedschaft pro Universum und Ticker. |
| `data_providers` | Provider-Katalog, z. B. `yfinance`, `simfin`, `csv`. |
| `provider_configs` | Nicht geheime Provider-Konfiguration; Secrets bleiben in `.env`. |
| `benchmarks` | Benchmark-Katalog mit Benchmark-Ticker, z. B. `SPY`. |
| `strategy_instances` | Versionierte fachliche Strategie-Konfiguration. |

`strategy_instances` ersetzt langfristig die breite Legacy-Tabelle `strategy_settings`.

Vorgesehene Kernfelder:

```text
id
portfolio_id
strategy_key
strategy_version
params_json
indicators_json
universe_id
benchmark_id
provider_config_id
valid_from
valid_to
is_active
created_at
```

### 3. Evaluation

Neue Evaluation-Tabellen:

```text
strategy_runs
strategy_run_metrics
strategy_run_equity_curve
strategy_run_trades
strategy_run_holdings
```

Zweck:

| Tabelle | Zweck |
|---|---|
| `strategy_runs` | Ein Backtest, Parameter-Sweep-Eintrag oder Reporting-Run mit eingefrorener Konfiguration. |
| `strategy_run_metrics` | Kompakte Kennzahlen wie CAGR, Volatilitaet, Max Drawdown, Sharpe, Benchmark-Alpha. |
| `strategy_run_equity_curve` | Zeitreihe fuer Strategie- und Benchmark-Wert. |
| `strategy_run_trades` | Simulierte Trades, Kosten, Steuern und Gruende. |
| `strategy_run_holdings` | Optionaler Audit-Snapshot der simulierten Holdings je Stichtag. |

`factor_metrics` und `factor_scores` werden in Evaluation nicht als globale Dauerzustands-Tabellen vorausgesetzt. Fuer den ersten vertikalen Schnitt duerfen sie aus Legacy-Logik gelesen oder temporaer berechnet werden; dauerhafte Speicherung gehoert an einen konkreten `strategy_run_id`, falls Audit oder Performance es erfordern.

### 4. Live-Betrieb

Neue oder weiterentwickelte Live-Tabellen:

```text
live_decisions
live_trade_plans
live_trade_plan_items
live_trade_executions
cash_ledger
portfolio_positions
portfolio_cash_snapshots
```

Zweck:

| Tabelle | Zweck |
|---|---|
| `live_decisions` | Auditierbare Model-/Shadow-Entscheidungen je Stichtag. |
| `live_trade_plans` | Kopf eines konkreten umsetzbaren Trade-Plans. |
| `live_trade_plan_items` | Einzelne geplante Orders inkl. Skip-Gruenden. |
| `live_trade_executions` | Manuell erfasste reale Ausfuehrungen. |
| `cash_ledger` | Cash-Bewegungen als Ledger, nicht nur aktueller Saldo. |
| `portfolio_positions` | Reale Positionen, spaeter mit `portfolio_id`. |
| `portfolio_cash_snapshots` | Abgeleitete Cash-Salden fuer Status/Reporting. |

Bestehende Legacy-Tabellen `trade_executions`, `cash_ledger`, `portfolio_positions` und `portfolio_cash` werden nicht sofort ersetzt. AP1 legt nur die Zieltrennung fest.

## Vorgeschlagene Abhaengigkeiten

```text
tenants
  -> portfolios
      -> strategy_instances
          -> strategy_runs
              -> strategy_run_metrics
              -> strategy_run_equity_curve
              -> strategy_run_trades
              -> strategy_run_holdings

universes
  -> universe_members

benchmarks
data_providers
  -> provider_configs
```

Rohdaten bleiben ticker-zentriert:

```text
tickers
  -> daily_candles
  -> financial_reports
  -> market_cap_snapshots
```

## Migrationsreihenfolge

### AP2: Minimaler Datenzugriff

Status: abgeschlossen.

- Neue `shared`-/`data`-DB-Verbindung fuer das modulare System angelegt.
- Fixture-Lesepfad fuer die Rohdatentabellen aus `fixtures/raw_market_data.sql` geschaffen.
- Read-only Loader fuer Ticker, Kerzen, Fundamentaldaten und Market-Caps implementiert.
- Smoke-Test-CLI `cli.data_status` fuer Rohdatenverfuegbarkeit angelegt.

### AP3: Modul-Contracts und Data-Provider-Schicht

Status: abgeschlossen.

- Standardisierte Python-Contracts fuer `DataProvider`, `UniverseLoader`, `Indicator`, `Strategy` und `Benchmark` eingefuehrt.
- `FixtureDataProvider` fuer bestehende MySQL-/Fixture-Daten implementiert.
- `ActiveTickerUniverse` fuer `tickers.is_active = 1` implementiert.
- `ProviderBenchmark` fuer Benchmark-Preisreihen ueber den Provider-Contract implementiert.
- Smoke-Test-CLI `cli.framework_status` angelegt.

### AP4: Linux-Umzug und lokale Toolchain

- Anlass: AP3 hatte Entwicklungs- und Toolchain-Probleme unter Windows mit WSL.
- Entwicklungsumgebung vollstaendig auf Linux ausrichten.
- Linux-venv als Standard verwenden und `requirements.txt` installieren.
- Docker/Compose, MySQL-Container, `.env` und Fixture-Daten stabil lauffaehig machen.
- AP3-Smoke-Commands gegen Linux-venv und Docker pruefen.

### AP5: Universum und Benchmark

- `universes` und `benchmarks` als Code- oder DB-Katalog einfuehren.
- S&P-500-Universum zunaechst aus `tickers.is_active = 1` laden.
- Benchmark `SPY` aus `daily_candles` lesen.

### AP6: Strategie-Run

- Erste `strategy_instances`-Default-Konfiguration definieren.
- Value/Quality/Momentum-Strategie auf Fixture-Daten ausfuehren.
- Ergebnis gegen Benchmark ausgeben.

### AP7: Persistenz fuer Evaluation

- `strategy_runs`, `strategy_run_metrics`, `strategy_run_equity_curve` und `strategy_run_trades` in SQL anlegen.
- Run-Konfiguration einfrieren.
- CLI fuer einen reproduzierbaren Backtest bereitstellen.

### AP8: Live-Migration

- Legacy-Live-Tabellen portfolio-faehig machen oder in neue Live-Tabellen migrieren.
- Execution Gap zwischen Shadow und Real Portfolio wieder anbinden.
- Manuelle Trade- und Cash-Erfassung erhalten.

## Initialer Schema-Sketch

Dieser Sketch ist eine Planungsgrundlage, noch nicht die finale Migration:

```sql
CREATE TABLE tenants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE portfolios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tenant_id INT NOT NULL,
    name VARCHAR(255) NOT NULL,
    base_currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE universes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    universe_key VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(500),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE universe_members (
    universe_id INT NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    PRIMARY KEY (universe_id, ticker, valid_from),
    FOREIGN KEY (universe_id) REFERENCES universes(id),
    FOREIGN KEY (ticker) REFERENCES tickers(ticker)
);

CREATE TABLE benchmarks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    benchmark_key VARCHAR(100) NOT NULL UNIQUE,
    ticker VARCHAR(10) NOT NULL,
    name VARCHAR(255) NOT NULL,
    FOREIGN KEY (ticker) REFERENCES tickers(ticker)
);

CREATE TABLE strategy_instances (
    id INT AUTO_INCREMENT PRIMARY KEY,
    portfolio_id INT NOT NULL,
    strategy_key VARCHAR(100) NOT NULL,
    strategy_version VARCHAR(50) NOT NULL,
    params_json JSON NOT NULL,
    indicators_json JSON NOT NULL,
    universe_id INT NOT NULL,
    benchmark_id INT NOT NULL,
    provider_config_id INT NULL,
    valid_from DATETIME NOT NULL,
    valid_to DATETIME NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
    FOREIGN KEY (universe_id) REFERENCES universes(id),
    FOREIGN KEY (benchmark_id) REFERENCES benchmarks(id)
);

CREATE TABLE strategy_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    strategy_instance_id INT NOT NULL,
    run_type ENUM('backtest','parameter_sweep','report','live_model') NOT NULL,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    config_snapshot_json JSON NOT NULL,
    status ENUM('running','completed','failed') NOT NULL DEFAULT 'running',
    FOREIGN KEY (strategy_instance_id) REFERENCES strategy_instances(id)
);
```

## Offene Punkte

- MySQL-Version pruefen, bevor JSON-Indizes oder Check-Constraints genutzt werden.
- Entscheiden, ob `data_providers`/`provider_configs` in AP2 schon als Tabellen noetig sind oder vorerst Code-Konfiguration bleiben.
- Entscheiden, ob `factor_metrics`/`factor_scores` fuer Performance als Run-bezogene Tabellen wieder eingefuehrt werden.
- Vor jeder echten Migration Backup- und Restore-Pfad fuer `init.sql` und die aktuelle Fixture testen.
