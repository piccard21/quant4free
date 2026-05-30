# Architektur

Stand: AP20.

Das neue Framework ist der regulaere operative Pfad. Legacy-Code liegt nur noch
als archivierte Referenz unter `legacy/current_system/`.

## Module

- `data/`: Provider, Sync und Zugriff auf `assets`, `asset_price_bars`,
  `asset_fundamental_reports`, `asset_market_caps`. AP18 ordnet diese
  Tabellen als Capability-Quellen ein: Preise sind generisch, Fundamentals
  aktienspezifisch, Market Caps optional je Assetklasse.
- `universes/`: Universumsdefinitionen, aktuell ueber aktive Assets. Fachlich
  sind Universen Asset-Auswahlen und keine impliziten Datenanforderungen.
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

## AP18/AP19 Capability- und Provider-Modell

AP18 und AP19 fuehren noch keine neuen Tabellen oder Contracts ein. Die
Architektur wird aber fachlich auf ein Capability- und Provider-Binding-Modell
ausgerichtet:

- `assets` ist der allgemeine Asset-Katalog, auch wenn das aktuelle Schema noch
  aktiennah ist.
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
  aktuellen Lauf zusammenpassen. Identifier-Abdeckung und echte Asset-Metadaten
  bleiben AP21+.

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
