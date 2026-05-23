# Quant Portfolio System

Regelbasiertes quantitatives Portfolio-Management-System für Aktien.

Dieses System erzeugt Kauf- und Verkaufsvorschläge, simuliert ein regelbasiertes Shadow Portfolio und trackt ein reales Portfolio inklusive Cash, Gebühren, Steuern und Performance.

Wichtig:

- kein automatisches Trading
- keine Broker-Anbindung
- alle Trades werden manuell umgesetzt
- Fokus auf Nachvollziehbarkeit und Einfachheit
- keine Blackbox

---

# Inhaltsverzeichnis

## I. Einführung
- [Was dieses System ist](#was-dieses-system-ist)
- [Was dieses System nicht ist](#was-dieses-system-nicht-ist)
- [Ziel des Systems](#ziel-des-systems)
- [Die drei Portfolio-Ebenen](#die-drei-portfolio-ebenen)

## II. Strategie
- [Faktor-Modell](#faktor-modell)
- [Universum](#universum)
- [Value](#value)
- [Quality](#quality)
- [Momentum](#momentum)
- [Trendfilter](#trendfilter)
- [Buy-Regeln](#buy-regeln)
- [Sell-Regeln](#sell-regeln)
- [Portfolio-Regeln](#portfolio-regeln)

## III. Installation
- [Voraussetzungen](#voraussetzungen)
- [Docker & Docker Compose auf Debian 13 installieren](#docker--docker-compose-auf-debian-13-installieren)
- [Projekt installieren](#projekt-installieren)
- [Docker Images bauen](#docker-images-bauen)
- [Initiales Setup](#initiales-setup)
- [Status prüfen](#status-prüfen)

## IV. Operativer Betrieb
- [Operations Guide](docs/operations.md)
- [Daily Operations](docs/operations.md#daily-operations)
- [Monthly Operations](docs/operations.md#monthly-operations)
- [Status-System](docs/operations.md#status-system)
- [Trade Execution](docs/operations.md#trade-execution)
- [Performance](docs/operations.md#performance)
- [Aliases & Shortcuts](docs/operations.md#operator-shortcuts)
- [Best Practices](docs/operations.md#best-practices)

## V. Weitere Dokumentation
- [Strategie-Dokumentation](docs/strategy.md)
- [Architektur-Dokumentation](docs/architecture.md)
- [Troubleshooting Guide](docs/troubleshooting.md)

## VI. Git & Versionierung
- [Git Status](#git-status)
- [Commit](#commit)
- [Tag erstellen](#tag-erstellen)
- [Push](#push)

---

# Was dieses System ist

Das Projekt ist ein regelbasiertes quantitatives Portfolio-System.

Es kombiniert:

- Value
- Quality
- Momentum

zu einem einfachen und nachvollziehbaren Entscheidungsmodell.

Das System beantwortet regelmäßig:

```text
Welche Aktien würde das Modell aktuell kaufen?
Welche Aktien sollten verkauft werden?
Wie stark weicht mein reales Portfolio vom Modell ab?
```

---

# Was dieses System NICHT ist

- kein automatisches Trading-System
- keine Broker-Anbindung
- kein Daytrading
- keine KI-Blackbox
- keine Echtzeitoptimierung

Trades werden immer manuell ausgeführt.

---

# Ziel des Systems

Das System soll:

- robust sein
- reproduzierbar sein
- transparent bleiben
- einfach wartbar bleiben

Prinzip:

```text
So einfach wie möglich, aber nicht einfacher.
```

---

# Die drei Portfolio-Ebenen

## 1. Raw Model Portfolio

Reines Ranking der besten Aktien nach Faktor-Score.

## 2. Tradable Shadow Portfolio

Regelbasierte simulierte Umsetzung inklusive:

- Mindesthaltedauer
- Turnover Control
- Sektorlimit
- Gebühren
- Steuern

## 3. Real Portfolio

Tatsächlich manuell ausgeführte Trades.

---

# Faktor-Modell

Aktive Strategie-Version:

```text
v1.5
```

| Faktor | Gewicht |
|---|---:|
| Value | 35% |
| Quality | 35% |
| Momentum | 30% |

---

# Universum

Basis:

```text
S&P 500
```

Filter:

- Preis > 10 USD
- Market Cap > 2 Milliarden USD
- ausreichende Liquidität
- valide Datenqualität

---

# Value

Verwendete Kennzahlen:

- EV / EBIT
- Free Cash Flow Yield
- Earnings Yield

Bewertung erfolgt sektorrelativ.

---

# Quality

Verwendete Kennzahlen:

- ROE
- Debt / Equity
- Revenue Growth

Bewertung erfolgt sektorrelativ.

---

# Momentum

Verwendete Kennzahlen:

- 12-Month Return
- 6-Month Return
- Relative Strength vs Benchmark

Momentum wird global bewertet.

---

# Trendfilter

Neue Käufe sind nur erlaubt wenn:

```text
Preis > 200DMA
```

---

# Buy-Regeln

```text
Rank <= 10
UND
Trend positiv
```

---

# Sell-Regeln

```text
Rank > 20
ODER
Trend negativ
```

---

# Portfolio-Regeln

- konfigurierbare Zielgröße (z. B. 5 / 7 / 10 / 15 Positionen)
- Equal Weight
- max. 2 Aktien pro Sektor
- Mindesthaltedauer: 3 Monate
- konfigurierbare max. Positionswechsel pro Monat
- dynamisches effektives Trade-Limit bei unterfülltem Portfolio
- Funding-Sells für kontrollierten Portfolio-Aufbau
- Handelskosten: 1 EUR pro Trade

---

# Voraussetzungen

Benötigt:

- Debian 13 (empfohlen)
- Git
- Docker Engine
- Docker Compose Plugin

Python muss nicht lokal installiert werden.

Alle Python-Abhängigkeiten werden automatisch im Docker-Container installiert.

---

# Docker & Docker Compose auf Debian 13 installieren

## 1. System vorbereiten

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
```

## 2. Docker GPG-Key hinzufügen

```bash
sudo install -m 0755 -d /etc/apt/keyrings

curl -fsSL https://download.docker.com/linux/debian/gpg | \
sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

sudo chmod a+r /etc/apt/keyrings/docker.gpg
```

## 3. Docker Repository hinzufügen

```bash
echo \
  "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

## 4. Docker installieren

```bash
sudo apt update

sudo apt install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin
```

## 5. Docker testen

```bash
sudo docker run hello-world
```

---

# Projekt installieren

## Repository klonen

```bash
git clone <REPOSITORY_URL>
cd <REPOSITORY_NAME>
```

## Docker Images bauen

```bash
docker compose build
```

Dabei werden automatisch installiert:

- Python
- requirements.txt
- alle Dependencies

## Datenbank starten

```bash
docker compose up -d db phpmyadmin
```

## Initiales Setup

Das Setup unterstützt jetzt zusätzlich:

- `--portfolio-size`
- `--max-trades-per-month`
- `--max-funding-sell-pct`

Damit kann die Zielgröße und Turnover-Control bereits beim ersten Setup definiert werden.

```bash
./setup.sh init \
  --start-capital 10000 \
  --portfolio-size 10 \
  --max-trades-per-month 2 \
  --max-funding-sell-pct 0.20
```



---

# Laufende Änderung aktiver Settings

Die wichtigsten Strategie-Parameter können im laufenden Betrieb geändert werden.

Wichtig:

- Änderungen gelten nur für zukünftige Monatsläufe
- bestehende Snapshots bleiben unverändert
- historische Rebalance-Stände werden niemals überschrieben

## Portfolio-Größe ändern

```bash
docker compose run --rm app python -m cli.update_settings \
  --portfolio-size 10
```

## Max Trades ändern

```bash
docker compose run --rm app python -m cli.update_settings \
  --max-trades-per-month 3
```

## Funding-Sell-Limit ändern

```bash
docker compose run --rm app python -m cli.update_settings \
  --max-funding-sell-pct 0.25
```

## Mehrere Werte gleichzeitig ändern

```bash
docker compose run --rm app python -m cli.update_settings \
  --portfolio-size 10 \
  --max-trades-per-month 3 \
  --max-funding-sell-pct 0.25
```

## Dry-Run

```bash
docker compose run --rm app python -m cli.update_settings \
  --portfolio-size 15 \
  --dry-run
```

---

# Dynamisches Trade-Limit

Das System verwendet jetzt ein effektives Trade-Limit:

```text
max(max_trades_per_month, fehlende_positionen)
```

Beispiel:

```text
portfolio_size = 10
real_positionen = 5
max_trades_per_month = 2

=> effektives_limit = 5
```

Dadurch kann ein unterfülltes Portfolio kontrolliert aufgebaut werden.

---

# Funding-Sells

Wenn für neue BUYs nicht genug Cash vorhanden ist, darf das System bestehende Positionen teilweise reduzieren.

Begrenzung:

```text
max_funding_sell_pct
```

Beispiel:

```text
0.20 = maximal 20% des Positionswerts
```

Funding-Sells:

- schließen Positionen nicht vollständig
- zählen nicht gegen das normale Trade-Limit
- dienen ausschließlich zur Finanzierung neuer BUYs


## Status prüfen

```bash
docker compose run --rm app python -m cli.show_status --details
```

---

# Weitere Dokumentation

- [Operations Guide](docs/operations.md)
- [Strategie](docs/strategy.md)
- [Architektur](docs/architecture.md)
- [Troubleshooting](docs/troubleshooting.md)

---

# Git Status

```bash
git status
```

# Commit

```bash
git add .
git commit -m "Beschreibung"
```

# Tag erstellen

```bash
git tag v2.12
```

# Push

```bash
git push
git push origin v2.12
git push --tags
```
