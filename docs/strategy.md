# Strategie

Siehe README und zukünftige Detaildokumentation.


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
