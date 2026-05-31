# Quant Portfolio System

Regelbasiertes quantitatives Portfolio- und Strategie-Evaluationssystem für Aktien.

Das Projekt wird vom bisherigen operativen Portfolio-System zu einem modularen Quant-Framework weiterentwickelt. Die Kernfrage des neuen Systems lautet:

```text
Schlägt eine Strategie mit bestimmten Parametern, Indikatoren, Datenquellen und einem definierten Universum ihren passenden Benchmark?
```

Das System soll Strategien reproduzierbar testen, mit Benchmarks vergleichen und später wieder in einen Live-Betrieb mit Model Portfolio, Shadow Portfolio, Real Portfolio und Execution Gap überführen.

Der aktuelle Default-Use-Case bleibt bewusst konkret:

```text
Universum      : S&P 500
Strategie     : Value / Quality / Momentum
Datenbasis    : tägliche Kerzendaten, Fundamentaldaten, Market-Cap-Daten
Benchmark     : SPY
Auswertung    : Strategie-Rendite vs. Benchmark, Equity Curve, Trades, Kennzahlen
Live-Betrieb  : manuelle Trade-Ausführung, Cash-Ledger, Shadow-vs-Real-Vergleich
```

Das bestehende operative System bleibt als Legacy-Referenz erhalten. Das neue Framework entsteht daneben in klar getrennten Modulen für Datenzugriff, Universen, Indikatoren, Strategien, Simulation, Evaluation und Live-Betrieb.

Wichtig:

- kein automatisches Trading
- keine Broker-Anbindung
- alle Trades werden manuell umgesetzt
- Fokus auf Nachvollziehbarkeit und Einfachheit
- keine Blackbox
- Tests und Experimente sollen ohne API-Zugriff mit Fixture-/Demo-Daten möglich sein

Dokumentationsregel:

- Jede implementierte Änderung, die Setup, Architektur, Bedienung, Datenmodell, Strategie, Tests oder Operator-Workflows betrifft, wird in dieser README dokumentiert.
- Detaildokumente in `docs/` können ergänzen, die README bleibt aber die erste Orientierung für den aktuellen lauffähigen Stand.

---

# Inhaltsverzeichnis

## I. Einführung
- [Projektstatus](#projektstatus)
- [Default-Use-Case](#default-use-case)
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
- [Day-to-day Einstieg](docs/operations.md#day-to-day-einstieg)
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
- [Datenmodell-Plan](docs/data-model.md)
- [Assetklassen & Daten-Capabilities](docs/data-capabilities.md)
- [Provider-/API-Modell](docs/provider-api-model.md)
- [Troubleshooting Guide](docs/troubleshooting.md)

## VI. Git & Versionierung
- [Git Status](#git-status)
- [Commit](#commit)
- [Tag erstellen](#tag-erstellen)
- [Push](#push)

---

# Projektstatus

Das bisherige operative Quant-Portfolio-System ist als Referenz unter `legacy/current_system/` eingefroren:

- `legacy/current_system/core/`
- `legacy/current_system/cli/`
- `legacy/current_system/research/`
- `legacy/current_system/shared/`

Die neue modulare Paketstruktur ist angelegt. Der read-only Rohdatenzugriff aus
AP2 und die standardisierten Modul-Contracts aus AP3 sind implementiert:

- `data/`
- `universes/`
- `indicators/`
- `strategies/`
- `simulation/`
- `evaluation/`
- `live/`
- `cli/`
- `shared/`

AP8 ist abgeschlossen: Der neue modulare Datenzugriff kann die bestehenden
Rohdatentabellen read-only lesen, austauschbare Bausteine haben klare
Python-Contracts, und Universen sowie Benchmarks koennen per Konfigurationskey
ausgewaehlt werden. Erste Indikatoren fuer Momentum, relative Staerke, Value
und Quality werden modular berechnet. Die erste Value/Quality/Momentum-Strategie
erzeugt daraus eine reproduzierbare Rangliste und ein erstes Model Portfolio.
Die Strategie kann jetzt ueber einen einfachen periodischen Backtest gegen den
Benchmark evaluiert werden; Equity Curve, Trades, Metriken und eingefrorene
Run-Konfiguration koennen in AP8-Tabellen gespeichert werden.
Der Datenmodell-Entwurf und Schema-Plan ist in
[docs/data-model.md](docs/data-model.md) dokumentiert. `init.sql` bleibt
vorerst Legacy-kompatibel; die AP8-Evaluationstabellen werden additiv durch
`cli.backtest_status --persist` angelegt.
Die bereinigte Testdatenbasis fuer das neue Framework liegt in
`fixtures/raw_market_data.sql`.

AP9 ist abgeschlossen: Der Live-Schnitt bildet Model, Shadow, Real und
Execution Gap im neuen `live/`-Paket ab. `cli.live_status` liest die
legacy-kompatiblen Live-Tabellen und zeigt Abweichungen zwischen Shadow-Ziel und
realem Portfolio. `cli.live_cash` und `cli.live_trade` buchen Cash-Bewegungen
und manuelle Trade-Ausfuehrungen in die bestehenden Live-Tabellen.

AP10 ist abgeschlossen: Die modularen Operator-CLIs verwenden einen
gemeinsamen Fehlerlayer fuer verwertbare Meldungen bei fehlenden Tabellen,
DB-Verbindungsproblemen, fehlenden Abhaengigkeiten und erwarteten leeren
Ergebnissen. `cli.operator_smoke` fuehrt den kompakten End-to-End-Check
Fixture-Health -> Strategie-Run -> Benchmark-Backtest aus.

AP11 ist abgeschlossen: Der neue modulare Data-Sync kann S&P-500-Ticker,
taegliche Candles inklusive Benchmark `SPY`, Fundamentaldaten und
Market-Cap-Snapshots ohne Legacy-Imports aktualisieren. yfinance/Wikipedia
liegen als Provider-Adapter unter `data/`, die Datenbank-Upserts im
`RawDataRepository`, und die Operator-Einstiege sind `cli.sync_prices`,
`cli.sync_fundamentals` und `cli.sync_data`.

AP12 ist abgeschlossen: `cli.daily_run` und `cli.monthly_run` stellen die neue
modulare Daily-/Monthly-Orchestrierung bereit. Der Daily-Run verbindet AP11
Data-Sync mit Indikator-/Strategie-Ausfuehrung und Model-Portfolio-Ausgabe.
Der Monthly-Run erzeugt das Model-Portfolio zum letzten verfuegbaren Handelstag
oder einem expliziten `--as-of-date`.

AP13 ist abgeschlossen: `cli.monthly_run --persist` schreibt die operativen
Model-/Shadow-/Rebalance-/Decision-Log-/Trade-Plan-Artefakte in die
legacy-kompatiblen Live-Tabellen. Ohne `--persist` bleibt der Monthly-Run
read-only. Doppelte Snapshots je Stichtag werden kontrolliert abgelehnt.

AP14 ist abgeschlossen: Der regulaere modulare Pfad nutzt jetzt kanonische
Tabellen statt legacy-kompatibler Tabellen. Rohdaten laufen ueber `assets`,
`asset_price_bars`, `asset_fundamental_reports` und `asset_market_caps`; AP23
ergaenzt `universes` und `universe_members` fuer historisierte
Universe-Mitgliedschaften.
Live-/Operations-Artefakte laufen ueber `portfolio_target_items`,
`live_rebalance_items`, `live_decision_items`, `live_trade_plans`,
`live_trade_plan_items`, `live_trade_executions`, `live_cash_ledger`,
`live_cash_balances` und `live_positions`. `init.sql`, Setup, Fixture,
Repositories, CLIs und fokussierte Regressionstests wurden auf dieses Schema
umgestellt.

AP15 ist abgeschlossen: Der Host-Crontab-Betrieb ist dokumentiert und ueber
`scripts/cron_daily.sh`, `scripts/cron_monthly.sh` und feste `flock`-/Logpfade
ausfuehrbar. `scripts/client_smoke.sh` prueft einen frischen isolierten Client
mit Fixture, kanonischem Schema, Startkapital, Monthly-Persistenz, Trade-Plan,
Live-Status, Cash-Dry-Run und optionaler Smoke-Trade-Buchung.

AP16 ist abgeschlossen: `live.performance` und `cli.live_performance` liefern
einen read-only Performance-Report fuer Real Portfolio, Shadow Portfolio und
Benchmark, initial `SPY`. Der Report erzeugt eine Wertreihe, Rendite,
Outperformance, Drawdown und Diagnosen aus kanonischen Live- und Preistabellen,
ohne Performance-Logik in eine spaetere UI zu verschieben.

AP17 ist abgeschlossen: Fuer DB-nahe Regressionen gibt es jetzt einen
isolierten MySQL-Testdienst `db_test`, einen pytest-`integration`-Marker,
geschuetzte Fixtures fuer Schema-Initialisierung und Fixture-Loading sowie
`scripts/db_integration_tests.sh`. Der schnelle Testlauf bleibt von echter
MySQL-Verifikation getrennt. DB-Integrationstests legen ausschliesslich die
isolierte Testdatenbank neu an und beruehren nicht die normale Entwicklungs-
oder Betriebsdatenbank.

AP18 ist abgeschlossen: Assetklassen, Universen und Daten-Capabilities sind
fachlich dokumentiert. `assets` ist kuenftig als allgemeiner Asset-Katalog zu
verstehen, Universen sind Asset-Auswahlen statt impliziter Datenannahmen, und
Strategien/Indikatoren/Benchmarks/Live-Workflows sollen ihre benoetigten
Capabilities wie `prices.daily_ohlcv`, `fundamentals.equity_reports`,
`market_caps`, `classification.equity_sector`, `live.cash` und
`live.positions` explizit deklarieren. Die aktuelle
Value/Quality/Momentum-Strategie ist als Aktienstrategie eingeordnet. AP18 war
ein Design- und Dokumentations-AP ohne Schema- oder Codeaenderungen.
Verifiziert wurde mit `.venv/bin/python -m pytest tests -m "not integration"`
und `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`.

AP19 ist abgeschlossen: Das Provider-/API-Modell ist als eigener
Planungs-AP dokumentiert. Universen, Provider, Provider-Konfigurationen,
Source-Rollen und Capabilities sind getrennt beschrieben, damit Yahoo Finance
nur ein moeglicher Equity-Provider ist, Binance z. B. ein Krypto-Provider sein
kann und kommerzielle S&P-/Nasdaq-/Fundamental-Anbieter austauschbar
modelliert werden koennen. AP19 war ein Design- und Dokumentations-AP ohne
Schema- oder Codeaenderungen. Verifiziert wurde mit
`.venv/bin/python -m pytest tests -m "not integration"` und
`.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`.

AP20 ist abgeschlossen: `shared.capabilities` bildet Capability-Schluessel,
Source-Rollen, Provider-Capabilities, Universe-Profile, Default-Bindings und
Requirements fuer Strategie, Indikatoren, Benchmarks und Live-Workflows als
schemafreie Python-Definitionen ab. Der read-only Checker validiert den
heutigen `sp500_active` + `value_quality_momentum` + `spy` +
`mysql_fixture`-Pfad als gueltig und bricht inkompatible Kombinationen wie
Equity-Strategie auf Krypto-Universum, falsche Fundamentals-Provider oder
fehlende Source-Rollen frueh mit klaren Operator-Fehlern ab. Eingebunden ist
der Check in die gemeinsame Strategie-Orchestrierung, Strategie-/Indikator-/
Backtest-/Operator-Smoke-CLIs und die Live-Status-/Performance-/Cash-/
Trade-CLIs. AP20 aendert kein Schema und bindet keine neue externe API an.
Verifiziert wurde mit
`.venv/bin/python -m pytest tests/test_capabilities.py tests/test_orchestration.py`
und `.venv/bin/python -m compileall shared cli tests`.

AP21 ist abgeschlossen: Der Asset-Katalog ist jetzt technisch konkreter.
`assets` enthaelt Assetklasse, Canonical-/Display-Symbol, Instrumenttyp,
Exchange, Markt, Quote-Waehrung und Primaer-Provider.
Provider-spezifische Symbole und IDs liegen in
`asset_provider_identifiers`. Repository-Upserts erzeugen fuer den
Default-Pfad automatisch ein `mysql_fixture`-Ticker-Mapping, die Fixture
fuellt die Mapping-Tabelle aus den vorhandenen Assets, und der
Capability-Checker kann optional echte Asset-Metadaten sowie
Provider-Identifier-Coverage validieren. Die Strategie-Orchestrierung reicht
diese Daten fuer Provider durch, die Coverage melden koennen. Verifiziert
wurde mit
`.venv/bin/python -m pytest tests/test_capabilities.py tests/test_data_sync.py tests/test_orchestration.py`
und
`.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`.

AP22 ist abgeschlossen: Die AP21-Identifier-Basis wird jetzt im modularen Sync
operativ genutzt. `RawDataRepository.resolve_provider_symbols` loest interne
Ticker ueber `asset_provider_identifiers` zu Provider-Symbolen auf. Preis-Sync
laedt mit Provider-Symbolen und speichert normalisierte Kerzen weiter unter dem
internen Ticker. Fundamental-Sync laedt ebenfalls mit Provider-Symbolen und
mappt Reports/Market Caps auf den internen Ticker zurueck.
Universumsdefinitionen tragen jetzt explizite Metadaten fuer Assetklassen,
Membership-Source-Role/-Provider und Membership-Regel. Verifiziert wurde mit
`.venv/bin/python -m pytest tests/test_data_sync.py tests/test_capabilities.py`
und
`.venv/bin/python -m compileall data universes shared cli tests`.

AP23 ist abgeschlossen: Universe-Identitaet und historisierte Mitgliedschaft
liegen jetzt in den kanonischen Tabellen `universes` und `universe_members`.
`init.sql` und die Rohdaten-Fixture seedet `sp500_active`, `active_tickers`
und `all_tickers`; `RawDataRepository` kann Universen und Mitglieder lesen,
Default-Mitgliedschaften bei Asset-Upserts pflegen und aktive
Mitgliedschaftsintervalle bei Deaktivierungen schliessen. Der modulare
Universe-Loader nutzt DB-Mitgliedschaften, wenn der Provider sie anbietet, und
behaelt fuer Tests/Fake-Provider den bisherigen `list_tickers`-Fallback.

AP24 ist abgeschlossen: Der kanonische Data-Sync-Audit-Trail
`data_sync_runs` ist in `init.sql`, der Rohdaten-Fixture, dem
`RawDataRepository`, den Preis-/Fundamental-/Membership-Syncs und
`cli.data_status --details` verdrahtet. Echte Sync-Laeufe speichern Provider,
Source-Rolle, Modus, Zeitfenster, Status, Zaehler und operator-sichtbare
Fehler. Dry-Runs bleiben weiterhin read-only und schreiben keine Audit-Zeilen.
Verifiziert wurde mit
`.venv/bin/python -m pytest tests/test_data_sync.py`,
`.venv/bin/python -m pytest tests -m "not integration"` und
`.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared tests`.

Als naechster technischer AP ist AP25 geplant: Sync-Audit-Bedienung und
Betriebshaertung ausbauen, z. B. dedizierte Filter-/Statusausgaben,
Retention-/Retry-Regeln und klarere Operator-Diagnosen auf Basis von
`data_sync_runs`.

Der Umbau erfolgt ab hier schrittweise. AP4 ist bewusst ein Infrastruktur-
Schritt, weil AP3 unter Windows mit WSL Toolchain-Probleme gezeigt hat:

1. Auf eine stabile Linux-Entwicklungsumgebung umziehen und dort venv, `requirements.txt`, Docker/Compose, MySQL und Fixture-Daten stabilisieren. Erledigt in AP4.
2. Universen und Benchmarks als Konfiguration konkretisieren. Erledigt in AP5.
3. Indikator-Engine fuer Momentum, relative Staerke, Value und Quality bauen. Erledigt in AP6.
4. Erste Value/Quality/Momentum-Strategie als Model-Portfolio-Ranking bauen. Erledigt in AP7.
5. Erste Strategie gegen Benchmark evaluieren. Erledigt in AP8.
6. Live-Funktionen wieder anbinden. Erledigt in AP9.
7. CLI- und Operator-Workflows stabilisieren. Erledigt in AP10.
8. Modularen Data-Sync als Legacy-Ersatz bauen. Erledigt in AP11.
9. Daily-/Monthly-Orchestrierung aus Legacy herausziehen. Erledigt in AP12.
10. Model-/Shadow-/Trade-Plan-Persistenz migrieren. Erledigt in AP13.
11. Legacy-unabhaengiges kanonisches Schema und operativen Cutover bauen. Erledigt in AP14.
12. Crontab-Betrieb fuer Daily und Monthly dokumentieren und testen. Erledigt in AP15.
13. Live-/Shadow-/Benchmark-Performance-Reporting bauen. Erledigt in AP16.
14. Isolierte Testdatenbank und DB-Integrationsregression einfuehren.
    Erledigt in AP17.
15. Assetklassen, Universen und Daten-Capabilities fuer neue Datenarten
    modellieren. Erledigt in AP18.
16. Provider-/API-Bindings und Source-of-Truth je Datenart planen.
    Erledigt in AP19.
17. Read-only Capability- und Provider-Checks fuer Strategie-, Indikator-,
    Benchmark- und Live-Anforderungen einfuehren. Erledigt in AP20.
18. Asset-Katalog und Provider-Identifier-Basis fuer mehrere Assetklassen
    konkretisieren. Erledigt in AP21.
19. Provider-spezifische Symbolaufloesung und explizitere Universums-Metadaten
    auf Basis der Identifier-Mappings umsetzen. Erledigt in AP22.
20. Echte `universes`- und `universe_members`-Tabellen fuer
    DB-identifizierbare und historisierte Universen einfuehren. Erledigt in
    AP23.
21. Kanonischen Data-Sync-Audit-Trail fuer Provider, Modus, Zeitfenster,
    Status, Zeilenzaehler und Fehler einfuehren. Erledigt in AP24.
22. Sync-Audit-Bedienung und Betriebshaertung ausbauen. Naechster Schritt
    AP25.

Der Arbeitsplan steht in [plan.md](plan.md).

---

# Default-Use-Case

Der erste lauffähige Schnitt des neuen Systems ist:

```text
bestehende DB/Fixture-Daten lesen
-> S&P-500-Universum laden
-> Value/Quality/Momentum-Strategie ausführen
-> gegen SPY vergleichen
-> Run-Ergebnis speichern oder anzeigen
```

Verwendete Rohdaten:

- `assets`: handelbare Assets und Stammdaten inklusive Assetklasse,
  Canonical-/Display-Symbol, Markt und Quote-Waehrung
- `asset_provider_identifiers`: Provider-spezifische Symbole und IDs je Asset
- `asset_price_bars`: tägliche OHLCV-/Kerzendaten
- `asset_fundamental_reports`: Fundamentaldaten
- `asset_market_caps`: Market-Cap-Historie

Neuer modularer Datenzugriff:

```bash
docker compose run --rm app python -m cli.data_status --details
docker compose run --rm app python -m cli.framework_status --universe sp500_active --benchmark spy
docker compose run --rm app python -m cli.framework_status --list-configs
docker compose run --rm app python -m cli.indicator_status --limit 10
docker compose run --rm app python -m cli.strategy_status --limit 10
docker compose run --rm app python -m cli.backtest_status --start-date 2026-01-02 --end-date 2026-05-22 --equity-limit 5 --trade-limit 10
docker compose run --rm app python -m cli.operator_smoke --ranking-limit 5 --trade-limit 5
docker compose run --rm app python -m cli.sync_prices --dry-run --plan-limit 5
docker compose run --rm app python -m cli.sync_fundamentals --dry-run --plan-limit 5
docker compose run --rm app python -m cli.sync_data --dry-run
docker compose run --rm app python -m cli.daily_run --dry-run-sync --model-limit 5
docker compose run --rm app python -m cli.monthly_run --model-limit 5
docker compose run --rm app python -m cli.live_performance --curve-limit 5
```

Bereinigte Rohdaten-Fixture-Daten aus `fixtures/raw_market_data.sql` koennen
ohne API-Zugriff in eine lokale Docker-Datenbank geladen werden:

```bash
cp .env.example .env
docker compose up -d db
docker compose exec -T db sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < fixtures/raw_market_data.sql
docker compose exec -T db sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < init.sql
docker compose run --rm app python -m cli.data_status --details
docker compose run --rm app python -m cli.framework_status --universe sp500_active --benchmark spy
docker compose run --rm app python -m cli.indicator_status --limit 10
docker compose run --rm app python -m cli.strategy_status --limit 10
docker compose run --rm app python -m cli.backtest_status --start-date 2026-01-02 --end-date 2026-05-22 --persist --equity-limit 5 --trade-limit 10
docker compose run --rm app python -m cli.operator_smoke --ranking-limit 5 --trade-limit 5
```

Die Fixture enthaelt nur raw-data- und universe-nahe Tabellen: `assets`,
`asset_provider_identifiers`, `universes`, `universe_members`,
`asset_price_bars`, `asset_fundamental_reports` und `asset_market_caps`.
Live-Daten wie Trades, Cash Ledger, Real-Positionen und Performance-Snapshots
sind bewusst nicht enthalten. `init.sql` legt die kanonischen
Live-/Operations-Tabellen an.

AP14-Live-Status und Write-CLIs laufen gegen die kanonischen Live-Tabellen:

```bash
docker compose run --rm app python -m cli.live_status
docker compose run --rm app python -m cli.live_performance --curve-limit 5
docker compose run --rm app python -m cli.live_cash --type deposit --amount 1000 --as-of-date 2026-04-30 --dry-run
docker compose run --rm app python -m cli.live_trade --help
```

Programmatisch kann der AP7/AP8-Zugriff so verwendet werden:

```python
from datetime import date, timedelta

from data import FixtureDataProvider
from evaluation import BacktestConfig, create_benchmark, run_backtest
from indicators import compute_indicators, create_indicators
from strategies import StrategyContext, create_default_strategy
from universes import create_universe

provider = FixtureDataProvider()
universe = create_universe("sp500_active", provider)
benchmark = create_benchmark("spy", provider)

as_of_date = date(2026, 5, 22)
start_date = as_of_date - timedelta(days=259)
members = universe.load_members(as_of_date)
prices = provider.load_prices(members, start_date=start_date, end_date=as_of_date)
fundamentals = provider.load_fundamentals(
    members,
    report_type="ttm",
    end_date=as_of_date,
)
market_caps = provider.load_market_caps(members, end_date=as_of_date)
benchmark_prices = benchmark.load_prices(start_date=start_date, end_date=as_of_date)
indicator_values = compute_indicators(
    create_indicators(),
    prices=prices,
    fundamentals=fundamentals,
    market_caps=market_caps,
    as_of_date=as_of_date,
)
strategy = create_default_strategy(portfolio_size=7)
result = strategy.run(
    StrategyContext(
        as_of_date=as_of_date,
        universe=members,
        prices=prices,
        fundamentals=fundamentals,
        market_caps=market_caps,
        benchmark_prices=benchmark_prices,
        indicators={"default": indicator_values},
    )
)
backtest = run_backtest(
    strategy=strategy,
    config=BacktestConfig(
        start_date=date(2026, 1, 2),
        end_date=as_of_date,
        initial_capital=10000,
    ),
    universe=members,
    prices=provider.load_prices(
        members,
        start_date=date(2025, 4, 19),
        end_date=as_of_date,
    ),
    fundamentals=fundamentals,
    market_caps=market_caps,
    benchmark_prices=benchmark_prices,
)
```

Die aktuelle Default-Strategie nutzt:

- Value-Kennzahlen: Free-Cash-Flow-Yield und Earnings Yield
- Quality-Kennzahlen: ROE und Debt/Equity
- Momentum-Kennzahlen: 12-Month Return und Relative Strength
- Top-Positionen als gleichgewichtetes Raw Model Portfolio

---

# Was dieses System ist

Das Projekt ist ein regelbasiertes quantitatives Portfolio- und Strategie-Evaluationssystem.

Es kombiniert:

- Value
- Quality
- Momentum

zu einem einfachen und nachvollziehbaren Entscheidungsmodell.

Das System beantwortet regelmäßig:

```text
Welche Strategie schlägt welchen Benchmark?
Welche Parameter funktionieren auf welchem Universum?
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
- Python 3 mit venv/pip fuer lokale AP4-Smoke-Checks

Die produktiven Kommandos laufen weiterhin im Docker-Container. Fuer AP4 wird
zusaetzlich eine lokale Linux-venv verwendet, damit Provider-, Universe- und
Benchmark-Contracts auch ohne Windows-/WSL-Sonderfaelle geprueft werden
koennen.

---

# Docker & Docker Compose auf Debian 13 installieren

## 1. System vorbereiten

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg python3-venv python3-pip
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

## Umgebung konfigurieren

Vor Docker-Start und Setup die Beispielumgebung kopieren:

```bash
cp .env.example .env
```

Die Default-Werte sind fuer die lokale Docker-Entwicklung vorbereitet:

```text
MYSQL_ROOT_PASSWORD=mypassword
DB_NAME=stocks_db
DB_HOST=localhost
```

Bei produktiver Nutzung die Passwoerter in `.env` anpassen. Wenn das
Passwort geaendert wird, muss `DB_PASSWORD` zum `MYSQL_ROOT_PASSWORD` passen,
solange `DB_USER=root` genutzt wird.

Wichtig fuer bestehende Docker-Volumes: Eine spaetere Aenderung von
`MYSQL_ROOT_PASSWORD` in `.env` aendert nicht rueckwirkend das Root-Passwort in
einer bereits initialisierten MySQL-Datenbank. Dafuer ist ein frischer Init mit
Volume-Reset noetig, zum Beispiel ueber `./setup.sh init ...` oder
`docker compose down -v --remove-orphans`.

## Docker-Only Pfad

```bash
docker compose build
```

Damit wird das Docker-App-Image gebaut. Innerhalb des Containers werden Python
und die Abhaengigkeiten aus `requirements.txt` installiert.

Dieser Pfad reicht aus, wenn du das System nur ueber Docker-Kommandos wie
`docker compose run --rm app ...` testen oder betreiben willst.

Im Docker-Image enthalten:

- Python
- Abhaengigkeiten aus `requirements.txt`

## Optional: Lokale Linux-venv fuer Host-Entwicklung

Die lokale `.venv` auf dem Host ist ein separater optionaler Pfad. Sie ist nur
noetig, wenn du Tests oder CLIs direkt auf dem Host statt im Container
ausfuehren willst.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared
```

Beispiel fuer Host-Nutzung:

```bash
.venv/bin/python -m pytest tests -m "not integration"
```

Die lokale venv nutzt standardmaessig `DB_HOST=localhost`, waehrend der Docker-
App-Container explizit mit `DB_HOST=db` startet.

## Datenbank starten

```bash
docker compose up -d db phpmyadmin
```

phpMyAdmin ist danach ueber Port `8080` erreichbar. Im Login-Dialog gilt:

- Server: `db`
- Benutzer: `root`
- Passwort: das aktuell aktive MySQL-Root-Passwort

`localhost` ist dort falsch, weil phpMyAdmin im eigenen Container laeuft und
MySQL intern ueber den Docker-Service `db` erreicht.

## Initiales Setup

Fuer einen lokalen Test mit Fixture-Daten den AP15-Pfad einmal frisch
initialisieren. Das Kommando setzt Docker-Container und Datenbank-Volume zurueck
und fragt deshalb interaktiv nach `yes`.

Dieser Schritt ist auch noetig, wenn `.env` geaendert wurde und das neue
`MYSQL_ROOT_PASSWORD` wirklich in der laufenden MySQL-Instanz gelten soll.

Das Setup unterstützt jetzt zusätzlich:

- `--portfolio-size`
- `--max-trades-per-month`
- `--max-funding-sell-pct`

Damit kann die Zielgröße und Turnover-Control bereits beim ersten Setup definiert werden.

```bash
./setup.sh init \
  --start-capital 10000 \
  --portfolio-size 7 \
  --max-trades-per-month 4 \
  --max-sector-positions 3 \
  --min-holding-months 2 \
  --max-funding-sell-pct 0.35 \
  --load-fixture
```

Ohne Fixture-Daten wird die Rohdatenbank leer angelegt; dann muss vor Strategie-
oder Monthly-Runs ein echter Data-Sync laufen.

## Lokalen Operator-Test Schritt Fuer Schritt

Fuer die Entwicklung gibt es einen automatisierten Checklauf:

```bash
scripts/dev_check.sh
```

Der Default laeuft im Docker-App-Container und prueft `compileall` sowie die
schnelle Pytest-Suite ohne DB-Integration. Fuer DB-Integrationsregressionen
gegen den isolierten MySQL-Testdienst:

```bash
scripts/db_integration_tests.sh
```

Der DB-Test-Runner startet den Compose-Service `db_test`, nutzt standardmaessig
die Datenbank `quant4free_test`, laedt `fixtures/raw_market_data.sql` und
`init.sql` ueber pytest-Fixtures und loescht danach nur diese Testdatenbank.
Die normale `db`-Entwicklungsdatenbank wird dabei nicht verwendet.

Fuer einen isolierten End-to-End-Smoke mit eigener Testdatenbank:

```bash
scripts/dev_check.sh --smoke
```

Mit echten Smoke-Trade-Buchungen in dieser isolierten Testdatenbank:

```bash
scripts/dev_check.sh --smoke --execute-smoke-trades
```

Nach dem initialen Setup kann der aktuelle Stand ohne externe API-Aufrufe
getestet werden:

```bash
docker compose ps
docker compose run --rm app python -m cli.data_status --details
docker compose run --rm app python -m cli.operator_smoke --ranking-limit 5 --trade-limit 5
docker compose run --rm app python -m cli.live_status --all --limit 10
```

Mit der AP15-Fixture und den Default-Parametern aus dieser Anleitung ist als
Beispielergebnis im Live-Status zu erwarten, dass die Real-Positionen noch
fehlen und diese Shadow-/Kaufkandidaten auftauchen:

```text
APA
CB
CF
INCY
NEM
TRV
```

Das sind Fixture-Testdaten fuer die Systempruefung, keine aktuellen
Anlageempfehlungen. Wenn Fixture, Strategieparameter oder Stichtag geaendert
werden, kann die Liste abweichen.

Einen Monthly-Run erst read-only pruefen:

```bash
docker compose run --rm app python -m cli.monthly_run --model-limit 7
```

Danach die operativen Artefakte persistieren. Dafuer genau eine der beiden
Varianten verwenden, weil ein zweiter Persist-Run fuer denselben Stichtag
kontrolliert abgelehnt wird.

Variante A: direkt ueber die CLI:

```bash
docker compose run --rm app python -m cli.monthly_run --persist --model-limit 7
docker compose run --rm app python -m cli.live_status --all --limit 10
```

Variante B: ueber das Monthly-Cron-Skript mit Lock und Log:

```bash
mkdir -p var/log var/lock
flock -n var/lock/monthly_run.lock scripts/cron_monthly.sh >> var/log/monthly_run.log 2>&1
tail -100 var/log/monthly_run.log
docker compose run --rm app python -m cli.live_status --all --limit 10
```

Den erzeugten Trade-Plan in der Datenbank ansehen:

```sql
SELECT as_of_date, execution_order, action, ticker, planned_shares, estimated_price, fee, is_executable
FROM live_trade_plan_items
ORDER BY as_of_date DESC, execution_order, ticker;
```

Cash- und Trade-Ausfuehrung nur als Dry-Run testen. Fuer den Trade-Test eine
Zeile aus `live_trade_plan_items` verwenden, statt einen freien Beispielticker
zu raten:

```bash
docker compose run --rm app python -m cli.live_cash --type deposit --amount 1000 --as-of-date 2026-05-22 --dry-run
```

Der folgende Bash-Block liest automatisch die erste ausfuehrbare BUY-Zeile aus
`live_trade_plan_items` und speichert `as_of_date`, `ticker`, `planned_shares`,
`estimated_price` und `fee` in Shell-Variablen. Diese Variablen werden danach
im `cli.live_trade --dry-run` verwendet:

```bash
read -r TRADE_AS_OF_DATE TRADE_TICKER TRADE_SHARES TRADE_PRICE TRADE_FEE < <(
  docker compose exec -T db sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -B -N -e "
    SELECT as_of_date, ticker, planned_shares, estimated_price, fee
    FROM live_trade_plan_items
    WHERE action = '\''BUY'\'' AND is_executable = 1
    ORDER BY as_of_date DESC, execution_order, ticker
    LIMIT 1;
  "'
)

docker compose run --rm app python -m cli.live_trade \
  --execution-type BUY \
  --ticker "${TRADE_TICKER}" \
  --shares "${TRADE_SHARES}" \
  --price "${TRADE_PRICE}" \
  --fee "${TRADE_FEE}" \
  --as-of-date "${TRADE_AS_OF_DATE}" \
  --trade-plan-action BUY \
  --dry-run
```

Das Daily-Cron-Skript manuell mit Lock und Log laufen lassen:

```bash
mkdir -p var/log var/lock
flock -n var/lock/daily_run.lock scripts/cron_daily.sh --dry-run-sync --model-limit 7 >> var/log/daily_run.log 2>&1
tail -100 var/log/daily_run.log
```

Den isolierten AP15-Client-Smoke optional gegen eine eigene Testdatenbank
ausfuehren:

```bash
scripts/client_smoke.sh --db-name ap15_client_smoke --mysql-root-password mypassword
```

Erst wenn diese manuellen Laeufe passen, die echten Host-Crontab-Eintraege aus
[docs/operations.md](docs/operations.md) setzen.



---

# Laufende Änderung aktiver Settings

Aktive Strategie-Parameter liegen seit AP14 in `strategy_instances`. Fuer
Setup-/Rebuild-Szenarien koennen die wichtigsten Werte ueber `setup.sh`
gesetzt werden:

```bash
./setup.sh rebuild \
  --start-capital 10000 \
  --portfolio-size 10 \
  --max-trades-per-month 3 \
  --max-funding-sell-pct 0.25
```

Direkte Aenderungen in `strategy_instances` gelten nur fuer zukuenftige
Monatslaeufe; bereits eingefrorene `strategy_config_snapshots` bleiben
unveraendert.

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
docker compose run --rm app python -m cli.live_status --all --limit 10
```

## AP15 Client-Smoke Und Cron

Frischen isolierten Client-End-to-End-Smoke ausfuehren:

```bash
scripts/client_smoke.sh --db-name ap15_client_smoke --mysql-root-password mypassword
```

Host-Cronpfad manuell mit Lock und Log testen:

```bash
mkdir -p var/log var/lock
flock -n var/lock/daily_run.lock scripts/cron_daily.sh >> var/log/daily_run.log 2>&1
flock -n var/lock/monthly_run.lock scripts/cron_monthly.sh >> var/log/monthly_run.log 2>&1
```

Die vollstaendige Crontab-Dokumentation steht in
[docs/operations.md](docs/operations.md).

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
