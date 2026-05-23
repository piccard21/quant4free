# Architektur

Siehe README und zukünftige Detaildokumentation.


---

# Neue Architektur-Komponenten

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
