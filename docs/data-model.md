# Datenmodell-Plan

Stand: AP25.

Dieses Dokument beschreibt den Zielzustand des neuen modularen Quant-Frameworks.
AP14 ersetzt die bisherige Uebergangsentscheidung, legacy-kompatible Tabellen
weiterzuverwenden: Der regulaere Betrieb soll nach AP14 ausschliesslich auf
kanonischen neuen Tabellen laufen. `init.sql` und
`fixtures/raw_market_data.sql` wurden im AP14-Cutover auf das kanonische Schema
umgestellt.

AP18 ergaenzt das fachliche Zielbild fuer mehrere Assetklassen, Universen und
Daten-Capabilities. AP19 ergaenzt die Provider-/API-Achse: Universen,
Capabilities und konkrete Datenquellen werden getrennt modelliert, damit z. B.
Yahoo Finance, Binance, SimFin, CSV oder kommerzielle APIs austauschbar
angebunden werden koennen. Die detaillierte Capability-Matrix und
Migrationslinie stehen in [docs/data-capabilities.md](data-capabilities.md);
das Provider-Binding-Modell steht in
[docs/provider-api-model.md](provider-api-model.md). AP20 setzt diese
Capability-/Provider-Pruefung in Python um. AP21 konkretisiert den
Asset-Katalog im Schema und fuehrt provider-spezifische Identifier-Mappings
ein. AP22 nutzt diese Mappings im modularen Sync fuer Provider-spezifische
Symbolaufloesung. AP23 fuehrt kanonische `universes` und `universe_members`
fuer Universe-Identitaet und historisierte Mitgliedschaften ein. AP24 setzt
`data_sync_runs` als kanonischen Audit-Trail fuer echte Preis-, Fundamental-
und Membership-Syncs um. AP25 nutzt diesen Trail fuer gefilterte
Operator-Diagnosen und haertet den Yahoo/yfinance-Sync ueber konfigurierbare
Request-Policies, ohne das Schema zu erweitern.

## Leitlinien

- Rohdaten bleiben dauerhaft gespeichert und werden nicht aus Strategie-Runs abgeleitet.
- Fachliche Konfiguration wird versioniert gespeichert, nicht in `.env`.
- Evaluation und Live-Betrieb werden getrennt modelliert.
- Billig reproduzierbare Zwischenwerte werden nicht dauerhaft gespeichert.
- Audit-relevante Entscheidungen, Trades, Cash-Bewegungen und Run-Konfigurationen werden eingefroren.
- Die erste Umsetzung bleibt auf MySQL und SQLAlchemy-nahe SQL-Zugriffe ausgerichtet.
- Assets werden fachlich als allgemeiner Asset-Katalog verstanden, nicht als
  reine Aktien-/S&P-Tickerliste.
- Universen beschreiben Asset-Mitgliedschaften; sie implizieren nicht
  automatisch, dass bestimmte Datenarten verfuegbar sind.
- Strategien, Indikatoren, Benchmarks und Live-Workflows sollen ihre
  benoetigten Daten-Capabilities explizit deklarieren.
- Provider/API-Bindings sollen pro Datenrolle explizit werden; ein Universum
  impliziert nicht automatisch Yahoo Finance, Binance oder eine andere API.
- Provider-Wechsel sind nur gueltig, wenn Capabilities, Identifier-Abdeckung,
  Granularitaet, Freshness und Mindestfelder kompatibel bleiben.

## Aktueller Legacy-Bestand Und AP14-Audit

`init.sql` beschreibt den legacy-kompatiblen Gesamtbestand. Der entfernte
Full-Dump `stocks_db.sql` enthielt dieselben 18 Tabellen und wurde durch die
bereinigte Rohdaten-Fixture `fixtures/raw_market_data.sql` ersetzt:

| Bereich | Tabellen | Bewertung |
|---|---|---|
| Rohdaten | `tickers`, `daily_candles`, `financial_reports`, `market_cap_snapshots` | Werden in AP14 in kanonische Asset-/Market-Data-Tabellen migriert. |
| Berechnete Faktoren | `factor_metrics`, `factor_scores` | Duerfen nicht mehr globale operative Quelle sein; Real-Positionspreise kommen kuenftig aus Preisbars. |
| Legacy-Settings | `strategy_settings`, `strategy_settings_snapshots` | Werden durch versionierte `strategy_instances` und Run-Konfigurations-Snapshots ersetzt. |
| Legacy-Model/Shadow | `portfolio_snapshots`, `rebalance_suggestions`, `decision_log`, `trade_plan_summary`, `trade_plan_snapshots` | Werden durch Portfolio-Target-, Rebalance- und Trade-Plan-Tabellen ersetzt. |
| Real Portfolio | `portfolio_positions`, `portfolio_cash`, `trade_executions`, `cash_ledger` | Werden durch portfolio-faehige Live-Positions-, Cash- und Execution-Tabellen ersetzt. |
| Research | `performance_snapshots` | Wird durch kompakte Run-Metriken und Equity-Curves ersetzt. |

Der AP14-Audit zeigte vor dem Cutover folgende Tabellenabhaengigkeiten:

| Modul | Aktuelle Tabellen | Nutzung |
|---|---|---|
| `data.repository` | `tickers`, `daily_candles`, `financial_reports`, `market_cap_snapshots` | Wurde auf `assets`, `asset_price_bars`, `asset_fundamental_reports`, `asset_market_caps` migriert. |
| `cli.data_status` | `tickers`, `daily_candles`, `financial_reports` | Wurde auf kanonische Rohdatentabellen migriert. |
| `live.repository` | `portfolio_snapshots`, `portfolio_positions`, `portfolio_cash`, `factor_metrics` | Wurde auf kanonische Live-Tabellen migriert; Preise kommen aus `asset_price_bars`. |
| `live.operations` | `strategy_settings`, `strategy_settings_snapshots`, `portfolio_snapshots`, `portfolio_positions`, `portfolio_cash`, `daily_candles`, `rebalance_suggestions`, `decision_log`, `trade_plan_summary`, `trade_plan_snapshots` | Wurde auf kanonische Settings-, Target-, Rebalance-, Decision- und Trade-Plan-Tabellen migriert. |
| `live.execution` | `strategy_settings`, `strategy_settings_snapshots`, `tickers`, `portfolio_positions`, `portfolio_cash`, `trade_executions`, `cash_ledger`, `trade_plan_snapshots` | Wurde auf kanonische Assets-, Live-Position-, Cash-, Execution- und Trade-Plan-Tabellen migriert. |
| `evaluation.repository` | `strategy_runs`, `strategy_run_metrics`, `strategy_run_equity_curve`, `strategy_run_trades` | Bereits neuer AP8-Pfad, aber noch ohne Portfolio-/Strategy-Instance-FKs. |

## Zielbereiche

### 1. Stammdaten und Rohdaten

AP14-Zieltabellen:

```text
assets
asset_provider_identifiers
asset_price_bars
asset_fundamental_reports
asset_market_caps
data_sync_runs
```

Zweck:

| Tabelle | Zweck |
|---|---|
| `assets` | Asset-Stammdaten inklusive Assetklasse, Canonical-/Display-Symbol, Instrumenttyp, Markt und Quote-Waehrung. Ersetzt `tickers`; `ticker` bleibt aktueller FK fuer den kanonischen Pfad. |
| `asset_provider_identifiers` | Provider-spezifische Symbole und optionale stabile IDs je Asset. |
| `universes` | Katalog auswählbarer Universen inklusive Membership-Quelle und Assetklassen. |
| `universe_members` | Historisierte Asset-Mitgliedschaften pro Universum. |
| `asset_price_bars` | Tägliche OHLCV-Preisbars. Ersetzt `daily_candles`. |
| `asset_fundamental_reports` | Annual-/TTM-Fundamentaldaten. Ersetzt `financial_reports`. |
| `asset_market_caps` | Market-Cap-Zeitreihe. Ersetzt `market_cap_snapshots`. |
| `data_sync_runs` | Audit fuer echte Daten-Syncs, Provider, Source-Rollen, Zeitfenster, Status, Zeilenzaehler und Fehlermeldungen. |

`tickers.is_active` wird nicht in `assets` uebernommen. Aktive
Universumsmitgliedschaft gehoert in `universe_members`.

AP18/AP21/AP23-Zielpraezisierung:

- `assets` bleibt der zentrale Asset-Katalog und traegt seit AP21 explizite
  Assetklassen wie `equity` oder `etf`; weitere Klassen wie `crypto`, `cash`,
  `fx` oder `future` sind fachlich vorbereitet.
- `asset_provider_identifiers` trennt interne Asset-Symbole von
  provider-spezifischen Symbolen und IDs.
- `universes` und `universe_members` sind seit AP23 Teil des kanonischen
  Rohdaten-/Katalogpfads; `sp500_active`, `active_tickers` und `all_tickers`
  werden in Schema und Fixture geseedet.
- `asset_price_bars` bleibt die generische Quelle fuer taegliche OHLCV-Daten,
  sofern eine Assetklasse solche Preisbars besitzt.
- `asset_fundamental_reports` ist aktienspezifisch und darf nicht als
  Pflichtdatenquelle fuer alle Assetklassen interpretiert werden.
- `asset_market_caps` ist eine optionale Zeitreihe, die bei Aktien und Krypto
  sinnvoll sein kann, aber nicht fuer jede Assetklasse vorausgesetzt wird.
- Neue assetklassenspezifische Tabellen, z. B. fuer Krypto-Netzwerkdaten oder
  ETF-Holdings, sollen als eigene Capabilities modelliert werden statt die
  Aktien-Fundamentaltabelle zu ueberladen.
- Seit AP24 schreibt `data_sync_runs` fuer echte Preis-, Fundamental- und
  Membership-Syncs Start-/Endzeit, Provider, Source-Rolle, Modus, optionales
  Datenfenster, geplante/verarbeitete Items, Row Counts, Status und
  operator-sichtbare Fehler. Dry-Runs bleiben read-only und erzeugen keine
  Audit-Zeilen.
- Seit AP25 kann `cli.data_status --details` diese Runs nach Typ, Status,
  Provider, Source-Rolle, Zeitraum und Limit filtern und meldet
  fehlgeschlagene sowie stale gestartete Runs. Retention bleibt konservativ:
  Audit-Zeilen werden nicht automatisch geloescht.
- Seit AP26 nutzt `data.diagnostics` die bestehenden Rohdaten- und
  Audit-Tabellen fuer schemafreie Freshness-/Qualitaetsdiagnosen.
  `cli.data_status --details` meldet Missing/Stale-Zustaende fuer
  `asset_price_bars`, TTM-Zeilen in `asset_fundamental_reports`,
  `asset_market_caps`, Provider-Identifier-Coverage und die juengste
  Sync-Health als `data_quality.*`-Zeilen.

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
Ab AP14 ist diese Ersetzung nicht mehr langfristig, sondern Cutover-Ziel:
`strategy_settings` und `strategy_settings_snapshots` sind danach kein
regulaerer Laufzeitpfad mehr.

AP18-Zielpraezisierung fuer Universen:

- Ein Universum ist eine Auswahl von Assets zu einem Stichtag.
- Assetklasse, Waehrung, Liquiditaet, Mindesthistorie und Datenabdeckung sind
  Universe-Policy- oder Capability-Pruefungen, nicht implizite Eigenschaften
  des Universumsnamens.
- Die aktuelle `sp500_active`-Konfiguration bleibt ein Aktienuniversum und
  benoetigt fuer die Default-Strategie Preise, Fundamentaldaten, Market Caps
  und Sector-Klassifikation.
- Ein spaeteres Krypto-Universum darf gueltig sein, obwohl
  `asset_fundamental_reports` leer bleibt, solange die gewaehlte Strategie
  keine Aktienfundamentals verlangt.

AP19-Zielpraezisierung fuer Provider:

- `data_providers` beschreibt konkrete externe oder interne Quellen, z. B.
  `yfinance`, `binance_spot`, `simfin`, `csv` oder einen kommerziellen
  Anbieter.
- `provider_configs` beschreibt fachliche Konfigurationen und Source-Rollen,
  aber keine Secrets; Tokens und Passwoerter bleiben in `.env` oder in einem
  Secret-Store.
- Membership, Preise, Fundamentals, Market Caps, Klassifikation und
  Benchmark-Preise koennen aus unterschiedlichen Providern stammen.
- Asset-Identifier muessen langfristig provider-spezifisch abbildbar sein,
  weil Provider unterschiedliche Symbole verwenden.

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

`factor_metrics` und `factor_scores` werden in Evaluation nicht als globale
Dauerzustands-Tabellen vorausgesetzt. Falls Indikator- oder Rankingwerte
persistiert werden muessen, gehoeren sie an einen konkreten `strategy_run_id`
oder `live_rebalance_run_id`, nicht in globale Tabellen.

### 4. Live-Betrieb

AP14-Zieltabellen:

```text
live_rebalance_runs
live_rebalance_items
portfolio_target_snapshots
portfolio_target_items
live_trade_plans
live_trade_plan_items
live_trade_executions
live_cash_ledger
live_cash_balances
live_positions
```

Zweck:

| Tabelle | Zweck |
|---|---|
| `live_rebalance_runs` | Kopf eines operativen Monthly-/Rebalance-Laufs inkl. `portfolio_id`, `strategy_run_id`, `as_of_date`, Konfigurationssnapshot und Status. |
| `live_rebalance_items` | Ersetzt `rebalance_suggestions` und `decision_log`; enthaelt Aktion, Grund, Scores, Holding-Daten und Umsetzbarkeit pro Asset. |
| `portfolio_target_snapshots` | Kopf fuer Model- oder Shadow-Zielportfolio je Lauf. |
| `portfolio_target_items` | Einzelpositionen eines Model-/Shadow-Zielportfolios. Ersetzt `portfolio_snapshots`. |
| `live_trade_plans` | Kopf eines konkreten kapitalabhaengigen Trade-Plans. Ersetzt `trade_plan_summary`. |
| `live_trade_plan_items` | Einzelne geplante Orders inkl. Reihenfolge, Cash-Simulation und Skip-Gruenden. Ersetzt `trade_plan_snapshots`. |
| `live_trade_executions` | Manuell erfasste reale Ausfuehrungen. Ersetzt `trade_executions`. |
| `live_cash_ledger` | Cash-Bewegungen als Ledger. Ersetzt `cash_ledger`. |
| `live_cash_balances` | Abgeleitete Cash-Salden fuer Status/Reporting. Ersetzt `portfolio_cash`. |
| `live_positions` | Reale Positionen je Portfolio und Asset. Ersetzt `portfolio_positions`. |

Live-Preise fuer reale Positionen werden aus `asset_price_bars` geladen.
`factor_metrics.current_price` ist nach AP14 keine operative Preisquelle mehr.

## AP14 Zielmapping

| Legacy-/Uebergangstabelle | Neue kanonische Tabelle(n) | Migration |
|---|---|---|
| `tickers` | `assets`, `universe_members` | Stammdaten nach `assets`; aktive S&P-500-Zugehoerigkeit nach `universe_members`. |
| `daily_candles` | `asset_price_bars` | 1:1 Preisbar-Migration mit kanonischem `ticker`-FK auf `assets`. |
| `financial_reports` | `asset_fundamental_reports` | 1:1 Report-Migration mit `asset_id`, `report_type`, `report_date`. |
| `market_cap_snapshots` | `asset_market_caps` | 1:1 Market-Cap-Migration mit kanonischem `ticker`-FK auf `assets`. |
| `strategy_settings` | `strategy_instances` | Aktive Defaults als versionierte Strategieinstanz mit JSON-Parametern. |
| `strategy_settings_snapshots` | `strategy_runs.config_snapshot_json`, `live_rebalance_runs.config_snapshot_json` | Settings werden pro Run eingefroren, nicht als eigene Stichtagstabelle. |
| `portfolio_snapshots` | `portfolio_target_snapshots`, `portfolio_target_items` | `snapshot_type` wird Snapshot-Typ `model`/`shadow`; Items referenzieren Snapshot-Kopf. |
| `rebalance_suggestions` | `live_rebalance_items` | Aktion, Grund, Zielgewicht und Real-Position-Kontext werden zusammengefuehrt. |
| `decision_log` | `live_rebalance_items` | Scores, Trend, Holding-Tage und Mindesthaltedauer werden in denselben Item-Datensatz integriert. |
| `trade_plan_summary` | `live_trade_plans` | Plan-Kopf, Cash-Simulation und Summen. |
| `trade_plan_snapshots` | `live_trade_plan_items` | Geplante Orders, Reihenfolge, Cash-vor/nach, Skip-Gruende. |
| `trade_executions` | `live_trade_executions` | Reale Ausfuehrungen mit optionaler Referenz auf `live_trade_plan_items`. |
| `cash_ledger` | `live_cash_ledger` | Cash-Ledger mit `portfolio_id` und optionalem Execution-FK. |
| `portfolio_cash` | `live_cash_balances` | Abgeleitete Salden, weiterhin aus Ledger validierbar. |
| `portfolio_positions` | `live_positions` | Reale Positionen mit Ticker-FK, Durchschnittspreis und offen/geschlossen-Status. |
| `factor_metrics` | keine globale Tabelle; optional `strategy_run_indicator_values` | Operative Preise aus `asset_price_bars`; persistierte Indikatoren nur run-bezogen. |
| `factor_scores` | keine globale Tabelle; optional `strategy_run_rankings` | Rankings werden pro Strategie-/Live-Run gespeichert, wenn Audit es erfordert. |

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

Rohdaten bleiben Asset-zentriert:

```text
assets
  -> asset_price_bars
  -> asset_fundamental_reports
  -> asset_market_caps
```

AP18 ergaenzt logisch, noch ohne Schemaumsetzung:

```text
assets
  -> asset_class
  -> data_capabilities by asset class/provider

universes
  -> universe_members
  -> universe_policy

strategies/indicators/benchmarks/live workflows
  -> required_capabilities
  -> capability validation before run (AP20: shared.capabilities)
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
- Benchmark `SPY` aus `asset_price_bars` lesen.

### AP6: Indikator-Engine

- `Indicator`-Contract fuer modulare Berechnungen verwenden.
- Momentum/Return, relative Staerke sowie einfache Value-/Quality-Kennzahlen
  auf Fixture-Daten berechnen.
- Fehlende Daten explizit als NaN/NULL behandeln.

### AP7: Erste Strategie Value/Quality/Momentum

- Erste `strategy_instances`-Default-Konfiguration definieren.
- Value/Quality/Momentum-Strategie auf Fixture-Daten ausfuehren.
- Ranking und erste Model-Portfolio-Ausgabe erzeugen.

### AP8: Persistenz fuer Evaluation

- `strategy_runs`, `strategy_run_metrics`, `strategy_run_equity_curve` und `strategy_run_trades` in SQL anlegen.
- Run-Konfiguration einfrieren.
- CLI fuer einen reproduzierbaren Backtest bereitstellen.
- AP8 legt die Evaluationstabellen additiv ueber `cli.backtest_status --persist`
  an.

### AP9: Live-Migration

- AP9 ist abgeschlossen und verwendet vorerst die bestehenden
  legacy-kompatiblen Live-Tabellen weiter.
- Execution Gap zwischen Shadow und Real Portfolio ist im neuen `live/`-Paket
  angebunden.
- Manuelle Trade- und Cash-Erfassung ist ueber `LiveExecutionService`,
  `cli.live_trade` und `cli.live_cash` wieder angebunden.
- Eine portfolio-/tenant-faehige Live-Schema-Migration bleibt AP14.

### AP14: Legacy-unabhaengiges Schema und operativer Cutover

- `assets`, `asset_price_bars`, `asset_fundamental_reports` und
  `asset_market_caps` ersetzen die bisherigen Rohdatentabellen.
- `strategy_instances` und Run-Snapshots ersetzen `strategy_settings` und
  `strategy_settings_snapshots`.
- `portfolio_target_*`, `live_rebalance_*`, `live_trade_*`,
  `live_cash_*` und `live_positions` ersetzen die legacy-kompatiblen
  operativen Live-Tabellen.
- Repositories und CLIs werden so migriert, dass eine Smoke-Datenbank ohne
  Legacy-Tabellen fuer `cli.daily_run`, `cli.monthly_run --persist`,
  `cli.live_status`, `cli.live_cash` und `cli.live_trade` genuegt.

### AP18: Assetklassen, Universen und Daten-Capabilities

Status: abgeschlossen als Dokumentations-/Design-AP.

- `assets` ist fachlich als allgemeiner Asset-Katalog eingeordnet.
- Assetklassen und typische Datenarten sind dokumentiert.
- Universen sind als historisierbare Asset-Auswahl beschrieben, getrennt von
  Strategie- und Datenanforderungen.
- Data-Capabilities wie `prices.daily_ohlcv`,
  `fundamentals.equity_reports`, `market_caps`,
  `classification.equity_sector`, `live.cash`, `live.positions` und spaetere
  Krypto-/ETF-spezifische Capabilities sind definiert.
- Die aktuelle Value/Quality/Momentum-Strategie ist als Aktienstrategie
  klassifiziert, weil sie Fundamentaldaten, Market Caps und Sector-Daten
  benoetigt.
- Eine spaetere Capability-Pruefung vor Strategieausfuehrungen ist als
  Migrationslinie beschrieben.
- Keine Schema- oder Codeaenderungen wurden in AP18 umgesetzt.

### AP19: Provider-, API- und Source-Binding-Modell

Status: abgeschlossen als Dokumentations-/Design-AP.

- Universen, Provider, Provider-Konfigurationen, Source-Rollen und
  Capabilities sind fachlich getrennt.
- Provider-Bindings werden pro Datenrolle beschrieben, z. B. Membership,
  Preise, Fundamentals, Market Caps, Klassifikation und Benchmark-Preise.
- Yahoo Finance ist nur ein moeglicher Equity-Provider; Binance kann z. B.
  ein Krypto-Provider sein; kommerzielle Anbieter koennen Membership,
  Preis- oder Fundamentaldaten liefern.
- Provider-spezifische Identifier werden als spaeterer notwendiger
  Mapping-Bereich dokumentiert.
- Keine Schema- oder Codeaenderungen wurden in AP19 umgesetzt.

### AP20: Capability- und Provider-Check

Status: abgeschlossen als read-only Code-AP.

- `shared.capabilities` deklariert Capability-Schluessel, Source-Rollen,
  Provider-Capabilities, Universe-Profile und Anforderungen fuer Strategie,
  Indikatoren, Benchmarks und Live-Workflows.
- Der aktuelle Default-Pfad bleibt gueltig, inkompatible Provider- oder
  Universe-Kombinationen werden frueh abgelehnt.
- Keine Schemaaenderungen wurden in AP20 umgesetzt.

### AP21: Asset-Katalog und Provider-Identifier

Status: abgeschlossen als Schema-/Repository-AP.

- `assets` enthaelt Assetklasse, Canonical-/Display-Symbol, Instrumenttyp,
  Exchange, Markt, Quote-Waehrung und Primaer-Provider.
- `asset_provider_identifiers` modelliert provider-spezifische Symbole und
  optionale stabile Provider-IDs.
- Repository-Upserts erzeugen fuer den Default-Pfad automatisch
  `mysql_fixture`-Ticker-Mappings.
- Der Capability-Checker kann supplied Asset-Metadaten und
  Provider-Identifier-Coverage optional auswerten.

### AP22: Provider-Symbolaufloesung

Status: abgeschlossen als Sync-/Metadaten-AP.

- Preis- und Fundamental-Sync loesen interne Ticker ueber
  `asset_provider_identifiers` zu Provider-Symbolen auf.
- Geladene Preise, Reports und Market Caps werden weiter auf interne Ticker
  normalisiert und in die kanonischen Tabellen geschrieben.
- Universumsdefinitionen tragen explizite Metadaten fuer Assetklassen,
  Membership-Quelle und Membership-Regel.

### AP23: DB-Universen und historisierte Mitgliedschaft

Status: abgeschlossen als Schema-/Repository-AP.

- `universes` und `universe_members` sind kanonische Tabellen in `init.sql`
  und der Rohdaten-Fixture.
- `sp500_active`, `active_tickers` und `all_tickers` werden als
  Universe-Katalogeintraege geseedet.
- `RawDataRepository` liest Universen und Mitglieder, pflegt
  Default-Mitgliedschaften bei Asset-Upserts und schliesst offene aktive
  Membership-Intervalle bei Deaktivierungen.
- Der modulare Universe-Loader liest DB-Mitgliedschaften, wenn ein Provider
  diese anbietet, und behaelt einen Fallback fuer Tests/Fake-Provider.

### AP24: Data-Sync-Audit-Trail

Status: abgeschlossen als Schema-/Repository-/Sync-AP.

- `data_sync_runs` ist kanonische Tabelle in `init.sql` und der
  Rohdaten-Fixture.
- `RawDataRepository` kann Sync-Runs starten, erfolgreich abschliessen,
  fehlschlagen lassen und die juengsten Runs lesen.
- Preis-, Fundamental- und Membership-Syncs schreiben echte Runs mit Provider,
  Source-Rolle, Modus, Zeitfenster, Status, Zaehlern und Fehlermeldung.
- Vorbereitungs- und Planungsfehler nach Start eines echten Syncs werden als
  `failed` auditiert.
- `cli.data_status --details` und `cli.operator_smoke` zeigen die juengsten
  Sync-Runs fuer Operatoren.
- Dry-Runs bleiben read-only und schreiben keine Audit-Zeilen.

### AP25: Sync-Audit-Bedienung und Betriebshaertung

Status: abgeschlossen ohne Schemaaenderung.

- `cli.data_status --details` kann `data_sync_runs` nach `sync_type`,
  `status`, Provider, Source-Rolle, Zeitraum und Limit filtern.
- Die Statusausgabe meldet failed Runs, stale `started` Runs, den letzten
  erfolgreichen und den letzten fehlgeschlagenen Sync als Diagnosezeile.
- Preis- und Fundamental-Syncs nutzen `SyncRequestPolicy` fuer Batch-Groessen,
  Throttle-Pausen, Retry mit exponentiellem Backoff und Circuit-Breaker.
- Die Sync-CLIs exponieren diese Request-Policy-Parameter fuer konservative
  Yahoo/yfinance-Laeufe.
- Retention bleibt bewusst konservativ: `data_sync_runs` wird nicht
  automatisch bereinigt, damit Audit-Historie erhalten bleibt.

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

CREATE TABLE assets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    sector VARCHAR(255),
    asset_type VARCHAR(32) NOT NULL DEFAULT 'equity',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    asset_id BIGINT NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    PRIMARY KEY (universe_id, asset_id, valid_from),
    FOREIGN KEY (universe_id) REFERENCES universes(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE TABLE benchmarks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    benchmark_key VARCHAR(100) NOT NULL UNIQUE,
    asset_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id)
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
- Fuer einen Implementierungs-AP nach AP18 entscheiden, ob Capabilities zuerst
  als Python-Contracts oder direkt als Tabellen modelliert werden.
