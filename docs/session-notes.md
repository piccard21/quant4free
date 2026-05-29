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

AP9 is complete. Current AP9 findings:

- `live.status` computes a read-only live status from Model targets, Shadow
  targets, real positions, and cash.
- The first Execution Gap states are `model_not_shadow`, `missing_in_real`,
  `extra_in_real`, `underweight_real`, `overweight_real`, and `aligned`.
- `live.repository` reads the existing legacy-compatible live tables
  (`portfolio_snapshots`, `portfolio_positions`, and `portfolio_cash`) without
  changing schema.
- `cli.live_status` prints the AP9 status and actionable gaps.
- `live.execution.LiveExecutionService` reconnects write-side live behavior for
  manual cash movements and manual BUY/SELL execution.
- Cash movements write `cash_ledger` and `portfolio_cash`.
- Trade executions write `trade_executions`, `cash_ledger`, `portfolio_cash`,
  and `portfolio_positions`.
- Write-side validation covers cash/ledger consistency, settings snapshots,
  ticker existence, dry-runs, duplicate execution detection, trade-plan matching,
  available cash, open shares, and SELL tax bookings.
- `cli.live_cash` and `cli.live_trade` expose the write-side AP9 workflows
  without the legacy `PYTHONPATH`.

AP10 is complete. Current AP10 findings:

- `cli.errors` centralizes expected operator-facing failures for modular CLIs.
- Missing raw tables now point operators to `fixtures/raw_market_data.sql`.
- Missing live tables now point operators to `init.sql` or the legacy setup
  path, because the raw fixture intentionally does not include live state.
- `cli.operator_smoke` runs fixture health, universe/benchmark loading,
  Value/Quality/Momentum strategy execution, and a non-persistent benchmark
  backtest in one command.
- Local smoke output ended with `operator_smoke=ok` against the current fixture
  database.

Planning update after AP10:

- The web UI is deferred.
- AP11 is now modular data sync as the replacement for legacy
  `core.sync_prices` and `core.sync_fundamentals`.
- AP12 is complete: new modular daily/monthly orchestration through
  `cli.daily_run`, `cli.monthly_run`, and shared `cli.orchestration`.
- AP13 is operational persistence for model portfolio, shadow portfolio,
  rebalance output, decision log, and trade plan.
- AP14 is the legacy-independent canonical schema and live cutover.
- AP15 is the simple host-crontab operating path for daily and monthly runs.
- AP16 is the deferred web interface.

AP11 is complete. Current AP11 findings:

- `data.sync.PriceSyncService` handles S&P 500 ticker refresh, benchmark
  planning, incremental candle start dates, yfinance downloads, and candle
  upserts without legacy imports.
- `data.sync.FundamentalSyncService` handles refresh selection, Annual/TTM
  normalization, market-cap snapshots, upserts, and
  `last_fundamental_update`.
- `data.yahoo` now contains the Wikipedia/yfinance provider adapters and pure
  normalization helpers.
- New CLIs:
  - `cli.sync_prices`
  - `cli.sync_fundamentals`
  - `cli.sync_data`
- Focused AP11 tests live in `tests/test_data_sync.py`.

AP12 is complete. Current AP12 findings:

- `cli.orchestration` centralizes the strategy/model-portfolio run for operator
  CLIs.
- `cli.daily_run` combines AP11 price/fundamental sync with the modular
  strategy run; `--dry-run-sync` keeps fixture smoke runs offline and read-only.
- `cli.monthly_run` resolves the same default stichtag as the modular strategy
  path: latest available trading day from raw prices unless `--as-of-date` is
  provided.

AP13 is complete:

- `live.operations` builds modular operational artifacts for the legacy-compatible
  live tables:
  - Model portfolio snapshots from AP12 strategy artifacts.
  - Tradable Shadow snapshots with previous-holding carry-forward,
    minimum-holding protection, resize handling, and dynamic trade limits.
  - Rebalance suggestions and decision log.
  - Trade-plan summary and snapshot rows using latest raw close prices,
    cash, real positions, fees, and limited funding sells.
- `OperationalRepository` persists all AP13 artifacts transactionally and
  rejects duplicate frozen artifact dates.
- `cli.monthly_run --persist` enables AP13 writes; without `--persist`, the
  monthly CLI stays read-only.
- Tests:
  - `tests/test_live_operations.py`
- Verification:
  - `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`
  - `.venv/bin/python -m pytest tests`
  - Docker/MySQL smoke against isolated `ap13_smoke` seeded with `init.sql` and
    `fixtures/raw_market_data.sql`.
  - Re-running `cli.monthly_run --persist` rejects duplicate artifact dates.
  - `cli.live_status --all --limit 10` reads the new Model/Shadow snapshots.
  - Cash-backed smoke against `ap13_smoke_cash` produced executable BUY plan
    rows, and `cli.live_trade --trade-plan-action BUY --dry-run` validated one
    planned trade.

AP14 started by auditing the remaining table dependencies and documenting the
target mapping in `docs/data-model.md`.

AP14 is complete:

- `init.sql` now creates the canonical AP14 schema instead of the old
  legacy-compatible tables.
- `fixtures/raw_market_data.sql` now loads `assets`, `asset_price_bars`,
  `asset_fundamental_reports`, and `asset_market_caps`.
- `data.repository`, `cli.data_status`, and `cli.operator_smoke` read/write the
  canonical raw tables.
- `live.repository`, `live.operations`, and `live.execution` read/write
  `strategy_instances`, `strategy_config_snapshots`, `portfolio_target_items`,
  `live_rebalance_items`, `live_decision_items`, `live_trade_plans`,
  `live_trade_plan_items`, `live_trade_executions`, `live_cash_ledger`,
  `live_cash_balances`, and `live_positions`.
- Real-position pricing now resolves latest closes from `asset_price_bars`.
- `setup.sh` no longer invokes legacy core modules and resets AP14 canonical
  live state.
- Verification:
  - `.venv/bin/python -m pytest tests/test_data_sync.py tests/test_live_operations.py tests/test_live_execution.py tests/test_live_status.py tests/test_cli_errors.py`

AP15 is complete:

- Added host scripts:
  - `scripts/cron_daily.sh`
  - `scripts/cron_monthly.sh`
  - `scripts/client_smoke.sh`
- `docs/operations.md` now documents host crontab entries, `flock` locks,
  fixed log paths, manual log checks, and lock-conflict testing.
- The cron path uses only modular CLIs: `cli.daily_run` and
  `cli.monthly_run --persist`.
- Fresh isolated client smoke was run against `ap15_client_smoke`:
  - loaded `fixtures/raw_market_data.sql`
  - applied `init.sql`
  - set start capital to 10000 and AP15 strategy overrides
  - ran `cli.operator_smoke`
  - ran `cli.monthly_run --persist`
  - validated `cli.live_status`, `cli.live_trade --dry-run`, and
    `cli.live_cash --dry-run`
  - executed seven smoke BUYs in the isolated DB
  - verified seven executions, seven open positions, and matching cash and
    latest ledger balances at 660.940000
- Cron verification:
  - `flock` lock-conflict test returned `lock_test=ok`
  - `DB_NAME=ap15_client_smoke flock -n var/lock/daily_run.lock scripts/cron_daily.sh --dry-run-sync --model-limit 1 >> var/log/daily_run.log 2>&1`
  - `DB_NAME=ap15_client_smoke flock -n var/lock/monthly_run.lock scripts/cron_monthly.sh --as-of-date 2026-05-21 >> var/log/monthly_run.log 2>&1`

Next step: AP16, keep the web UI behind the now-tested modular operator path.
