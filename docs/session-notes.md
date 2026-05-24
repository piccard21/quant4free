# Session Notes

Date: 2026-05-24

## Current Analysis Summary

The repository is in the middle of a migration from a working operational
quantitative portfolio system into a modular Python/MySQL quant framework.
The legacy system has been preserved under `legacy/current_system/` and should
be treated as a reference implementation unless a task explicitly targets
legacy behavior.

AP0 is complete. The old operational modules were moved into the legacy tree,
new package directories were created for the future framework, and basic
`compileall` checks were recorded as successful in `plan.md`.

AP1 is complete. `docs/data-model.md` contains the current data-model and
schema plan. `init.sql` remains legacy-compatible for now. No schema migration
has been executed yet.

The intended first runnable slice of the new framework is deliberately narrow:
read existing fixture/database data, load the S&P 500 universe, run the
Value/Quality/Momentum strategy, compare it against SPY, and display or store
the run result.

Important implementation constraints:

- Keep `legacy/current_system/` stable as a reference.
- Prefer fixture/demo data from `fixtures/raw_market_data.sql` for regression work.
- Keep API access optional during early implementation.
- Use the new top-level packages for new framework code.
- Run legacy commands with `PYTHONPATH=/app/legacy/current_system`.
- Document changes that affect setup, architecture, operation, schema,
  strategies, tests, or operator workflows.

AP2 is complete. The new modular framework has a read-only SQLAlchemy data
access path for the legacy-compatible raw data tables, plus a `cli.data_status`
smoke-check command.

AP3 is complete. The first modular contracts and adapters exist for data
providers, universes, benchmarks, indicators, and strategies. The first
fixture-backed provider, active-ticker universe, provider benchmark adapter, and
`cli.framework_status` smoke-check command are implemented.

The AP3 follow-up problem was environment stability on Windows with WSL. AP4 is
therefore not a feature step: it is the move to a stable Linux development
environment, including Linux venv, requirements installation, Docker/Compose,
MySQL, fixture/demo data loading, and rerunning the AP3 smoke checks there.

AP4 is complete. Current Linux/AP4 findings:

- `.venv-linux` was removed and replaced with the standard Linux venv path
  `.venv`.
- `.venv` exists with Python 3.14.4 and working pip.
- `.venv/bin/python -m pip install -r requirements.txt` succeeds when run
  outside the sandbox with network access.
- `.venv/bin/python -m pip check` reports no broken installed requirements.
- `.venv/bin/python -m compileall data universes indicators strategies simulation
  evaluation live cli shared` succeeds.
- `.venv/bin/python -m compileall legacy/current_system` succeeds.
- Docker/Compose access works outside the sandbox. `sp500_db` is healthy, and
  `sp500_worker` plus `sp500_pma` are running.
- A sanitized fixture was created at `fixtures/raw_market_data.sql` with only
  `tickers`, `daily_candles`, `financial_reports`, and `market_cap_snapshots`.
- The local `stocks_db` database was rebuilt from `fixtures/raw_market_data.sql`
  and now contains only those four raw-data tables.
- The former full dump `stocks_db.sql` was removed after the sanitized fixture
  was generated and smoke-tested.
- `.venv/bin/python -m cli.data_status --details` succeeds outside the sandbox:
  506 tickers, 200962 daily candles, 1386 financial reports, 1852 market-cap
  snapshots, 503 active tickers, and 524 SPY benchmark rows.
- `cli.data_status --details` now prints fundamental detail rows by report type:
  `financial_reports.annual` and `financial_reports.ttm`, with `report_dates`
  separated from `imported` timestamps.
- `.venv/bin/python -m cli.framework_status --benchmark-ticker SPY` succeeds
  outside the sandbox with 503 universe members and 524 SPY benchmark rows.
- The same `cli.data_status` and `cli.framework_status` smoke checks succeed in
  the Docker app container.
- Legacy health succeeded locally before the full-dump cleanup. It is no longer
  the AP4 standard check after switching to the raw-data fixture because
  Legacy-/Live-Snapshot-, Cash-, Trade-, and Portfolio tables are intentionally
  absent.

AP5 is complete. Current AP5 findings:

- Universes are now selectable by configuration key:
  `sp500_active`, `active_tickers`, and `all_tickers`.
- Benchmarks are now selectable by configuration key: `spy`, `qqq`, and `iwm`.
- `cli.framework_status` now supports `--universe`, `--benchmark`, and
  `--list-configs`.
- The old `--benchmark-ticker SPY` path still works as an ad-hoc compatibility
  override.
- Local smoke checks succeeded:
  `.venv/bin/python -m cli.framework_status --list-configs`
  `.venv/bin/python -m cli.framework_status`
  `.venv/bin/python -m cli.framework_status --universe all_tickers --benchmark spy`
  `.venv/bin/python -m cli.framework_status --benchmark-ticker SPY`
- Default AP5 status: 503 `sp500_active` members and 524 SPY benchmark rows
  from 2024-04-22 to 2026-05-22.

AP6 is complete. Current AP6 findings:

- `indicators.core` contains modular indicators for momentum return, relative
  strength, earnings yield, free-cash-flow yield, return on equity, and
  debt/equity.
- `indicators.engine` provides a default registry and a `compute_indicators`
  helper that merges indicator outputs by ticker.
- Missing lookback, fundamental, or market-cap inputs remain explicit NaN
  values instead of becoming default scores.
- `cli.indicator_status` runs the AP6 smoke path against the configured
  universe and fixture-backed raw data.
- Local smoke checks succeeded:
  `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  `.venv/bin/python -m unittest tests.test_indicators`
  `.venv/bin/python -m cli.indicator_status --limit 3`
- Default AP6 status: 503 `sp500_active` rows as of 2026-05-22 with all six
  default indicators calculated.

AP7 is complete. Current AP7 findings:

- `strategies.value_quality_momentum` contains the first modular
  Value/Quality/Momentum strategy.
- Factor weights are configurable and validated. The default weights are
  Value 0.35, Quality 0.30, and Momentum 0.35.
- The strategy consumes AP6 indicator frames through `StrategyContext`, creates
  value, quality, momentum, and composite scores, ranks eligible tickers, and
  assigns equal `model_weight` to the top model-portfolio rows.
- `cli.strategy_status` runs the AP7 smoke path against the configured
  universe, benchmark, and fixture-backed raw data.
- Local smoke checks succeeded:
  `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  `.venv/bin/python -m unittest tests.test_value_quality_momentum tests.test_indicators`
  `.venv/bin/python -m cli.strategy_status --limit 3`
- Default AP7 status: 503 `sp500_active` rows as of 2026-05-22, 500 eligible
  scored rows, and 7 equal-weight model positions.

AP8 is complete. Current AP8 findings:

- `evaluation.backtest` contains a reproducible equal-weight Top-N backtest for
  the AP7 strategy output, including periodic rebalancing, a basis-point cost
  model, equity curve, benchmark curve, trades, and summary metrics.
- `evaluation.repository` adds SQL persistence for `strategy_runs`,
  `strategy_run_metrics`, `strategy_run_equity_curve`, and
  `strategy_run_trades`. The schema is created additively by the AP8 CLI when
  `--persist` is supplied.
- `cli.backtest_status` runs the AP8 smoke path against fixture-backed raw
  data. Without `--persist` it prints a report only; with `--persist` it stores
  the run and prints `stored_run_id` plus `run_key`.

Next planned step: AP9, migrate or reconnect the live Model/Shadow/Real
portfolio workflows and execution gap handling.
