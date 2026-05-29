# Repository Guidelines

## Project Structure & Module Organization

This repository is being migrated from an operational quantitative portfolio system into a modular Python/MySQL quant framework.

- `legacy/current_system/`: frozen reference copy of the previous operational system.
- `legacy/current_system/core/`: legacy operational pipeline modules for price/fundamental sync, factor metrics, scores, model portfolio, tradable shadow portfolio, rebalance, trade plans, and manual trade/cash execution.
- `legacy/current_system/cli/`: legacy command-line entry points such as `cli.core_main`, `cli.show_status`, and `cli.update_settings`.
- `legacy/current_system/research/`: legacy analysis jobs, currently focused on performance snapshots.
- `legacy/current_system/shared/`: legacy database connection, constants, and strategy settings validation.
- `data/`: new data access, provider adapters, and raw-data normalization.
- `universes/`: new selectable investment universes and membership loaders.
- `indicators/`: new modular indicator implementations.
- `strategies/`: new strategy logic.
- `simulation/`: new portfolio simulation, rebalancing, costs, and taxes.
- `evaluation/`: new backtests, parameter sweeps, benchmark comparison, and metrics.
- `live/`: new model/shadow/real portfolio and execution-gap workflows.
- `cli/`: new command-line entry points for runs, status, experiments, and reports.
- `shared/`: new shared helpers for the modular framework.
- `tests/`: pytest regression tests for indicators, strategy ranking, backtest behavior, and live workflows.
- `docs/`: operator, strategy, architecture, and troubleshooting documentation.
- `init.sql`: canonical schema initialization.
- `fixtures/raw_market_data.sql`: sanitized raw-data fixture for modular framework smoke checks.
- `simfin/`: bundled SimFin ZIP data assets.

## Current Migration State

AP0 is complete: the previous operational modules were moved under
`legacy/current_system/`, and the new top-level package skeleton was created.

After each AP is accepted as complete, update the repository status documents
in the same change so future sessions can identify the current AP without
re-auditing the implementation. `README.md` must always be updated for a
completed AP. At minimum keep `AGENTS.md`, `plan.md`, `README.md`, and relevant
files under `docs/` in sync with the completed AP, the verification that was
run, and the next AP.

AP1 is complete: the data-model and schema plan are documented in
`docs/data-model.md`. AP14 later replaced the temporary legacy-compatible
schema with the canonical modular schema.

AP2, AP3, and AP4 are complete. The new modular framework can read raw fixture
data from MySQL through the new data-provider layer. The canonical fixture is
`fixtures/raw_market_data.sql`, which contains only `assets`,
`asset_price_bars`, `asset_fundamental_reports`, and `asset_market_caps`.

AP5 is complete: selectable universes and benchmarks are implemented through
configuration keys.

AP6 is complete: the modular indicator engine calculates momentum, relative
strength, value, and quality indicators.

AP7 is complete: the first Value/Quality/Momentum strategy consumes AP6
indicator frames and produces a reproducible ranking plus model portfolio.

AP8 is complete: the first periodic strategy backtest can evaluate the AP7
strategy against a benchmark, including rebalancing, trading costs, equity
curve, benchmark curve, trades, summary metrics, and optional SQL persistence
through additive AP8 evaluation tables.

AP9 is complete: the new `live` package computes Model/Shadow/Real portfolio
status and execution gaps. AP14 moved these workflows to canonical live tables.
`cli.live_status` exposes this status. Write-side live workflows are reconnected through
`LiveExecutionService`, `cli.live_cash`, and `cli.live_trade`, covering cash
ledger movements, manual BUY/SELL execution, position updates, cash updates,
trade history, dry-runs, and core consistency checks.

AP10 is complete: modular operator CLIs share `cli.errors` for concise
operator-facing failures, and `cli.operator_smoke` runs the fixture-health,
strategy-run, and benchmark-backtest smoke path without requiring a web UI.

AP11 is complete: modular data sync replaces the legacy data-fetch path for
raw tickers, daily candles, fundamentals, and market-cap snapshots. The new
entry points are `cli.sync_prices`, `cli.sync_fundamentals`, and
`cli.sync_data`; dry-runs do not require external API calls.

AP12 is complete: modular daily/monthly orchestration is available through
`cli.daily_run` and `cli.monthly_run`. Daily runs can combine AP11 data sync
with the modular indicator/strategy/model-portfolio path. Monthly runs produce
the model portfolio for the latest available trading day or an explicit
`--as-of-date`.

AP13 is complete: `cli.monthly_run --persist` writes model, shadow, rebalance,
decision-log, trade-plan-summary, and trade-plan-snapshot artifacts.

AP14 is complete: the regular modular path now uses canonical tables instead
of legacy-compatible tables. Raw data uses `assets`, `asset_price_bars`,
`asset_fundamental_reports`, and `asset_market_caps`. Live/operations uses
`strategy_instances`, `strategy_config_snapshots`, `portfolio_target_items`,
`live_rebalance_items`, `live_decision_items`, `live_trade_plans`,
`live_trade_plan_items`, `live_trade_executions`, `live_cash_ledger`,
`live_cash_balances`, and `live_positions`. `init.sql`, setup, fixture,
repositories, CLIs, and focused regression tests have been migrated.

AP15 is complete: host-crontab operation for daily and monthly runs is
documented and backed by `scripts/cron_daily.sh`, `scripts/cron_monthly.sh`,
fixed `flock` locks, fixed log paths, and `scripts/client_smoke.sh` for a fresh
isolated client smoke covering initialization, start capital, monthly
persistence, trade-plan validation, live status, cash dry-run, and optional
smoke trade execution. AP16 is next: build a web UI only after the core
operator path remains stable.

## Build, Test, and Development Commands

Build the application image:

```bash
docker compose build
```

Start MySQL and phpMyAdmin:

```bash
docker compose up -d db phpmyadmin
```

Initialize a fresh system:

```bash
./setup.sh init --start-capital 10000 --portfolio-size 7 --max-trades-per-month 4 --max-sector-positions 3 --min-holding-months 2 --max-funding-sell-pct 0.35
```

Basic syntax check:

```bash
docker compose run --rm app python -m compileall data universes indicators strategies simulation evaluation live cli shared
```

Run regression tests:

```bash
python -m pytest tests
```

Run current modular smoke CLIs:

```bash
python -m cli.indicator_status
python -m cli.strategy_status
python -m cli.backtest_status
python -m cli.live_status
python -m cli.live_cash --help
python -m cli.live_trade --help
python -m cli.operator_smoke
python -m cli.sync_prices --dry-run
python -m cli.sync_fundamentals --dry-run
python -m cli.sync_data --dry-run
python -m cli.daily_run --dry-run-sync
python -m cli.monthly_run
```

## Coding Style & Naming Conventions

Use Python 3.10-compatible code, 4-space indentation, descriptive function names, and explicit CLI arguments. Prefer small functions around one pipeline step or query. Treat `legacy/current_system/` as reference code first; do not reshape it unless a task explicitly targets legacy behavior. Keep new framework helpers in the new top-level packages.

Use object orientation only where it represents genuinely interchangeable
concepts such as strategies, indicators, providers, benchmarks, simulators,
cost models, tax models, or experiment runners. Keep mass data processing in
SQL/DataFrames and avoid storing intermediate results that are cheap to
recompute.

## Testing Guidelines

Pytest regression tests now live under `tests/` and should be named
`test_<module>.py`. For changes, at minimum run `python -m pytest tests`,
`compileall`, and a relevant pipeline/status command against a local Docker
database when the change touches database-backed behavior. Prefer using
`fixtures/raw_market_data.sql` as the fixture to avoid unnecessary API calls and
to keep trades, cash balances, and portfolio history out of regression data.

## Commit & Pull Request Guidelines

Git history was not available during guide creation, so no existing commit convention could be verified. Use concise imperative commit messages, for example:

```text
Add benchmark comparison metrics
Refactor strategy settings loading
```

Pull requests should describe the behavioral change, list commands run, mention database/schema impacts, and include sample CLI output for user-facing status or reporting changes.

## Security & Configuration Tips

Keep secrets and infrastructure access in `.env`; do not commit real credentials. Do not reintroduce full SQL dumps containing real trades, cash balances, or portfolio history unless explicitly required and reviewed.
