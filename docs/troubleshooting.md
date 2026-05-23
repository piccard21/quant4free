# Troubleshooting

Siehe README und zukünftige Detaildokumentation.


---

# Neue typische Probleme

## Portfolio bleibt unter Zielgröße

Prüfen:

```bash
qs --details
```

Auf folgende Werte achten:

```text
Fehlende Real-Positionen
Effektives Trade-Limit
```

---

## BUY nicht ausführbar

Mögliche Ursache:

```text
max_funding_sell_pct zu niedrig
```

Anpassen:

```bash
docker compose run --rm app python -m cli.update_settings   --max-funding-sell-pct 0.25
```

---

## Settings geändert aber keine Wirkung

Settings wirken nur auf zukünftige Monatsläufe.

Historische Snapshots bleiben eingefroren.
