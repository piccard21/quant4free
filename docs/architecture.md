# Architektur

Stand: AP16.

Das neue Framework ist der regulaere operative Pfad. Legacy-Code liegt nur noch
als archivierte Referenz unter `legacy/current_system/`.

## Module

- `data/`: Provider, Sync und Zugriff auf `assets`, `asset_price_bars`,
  `asset_fundamental_reports`, `asset_market_caps`.
- `universes/`: Universumsdefinitionen, aktuell ueber aktive Assets.
- `indicators/`: modulare Indikatorberechnung.
- `strategies/`: Value/Quality/Momentum-Strategie und Model Portfolio.
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

## Operator-Pfad

```bash
python -m cli.data_status --details
python -m cli.operator_smoke
python -m cli.daily_run --dry-run-sync
python -m cli.monthly_run --persist
python -m cli.live_status --all
python -m cli.live_performance
```
