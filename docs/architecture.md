# Architektur

Stand: AP25.

Das neue Framework ist der regulaere operative Pfad. Legacy-Code liegt nur noch
als archivierte Referenz unter `legacy/current_system/`.

## Module

- `data/`: Provider, Sync und Zugriff auf `assets`,
  `asset_provider_identifiers`, `universes`, `universe_members`,
  `asset_price_bars`,
  `asset_fundamental_reports`, `asset_market_caps`. AP18 ordnet diese
  Tabellen als Capability-Quellen ein; AP21 trennt interne Assets von
  provider-spezifischen Symbolen, AP22 nutzt diese Symbole im Sync, AP23
  fuehrt DB-Universen und historisierte Mitgliedschaften ein, AP24 ergaenzt
  `data_sync_runs` als Audit-Trail fuer echte Sync-Laeufe, AP25 ergaenzt
  gefilterte Sync-Diagnosen und konservative Provider-Request-Policies.
- `universes/`: Universumsloader. Fachlich sind Universen Asset-Auswahlen und
  keine impliziten Datenanforderungen. Seit AP23 liest der Loader
  `universe_members`, wenn der Provider DB-Mitgliedschaften anbietet.
- `indicators/`: modulare Indikatorberechnung.
- `strategies/`: Value/Quality/Momentum-Strategie und Model Portfolio. Die
  aktuelle Strategie ist eine Aktienstrategie, weil sie Preise,
  Fundamentaldaten, Market Caps und Sector-Daten benoetigt.
- `evaluation/`: Backtests, Benchmark-Vergleich und `strategy_run_*` Tabellen.
- `live/`: Model/Shadow/Real Status, Rebalance-Artefakte, Trade Plans, Cash,
  manuelle Ausfuehrungen und Real/Shadow/Benchmark-Performance auf
  kanonischen Live- und Preistabellen.
- `cli/`: Operator-Einstiege fuer Status, Sync, Daily/Monthly, Live-Cash und
  Live-Trades sowie Live-Performance.

## Kanonische Tabellen

Rohdaten:

- `assets`
- `asset_provider_identifiers`
- `universes`
- `universe_members`
- `asset_price_bars`
- `asset_fundamental_reports`
- `asset_market_caps`
- `data_sync_runs`

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

## AP18-AP25 Capability- und Provider-Modell

AP18 und AP19 richten die Architektur fachlich auf ein Capability- und
Provider-Binding-Modell aus. AP20 setzt die read-only Pruefung in Code um.
AP21 verankert Asset-Metadaten und Provider-Identifier im kanonischen Schema.
AP22 nutzt diese Identifier im modularen Sync. AP23 verankert Universe-Katalog
und historisierte Mitgliedschaften in der Datenbank. AP24 macht echte Syncs
ueber `data_sync_runs` auditierbar. AP25 macht diesen Audit-Trail fuer
Operatoren filterbar und haertet Yahoo/yfinance-Abrufe:

- `assets` ist der allgemeine Asset-Katalog mit Assetklasse,
  Canonical-/Display-Symbol, Instrumenttyp, Markt und Quote-Waehrung.
- `asset_provider_identifiers` speichert provider-spezifische Symbole und IDs.
- Assetklassen wie `equity`, `etf`, `crypto`, `cash`, `fx` und `future`
  bestimmen, welche Datenarten sinnvoll sind.
- Universen sind Asset-Auswahlen und duerfen nicht implizit eine konkrete API
  auswaehlen.
- Provider wie Yahoo Finance, Binance, SimFin, CSV oder kommerzielle APIs
  liefern Capabilities fuer konkrete Source-Rollen wie Membership, Preise,
  Fundamentals, Market Caps, Klassifikation oder Benchmark-Preise.
- Data-Capabilities wie `prices.daily_ohlcv`,
  `fundamentals.equity_reports`, `market_caps`,
  `classification.equity_sector`, `live.cash` und `live.positions` werden
  kuenftig explizit von Strategien, Indikatoren, Benchmarks und Live-Workflows
  verlangt.
- Seit AP20 prueft ein read-only Capability-Checker in `shared.capabilities`,
  ob Universum, Provider-Bindings und deklarierte Anforderungen fuer den
  aktuellen Lauf zusammenpassen.
- Seit AP21 kann der Checker supplied Asset-Metadaten und
  Provider-Identifier-Coverage auswerten; die Strategie-Orchestrierung reicht
  diese Daten durch, wenn der Provider sie melden kann.
- Seit AP22 loesen Preis- und Fundamental-Sync interne Ticker auf
  Provider-Symbole auf und schreiben normalisierte Daten wieder unter dem
  internen Ticker zurueck.
- Seit AP23 sind `sp500_active`, `active_tickers` und `all_tickers` als
  DB-Universen geseedet; offene und historische Mitgliedschaften werden in
  `universe_members` abgefragt.
- Seit AP24 schreiben Preis-, Fundamental- und Membership-Syncs kanonische
  Audit-Runs mit Provider, Source-Rolle, Modus, Zeitfenster, Status,
  Zeilenzaehlern und operator-sichtbaren Fehlern. Dry-Runs bleiben read-only.
- Seit AP25 meldet `cli.data_status --details` filtered Runs sowie failed/stale
  Diagnosen, und Preis-/Fundamental-Syncs koennen Batch-Groessen, Throttle,
  Retry/Backoff und Circuit-Breaker pro Lauf konfigurieren.
- Seit AP26 erzeugt `data.diagnostics` eine read-only Preflight-Sicht auf
  Missing/Stale-Zustaende fuer Preise, TTM-Fundamentals und Market Caps,
  Provider-Identifier-Coverage sowie die juengste Sync-Health. `cli.data_status
  --details` und `cli.operator_smoke` geben diese Diagnose als
  `data_quality.*`-Zeilen aus.

Details stehen in [Assetklassen, Universen und Daten-Capabilities](data-capabilities.md)
und [Provider-, API- und Source-Binding-Modell](provider-api-model.md).

## Operator-Pfad

```bash
python -m cli.data_status --details
python -m cli.operator_smoke
python -m cli.daily_run --dry-run-sync
python -m cli.monthly_run --persist
python -m cli.live_status --all
python -m cli.live_performance
```
