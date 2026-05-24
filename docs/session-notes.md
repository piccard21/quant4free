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

Current AP4 Linux findings:

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
- `.venv/bin/python -m cli.framework_status --benchmark-ticker SPY` succeeds
  outside the sandbox with 503 universe members and 524 SPY benchmark rows.
- The same `cli.data_status` and `cli.framework_status` smoke checks succeed in
  the Docker app container.
- Legacy health succeeded locally before the full-dump cleanup. It is no longer
  the AP4 standard check after switching to the raw-data fixture because
  Legacy-/Live-Snapshot-, Cash-, Trade-, and Portfolio tables are intentionally
  absent.
