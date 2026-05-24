# Architektur

Siehe README und zukünftige Detaildokumentation.


---

# Neue Architektur-Komponenten

## AP5: Universe- und Benchmark-Konfiguration

Universen und Benchmarks sind im neuen Framework per Key auswaehlbar, ohne
Schema-Migration und ohne Aenderung am Legacy-System.

Universen:

- `sp500_active`: Default-Universum fuer die aktuelle Fixture, basierend auf
  aktiven Tickern.
- `active_tickers`: alle Ticker mit `tickers.is_active = 1`.
- `all_tickers`: alle in den Rohdaten bekannten Ticker.

Benchmarks:

- `spy`: SPDR S&P 500 ETF Trust.
- `qqq`: Invesco QQQ Trust.
- `iwm`: iShares Russell 2000 ETF.

Die CLI-Auswahl erfolgt ueber:

```bash
python -m cli.framework_status --universe sp500_active --benchmark spy
python -m cli.framework_status --list-configs
```

## setup.sh

Neue Parameter:

- --portfolio-size
- --max-trades-per-month
- --max-funding-sell-pct

---

## cli/update_settings.py

Neue Runtime-Konfiguration aktiver Strategie-Settings.

---

## core/build_trade_plan.py

Neue Features:

- Funding-Sells
- dynamisches Trade-Limit
- kontrollierter Portfolio-Aufbau

---

## core/build_tradable_shadow.py

Neue Features:

- dynamisches Positionswechsel-Limit
- kontrolliertes Auffüllen des Portfolios

---

## core/build_rebalance.py

Neue Features:

- effektives Rebalance-Limit
- Auffüll-Logik
