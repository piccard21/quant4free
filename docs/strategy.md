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
