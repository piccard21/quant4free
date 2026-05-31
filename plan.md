# Plan: Neues Quant-System

## Umsetzungsstand

Stand: AP26 ist abgeschlossen. Das kanonische AP14-Schema ist der regulaere
modulare Betriebspfad, AP15 dokumentiert den Host-Crontab-Betrieb fuer Daily
und Monthly, und AP16 ergaenzt einen read-only Performance-Report fuer Real
Portfolio, Shadow Portfolio und Benchmark. AP17 ergaenzt eine isolierte
MySQL-Testdatenbank samt DB-Integrationsregression fuer den kanonischen
MySQL-Pfad. AP18 dokumentiert das Datenmodell fuer mehrere Assetklassen,
Universen und optionale Datenarten explizit. AP19 trennt Universen,
Provider/APIs, Source-Rollen, Identifier und Capability-Bindings fachlich. AP20
setzt dieses Design als read-only Capability- und Provider-Check fuer den
bestehenden Pfad um. AP21 konkretisiert den Asset-Katalog und Provider-
Identifier, AP22 nutzt Provider-Symbole im Sync, und AP23 verlagert
Universe-Identitaet sowie historisierte Mitgliedschaft in kanonische
DB-Tabellen. AP24 ergaenzt einen kanonischen Data-Sync-Audit-Trail fuer Preis-,
Fundamental- und Membership-Syncs. AP25 macht diesen Trail fuer Operatoren
filterbar und haertet den Yahoo/yfinance-Sync ueber konfigurierbare
Request-Policies. AP26 ergaenzt read-only Freshness- und Qualitaetsdiagnosen
fuer Rohdaten, Provider-Identifier-Coverage und Provider-Sync-Health.

Strategische Anpassung:

- Die Weboberflaeche wird vorerst aus dem AP-Plan entfernt.
- Infrastruktur- und Qualitaetsthemen werden vor neuen Oberflaechenbausteinen
  als eigene modulare APs behandelt.
- Reproduzierbare DB-Verifikation gegen das kanonische MySQL-Schema ist seit
  AP17 ueber den isolierten `db_test`-Pfad verfuegbar.
- Das Asset-/Universe-/Data-Capability-Modell ist seit AP18 dokumentiert, damit
  z. B. Krypto-Universen ohne Fundamentaldaten und spaetere Universen mit
  eigenen Zusatzdaten sauber modelliert werden koennen.
- Das Provider-/API-Binding-Modell ist seit AP19 dokumentiert, damit Yahoo
  Finance nur ein moeglicher Equity-Provider ist, Binance z. B. als
  Krypto-Provider modelliert werden kann und kommerzielle Anbieter fuer
  S&P-/Nasdaq-/Fundamental-Daten austauschbar bleiben.
- Der produktive Monthly-Pfad fuer persistierte Artefakte steht jetzt ueber
  `cli.monthly_run --persist` auf dem kanonischen AP14-Pfad bereit.

Naechster AP:

AP27:

- Freshness-Policies je Workflow und Source-Binding konfigurierbar machen.
- Ausgewaehlte Strategie- und Live-Workflows sollen die AP26-Diagnosen optional
  als fail-fast Preflight-Gates nutzen koennen.

Erledigt:

AP26:

- `data.diagnostics` mit `DataQualityDiagnostics` und formatierten
  `data_quality.*`-Statuszeilen angelegt.
- Rohpreise werden fuer Universumsmitglieder plus Benchmark auf Missing/Stale
  geprueft.
- TTM-Fundamentals und Market Caps werden fuer aktuelle Universumsmitglieder
  auf Missing/Stale geprueft.
- Provider-Identifier-Coverage wird fuer den konfigurierten Provider und das
  Identifier-Schema sichtbar, inklusive fehlender Ticker-Beispiele.
- Die juengsten Provider-Syncs fuer Membership, Preise und Fundamentals werden
  als `ok`, `failed`, `started`, `stale_started` oder `no_runs` eingeordnet.
- `cli.data_status --details` und `cli.operator_smoke` drucken die neue
  Preflight-Sicht ohne Schemaaenderung.
- Verifikation:
  - `.venv/bin/python -m pytest tests/test_data_sync.py`
  - `.venv/bin/python -m compileall data cli tests`

AP25:

- `cli.data_status --details` filtert `data_sync_runs` nach Sync-Typ, Status,
  Provider, Source-Rolle, Zeitraum und Limit.
- Die Statusausgabe zeigt Diagnosezaehler fuer failed Runs, stale gestartete
  Runs sowie den letzten erfolgreichen und letzten fehlgeschlagenen Sync.
- Preis- und Fundamental-Syncs nutzen `SyncRequestPolicy` mit Batch-Groessen,
  Throttle-Pausen, Retry mit exponentiellem Backoff und Circuit-Breaker.
- `cli.sync_prices`, `cli.sync_fundamentals` und `cli.sync_data` exponieren
  diese Policy-Schalter fuer konservative Yahoo/yfinance-Laeufe.
- Retention bleibt konservativ und manuell: Audit-Zeilen werden nicht
  automatisch geloescht.
- Verifikation:
  - `.venv/bin/python -m pytest tests/test_data_sync.py`
  - `.venv/bin/python -m pytest tests -m "not integration"`
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  - `scripts/db_integration_tests.sh`

AP24:

- Tabelle `data_sync_runs` in `init.sql`, Fixture und SQLite-Testschema
  eingefuehrt.
- `RawDataRepository` kann Sync-Runs starten, erfolgreich abschliessen,
  fehlschlagen lassen und die juengsten Runs lesen.
- Preis-Sync schreibt Audit-Runs fuer echte Preisdownloads und, bei
  Membership-Refresh, einen separaten Membership-Run.
- Fundamental-Sync schreibt Audit-Runs inklusive Report-/Market-Cap-Zaehlern.
- Fehler in Provider-Downloads werden als `failed` mit operator-sichtbarer
  Fehlermeldung persistiert und danach weiterhin an die CLI durchgereicht.
- Vorbereitungs- und Planungsfehler nach Start eines echten Preis- oder
  Fundamental-Syncs werden ebenfalls als `failed` persistiert.
- `cli.data_status --details` und `cli.operator_smoke` zeigen die juengsten
  Sync-Runs; Sync-CLIs geben erzeugte Run-IDs aus.
- Dry-Runs bleiben read-only und schreiben keine Audit-Zeilen.
- Verifikation:
  - `.venv/bin/python -m pytest tests/test_data_sync.py`
  - `.venv/bin/python -m pytest tests -m "not integration"`
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`

AP23:

- Echte Tabellen `universes` und `universe_members` eingefuehrt.
- `sp500_active`, `active_tickers` und `all_tickers` in `init.sql` und
  Fixture geseedet.
- `RawDataRepository` liest Universen und Mitglieder, pflegt Default-
  Mitgliedschaften bei Asset-Upserts und schliesst aktive Membership-
  Intervalle bei Deaktivierungen.
- Der Universe-Loader liest DB-Mitgliedschaften, wenn der Provider sie
  anbietet, und behaelt den Fallback fuer Tests/Fake-Provider.
- Verifikation:
  - `.venv/bin/python -m pytest tests -m "not integration"`
  - `.venv/bin/python -m compileall data universes cli tests`
  - `scripts/db_integration_tests.sh`

AP22:

- `RawDataRepository.resolve_provider_symbols` loest interne Ticker ueber
  `asset_provider_identifiers` zu provider-spezifischen Symbolen auf.
- Preis-Sync nutzt Provider-Symbole fuer Downloads und schreibt Kerzen unter
  dem internen Ticker zurueck.
- Fundamental-Sync nutzt Provider-Symbole fuer API-Zugriffe und mappt Reports
  sowie Market Caps auf interne Ticker zurueck.
- `UniverseDefinition` traegt explizite Metadaten fuer Assetklassen,
  Membership-Source-Role/-Provider und Membership-Regel.
- `shared.capabilities` enthaelt Yahoo-Finance- und Wikipedia-S&P-500-
  Provider-Capabilities.
- Verifikation:
  - `.venv/bin/python -m pytest tests/test_data_sync.py tests/test_capabilities.py`
  - `.venv/bin/python -m compileall data universes shared cli tests`

AP21:

- `assets` um Assetklasse, Canonical-/Display-Symbol, Instrumenttyp,
  Exchange, Markt, Quote-Waehrung und Primaer-Provider erweitert.
- Separate Tabelle `asset_provider_identifiers` fuer provider-spezifische
  Symbole und IDs eingefuehrt.
- Repository-Modelle, Upserts, Fixture, Status-CLI, Setup-/Smoke-Checks und
  DB-Integrationserwartungen angepasst.
- `shared.capabilities` kann supplied Asset-Metadaten und
  Provider-Identifier-Coverage pruefen.
- `cli.orchestration` reicht reale Member-Metadaten und Identifier-Coverage an
  den Checker weiter, wenn ein Provider diese Coverage melden kann.
- Verifikation:
  - `.venv/bin/python -m pytest tests/test_capabilities.py tests/test_data_sync.py tests/test_orchestration.py`
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`

AP20:

- `shared.capabilities` mit Capability-Konstanten, Source-Rollen,
  Universe-Profilen, Provider-Capabilities, Default-Bindings und Requirements
  fuer Strategie, Indikatoren, Benchmarks und Live-Workflows angelegt.
- Read-only Checker fuer Strategie-, Indikator- und Live-Workflows
  implementiert.
- Der aktuelle Default-Pfad `sp500_active` plus
  `value_quality_momentum` plus `spy` und `mysql_fixture` bleibt gueltig.
- Negative Capability-/Provider-Faelle fuer Krypto-Universum, falsches
  Fundamentals-Binding und fehlende Source-Rolle abgedeckt.
- Checker in `cli.orchestration`, `cli.indicator_status`,
  `cli.strategy_status`, `cli.backtest_status`, `cli.operator_smoke`,
  `cli.live_status`, `cli.live_performance`, `cli.live_cash` und
  `cli.live_trade` eingebunden.
- Keine Schemaaenderung und keine neue externe API-Abhaengigkeit.
- Tests:
  - `tests/test_capabilities.py`
  - `tests/test_orchestration.py`
- Verifikation:
  - `.venv/bin/python -m pytest tests/test_capabilities.py tests/test_orchestration.py`
  - `.venv/bin/python -m compileall shared cli tests`

AP19:

- Provider-, API- und Source-Binding-Modell in
  `docs/provider-api-model.md` dokumentiert.
- Universum, Provider, Provider-Konfiguration, Source-Rollen und Capabilities
  explizit getrennt.
- Source-of-Truth je Datenart beschrieben:
  - Membership
  - Preise
  - Fundamentals
  - Market Caps
  - Klassifikation
  - Benchmark-Preise
- Provider-Capability-Metadaten beschrieben, z. B. `provider_key`,
  `source_role`, `capability_key`, `asset_classes`, `markets`, `granularity`,
  `required_fields`, `identifier_scheme`, `coverage_policy` und
  `freshness_policy`.
- Identifier- und Symbolmodell fuer spaetere Provider-spezifische IDs
  beschrieben.
- Austauschbarkeitsregeln fuer Provider dokumentiert.
- AP20 so angepasst, dass der kommende Checker Provider-/Source-Bindings
  mitprueft und nicht nur Datenarten.
- Keine Schema- oder Codeaenderungen vorgenommen.
- Verifikation:
  - `.venv/bin/python -m pytest tests -m "not integration"`
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`

AP18:

- Asset-, Universums- und Datenartenmodell fuer mehrere Assetklassen in
  `docs/data-capabilities.md` dokumentiert.
- `assets` fachlich von einer Aktien-/S&P-Tickerliste zu einem allgemeinen
  Asset-Katalog weiterentwickelt, ohne das Schema zu aendern.
- Universen als Auswahl von Assets modelliert, nicht als implizite Annahme
  ueber vorhandene Datenarten.
- Datenarten als Capabilities getrennt:
  - generische Preisbars fuer Assets mit OHLCV-Daten
  - aktienspezifische Fundamentaldaten
  - Market-Cap-Zeitreihen
  - Sector-/Klassifikationsdaten
  - Live-Cash und Live-Positionen
  - spaetere assetklassenspezifische Zusatzdaten, z. B. Krypto-Netzwerkdaten
- Strategie- und Indikatoranforderungen als Data-Capabilities beschrieben,
  z. B. `prices.daily_ohlcv`, `fundamentals.equity_reports`, `market_caps`,
  `classification.equity_sector`, `live.cash`, `live.positions`,
  `crypto.network_metrics`.
- Value/Quality/Momentum als Aktienstrategie eingeordnet.
- Capability-Validierungsablauf vor Strategieausfuehrungen dokumentiert.
- Keine Schema- oder Codeaenderungen vorgenommen.
- Verifikation:
  - `.venv/bin/python -m pytest tests -m "not integration"`
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`

AP17:

- Isolierten Compose-MySQL-Dienst `db_test` mit eigenem Volume
  `db_test_data` angelegt.
- pytest-Marker `integration` und Collection-Guard eingefuehrt, damit der
  Default-Testlauf keine DB-Integrationstests ausfuehrt.
- `tests/integration/` mit Session-Fixtures angelegt:
  - Testdatenbankname muss `test` enthalten.
  - Testdatenbank darf nicht `DB_NAME` entsprechen.
  - Fixture laedt `fixtures/raw_market_data.sql` und `init.sql`.
  - Fixture loescht am Ende nur die isolierte Testdatenbank.
- Integrationstests fuer echten MySQL-Pfad ergaenzt:
  - kanonische Tabellen und Fixture-Verfuegbarkeit
  - `RawDataRepository` Upserts und Latest-Queries
  - `OperationalRepository` Persistenz fuer Model/Shadow/Rebalance/Decision/
    Trade-Plan-Artefakte
  - `LiveExecutionService` Cash-Dry-Run ohne Writes
  - `cli.data_status --details` gegen die Testdatenbank
- `scripts/db_integration_tests.sh` als Standard-Runner fuer die isolierte
  DB-Verifikation hinzugefuegt.
- `scripts/dev_check.sh` auf schnelle Tests mit `-m "not integration"`
  umgestellt.
- Verifikation:
  - `.venv/bin/python -m pytest tests -m "not integration"`
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  - `scripts/db_integration_tests.sh`

AP16:

- `live.performance` angelegt:
  - `LivePerformanceRepository` liest Shadow Targets, Real-Positionen,
    Cash-Balances und Preisbars aus den kanonischen Tabellen.
  - `LivePerformanceService` berechnet Real-, Shadow- und Benchmark-Wertreihe,
    Rendite, Benchmark-Rendite, Outperformance und Drawdown.
  - Shadow wird als target-weight Portfolio aus `portfolio_target_items` mit
    `snapshot_type='shadow'` fortgeschrieben und bei neuen Snapshots
    rebalanciert.
  - Benchmark, initial `SPY`, wird aus `asset_price_bars` auf denselben
    Startwert normalisiert.
- `cli.live_performance` als Operator-Report bereitgestellt.
- AP16 bleibt read-only; `performance_snapshots` wird nicht als Pflicht-Persistenz
  fuer den regulaeren Report verwendet.
- Verifikation:
  - `.venv/bin/python -m pytest tests/test_live_performance.py`
  - `.venv/bin/python -m pytest tests`
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared`
  - `.venv/bin/python -m cli.live_performance --help`

AP15:

- Host-Skripte angelegt:
  - `scripts/cron_daily.sh`
  - `scripts/cron_monthly.sh`
  - `scripts/client_smoke.sh`
- Crontab-Betrieb in `docs/operations.md` dokumentiert:
  - Daily-Run per Host-Crontab nach Marktschluss
  - Monthly-Run per Host-Crontab am definierten Monatstag
  - `flock`-Locks unter `var/lock/`
  - Logs unter `var/log/`
  - manuelles Testen, Logpruefung und parallele Lock-Pruefung
- Der Cronpfad nutzt nur modulare CLIs:
  - `cli.daily_run`
  - `cli.monthly_run --persist`
- Frischer Client-Smoke gegen isolierte DB `ap15_client_smoke` erfolgreich
  getestet:
  - Fixture und AP14-Schema geladen
  - Startkapital gesetzt
  - `cli.operator_smoke` ausgefuehrt
  - `cli.monthly_run --persist` ausgefuehrt
  - `cli.live_status` vor und nach Smoke-Trades ausgefuehrt
  - Cash- und Trade-Dry-Runs validiert
  - sieben geplante BUYs in der isolierten Smoke-DB gebucht
  - Cash-Saldo und letzter Ledger-Saldo stimmten ueberein
- Cron-Skripte manuell mit `flock` getestet:
  - Lock-Konflikt bricht parallele Ausfuehrung ab
  - `scripts/cron_daily.sh --dry-run-sync --model-limit 1` schrieb Start/Ende
    in `var/log/daily_run.log`
  - `scripts/cron_monthly.sh --as-of-date 2026-05-21` schrieb Start/Ende in
    `var/log/monthly_run.log` und persistierte gegen die isolierte Smoke-DB

AP14:

- Tabellen-Audit fuer den neuen Code dokumentiert:
  - `data.repository` nutzt jetzt `assets`, `asset_price_bars`,
    `asset_fundamental_reports`, `asset_market_caps`.
  - `live.repository`, `live.operations` und `live.execution` nutzen jetzt die
    kanonischen Live-/Settings-Tabellen.
  - `live.repository` liest Real-Positionspreise aus `asset_price_bars`.
  - `evaluation.repository` ist bereits auf eigenen `strategy_run_*`-Tabellen,
    aber noch nicht portfolio-/strategy-instance-faehig.
- `init.sql` erzeugt keine Legacy-Tabellen mehr.
- `fixtures/raw_market_data.sql` wurde auf kanonische Rohdatentabellen
  umgestellt.
- `setup.sh` nutzt keine Legacy-Core-Module mehr.
- Fokussierte Regressionstests fuer Rohdaten, Live-Status, Live-Operations,
  Cash/Trades und CLI-Fehler laufen auf dem neuen Schema.

AP13:

- Modulare operative Persistenz im neuen `live/operations.py` angelegt:
  - Model Portfolio Snapshot aus AP12-Strategieartefakten
  - Tradable Shadow Snapshot mit Carry-forward vorhandener Positionen,
    Mindesthaltedauer-Schutz und dynamischem Trade-Limit
  - Rebalance Suggestions und Decision Log
  - Trade Plan Summary und Trade Plan Snapshots mit Cash, realen Positionen,
    aktuellen Preisen, Gebuehren und limitierten Funding-Sells
- `OperationalRepository` schreibt alle AP13-Artefakte transaktional in die
  legacy-kompatiblen Live-Tabellen und verhindert doppelte Snapshots je
  Stichtag.
- `cli.monthly_run --persist` aktiviert AP13-Schreibzugriffe; ohne `--persist`
  bleibt der Monthly-Run read-only.
- Verifikation:
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  - `.venv/bin/python -m pytest tests`
  - Docker/MySQL-Smoke gegen separate DB `ap13_smoke` mit `init.sql` plus
    `fixtures/raw_market_data.sql`
  - `docker compose run --rm -e DB_NAME=ap13_smoke app python -m cli.monthly_run --persist --model-limit 7`
  - Wiederholter Persist-Run bricht kontrolliert mit bestehendem Snapshot ab.
  - `docker compose run --rm -e DB_NAME=ap13_smoke app python -m cli.live_status --all --limit 10`
  - Cash-Smoke gegen `ap13_smoke_cash` erzeugt ausfuehrbare BUY-Planzeilen und
    `cli.live_trade --trade-plan-action BUY --dry-run` validiert eine
    Trade-Plan-Zeile.

AP11:

- Modularen Data-Sync im neuen `data/`-Paket angelegt:
  - `PriceSyncService` fuer S&P-500-Ticker, Benchmark und daily Candles
  - `FundamentalSyncService` fuer Annual/TTM-Fundamentals und Market Caps
  - inkrementelle Preis-Startdaten ueber `MAX(date)` je Ticker
  - Benchmark `SPY` wird wie ein normaler Candle-Ticker geplant und geladen
- Provider-Adapter von DB-Zugriff getrennt:
  - `WikipediaSP500TickerSource`
  - `YFinancePriceSource`
  - `YFinanceFundamentalSource`
- Write-Methoden im `RawDataRepository` ergaenzt:
  - Ticker-Upsert und Deaktivierung entfernter aktiver Ticker
  - Candle-, Financial-Report- und Market-Cap-Upserts
  - Auswahl und Markierung von Fundamental-Refreshes
- Neue Operator-CLIs:
  - `cli.sync_prices`
  - `cli.sync_fundamentals`
  - `cli.sync_data`
  - jeweils mit `--dry-run` fuer Fixture-Smoke ohne externe API-Calls
- Tests:
  - `tests/test_data_sync.py`

AP10:

- Gemeinsamer Operator-Fehlerlayer fuer modulare CLIs angelegt:
  - `cli.errors.run_cli`
  - klare Meldungen fuer fehlende Datenbanktabellen, Verbindungsfehler,
    fehlende Python-Abhaengigkeiten und erwartete leere Ergebnisse
  - fehlende Raw-Tabellen verweisen auf `fixtures/raw_market_data.sql`
  - fehlende Live-Tabellen verweisen auf `init.sql` bzw. Legacy-Setup, da die
    Raw-Fixture bewusst keine Live-Daten enthaelt
- Bestehende modulare Operator-CLIs an den Fehlerlayer angebunden:
  - `cli.data_status`
  - `cli.framework_status`
  - `cli.indicator_status`
  - `cli.strategy_status`
  - `cli.backtest_status`
  - `cli.live_status`
  - `cli.live_cash`
  - `cli.live_trade`
- Zusammenhaengende AP10-Smoke-CLI angelegt:
  - `cli.operator_smoke`
  - prueft Datenbank-Ping und Raw-Fixture-Health
  - laedt Universum und Benchmark
  - fuehrt Value/Quality/Momentum-Strategie aus
  - fuehrt Benchmark-Backtest ohne Persistenz aus
  - meldet Kennzahlen und `operator_smoke=ok`
- Tests:
  - `tests/test_cli_errors.py`

AP9:

- Read-only Live-Status im neuen `live/`-Paket angelegt:
  - Model-, Shadow- und Real-Portfolio werden aus legacy-kompatiblen Tabellen gelesen.
  - Execution-Gap-Zustaende werden berechnet:
    `model_not_shadow`, `missing_in_real`, `extra_in_real`,
    `underweight_real`, `overweight_real`, `aligned`.
  - `cli.live_status` zeigt Model/Shadow/Real-Anzahlen, Cash, investierten Wert
    und actionable Gaps.
- Write-side Live-Ausfuehrung wieder angebunden:
  - `LiveExecutionService`
  - `CashMovementRequest` / `CashMovementResult`
  - `TradeExecutionRequest` / `TradeExecutionResult`
  - Buchung von Einzahlungen und Auszahlungen in `cash_ledger` und `portfolio_cash`
  - Buchung manueller BUY/SELL-Ausfuehrungen in `trade_executions`,
    `cash_ledger`, `portfolio_cash` und `portfolio_positions`
  - Cash-/Ledger-Konsistenzpruefung, Dry-Run, Duplikatpruefung,
    Trade-Plan-Abgleich und Steuerbuchung bei realisiertem SELL-Gewinn
- Neue Operator-CLIs:
  - `cli.live_cash`
  - `cli.live_trade`
- Tests:
  - `tests/test_live_status.py`
  - `tests/test_live_execution.py`

AP8:

- Reproduzierbaren Backtest fuer die AP7-Strategie eingefuehrt:
  - `BacktestConfig`
  - `run_backtest`
  - periodisches Rebalancing
  - einfaches Basiskostenmodell
  - Equity Curve und normalisierte Benchmark Curve
- AP8-Metriken berechnet:
  - Rendite
  - Benchmark-Rendite
  - Outperformance
  - Volatilitaet
  - Max Drawdown
- Persistenz fuer Evaluation angelegt:
  - `strategy_runs`
  - `strategy_run_metrics`
  - `strategy_run_equity_curve`
  - `strategy_run_trades`
- `cli.backtest_status` als AP8-Smoke-CLI angelegt.
- Lokale Checks erfolgreich ausgefuehrt:
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  - `.venv/bin/python -m unittest tests.test_indicators tests.test_value_quality_momentum tests.test_backtest`
  - `.venv/bin/python -m cli.backtest_status --start-date 2026-01-02 --end-date 2026-05-22 --equity-limit 3 --trade-limit 5`
  - `.venv/bin/python -m cli.backtest_status --start-date 2026-01-02 --end-date 2026-05-22 --persist --equity-limit 0 --trade-limit 0`

AP7:

- Erste modulare Value/Quality/Momentum-Strategie eingefuehrt:
  - `ValueQualityMomentumStrategy`
  - `create_default_strategy`
  - validierte Faktor-Gewichte fuer Value, Quality und Momentum
- Ranking- und Model-Portfolio-Ausgabe erzeugt:
  - `composite_score`
  - Faktor-Subscores
  - `rank`
  - equal-weight `model_weight` fuer die Top-Positionen
- `cli.strategy_status` als AP7-Smoke-CLI angelegt.
- Kleiner unittest-Satz unter `tests/test_value_quality_momentum.py` angelegt.
- Lokale Checks erfolgreich ausgefuehrt:
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  - `.venv/bin/python -m unittest tests.test_value_quality_momentum tests.test_indicators`
  - `.venv/bin/python -m cli.strategy_status --limit 3`

AP6:

- Indikator-Engine eingefuehrt:
  - `compute_indicators`
  - `create_indicators`
  - `get_indicator`
  - `list_indicator_keys`
  - `merge_indicator_results`
- Erste konkrete Indikatoren implementiert:
  - `momentum_return`
  - `relative_strength`
  - `earnings_yield`
  - `free_cash_flow_yield`
  - `return_on_equity`
  - `debt_to_equity`
- Fehlende Lookback-, Fundamental- oder Market-Cap-Daten bleiben explizit als
  NaN erhalten.
- `cli.indicator_status` als AP6-Smoke-CLI angelegt.
- Kleiner unittest-Satz unter `tests/test_indicators.py` angelegt.
- Lokale Checks erfolgreich ausgefuehrt:
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  - `.venv/bin/python -m unittest tests.test_indicators`
  - `.venv/bin/python -m cli.indicator_status --limit 3`

AP5:

- Universen als konfigurierte Definitionen konkretisiert:
  - `sp500_active`
  - `active_tickers`
  - `all_tickers`
- Universe-Registry und Factory eingefuehrt:
  - `UNIVERSE_DEFINITIONS`
  - `list_universe_definitions`
  - `get_universe_definition`
  - `create_universe`
- Benchmarks als konfigurierte Spezifikationen konkretisiert:
  - `spy`
  - `qqq`
  - `iwm`
- Benchmark-Registry und Factory eingefuehrt:
  - `BENCHMARK_SPECS`
  - `list_benchmark_specs`
  - `get_benchmark_spec`
  - `create_benchmark`
- `cli.framework_status` erweitert:
  - `--universe` waehlt ein konfiguriertes Universum.
  - `--benchmark` waehlt einen konfigurierten Benchmark.
  - `--list-configs` zeigt verfuegbare Universen und Benchmarks.
  - `--benchmark-ticker` bleibt als kompatibler Ad-hoc-Override erhalten.
- Lokale Smoke-Checks fuer Default-Konfiguration, `all_tickers`, alte
  `--benchmark-ticker`-Nutzung und `--list-configs` erfolgreich ausgefuehrt.
- Keine Schema-Migration und keine Aenderung an `legacy/current_system/`.

AP4:

- Linux-Standard-venv `.venv` eingerichtet und Requirements installiert.
- `pip check` erfolgreich ausgefuehrt.
- Docker/Compose-Zugriff stabilisiert; `sp500_db` laeuft healthy, `sp500_worker` und `sp500_pma` laufen.
- Bereinigte Rohdaten-Fixture `fixtures/raw_market_data.sql` erzeugt.
- Lokale `stocks_db` aus `fixtures/raw_market_data.sql` neu aufgebaut.
- Vollstaendigen Legacy-Dump `stocks_db.sql` entfernt, damit Trade-, Cash- und Portfolio-Historie nicht als Standard-Fixture im Repo bleibt.
- `cli.data_status --details` erweitert:
  - trennt `financial_reports.annual` und `financial_reports.ttm`.
  - zeigt `report_dates` getrennt von `imported`.
- Lokale und Container-Smoke-Checks fuer `cli.data_status --details` und `cli.framework_status --benchmark-ticker SPY` erfolgreich ausgefuehrt.
- Hinweis festgehalten: Legacy-Health ist gegen die bereinigte Rohdaten-Fixture kein Standardcheck mehr, weil Legacy-/Live-Tabellen bewusst fehlen.

AP3:

- Standardisierte Python-Contracts fuer austauschbare Framework-Bausteine eingefuehrt:
  - `data.provider.DataProvider`
  - `universes.base.UniverseLoader`
  - `indicators.base.Indicator`
  - `strategies.base.Strategy`
  - `evaluation.benchmarks.Benchmark`
- Gemeinsame Kontext-/Resultattypen angelegt:
  - `indicators.base.IndicatorResult`
  - `strategies.base.StrategyContext`
  - `strategies.base.StrategyResult`
  - `evaluation.benchmarks.BenchmarkSpec`
- Ersten Fixture-/MySQL-Provider `FixtureDataProvider` auf Basis von `RawDataRepository` implementiert.
- Erstes Universum `ActiveTickerUniverse` auf Basis von `tickers.is_active = 1` implementiert.
- Benchmark-Zugriff `ProviderBenchmark` ueber den Provider-Contract implementiert.
- Smoke-Test-CLI `cli.framework_status` fuer Provider, Universum und Benchmark angelegt.
- Keine Schema-Migration und keine Aenderung an `legacy/current_system/`.

AP2:

- Neue modulare DB-Verbindung in `shared/db.py` angelegt.
- Read-only Rohdatenmodelle fuer `tickers`, `daily_candles`, `financial_reports` und `market_cap_snapshots` in `data/models.py` angelegt.
- Fixture-kompatible Loader in `data/repository.py` implementiert:
  - Ticker-Liste und einzelne Ticker.
  - Kerzen-Zeitreihen und letzte Kerze je Ticker.
  - Fundamentaldaten-Zeitreihen und letzter Report je Ticker.
  - Market-Cap-Zeitreihen und letzter Snapshot je Ticker.
- Smoke-Test-CLI `cli.data_status` fuer Rohdatenverfuegbarkeit angelegt.
- Keine Schema-Migration und keine Aenderung an `legacy/current_system/`.

AP1:

- Datenmodell-Entwurf und Schema-Plan in `docs/data-model.md` dokumentiert.
- Bestehende Tabellen aus `init.sql` und dem ehemaligen Full-Dump `stocks_db.sql` in Rohdaten, Legacy-Settings, Legacy-Snapshots, Live-Betrieb und Research eingeordnet.
- Zieltabellen fuer Mandanten, Portfolios, Universen, Benchmarks, Strategieinstanzen, Evaluation-Runs und Live-Betrieb festgelegt.
- Migrationsreihenfolge AP2 bis AP6 definiert.
- Entscheidung festgehalten: `init.sql` bleibt vorerst Legacy-kompatibel; AP1 fuehrt noch keine Schema-Migration aus.

AP0:

- Bestehende Module nach `legacy/current_system/` verschoben:
  - `core/`
  - `cli/`
  - `research/`
  - `shared/`
- Neue leere Paketstruktur angelegt:
  - `data/`
  - `universes/`
  - `indicators/`
  - `strategies/`
  - `simulation/`
  - `evaluation/`
  - `live/`
  - `cli/`
  - `shared/`
- Paketmarker `__init__.py` fuer die neue Struktur angelegt.
- README auf den AP0-Stand aktualisiert.
- `AGENTS.md` auf die neue Legacy-/Framework-Struktur aktualisiert.
- `.gitignore` um lokale IDE-/Venv-Verzeichnisse erweitert.
- `compileall` fuer Legacy und neue Paketstruktur erfolgreich ausgefuehrt.

Geprueft AP0:

```bash
python3 -m compileall legacy/current_system
python3 -m compileall data universes indicators strategies simulation evaluation live cli shared
```

Wichtiger Hinweis:

- Die Legacy-CLI verwendet weiterhin alte absolute Imports wie `core.*` und `shared.*`.
- Legacy-Kommandos daher vorerst mit Legacy-Pythonpfad ausfuehren, z. B.:

```bash
docker compose run --rm -e PYTHONPATH=/app/legacy/current_system app python -m cli.core_main daily
```

Naechster Schritt:

- AP7: Erste Value/Quality/Momentum-Strategie mit AP6-Indikatoren bauen.

## Zielbild

Das neue System soll aus dem aktuellen operativen Quant-Portfolio-Projekt ein schlankes, erweiterbares Quant-Framework machen. Kernfrage:

```text
Schlaegt eine Strategie mit bestimmten Parametern, Indikatoren, Datenquellen und einem definierten Universum ihren passenden Benchmark?
```

Das System bleibt bewusst nach Occams Rasiermesser gebaut: Rohdaten sauber speichern, Strategien modular machen, Experimente kompakt auswerten, Live-Entscheidungen auditierbar halten und nichts dauerhaft speichern, was guenstig reproduzierbar ist.

## Was Das System Leisten Soll

- Mehrere Portfolios verwalten, spaeter mandantenfaehig mit `tenant_id`.
- Pro Portfolio Strategie, Universum, Benchmark, Datenquelle/API, Indikatoren und Parameter aendern koennen.
- Strategien gegeneinander evaluieren: Backtests, Parameter-Sweeps, Equity Curves, Benchmark-Vergleich.
- Live-Betrieb unterstuetzen: Model Portfolio, Shadow Portfolio, Real Portfolio, Execution Gap, manuelle Trades, Cash-Ledger.
- Pro Client/Portfolio/Run vollstaendig tracken, welche Konfiguration verwendet wurde.
- Tests und Experimente ohne API-Zugriff mit `fixtures/raw_market_data.sql` ermoeglichen.
- Weboberflaeche erst ganz am Schluss bauen, wenn Kern, Datenmodell und Workflows stabil sind.

## Behalten, Aendern, Weglassen

### Behalten

- Rohdatenbasis aus `tickers`, `daily_candles`, `financial_reports`, `market_cap_snapshots`.
- Docker/MySQL-Grundsetup.
- Manuelle Trade-Erfassung.
- Cash-/Trade-Historie.
- Performance-Vergleich gegen Benchmark.
- Bereinigte Rohdaten-Fixture `fixtures/raw_market_data.sql` als Test- und Demo-Datenbasis.

### Aendern

- Strategien, Indikatoren, APIs, Universen und Benchmarks werden austauschbare Bausteine.
- `.env` enthaelt nur technische Zugaenge und Secrets.
- Fachliche Settings liegen versioniert in der DB.
- Operative Snapshots bleiben nur dort, wo Auditierbarkeit noetig ist.

### Weglassen Oder Reduzieren

- Keine grosse starre `strategy_settings`-Tabelle mit immer mehr Spalten.
- Keine Snapshot-Flut im Evaluation-System.
- Keine uebertriebene OO-/ORM-Struktur.
- Keine dauerhafte Speicherung billiger Zwischenberechnungen.

## Zielarchitektur

```text
legacy/current_system/
  eingefrorene Referenz des bisherigen operativen Systems

data/
  Datenzugriff, Provider-Adapter, Rohdaten-Normalisierung

universes/
  auswaehlbare Anlageuniversen und deren Mitglieder

indicators/
  modulare Indikatoren und Indikatorparameter

strategies/
  austauschbare Strategie-Logik

simulation/
  Portfolio-Simulation, Rebalancing, Kosten, Steuern

evaluation/
  Backtests, Parameter-Sweeps, Benchmark-Vergleich, Kennzahlen

live/
  Model Portfolio, Shadow Portfolio, Real Portfolio, Execution Gap

cli/
  Runs, Status, Experimente, Reports
```

Objektorientierung wird nur fuer austauschbare Konzepte eingesetzt: `Strategy`, `Indicator`, `DataProvider`, `UniverseLoader`, `Benchmark`, `PortfolioSimulator`, `CostModel`, `TaxModel`, `ExperimentRunner`. Massendaten bleiben in SQL/DataFrames.

Die austauschbaren Konzepte bekommen klare Python-Schnittstellen, bevorzugt als `typing.Protocol` oder, falls gemeinsame Basislogik noetig ist, als abstrakte Basisklassen. Neue Module sollen dadurch nicht nur in passenden Ordnern liegen, sondern einen expliziten Vertrag erfuellen:

- `DataProvider`: liefert Rohdaten wie Preise, Fundamentals, Ticker und Benchmark-Zeitreihen.
- `UniverseLoader`: liefert die Mitglieder eines Anlageuniversums fuer einen Stichtag.
- `Indicator`: berechnet aus definierten Eingabedaten reproduzierbare Kennzahlen.
- `Strategy`: erzeugt aus Kontext, Universum, Daten und Indikatoren Rankings, Signale oder Model-Portfolios.
- `Benchmark`: beschreibt und laedt die Vergleichsreihe fuer Evaluation und Reporting.
- `PortfolioSimulator`, `CostModel`, `TaxModel`: simulieren Umsetzung, Kosten und Steuereffekte.

Jede Schnittstelle dokumentiert Eingaben, Rueckgabeformat, Fehlerverhalten und minimale Validierung. Fuer tabellarische Massendaten bleiben `pandas.DataFrame` und SQL-nahe Datenzugaenge erlaubt; der Vertrag legt aber Spalten, Datentypen und Semantik fest.

## Umgang Mit Dem Altsystem

Das neue System wird als neues Framework parallel zum bestehenden operativen System gebaut. Die vorhandenen Module werden nicht schrittweise im bestehenden `core/` verbogen, sondern zuerst als Legacy-Referenz eingefroren.

Geplante Ablage:

```text
legacy/current_system/
  core/
  cli/
  research/
  shared/
```

Die Legacy-Version bleibt lesbar und lauffaehig genug, um bestehende Logik fuer Faktorberechnung, Portfolio-Build, Shadow Portfolio, Trade Plan, Cash-/Trade-Erfassung und Performance-Vergleich als Referenz zu nutzen.

Nicht blind verschoben werden zunaechst:

```text
init.sql
fixtures/raw_market_data.sql
docker-compose.yml
Dockerfile
setup.sh
requirements.txt
simfin/
docs/
```

Diese Dateien werden separat bewertet, weil sie Rohdaten, Infrastruktur, Demo-/Fixture-Daten oder Dokumentation betreffen und auch fuer das neue System relevant bleiben koennen.

Erster vertikaler Schnitt des neuen Systems:

```text
bestehende DB/Fixture-Daten lesen
-> Universum laden
-> Strategie ausfuehren
-> Benchmark vergleichen
-> Run-Ergebnis speichern oder anzeigen
```

## Datenmodell Grundidee

Dauerhaft gespeicherte Rohdaten:

```text
tickers
daily_candles
financial_reports
market_cap_snapshots
```

Neue Konfigurations- und Katalogtabellen:

```text
tenants
portfolios
universes
universe_members
data_providers
benchmarks
strategy_instances
```

`strategy_instances` enthaelt versionierte fachliche Konfigurationen:

```text
strategy_key
params_json
indicators_json
universe_id
benchmark_id
provider_config_id
valid_from
valid_to
is_active
```

Experiment-/Evaluation-Ergebnisse werden kompakt gespeichert:

```text
strategy_runs
strategy_run_metrics
strategy_run_equity_curve
strategy_run_trades
```

Live-Betrieb bleibt getrennt:

```text
live_trade_executions
cash_ledger
portfolio_positions
shadow_portfolio_state
```

## Shadow Portfolio

Das Shadow Portfolio bleibt im Live-Betrieb erhalten:

```text
Model Portfolio   = reine Strategieauswahl
Shadow Portfolio  = regelkonforme Soll-Umsetzung
Real Portfolio    = tatsaechlich ausgefuehrte Trades
Execution Gap     = Abweichung zwischen Shadow und Real
```

Im Evaluation-System wird dasselbe Konzept als simuliertes Portfolio mit Holdings, Trades und Equity Curve behandelt.

## Dynamische Bausteine

Clients koennen spaeter pro Portfolio auswaehlen oder aendern:

- Universum: z. B. S&P 500, Nasdaq 100, ETFs, eigene Watchlist.
- Datenquelle/API: z. B. yfinance, SimFin, CSV, spaeter weitere Provider.
- Benchmark: z. B. `SPY`, `QQQ`, `IWM`, eigener Marktindex.
- Strategie: z. B. Value/Quality/Momentum, Momentum, Quality, Low Volatility.
- Indikatoren und deren Parameter.
- Gewichtungen, Portfolio-Groesse, Buy-/Sell-Regeln, Rebalance-Frequenz.
- Kostenmodell und Steuermodell.

Aenderungen ueberschreiben keine Historie. Jede Aenderung erzeugt eine neue versionierte Strategieinstanz oder einen neuen Run-Snapshot.

## Arbeitspakete

Die Umsetzung erfolgt in kleinen, pruefbaren Arbeitspaketen. Jedes Paket endet mit einem lauffaehigen Zustand, einer kurzen Dokumentation der getroffenen Entscheidung und mindestens einer technischen Pruefung.

Dokumentationsregel:

- Jede implementierte Aenderung wird in `README.md` dokumentiert, sofern sie Setup, Architektur, Bedienung, Datenmodell, Strategie, Tests oder Operator-Workflows betrifft.
- Die README beschreibt immer den aktuellen lauffaehigen Stand, nicht nur das Zielbild.
- Neue CLI-Befehle, Datenbanktabellen, Standardkonfigurationen und Testpfade werden mit Beispiel dokumentiert.
- Detaildokumente in `docs/` duerfen ergaenzen, ersetzen aber nicht die kurze Orientierung in `README.md`.

### AP0: Projektbasis Und Legacy-Schnitt

Ziel:

- Bestehendes System als Referenz einfrieren.
- Neue Zielstruktur anlegen.
- Sicherstellen, dass keine IDE-, Venv- oder Cache-Dateien versehentlich Teil des Projekts werden.
- README initial auf das neue System ausrichten und den bisherigen Stand klar als Legacy/Referenz markieren.

Umfang:

- `.gitignore` fuer lokale Arbeitsdateien pruefen/ergaenzen.
- Bestehende Module nach `legacy/current_system/` verschieben:
  - `core/`
  - `cli/`
  - `research/`
  - `shared/`
- Neue leere Paketstruktur anlegen:
  - `data/`
  - `universes/`
  - `indicators/`
  - `strategies/`
  - `simulation/`
  - `evaluation/`
  - `live/`
  - `cli/`
  - `shared/`
- Imports noch nicht fachlich migrieren, sondern nur den sauberen Schnitt herstellen.
- README mit Zweck, Default-Use-Case und aktuellem Projektstatus aktualisieren.

Tests/Akzeptanz:

- `python3 -m compileall legacy/current_system`
- Neue Pakete sind importierbar, z. B. `python3 -m compileall data universes indicators strategies simulation evaluation live cli shared`
- `git status` zeigt nur erwartete Verschiebungen und neue Struktur.
- README erklaert, was das neue System macht und was der Default-Fall ist.

### AP1: Datenmodell-Entwurf Und Schema-Plan

Ziel:

- Neues Datenmodell konkretisieren, ohne sofort das bestehende Schema zu zerstoeren.
- Bestehende Tabellen aus `init.sql` den Bereichen Rohdaten, Konfiguration, Evaluation und Live zuordnen.

Umfang:

- Tabelleninventar aus `init.sql` dokumentieren.
- Zieltabellen fuer Portfolio, Universum, Benchmark, Provider, Strategieinstanzen und Runs definieren.
- Entscheiden, welche bestehenden Tabellen unveraendert weitergenutzt werden.
- Migrationsstrategie festlegen: neues `schema_v2.sql` oder additive Migrationen.

Tests/Akzeptanz:

- Dokumentierte Mapping-Tabelle: Alt-Tabelle -> neue Rolle -> behalten/aendern/ersetzen.
- SQL-Syntaxcheck fuer neue Schema-Datei, sofern bereits erstellt.
- Keine Veraenderung an operativen Daten ohne explizite Migration.

### AP2: Fixture-/Demo-Daten Lauffaehig Machen

Ziel:

- Entwicklung und Tests ohne API-Zugriff ermoeglichen.
- `fixtures/raw_market_data.sql` als reproduzierbare Rohdatenbasis nutzbar machen.

Umfang:

- Dokumentieren, wie `fixtures/raw_market_data.sql` lokal in MySQL geladen wird.
- Kleinen Health-Check fuer vorhandene Kerzen, Ticker, Fundamentals und Benchmark-Daten bauen.
- Minimalen Test-Datensatz definieren, falls der Dump zu gross oder sensibel ist.

Tests/Akzeptanz:

- Datenbank kann aus Fixture neu aufgebaut werden.
- Health-Check meldet Anzahl Ticker, Preisreihen, Fundamentals und Benchmark-Verfuegbarkeit.
- Keine externen API-Calls fuer diesen Testpfad.

### AP3: Modul-Contracts Und Data-Provider-Schicht

Ziel:

- Die neue Modularitaet ueber klare Schnittstellen standardisieren.
- Rohdatenzugriff von Strategie- und Evaluationslogik trennen.
- Sicherstellen, dass neue Strategien, Indikatoren, Universen und Provider einen bekannten Vertrag erfuellen.

Umfang:

- `Protocol`- oder ABC-basierte Basis-Schnittstellen definieren:
  - `DataProvider`
  - `UniverseLoader`
  - `Indicator`
  - `Strategy`
  - `Benchmark`
- Ersten Provider fuer bestehende MySQL-/Fixture-Daten bauen.
- Spaeteren yfinance-Provider nur vorbereiten, nicht als Voraussetzung fuer Tests machen.
- Gemeinsame Rueckgabeformate fuer Preise, Fundamentals, Ticker und Benchmarks festlegen.
- Gemeinsame Kontext-/Resultattypen skizzieren, z. B. `StrategyContext`, `StrategyResult`, `IndicatorResult`.
- Schnittstellen mit kurzen Docstrings dokumentieren: erwartete Eingaben, Rueckgaben, Fehlerfaelle.

Tests/Akzeptanz:

- Neue Contract-Module sind importierbar und mit `compileall` geprueft.
- Ein Beispiel-Provider und ein Beispiel-Universe-Loader erfuellen die definierten Schnittstellen.
- Provider liefert Preisreihen fuer ein Ticker-Set und einen Zeitraum.
- Provider liefert Benchmark-Reihe fuer z. B. `SPY`.
- Unit-Tests oder CLI-Smoke-Test laufen gegen Fixture-Daten.

### AP4: Linux-Umzug Und Lokale Toolchain

Status: abgeschlossen.

Ausloeser:

- In AP3 gab es Entwicklungs- und Toolchain-Probleme unter Windows mit WSL.
- Bevor weitere Fachlogik gebaut wird, zieht die Entwicklung auf eine stabile Linux-Umgebung um.

Ziel:

- Die Entwicklungsumgebung vollstaendig auf Linux ausrichten, bevor weitere Fachlogik gebaut wird.
- Eine reproduzierbare lokale Basis fuer venv, Requirements, Docker, MySQL und Fixture-Daten herstellen.

Umfang:

- Windows-venv nicht weiter als Projektstandard verwenden.
- Linux-venv `.venv` als Standard festlegen.
- `requirements.txt` in der Linux-venv installieren und mit `pip check` pruefen.
- Docker-/Compose-Zugriff auf der Linux-Umgebung stabilisieren.
- `.env.example`, `.env` und `docker-compose.yml` so abgleichen, dass `MYSQL_ROOT_PASSWORD`, `DB_NAME`, `DB_USER` und `DB_PASSWORD` sicher gesetzt sind.
- DB-Container mit frischem Volume neu erstellen.
- Fixture-/Demo-Daten laden oder den init-Pfad eindeutig dokumentieren.
- AP3-Smoke-Commands lokal gegen die Linux-venv und gegen Docker ausfuehren.

Tests/Akzeptanz:

- `.venv/bin/python -m pip install -r requirements.txt` laeuft erfolgreich.
- `.venv/bin/python -m pip check` meldet keine kaputten Abhaengigkeiten.
- `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared` laeuft erfolgreich.
- `docker compose up -d db` startet MySQL healthy.
- `docker compose run --rm app python -m cli.data_status --details` laeuft gegen die lokale DB.
- `docker compose run --rm app python -m cli.framework_status --benchmark-ticker SPY` laeuft gegen die lokale DB.

Aktueller Linux-Befund:

- `.venv-linux` wurde entfernt; der Linux-Standard ist jetzt `.venv`.
- `.venv` ist angelegt und hat funktionierendes pip mit installierten Requirements.
- `.venv/bin/python -m pip check` meldet keine kaputten Abhaengigkeiten.
- Lokale und Container-Compilechecks fuer Legacy und neue Paketstruktur laufen erfolgreich.
- Docker/Compose funktioniert ausserhalb der Sandbox; `sp500_db` ist healthy,
  `sp500_worker` und `sp500_pma` laufen.
- `fixtures/raw_market_data.sql` ist in die lokale `stocks_db` geladen.
- Die lokale `stocks_db` enthaelt nach AP4 bewusst nur noch die vier Rohdatentabellen
  `tickers`, `daily_candles`, `financial_reports` und `market_cap_snapshots`.
- Der vollstaendige Legacy-Dump `stocks_db.sql` wurde nach erfolgreicher
  Fixture-Erzeugung und Smoke-Pruefung geloescht, um Trade-, Cash- und
  Portfolio-Historie nicht als Standard-Fixture zu behalten.
- Lokale und Container-Smoke-Checks fuer `cli.data_status --details` und
  `cli.framework_status --benchmark-ticker SPY` laufen erfolgreich.
- `cli.data_status --details` zeigt Fundamentaldaten jetzt nach `annual` und
  `ttm` getrennt mit `report_dates` und `imported`, damit Report-Stichtage
  nicht mit Import-Zeitpunkten verwechselt werden.
- Legacy-Health lief vor der Bereinigung mit dem Full-Dump. Nach Umstellung auf
  die Rohdaten-Fixture ist Legacy-Health nicht mehr der AP4-Standardcheck, weil
  Legacy-/Live-Snapshot-, Cash- und Portfolio-Tabellen bewusst fehlen.

### AP5: Universen Und Benchmarks

Status: erledigt in AP21.

Verifikation:

- `.venv/bin/python -m pytest tests/test_capabilities.py tests/test_data_sync.py tests/test_orchestration.py`
- `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`

Ziel:

- Anlageuniversum und Benchmark als austauschbare Konfiguration behandeln.

Umfang:

- Tabellen/Modelle fuer `universes`, `universe_members`, `benchmarks` konkretisieren.
- Loader fuer ein erstes Universum bauen, z. B. S&P 500 aus bestehender DB, gemaess `UniverseLoader`-Contract.
- Benchmark-Resolver bauen, gemaess `Benchmark`-/`DataProvider`-Contract.

Tests/Akzeptanz:

- CLI oder Test zeigt Mitglieder eines Universums.
- Benchmark kann pro Run eindeutig geladen werden.
- Fehlerfall wird sauber gemeldet, wenn Benchmark-Daten fehlen.

### AP6: Indikator-Engine

Ziel:

- Indikatoren modular berechnen, statt sie fest in eine Pipeline zu giessen.

Umfang:

- `Indicator`-Contract aus AP3 verwenden und bei Bedarf konkretisieren.
- Erste Indikatoren aus der bestehenden Strategie extrahieren:
  - Momentum/Return
  - Relative Staerke
  - einfache Value-/Quality-Kennzahlen, soweit Daten vorhanden sind
- Parameterisierung pro Indikator ermoeglichen.

Tests/Akzeptanz:

- Indikatorberechnung ist fuer denselben Datenstand reproduzierbar.
- Fehlende Daten erzeugen definierte `NULL`/NaN-Behandlung statt stiller Fehlbewertung.
- Mindestens ein kleiner Test mit Fixture-Daten.

### AP7: Erste Strategie Value/Quality/Momentum

Ziel:

- Die bestehende Hauptstrategie als modulare Strategieinstanz nachbauen.

Umfang:

- `Strategy`-Contract aus AP3 verwenden und bei Bedarf konkretisieren.
- Value/Quality/Momentum-Strategie mit konfigurierbaren Gewichten bauen.
- Ranking und Buy-/Sell-relevante Scores erzeugen.
- Ergebnis zunaechst nur als Model Portfolio ausgeben.

Tests/Akzeptanz:

- Strategie erzeugt fuer einen Stichtag eine reproduzierbare Rangliste.
- Gewichte werden validiert und muessen zusammen 1.0 ergeben.
- Vergleich gegen Legacy-Ergebnis fuer einen bekannten Stichtag, soweit Daten vorhanden sind.

### AP8: Evaluation Und Backtest

Ziel:

- Strategien gegen Benchmark evaluieren.

Umfang:

- `strategy_runs` und Ergebnisstruktur implementieren.
- Einfachen Backtest mit Rebalancing, Kostenmodell und Equity Curve bauen.
- Kennzahlen berechnen: Rendite, Benchmark-Rendite, Outperformance, Volatilitaet, Max Drawdown.
- Parameter-Sweeps vorbereiten.

Tests/Akzeptanz:

- Ein Run ist reproduzierbar speicherbar oder als Report ausgebbar.
- Equity Curve und Benchmark Curve haben konsistente Datumsachsen.
- Backtest laeuft komplett gegen Fixture-Daten.

### AP9: Live-System Wieder Anbinden

Ziel:

- Model, Shadow, Real und Execution Gap im neuen System abbilden.

Umfang:

- Bestehende Konzepte aus Legacy uebernehmen:
  - Model Portfolio
  - Shadow Portfolio
  - Real Portfolio
  - Cash Ledger
  - manuelle Trade-Ausfuehrung
- Live-Tabellen von Evaluation-Tabellen trennen.
- Auditierbare Snapshots nur dort speichern, wo sie fuer Live-Entscheidungen noetig sind.

Umsetzung:

- Read-only Live-Status im neuen `live/`-Paket angelegt.
- Execution Gap zwischen Shadow-Ziel und realem Portfolio berechnet.
- Legacy-kompatible Tabellen `portfolio_snapshots`, `portfolio_positions` und
  `portfolio_cash` werden gelesen.
- `cli.live_status` zeigt Model/Shadow/Real-Anzahlen, Cash, investierten Wert
  und actionable Gaps.
- `LiveExecutionService` schreibt Cash-Bewegungen und manuelle Trades in die
  bestehenden Legacy-kompatiblen Live-Tabellen.
- `cli.live_cash` und `cli.live_trade` stellen die Write-Seite ohne
  Legacy-`PYTHONPATH` bereit.

Tests/Akzeptanz:

- Aktives Portfolio zeigt Model, Shadow, Real und Execution Gap.
- Manuelle Trade-Ausfuehrung veraendert Cash und Positionen nachvollziehbar.
- Cash-Bewegungen veraendern Ledger und aktuellen Cash-Saldo nachvollziehbar.

### AP10: CLI Und Operator-Workflows

Ziel:

- Das neue System ohne Weboberflaeche bedienbar machen.

Umfang:

- CLI fuer Fixture-Health, Universum, Strategie-Run, Backtest, Status und Live-Aktionen.
- Klare Fehlerausgaben fuer fehlende Daten, falsche Konfiguration und leere Ergebnisse.
- Bestehende Operator-Dokumentation aktualisieren.

Tests/Akzeptanz:

- `compileall` fuer alle neuen und Legacy-Pakete.
- Smoke-Test: Fixture laden -> Strategie-Run -> Benchmark-Report.
- Status-CLI zeigt verwertbare Ausgabe ohne Weboberflaeche.

Status:

- Abgeschlossen.
- Verifikation:
  - `.venv/bin/python -m pytest tests`
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  - `.venv/bin/python -m compileall legacy/current_system`
  - `.venv/bin/python -m cli.operator_smoke --ranking-limit 0 --trade-limit 0`
  - `.venv/bin/python -m cli.live_status --limit 3`

### AP11: Modularer Data-Sync Als Legacy-Ersatz

Ziel:

- Preis-, Benchmark-, Ticker- und Fundamental-Daten ohne Legacy-Imports im
  neuen `data/`-Paket aktualisieren koennen.

Umfang:

- Bestehendes Legacy-Verhalten aus `core.sync_prices` und
  `core.sync_fundamentals` fachlich uebernehmen.
- Provider-Adapter fuer yfinance klar vom Repository trennen.
- Inkrementelle Candle-Updates ueber `MAX(date)` je Ticker abbilden.
- Benchmark `SPY` analog zu normalen Candles aktualisieren.
- S&P-500-Tickerliste aktualisieren und in `tickers` upserten.
- Fundamentals und Market-Cap-Snapshots aktualisieren.
- Neue CLIs bereitstellen:
  - `cli.sync_prices`
  - `cli.sync_fundamentals`
  - optional `cli.sync_data`
- Legacy-Code bleibt Referenz, wird aber nicht mehr vom neuen Pfad importiert.

Tests/Akzeptanz:

- Unit-Tests fuer Normalisierung, Startdatum-Logik und Upsert-Verhalten.
- Dry-/Smoke-Run gegen Fixture-DB ohne externe API-Abhaengigkeit.
- Echter manueller Run kann fehlende Candles bis zum aktuellen Stand nachziehen.
- Neue CLIs laufen ohne `PYTHONPATH=/app/legacy/current_system`.

Status:

- Abgeschlossen.
- Implementiert:
  - `data.sync`
  - `data.yahoo`
  - write-seitige AP11-Methoden in `data.repository`
  - `cli.sync_prices`
  - `cli.sync_fundamentals`
  - `cli.sync_data`
- Verifikation:
  - `.venv/bin/python -m pytest tests`
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  - `.venv/bin/python -m compileall legacy/current_system`
  - `.venv/bin/python -m cli.sync_prices --dry-run --plan-limit 3`
  - `.venv/bin/python -m cli.sync_fundamentals --dry-run --plan-limit 3`

### AP12: Neue Daily-/Monthly-Orchestrierung

Ziel:

- `daily` und `monthly` als neue modulare Operator-CLIs bereitstellen, ohne
  `legacy/current_system/cli/core_main.py`.

Umfang:

- `cli.daily_run` orchestriert:
  - modularen Data-Sync
  - Indikator-/Strategie-Run
  - optional Performance-/Status-Ausgabe
- `cli.monthly_run` orchestriert:
  - Strategie-Run zum letzten Handelstag
  - Model-Portfolio-Erzeugung
  - Shadow-/Rebalance-/Trade-Plan-Schritte, soweit in AP13 persistierbar
- Einheitliche Fehlerausgaben ueber `cli.errors`.
- Bestehende `cli.operator_smoke` bleibt schneller Health-Check, ersetzt aber
  nicht den echten Daily-/Monthly-Run.

Tests/Akzeptanz:

- Daily-CLI laeuft gegen Fixture-Daten reproduzierbar durch.
- Monthly-CLI erzeugt denselben fachlichen Stichtag wie die Legacy-Pipeline.
- Fehler bei fehlenden Rohdaten, leerem Universum oder fehlendem Benchmark sind
  operator-verstaendlich.
- Legacy-Daily kann parallel als Rueckfallpfad bestehen bleiben.

Status:

- Abgeschlossen.
- Implementiert:
  - `cli.orchestration`
  - `cli.daily_run`
  - `cli.monthly_run`
- `cli.daily_run` orchestriert AP11-Data-Sync und den modularen
  Strategie-/Model-Portfolio-Run. Fuer Fixture-/Smoke-Laeufe steht
  `--dry-run-sync` bereit, damit keine externen API-Calls oder Writes
  erforderlich sind.
- `cli.monthly_run` verwendet denselben fachlichen Stichtag wie der modulare
  Daily-/Strategiepfad: den letzten verfuegbaren Handelstag aus den
  Rohpreisen, sofern kein `--as-of-date` uebergeben wird.
- Shadow-, Rebalance- und Trade-Plan-Persistenz wurden anschliessend in AP13
  umgesetzt.
- Verifikation:
  - `.venv/bin/python -m pytest tests`
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  - `.venv/bin/python -m compileall legacy/current_system`
  - `.venv/bin/python -m cli.daily_run --dry-run-sync --model-limit 2`
  - `.venv/bin/python -m cli.monthly_run --model-limit 2`

### AP13: Operative Persistenz Fuer Model, Shadow Und Trade Plan

Ziel:

- Die neue Monthly-Pipeline schreibt die operativen Artefakte, die bisher aus
  Legacy kommen.

Umfang:

- Model Portfolio Snapshot aus Strategie-Ranking persistieren.
- Tradable Shadow Portfolio erzeugen und persistieren.
- Rebalance-Vorschlaege und Decision Log erzeugen.
- Trade Plan und Trade Plan Summary schreiben.
- Settings-Snapshot zum Stichtag einfrieren.
- Idempotenzregeln definieren: existierende Snapshots nicht unabsichtlich
  ueberschreiben.
- Legacy-kompatible Tabellen duerfen weiterverwendet werden, solange die
  Migration noch nicht abgeschlossen ist.

Tests/Akzeptanz:

- Monthly-Run erzeugt nachvollziehbare Snapshots fuer einen Stichtag.
- Wiederholter Run erkennt bestehende Snapshots und bricht kontrolliert ab oder
  nutzt explizite `--force`/`--replace`-Semantik.
- `cli.live_status` kann die neu erzeugten Model-/Shadow-Snapshots lesen.
- Trade-Plan-Daten koennen mit `cli.live_trade --trade-plan-action ...`
  validiert werden.
- Status: abgeschlossen und per lokaler Testsuite sowie Docker/MySQL-Smoke
  verifiziert.

### AP14: Legacy-Unabhaengiges Schema Und Operativer Cutover

Ziel:

- Der neue modulare Pfad nutzt im normalen Betrieb weder Legacy-Python-Code noch
  legacy-kompatible operative Tabellen als Quelle der Wahrheit.

Umfang:

- Neues kanonisches Schema fuer Rohdaten, Strategie-Laeufe,
  Model-/Shadow-/Real-Portfolios, Cash, Trades, Rebalance-Entscheidungen und
  Trade Plans definieren.
- Entscheiden, ob die bisherigen Rohdatentabellen als neue kanonische Tabellen
  akzeptiert oder in neue Namen wie `assets`, `asset_price_bars`,
  `asset_fundamental_reports` und `asset_market_caps` migriert werden.
- Live-Repositories und Live-Schreibpfade von `portfolio_snapshots`,
  `portfolio_positions`, `portfolio_cash`, `trade_executions`, `cash_ledger`,
  `rebalance_suggestions`, `decision_log`, `trade_plan_summary` und
  `trade_plan_snapshots` auf neue Tabellen umstellen.
- Preisermittlung fuer Real-Positionen aus Legacy-`factor_metrics` entfernen
  und auf kanonische Preis-/Indicator-Daten umstellen.
- `cli.live_status`, `cli.live_cash`, `cli.live_trade` und
  `cli.monthly_run --persist` auf die neuen Tabellen migrieren.
- `init.sql` und Fixtures so aktualisieren, dass Smoke- und Regressionstests
  ohne Legacy-/Live-Altbestand laufen.
- Operator-Dokumentation von Legacy-CLIs und `PYTHONPATH=/app/legacy/current_system`
  als Standardpfad bereinigen; Legacy bleibt hoechstens als archivierte
  Referenz dokumentiert.
- Nach erfolgreichem Cutover pruefen, ob `legacy/current_system/` im Repo
  geloescht, ausgelagert oder nur noch als nicht-operatives Archiv behalten
  wird.

Tests/Akzeptanz:

- Kein neues Top-Level-Modul importiert Legacy-Code oder `shared.settings`.
- Modularer Smoke-Pfad laeuft gegen eine Datenbank, die nur das neue
  kanonische Schema enthaelt.
- `cli.daily_run`, `cli.monthly_run --persist`, `cli.live_status`,
  `cli.live_cash` und `cli.live_trade` funktionieren ohne Legacy-Tabellen.
- Regressionstests decken Migration, Live-Status, Cash, Trades und
  Monthly-Persistenz auf dem neuen Schema ab.
- Dokumentation nennt Legacy nicht mehr als operativen Standardpfad.
- Status: abgeschlossen. Fokussierte Tests fuer Rohdaten, Live-Operations,
  Live-Execution, Live-Status und CLI-Fehler wurden lokal ausgefuehrt.

### AP15: Crontab-Betrieb Fuer Daily Und Monthly

Status: abgeschlossen.

Ziel:

- Den operativen Lauf zunaechst einfach per Host-Crontab automatisieren.

Umfang:

- Dokumentierte Crontab-Eintraege fuer:
  - Daily-Run an Handelstagen bzw. Werktagen nach Marktschluss
  - Monthly-Run am Monatsanfang oder bewusst definierten Monatstag
- `flock` gegen parallele Runs verwenden.
- Logs nach festen Dateien schreiben.
- Cron-Eintraege nutzen nur die neuen modularen CLIs aus AP14; Legacy-Fallbacks
  werden nicht als Standard-Cronpfad dokumentiert.
- Operator-Dokumentation fuer manuelles Testen, Logpruefung und Fehlerfall.

Tests/Akzeptanz:

- Dokumentierter Cron-Befehl kann manuell erfolgreich ausgefuehrt werden.
- Parallelausfuehrung wird durch Lock verhindert.
- Logs enthalten Start, Ende und Fehlerdetails.
- Dokumentation beschreibt den modularen Cron-Befehl als einzigen regulaeren
  Betriebsweg.

### AP16: Live-/Shadow-/Benchmark-Performance-Reporting

Status: abgeschlossen.

Ziel:

- Eine belastbare Performance-Sicht fuer den operativen Pfad schaffen, bevor
  eine UI gebaut wird.
- Real Portfolio, Shadow Portfolio und Benchmark vergleichbar bewerten.

Umfang:

- Live-Performance-Repository/Service entwerfen.
- Real Portfolio aus `live_positions`, `live_cash_balances` und historischen
  Preisen bewerten.
- Shadow Portfolio aus `portfolio_target_items` und historischen Preisen
  bewerten.
- Benchmark, initial `SPY`, aus `asset_price_bars` normalisiert vergleichen.
- CLI `cli.live_performance` bereitstellen.
- Ergebnisse fuer AP16 read-only berechnen; Persistenz in
  `performance_snapshots` bleibt optional fuer eine spaetere AP.

Tests/Akzeptanz:

- Report zeigt Real-, Shadow- und Benchmark-Wertreihe fuer einen Zeitraum.
- Report zeigt Rendite, Outperformance und Drawdown fuer Real und Shadow gegen
  Benchmark.
- Fixture-basierter Smoke laeuft ohne externe API-Zugriffe.
- Die Werte sind reproduzierbar und koennen spaeter von einer UI verwendet
  werden, ohne Berechnungslogik zu duplizieren.

Verifikation:

- `.venv/bin/python -m pytest tests/test_live_performance.py`
- `.venv/bin/python -m pytest tests`
- `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared`
- `.venv/bin/python -m cli.live_performance --help`

### AP17: Isolierte Testdatenbank Und DB-Integrationsregression

Ziel:

- Eine dedizierte Testdatenbank und eine reproduzierbare DB-Verifikation fuer
  den kanonischen modularen MySQL-Pfad einfuehren, ohne Entwicklungs- oder
  operative Datenbanken zu beruehren.

Umfang:

- Separate MySQL-Testdatenbank definieren, z. B. fuer lokale Entwicklung,
  Regression und CI.
- Testschichten klar trennen:
  - schnelle Unit-Tests ohne echte MySQL-Abhaengigkeit
  - DB-Integrations-/Regressionstests gegen echtes MySQL
- pytest-Fixtures fuer Schema-Initialisierung, Fixture-Loading und Isolierung
  der Testdatenbank bereitstellen.
- Relevante Repository-, Persistenz- und CLI-Pfade mit echter MySQL-Verifikation
  absichern.
- Dokumentierte Standardbefehle fuer schnellen lokalen Testlauf und
  vollstaendige DB-Verifikation bereitstellen.

Tests/Akzeptanz:

- `python -m pytest tests -m "not integration"` bleibt schnell und ohne echte
  MySQL-Testdatenbank nutzbar.
- `scripts/db_integration_tests.sh` laeuft reproduzierbar gegen die isolierte
  MySQL-Testdatenbank `quant4free_test` auf dem Compose-Service `db_test`.
- DB-nahe Tests verifizieren mindestens Schema, Repository-Zugriffe, Persistenz
  und relevante CLI-Pfade gegen echtes MySQL-Verhalten.
- Die normale Entwicklungsdatenbank und operative Daten werden von
  Testlaeufen nicht veraendert.

Status: abgeschlossen in AP17.

### AP18: Assetklassen, Universen Und Daten-Capabilities

Ziel:

- Das Datenmodell so beschreiben und vorbereiten, dass neue Universen mit
  unterschiedlichen Datenarten sauber abgebildet werden koennen, z. B. Aktien
  mit Fundamentaldaten, Krypto nur mit Kerzen oder spaetere Assetklassen mit
  eigenen Zusatzdaten.

Umfang:

- `assets` als allgemeinen Asset-Katalog beschreiben, nicht als reine
  S&P-/Aktien-Tickerliste.
- Universen als historisierte Asset-Auswahl modellieren:
  `universes` und `universe_members`.
- Datenarten fachlich trennen:
  - Preisbars als generische Zeitreihe fuer handelbare Assets
  - Fundamentaldaten als aktienspezifische Datenart
  - Market Caps als eigene Zeitreihe
  - neue assetklassenspezifische Tabellen fuer Zusatzdaten, falls notwendig
- Provider- und Strategie-Capabilities dokumentieren, z. B. `prices`,
  `fundamentals`, `market_caps`, `crypto_metrics`.
- Validierungsregeln entwerfen, damit eine Strategie nur mit Universen laeuft,
  deren Assetklassen und Datenarten ihre Anforderungen erfuellen.
- Migrationspfad vom aktuellen ticker-basierten Schema zu stabileren
  Asset-Schluesseln beschreiben.

Tests/Akzeptanz:

- Dokumentation beantwortet explizit, welche Datenarten zu welcher Assetklasse,
  welchem Universum und welcher Strategie gehoeren.
- Der Entwurf zeigt mindestens zwei Faelle:
  - Aktienuniversum mit Preisen, Fundamentaldaten und Market Caps
  - Krypto-Universum mit Preisen, aber ohne Fundamentaldaten
- Es ist klar definiert, wann neue Zusatzdaten eine eigene Tabelle bekommen und
  wie Strategien diese Daten als Capability deklarieren.
- AP18 bleibt Entwurfs- und Dokumentationsarbeit; Schema- und Codeaenderungen
  erfolgen in spaeteren Implementierungs-APs.

Status: abgeschlossen in AP18.

Verifikation:

- `.venv/bin/python -m pytest tests -m "not integration"`
- `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`

### AP19: Provider-, API- und Source-Binding-Planung

Ziel:

- AP18 so schaerfen, dass Universen, Daten-Capabilities und konkrete
  API-/Provider-Quellen sauber getrennt sind.

Umfang:

- Universum, Provider, Provider-Konfiguration, Source-Rollen und Capabilities
  fachlich trennen.
- Source-of-Truth je Datenart beschreiben:
  - Membership
  - Preise
  - Fundamentals
  - Market Caps
  - Klassifikation
  - Benchmark-Preise
- Provider-Capabilities definieren, inklusive Assetklassen, Maerkten,
  Granularitaet, Mindestfeldern, Freshness, Coverage und Identifier-Schema.
- Austauschbarkeitsregeln fuer Provider dokumentieren, damit z. B.
  Yahoo Finance, Binance, SimFin, CSV oder kommerzielle Anbieter sauber
  verglichen werden koennen.
- Identifier- und Symbolmodell fuer provider-spezifische Symbole vorbereiten.
- Den folgenden Implementierungs-AP so anpassen, dass er Provider-Bindings
  mitprueft und nicht nur abstrakte Datenarten.

Tests/Akzeptanz:

- Dokumentation zeigt, dass ein Universum keine API ist.
- Es ist klar, wie S&P-/Nasdaq-/Equity-Provider, Binance/Krypto-Provider und
  kommerzielle Fundamental-Provider modelliert werden.
- Es ist klar, wann ein Providerwechsel fachlich gueltig ist.
- AP19 bleibt Entwurfs- und Dokumentationsarbeit; Schema- und Codeaenderungen
  erfolgen in spaeteren Implementierungs-APs.

Status: abgeschlossen in AP19.

Verifikation:

- `.venv/bin/python -m pytest tests -m "not integration"`
- `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`

### AP20: Read-only Capability- und Provider-Check

Ziel:

- Das AP18/AP19-Design als erste technische Validierung umsetzen, ohne das
  kanonische AP14-Schema zu migrieren.

Umfang:

- Capability-Schluessel fuer die bestehenden Datenarten definieren.
- Provider-, Source-Rollen- und Default-Binding-Definitionen fuer den heutigen
  Pfad definieren.
- Anforderungen der aktuellen Strategie, Indikatoren, Benchmarks und
  Live-Reports deklarieren.
- Einen read-only Checker bauen, der Universum, Provider-Bindings, vorhandene
  Daten und Anforderungen vor Strategieausfuehrungen validieren kann.
- Den heutigen Default-Pfad `sp500_active` plus `value_quality_momentum`
  mit seinen Default-Bindings unveraendert erlauben.
- Inkompatible Universums-, Provider- oder Capability-Kombinationen mit klaren
  Operator-Fehlern abbrechen.

Tests/Akzeptanz:

- Default-Capability-/Provider-Pruefung fuer S&P 500
  Value/Quality/Momentum ist gruen.
- Negative Tests zeigen fehlende Pflichtdaten, inkompatible Assetklassen,
  unpassende Provider-Bindings oder fehlende Source-Rollen.
- Keine Schemaaenderung und keine neue externe API-Abhaengigkeit.

Status: abgeschlossen in AP20.

Verifikation:

- `.venv/bin/python -m pytest tests/test_capabilities.py tests/test_orchestration.py`
- `.venv/bin/python -m compileall shared cli tests`

### AP21: Asset-Katalog und Provider-Identifier-Basis

Ziel:

- Den AP20-Checker von code-nahen Profilen in Richtung echter Asset-Metadaten
  und Provider-Identifier-Abdeckung weiterentwickeln.

Umfang:

- `assets` enthaelt jetzt `asset_class`, Canonical-/Display-Symbol,
  Instrumenttyp, Exchange, Markt, Quote-Waehrung und Primaer-Provider.
- Provider-Identifier werden in der separaten Tabelle
  `asset_provider_identifiers` modelliert.
- Fixture, Repository, Status-CLI, Setup-/Smoke-Checks und
  DB-Integrationserwartungen wurden fuer diese Linie angepasst.
- Der Capability-Checker kann supplied Asset-Metadaten und
  Provider-Identifier-Coverage validieren.
- Sicherstellen, dass der bestehende AP14/AP20-Default-Pfad unveraendert
  lauffaehig bleibt.

Status: abgeschlossen in AP21.

Verifikation:

- `.venv/bin/python -m pytest tests/test_capabilities.py tests/test_data_sync.py tests/test_orchestration.py`
- `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`

### AP22: Provider-Symbolaufloesung und Universums-Metadaten

Ziel:

- Die AP21-Identifier-Basis fuer echte Provider-/Source-Binding-Workflows
  nutzen.

Umfang:

- Provider-spezifische Symbolaufloesung in den modularen Sync-Pfad integriert.
- Explizitere Universums-Metadaten fuer Membership-Quelle, Assetklassen-Policy
  und Identifier-Anforderungen modelliert.
- Yahoo-Finance- und Wikipedia-S&P-500-Capabilities in den Provider-Katalog
  aufgenommen.
- Den bestehenden `mysql_fixture`-Default-Pfad als Referenz unveraendert
  lauffaehig halten.

Status: abgeschlossen in AP22.

Verifikation:

- `.venv/bin/python -m pytest tests/test_data_sync.py tests/test_capabilities.py`
- `.venv/bin/python -m compileall data universes shared cli tests`

### AP23: DB-Universen und historisierte Mitgliedschaft

Ziel:

- Universen als echte DB-Entitaeten modellieren, statt sie nur ueber
  Python-Keys und `assets.is_active` abzuleiten.

Umfang:

- Tabellen `universes` und `universe_members` in das kanonische Schema
  einfuehren.
- `sp500_active`, `active_tickers` und `all_tickers` als initiale
  Universe-Definitionen und Memberships migrieren.
- Universe-Loader so erweitern, dass er DB-Mitgliedschaften lesen kann.
- Fixture, Setup, Status-CLIs und Regressionstests auf die neuen Tabellen
  erweitern.

Status: abgeschlossen in AP23.

Verifikation:

- `.venv/bin/python -m pytest tests -m "not integration"`
- `.venv/bin/python -m compileall data universes cli tests`
- `scripts/db_integration_tests.sh`

### AP24: Data-Sync-Audit-Trail

Ziel:

- Daten-Syncs operator-faehig nachvollziehbar machen, ohne Logs als einzige
  Quelle fuer Status, Zaehler und Fehler zu verwenden.

Umfang:

- Tabelle `data_sync_runs` fuer Provider, Source-Rolle, Modus, Zeitfenster,
  Status, Row Counts und Fehlermeldung einfuehren.
- Preis-, Fundamental- und Membership-Syncs sollen Runs schreiben.
- Status-/Smoke-CLIs sollen die juengsten Sync-Runs anzeigen koennen.

Status: abgeschlossen in AP24.

Verifikation:

- `.venv/bin/python -m pytest tests/test_data_sync.py`
- `.venv/bin/python -m pytest tests -m "not integration"`
- `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
- `scripts/db_integration_tests.sh`

### AP25: Sync-Audit-Bedienung und Betriebshaertung

Ziel:

- Den AP24-Audit-Trail fuer den laufenden Betrieb besser nutzbar machen.

Umfang:

- Dedizierte Sync-Statusausgaben mit Filtern fuer Provider, Sync-Typ, Status
  und Zeitraum.
- Retention- und Retry-Regeln definieren: Runs werden aus Audit-Gruenden nicht
  automatisch geloescht; Retry/Backoff ist pro Provider-Request
  konfigurierbar.
- Operator-Diagnosen fuer fehlgeschlagene und stale gestartete Sync-Runs auf
  Basis von `data_sync_runs` erweitern.
- Den aktuellen Yahoo-/yfinance-Sync konservativ haerten:
  Preis-Init in kleinen Batches, Daily nicht aggressiv parallelisieren,
  Fundamentals sequentiell lassen, Sleeps sowie Retry mit Backoff und
  Circuit-Breaker fuer wiederholte Provider-Fehler einbauen.

Status: abgeschlossen in AP25.

Verifikation:

- `.venv/bin/python -m pytest tests/test_data_sync.py`
- `.venv/bin/python -m pytest tests -m "not integration"`
- `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`

### AP26: Daten-Freshness- und Qualitaetsdiagnosen

Ziel:

- Fehlende Daten, stale Daten und Provider-Identifier-Luecken vor Strategie-
  oder Live-Laeufen klarer sichtbar machen.
- Rohpreise, TTM-Fundamentals, Market Caps, Identifier-Coverage und Sync-Health
  ohne Schemaaenderung als `data_quality.*`-Diagnosen ausgeben.

Status: abgeschlossen in AP26.

Verifikation:

- `.venv/bin/python -m pytest tests/test_data_sync.py`
- `.venv/bin/python -m compileall data cli tests`

### AP27: Konfigurierbare Freshness-Preflights

Ziel:

- Freshness-Policies je Workflow und Source-Binding konfigurierbar machen.
- AP26-Diagnosen optional als fail-fast Gates fuer ausgewaehlte Strategie- und
  Live-Workflows nutzen.

Status: naechster Schritt.

## Roadmap

1. Datenmodell und Modulstruktur entwerfen.
2. `fixtures/raw_market_data.sql` als bereinigte Demo-/Fixture-Datenbasis nutzbar machen.
3. Standardisierte Modul-Contracts fuer Provider, Universen, Benchmarks, Indikatoren und Strategien einfuehren.
4. Linux-Umzug und lokale Toolchain stabilisieren: venv, Requirements, Docker, MySQL und Fixture-Daten.
5. Provider-/Universums-/Benchmark-Schicht auf stabiler Linux-Basis weiter konkretisieren.
6. Indikator-Engine bauen.
7. Erste Strategie Value/Quality/Momentum modularisieren.
8. Evaluation-System mit Backtests, Parameter-Sweeps und Benchmark-Vergleich bauen.
9. Live-System mit Model, Shadow, Real, Execution Gap und manuellen Trades anbinden.
10. Konfiguration versionieren und pro Portfolio steuerbar machen.
11. CLI/Reports stabilisieren.
12. Modularen Data-Sync als Legacy-Ersatz bauen.
13. Neue Daily-/Monthly-Orchestrierung ohne Legacy-Imports bereitstellen.
14. Operative Persistenz fuer Model, Shadow und Trade Plan migrieren.
15. Legacy-unabhaengiges Schema und operativen Cutover bauen.
16. Crontab-Betrieb fuer Daily und Monthly dokumentieren und testen.
17. Live-/Shadow-/Benchmark-Performance-Reporting bauen.
18. Isolierte Testdatenbank und DB-Integrationsregression einfuehren.
19. Assetklassen, Universen und Daten-Capabilities fuer neue Datenarten
    modellieren.
20. Provider-/API-Bindings und Source-of-Truth je Datenart planen.
21. Read-only Capability- und Provider-Check fuer bestehende Strategie- und Datenpfade
    einfuehren.
22. Asset-Katalog und Provider-Identifier-Basis konkretisieren.
23. Provider-Symbolaufloesung und explizitere Universums-Metadaten umsetzen.
24. DB-Universen und historisierte Mitgliedschaften einfuehren.
25. Data-Sync-Audit-Trail einfuehren.
26. Sync-Audit-Bedienung und Betriebshaertung ausbauen.
27. Daten-Freshness- und Qualitaetsdiagnosen ausbauen.
28. Freshness-Policies konfigurierbar machen und optional als Preflight-Gates
    durchsetzen.

## Testing Und Akzeptanz

- `fixtures/raw_market_data.sql` wird als Demo-/Fixture-Datenbank genutzt, damit Ticker, Kerzen und Fundamentals ohne API-Aufrufe verfuegbar sind.
- Erste Akzeptanz: dieselben Rohdaten koennen fuer mehrere Strategien, Universen und Benchmarks genutzt werden.
- Backtest-Akzeptanz: ein Run erzeugt reproduzierbar Metriken, Equity Curve und simulierte Trades.
- Live-Akzeptanz: aktives Portfolio zeigt Model, Shadow, Real und Execution Gap.
- Performance-Akzeptanz: operativer Report vergleicht Real, Shadow und
  Benchmark reproduzierbar ueber eine Zeitreihe.
- Konfigurations-Akzeptanz: Strategieaenderungen gelten nur ab neuem `valid_from` und zerstoeren keine historischen Ergebnisse.
- Legacy-Cutover entfernt als AP14 die verbleibenden Abhaengigkeiten von
  legacy-kompatiblen Tabellen im regulaeren Betrieb.
- Crontab startet seit AP15 auf dem modularen operativen Pfad nach AP14.
- Performance-Reporting fuer Real vs. Shadow vs. Benchmark ist seit AP16
  read-only verfuegbar.
- DB-Integrationsregression gegen echtes MySQL ist seit AP17 ueber eine
  isolierte Testdatenbank umgesetzt.
- Multi-Asset-Erweiterungen muessen Universen, Assetklassen und verfuegbare
  Datenarten explizit trennen; Krypto darf z. B. ohne Fundamentaldaten
  modellierbar sein. AP18 dokumentiert dieses Zielbild.
- Der naechste technische Schritt ist konfigurierbare Freshness-Preflight-
  Policy auf Basis der AP26-Diagnosen.

## Annahmen Und Defaults

- Start mit `portfolio_id`; echte Mandantenfaehigkeit mit `tenant_id` wird vorbereitet, aber nicht als erster Zwang umgesetzt.
- MySQL bleibt zunaechst bestehen.
- `fixtures/raw_market_data.sql` wird nicht als neues `init.sql` verwendet, sondern als bereinigte Test-/Demo-Fixture.
- Erste Provider sind bestehende DB/Fixture-Daten und yfinance; weitere APIs
  kommen ueber Adapter und explizite Source-Bindings.
- Erste Strategie bleibt Value/Quality/Momentum, wird aber in die neue modulare Strategieform ueberfuehrt.
- Neue Oberflaechenbausteine sind derzeit nicht Teil des aktiven AP-Plans; der
  naechste Fokus liegt auf einem read-only Capability- und Provider-Check fuer
  den bestehenden AP14/AP17-Pfad.
