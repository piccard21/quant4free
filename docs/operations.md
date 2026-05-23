# Operations Guide

# Inhaltsverzeichnis

- [Daily Operations](#daily-operations)
- [Monthly Operations](#monthly-operations)
- [Status-System](#status-system)
- [Trade Execution](#trade-execution)
- [Performance](#performance)
- [Operator Shortcuts](#operator-shortcuts)
- [Best Practices](#best-practices)

---

# Daily Operations

## Daily Run

```bash
docker compose run --rm app python -m cli.core_main daily
```

Der Daily Run aktualisiert:

- Preise
- Fundamentaldaten
- Factor Metrics
- Factor Scores
- Performance

---

# Monthly Operations

## Monthly Run

```bash
docker compose run --rm app python -m cli.core_main monthly
```

Wichtig:

Das System verwendet jetzt ein dynamisches effektives Trade-Limit:

```text
max(max_trades_per_month, fehlende_positionen)
```

Dadurch kann ein unterfülltes Portfolio kontrolliert aufgebaut werden.

Der Monthly Run erstellt:

- Model Portfolio Snapshot
- Tradable Shadow Snapshot
- Rebalance Suggestions
- Decision Log
- Trade Plan
- Performance Snapshot

---

## Typischer Monatsablauf

```text
1. Monthly Run starten
2. show_status prüfen
3. Trade Plan lesen
4. Dry-Run pro Trade
5. Trades beim Broker ausführen
6. Trades im System erfassen
7. show_status erneut prüfen
```

---

# Status-System

## Voller Status

```bash
docker compose run --rm app python -m cli.show_status --details
```

Mit Alias:

```bash
qs
```

---

## Health Only

```bash
docker compose run --rm app python -m cli.show_status --health
```

Mit Alias:

```bash
qs-health
```

---

## Brief Status

```bash
docker compose run --rm app python -m cli.show_status --brief
```

Mit Alias:

```bash
qs-brief
```

---

# Trade Execution

## Grundregel

Vor jeder echten Buchung zuerst einen Dry-Run machen.

```text
Dry-Run erfolgreich
→ Trade beim Broker ausführen
→ Trade im System ohne --dry-run erfassen
→ show_status erneut prüfen
```

---

## Warum `--executed-at` wichtig ist

`--executed-at` sollte bei echten Trades und rückwirkenden Tests immer gesetzt werden.

Der Zeitpunkt der Ausführung ist wichtig für:

- korrekte Cash-Historie
- korrekte Performance-Berechnung
- saubere Zuordnung zum Monatslauf
- reproduzierbare Tests
- Vermeidung von Datumschaos bei rückwirkenden Buchungen

Format:

```text
YYYY-MM-DD HH:MM:SS
```

Beispiel:

```text
2026-04-30 16:00:00
```

---

## SELL als Dry-Run testen

```bash
docker compose run --rm app python -m core.apply_trade_execution \
  --as-of-date 2026-04-30 \
  --ticker INCY \
  --execution-type SELL \
  --shares 20 \
  --price 98.21 \
  --fee 1.00 \
  --executed-at "2026-04-30 16:00:00" \
  --broker "Test" \
  --notes "Off-Plan Test SELL INCY" \
  --dry-run
```

Mit Alias:

```bash
qt --as-of-date 2026-04-30 \
   --ticker INCY \
   --execution-type SELL \
   --shares 20 \
   --price 98.21 \
   --fee 1.00 \
   --executed-at "2026-04-30 16:00:00" \
   --broker "Test" \
   --notes "Off-Plan Test SELL INCY" \
   --dry-run
```

---

## SELL erfassen

Nach erfolgreichem Dry-Run und tatsächlicher Broker-Ausführung:

```bash
docker compose run --rm app python -m core.apply_trade_execution \
  --as-of-date 2026-04-30 \
  --ticker INCY \
  --execution-type SELL \
  --shares 20 \
  --price 98.21 \
  --fee 1.00 \
  --executed-at "2026-04-30 16:00:00" \
  --broker "Test" \
  --notes "SELL INCY laut Ausführung"
```

Mit Alias:

```bash
qt --as-of-date 2026-04-30 \
   --ticker INCY \
   --execution-type SELL \
   --shares 20 \
   --price 98.21 \
   --fee 1.00 \
   --executed-at "2026-04-30 16:00:00" \
   --broker "Test" \
   --notes "SELL INCY laut Ausführung"
```

---

## BUY als Dry-Run testen

```bash
docker compose run --rm app python -m core.apply_trade_execution \
  --as-of-date 2026-04-30 \
  --ticker DVN \
  --execution-type BUY \
  --shares 36 \
  --price 50.57 \
  --fee 1.00 \
  --executed-at "2026-04-30 16:00:00" \
  --broker "Test" \
  --notes "BUY DVN laut Trade Plan" \
  --dry-run
```

Mit Alias:

```bash
qt --as-of-date 2026-04-30 \
   --ticker DVN \
   --execution-type BUY \
   --shares 36 \
   --price 50.57 \
   --fee 1.00 \
   --executed-at "2026-04-30 16:00:00" \
   --broker "Test" \
   --notes "BUY DVN laut Trade Plan" \
   --dry-run
```

---

## BUY erfassen

Nach erfolgreichem Dry-Run und tatsächlicher Broker-Ausführung:

```bash
docker compose run --rm app python -m core.apply_trade_execution \
  --as-of-date 2026-04-30 \
  --ticker DVN \
  --execution-type BUY \
  --shares 36 \
  --price 50.57 \
  --fee 1.00 \
  --executed-at "2026-04-30 16:00:00" \
  --broker "Test" \
  --notes "BUY DVN laut Trade Plan"
```

Mit Alias:

```bash
qt --as-of-date 2026-04-30 \
   --ticker DVN \
   --execution-type BUY \
   --shares 36 \
   --price 50.57 \
   --fee 1.00 \
   --executed-at "2026-04-30 16:00:00" \
   --broker "Test" \
   --notes "BUY DVN laut Trade Plan"
```

---

## Off-Plan-Trade

Ein Off-Plan-Trade ist ein bewusst manuell ausgeführter Trade außerhalb des Trade Plans.

Wichtig:

- immer mit `--notes` dokumentieren
- immer mit `--executed-at` buchen
- vorher immer `--dry-run` verwenden

Beispiel:

```bash
qt --as-of-date 2026-04-30 \
   --ticker INCY \
   --execution-type SELL \
   --shares 20 \
   --price 98.21 \
   --fee 1.00 \
   --executed-at "2026-04-30 16:00:00" \
   --broker "Test" \
   --notes "Off-Plan Test SELL INCY" \
   --dry-run
```

---

# Performance

## Performance manuell berechnen

Mit Alias:

```bash
qp --as-of-date 2026-04-30
```

Ohne Alias:

```bash
docker compose run --rm app python -m cli.research_main performance \
  --as-of-date 2026-04-30
```

---

## Performance Backfill

Backfill berechnet fehlende historische Performance-Tage nach.

Das ist hilfreich wenn:

- historische Tage fehlen
- rückwirkende Trades gebucht wurden
- alte Snapshots ergänzt wurden
- Tests historische Daten verändert haben

Mit Alias:

```bash
qp-backfill
```

Ohne Alias:

```bash
docker compose run --rm app python -m cli.research_main performance \
  --backfill
```

Der Backfill läuft historische Tage erneut durch und ergänzt fehlende Performance-Snapshots.

---

# Operator Shortcuts

## Empfohlene Aliases

```bash
# =========================
# QUANT SYSTEM SHORTCUTS
# =========================

# Status
alias qs='docker compose run --rm app python -m cli.show_status --details'
alias qs-brief='docker compose run --rm app python -m cli.show_status --brief'
alias qs-health='docker compose run --rm app python -m cli.show_status --health'
alias qs-now='date && qs'

# Pipeline
alias qd='docker compose run --rm app python -m cli.core_main daily'
alias qm='docker compose run --rm app python -m cli.core_main monthly'

# Performance
alias qp='docker compose run --rm app python -m cli.research_main performance'
alias qp-backfill='qp --backfill'

# Trade Execution
alias qt='docker compose run --rm app python -m core.apply_trade_execution'

# Dry-Run-Hilfe mit executed-at
alias qt-dry='echo "Beispiel: qt --as-of-date YYYY-MM-DD --ticker XXX --execution-type BUY --shares N --price X --fee 1 --executed-at \\"YYYY-MM-DD HH:MM:SS\\" --broker \\"Scalable\\" --notes \\"Trade Plan Ausführung\\" --dry-run"'

# Top Sektoren
alias qtop-sector='docker compose run --rm app python -m cli.show_top_sector'
alias qtop5-sector='qtop-sector --limit 5'
alias qtop10-sector='qtop-sector --limit 10'

# Rebuild + Status
alias qi='./setup.sh init --start-capital 10000'
alias qr='./setup.sh rebuild --start-capital 10000'
alias qrs='qr && qs'
```

---

# Best Practices

```text
1. Immer show_status prüfen
2. Nie ohne Dry-Run buchen
3. Immer --executed-at setzen
4. Snapshots nie überschreiben
5. Cash-Differenzen sofort prüfen
6. Off-Plan-Trades immer dokumentieren
```


---

# Settings im laufenden Betrieb ändern

## Portfolio-Größe ändern

```bash
docker compose run --rm app python -m cli.update_settings   --portfolio-size 10
```

## Max Trades ändern

```bash
docker compose run --rm app python -m cli.update_settings   --max-trades-per-month 3
```

## Funding-Sell-Limit ändern

```bash
docker compose run --rm app python -m cli.update_settings   --max-funding-sell-pct 0.25
```

## Setup mit neuen Parametern

```bash
./setup.sh init   --start-capital 10000   --portfolio-size 10   --max-trades-per-month 2   --max-funding-sell-pct 0.20
```

---

# Funding-Sells

Funding-Sells sind defensive Teilverkäufe bestehender Positionen.

Sie werden nur verwendet wenn:

- Cash für neue BUYs fehlt
- bestehende Positionen über Bucket-Größe liegen
- max_funding_sell_pct dies erlaubt

Funding-Sells:

- schließen Positionen nicht
- zählen nicht gegen max_trades_per_month
- dienen nur zur Finanzierung neuer BUYs
