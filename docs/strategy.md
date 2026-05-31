# Strategie

## AP7: Value/Quality/Momentum

Die erste modulare Strategie ist `value_quality_momentum`.

Sie konsumiert AP6-Indikatoren ueber `StrategyContext` und liest keine
Rohdaten direkt. Die Default-Gewichtung ist:

- Value: 0.35
- Quality: 0.30
- Momentum: 0.35

Die Gewichte sind konfigurierbar, muessen aber exakt die Faktoren `value`,
`quality` und `momentum` enthalten und zusammen 1.0 ergeben.

Aktuelle Subscores:

- Value: `earnings_yield`, `free_cash_flow_yield`
- Quality: `return_on_equity`, invertiertes `debt_to_equity`
- Momentum: `momentum_return`, `relative_strength`

Das Ergebnis ist ein Ranking mit `composite_score`, Faktor-Subscores, `rank`
und einem gleichgewichteten `model_weight` fuer die Top-Positionen.

AP18-Einordnung:

- Die Strategie ist fachlich eine Aktienstrategie.
- Sie benoetigt die Data-Capabilities `prices.daily_ohlcv`,
  `fundamentals.equity_reports`, `market_caps` und
  `classification.equity_sector`.
- Sie ist nicht unveraendert fuer reine Krypto-, Cash-, FX- oder
  Futures-Universen geeignet, weil diese keine Aktienfundamentals liefern.
- Eine spaetere Capability-Pruefung soll vor dem Lauf klar abbrechen, wenn ein
  Universum die erforderlichen Pflichtdaten nicht liefern kann.

AP19-Einordnung:

- Die Strategie darf fachlich nicht direkt an Yahoo Finance, SimFin oder einen
  anderen Provider gekoppelt werden.
- Provider sind fuer Source-Rollen austauschbar, solange sie die benoetigten
  Capabilities, normalisierten Felder, Granularitaet, Freshness und
  Identifier-Abdeckung fuer das gewaehlte Universum liefern.
- Ein Krypto-Provider wie Binance ist fuer diese Strategie nicht ausreichend,
  solange `fundamentals.equity_reports` und `classification.equity_sector`
  fehlen.

AP20-Einordnung:

- Die Requirements fuer `value_quality_momentum` und die genutzten Indikatoren
  sind in `shared.capabilities` deklariert.
- Der read-only Checker erlaubt den aktuellen `sp500_active` + `spy` +
  `mysql_fixture`-Pfad und lehnt inkompatible Universums-/Provider-
  Kombinationen vor dem Datenlauf ab.
- Die Strategie bleibt selbst provideragnostisch; die Validierung sitzt vor
  Strategieausfuehrung und CLI-Orchestrierung.

AP21-Einordnung:

- Die Strategie-Orchestrierung reicht echte Member-Metadaten und
  Provider-Identifier-Coverage an den Capability-Checker weiter, wenn der
  Provider diese Informationen liefern kann.
- Die Strategie selbst arbeitet weiterhin nur mit normalisierten DataFrames und
  bleibt von provider-spezifischen Symbolen entkoppelt.

Smoke-Check:

```bash
docker compose run --rm app python -m cli.strategy_status --limit 10
```


---

# Erweiterungen der Strategie-Umsetzung

## Dynamische Portfolio-Größe

Die Zielgröße ist jetzt vollständig konfigurierbar.

Beispiele:

- 5
- 7
- 10
- 15

---

## Dynamische Turnover-Control

Das effektive Trade-Limit lautet:

```text
max(max_trades_per_month, fehlende_positionen)
```

Dadurch kann das Portfolio kontrolliert aufgefüllt werden.

---

## Funding-Sells

Funding-Sells erzeugen kontrolliert Cash für neue BUYs.

Begrenzung:

```text
max_funding_sell_pct
```

Beispiel:

```text
0.20 = maximal 20% des Positionswerts
```
