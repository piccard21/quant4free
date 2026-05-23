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
schema plan. Existing database files, especially `init.sql` and
`stocks_db.sql`, remain legacy-compatible for now. No schema migration has been
executed yet.

The intended first runnable slice of the new framework is deliberately narrow:
read existing fixture/database data, load the S&P 500 universe, run the
Value/Quality/Momentum strategy, compare it against SPY, and display or store
the run result.

Important implementation constraints:

- Keep `legacy/current_system/` stable as a reference.
- Prefer fixture/demo data from `stocks_db.sql` for regression work.
- Keep API access optional during early implementation.
- Use the new top-level packages for new framework code.
- Run legacy commands with `PYTHONPATH=/app/legacy/current_system`.
- Document changes that affect setup, architecture, operation, schema,
  strategies, tests, or operator workflows.

The next planned step is AP2: implement minimal data access for the new modular
system.
