# Plan: Neues Quant-System

## Umsetzungsstand

Stand: AP0 ist abgeschlossen.

Erledigt:

- Bestehende Module nach `legacy/current_system/` verschoben:
  - `core/`
  - `cli/`
  - `research/`
  - `shared/`
- Neue leere Paketstruktur angelegt:
  - `data/`
  - `universes/`
  - `indicators/`
  - `strategies/`
  - `simulation/`
  - `evaluation/`
  - `live/`
  - `cli/`
  - `shared/`
- Paketmarker `__init__.py` fuer die neue Struktur angelegt.
- README auf den AP0-Stand aktualisiert.
- `AGENTS.md` auf die neue Legacy-/Framework-Struktur aktualisiert.
- `.gitignore` um lokale IDE-/Venv-Verzeichnisse erweitert.
- `compileall` fuer Legacy und neue Paketstruktur erfolgreich ausgefuehrt.

Geprueft:

```bash
python3 -m compileall legacy/current_system
python3 -m compileall data universes indicators strategies simulation evaluation live cli shared
```

Wichtiger Hinweis:

- Die Legacy-CLI verwendet weiterhin alte absolute Imports wie `core.*` und `shared.*`.
- Legacy-Kommandos daher vorerst mit Legacy-Pythonpfad ausfuehren, z. B.:

```bash
docker compose run --rm -e PYTHONPATH=/app/legacy/current_system app python -m cli.core_main daily
```

Naechster Schritt:

- AP1: Datenmodell-Entwurf und Schema-Plan.

## Zielbild

Das neue System soll aus dem aktuellen operativen Quant-Portfolio-Projekt ein schlankes, erweiterbares Quant-Framework machen. Kernfrage:

```text
Schlaegt eine Strategie mit bestimmten Parametern, Indikatoren, Datenquellen und einem definierten Universum ihren passenden Benchmark?
```

Das System bleibt bewusst nach Occams Rasiermesser gebaut: Rohdaten sauber speichern, Strategien modular machen, Experimente kompakt auswerten, Live-Entscheidungen auditierbar halten und nichts dauerhaft speichern, was guenstig reproduzierbar ist.

## Was Das System Leisten Soll

- Mehrere Portfolios verwalten, spaeter mandantenfaehig mit `tenant_id`.
- Pro Portfolio Strategie, Universum, Benchmark, Datenquelle/API, Indikatoren und Parameter aendern koennen.
- Strategien gegeneinander evaluieren: Backtests, Parameter-Sweeps, Equity Curves, Benchmark-Vergleich.
- Live-Betrieb unterstuetzen: Model Portfolio, Shadow Portfolio, Real Portfolio, Execution Gap, manuelle Trades, Cash-Ledger.
- Pro Client/Portfolio/Run vollstaendig tracken, welche Konfiguration verwendet wurde.
- Tests und Experimente ohne API-Zugriff mit `stocks_db.sql` ermoeglichen.
- Weboberflaeche erst ganz am Schluss bauen, wenn Kern, Datenmodell und Workflows stabil sind.

## Behalten, Aendern, Weglassen

### Behalten

- Rohdatenbasis aus `tickers`, `daily_candles`, `financial_reports`, `market_cap_snapshots`.
- Docker/MySQL-Grundsetup.
- Manuelle Trade-Erfassung.
- Cash-/Trade-Historie.
- Performance-Vergleich gegen Benchmark.
- `stocks_db.sql` als Test- und Demo-Datenbasis.

### Aendern

- Strategien, Indikatoren, APIs, Universen und Benchmarks werden austauschbare Bausteine.
- `.env` enthaelt nur technische Zugaenge und Secrets.
- Fachliche Settings liegen versioniert in der DB.
- Operative Snapshots bleiben nur dort, wo Auditierbarkeit noetig ist.

### Weglassen Oder Reduzieren

- Keine grosse starre `strategy_settings`-Tabelle mit immer mehr Spalten.
- Keine Snapshot-Flut im Evaluation-System.
- Keine uebertriebene OO-/ORM-Struktur.
- Keine dauerhafte Speicherung billiger Zwischenberechnungen.

## Zielarchitektur

```text
legacy/current_system/
  eingefrorene Referenz des bisherigen operativen Systems

data/
  Datenzugriff, Provider-Adapter, Rohdaten-Normalisierung

universes/
  auswaehlbare Anlageuniversen und deren Mitglieder

indicators/
  modulare Indikatoren und Indikatorparameter

strategies/
  austauschbare Strategie-Logik

simulation/
  Portfolio-Simulation, Rebalancing, Kosten, Steuern

evaluation/
  Backtests, Parameter-Sweeps, Benchmark-Vergleich, Kennzahlen

live/
  Model Portfolio, Shadow Portfolio, Real Portfolio, Execution Gap

cli/
  Runs, Status, Experimente, Reports
```

Objektorientierung wird nur fuer austauschbare Konzepte eingesetzt: `Strategy`, `Indicator`, `DataProvider`, `Benchmark`, `PortfolioSimulator`, `CostModel`, `TaxModel`, `ExperimentRunner`. Massendaten bleiben in SQL/DataFrames.

## Umgang Mit Dem Altsystem

Das neue System wird als neues Framework parallel zum bestehenden operativen System gebaut. Die vorhandenen Module werden nicht schrittweise im bestehenden `core/` verbogen, sondern zuerst als Legacy-Referenz eingefroren.

Geplante Ablage:

```text
legacy/current_system/
  core/
  cli/
  research/
  shared/
```

Die Legacy-Version bleibt lesbar und lauffaehig genug, um bestehende Logik fuer Faktorberechnung, Portfolio-Build, Shadow Portfolio, Trade Plan, Cash-/Trade-Erfassung und Performance-Vergleich als Referenz zu nutzen.

Nicht blind verschoben werden zunaechst:

```text
init.sql
stocks_db.sql
docker-compose.yml
Dockerfile
setup.sh
requirements.txt
simfin/
docs/
```

Diese Dateien werden separat bewertet, weil sie Rohdaten, Infrastruktur, Demo-/Fixture-Daten oder Dokumentation betreffen und auch fuer das neue System relevant bleiben koennen.

Erster vertikaler Schnitt des neuen Systems:

```text
bestehende DB/Fixture-Daten lesen
-> Universum laden
-> Strategie ausfuehren
-> Benchmark vergleichen
-> Run-Ergebnis speichern oder anzeigen
```

## Datenmodell Grundidee

Dauerhaft gespeicherte Rohdaten:

```text
tickers
daily_candles
financial_reports
market_cap_snapshots
```

Neue Konfigurations- und Katalogtabellen:

```text
tenants
portfolios
universes
universe_members
data_providers
benchmarks
strategy_instances
```

`strategy_instances` enthaelt versionierte fachliche Konfigurationen:

```text
strategy_key
params_json
indicators_json
universe_id
benchmark_id
provider_config_id
valid_from
valid_to
is_active
```

Experiment-/Evaluation-Ergebnisse werden kompakt gespeichert:

```text
strategy_runs
strategy_run_metrics
strategy_run_equity_curve
strategy_run_trades
```

Live-Betrieb bleibt getrennt:

```text
live_trade_executions
cash_ledger
portfolio_positions
shadow_portfolio_state
```

## Shadow Portfolio

Das Shadow Portfolio bleibt im Live-Betrieb erhalten:

```text
Model Portfolio   = reine Strategieauswahl
Shadow Portfolio  = regelkonforme Soll-Umsetzung
Real Portfolio    = tatsaechlich ausgefuehrte Trades
Execution Gap     = Abweichung zwischen Shadow und Real
```

Im Evaluation-System wird dasselbe Konzept als simuliertes Portfolio mit Holdings, Trades und Equity Curve behandelt.

## Dynamische Bausteine

Clients koennen spaeter pro Portfolio auswaehlen oder aendern:

- Universum: z. B. S&P 500, Nasdaq 100, ETFs, eigene Watchlist.
- Datenquelle/API: z. B. yfinance, SimFin, CSV, spaeter weitere Provider.
- Benchmark: z. B. `SPY`, `QQQ`, `IWM`, eigener Marktindex.
- Strategie: z. B. Value/Quality/Momentum, Momentum, Quality, Low Volatility.
- Indikatoren und deren Parameter.
- Gewichtungen, Portfolio-Groesse, Buy-/Sell-Regeln, Rebalance-Frequenz.
- Kostenmodell und Steuermodell.

Aenderungen ueberschreiben keine Historie. Jede Aenderung erzeugt eine neue versionierte Strategieinstanz oder einen neuen Run-Snapshot.

## Arbeitspakete

Die Umsetzung erfolgt in kleinen, pruefbaren Arbeitspaketen. Jedes Paket endet mit einem lauffaehigen Zustand, einer kurzen Dokumentation der getroffenen Entscheidung und mindestens einer technischen Pruefung.

Dokumentationsregel:

- Jede implementierte Aenderung wird in `README.md` dokumentiert, sofern sie Setup, Architektur, Bedienung, Datenmodell, Strategie, Tests oder Operator-Workflows betrifft.
- Die README beschreibt immer den aktuellen lauffaehigen Stand, nicht nur das Zielbild.
- Neue CLI-Befehle, Datenbanktabellen, Standardkonfigurationen und Testpfade werden mit Beispiel dokumentiert.
- Detaildokumente in `docs/` duerfen ergaenzen, ersetzen aber nicht die kurze Orientierung in `README.md`.

### AP0: Projektbasis Und Legacy-Schnitt

Ziel:

- Bestehendes System als Referenz einfrieren.
- Neue Zielstruktur anlegen.
- Sicherstellen, dass keine IDE-, Venv- oder Cache-Dateien versehentlich Teil des Projekts werden.
- README initial auf das neue System ausrichten und den bisherigen Stand klar als Legacy/Referenz markieren.

Umfang:

- `.gitignore` fuer lokale Arbeitsdateien pruefen/ergaenzen.
- Bestehende Module nach `legacy/current_system/` verschieben:
  - `core/`
  - `cli/`
  - `research/`
  - `shared/`
- Neue leere Paketstruktur anlegen:
  - `data/`
  - `universes/`
  - `indicators/`
  - `strategies/`
  - `simulation/`
  - `evaluation/`
  - `live/`
  - `cli/`
  - `shared/`
- Imports noch nicht fachlich migrieren, sondern nur den sauberen Schnitt herstellen.
- README mit Zweck, Default-Use-Case und aktuellem Projektstatus aktualisieren.

Tests/Akzeptanz:

- `python3 -m compileall legacy/current_system`
- Neue Pakete sind importierbar, z. B. `python3 -m compileall data universes indicators strategies simulation evaluation live cli shared`
- `git status` zeigt nur erwartete Verschiebungen und neue Struktur.
- README erklaert, was das neue System macht und was der Default-Fall ist.

### AP1: Datenmodell-Entwurf Und Schema-Plan

Ziel:

- Neues Datenmodell konkretisieren, ohne sofort das bestehende Schema zu zerstoeren.
- Bestehende Tabellen aus `init.sql` den Bereichen Rohdaten, Konfiguration, Evaluation und Live zuordnen.

Umfang:

- Tabelleninventar aus `init.sql` dokumentieren.
- Zieltabellen fuer Portfolio, Universum, Benchmark, Provider, Strategieinstanzen und Runs definieren.
- Entscheiden, welche bestehenden Tabellen unveraendert weitergenutzt werden.
- Migrationsstrategie festlegen: neues `schema_v2.sql` oder additive Migrationen.

Tests/Akzeptanz:

- Dokumentierte Mapping-Tabelle: Alt-Tabelle -> neue Rolle -> behalten/aendern/ersetzen.
- SQL-Syntaxcheck fuer neue Schema-Datei, sofern bereits erstellt.
- Keine Veraenderung an operativen Daten ohne explizite Migration.

### AP2: Fixture-/Demo-Daten Lauffaehig Machen

Ziel:

- Entwicklung und Tests ohne API-Zugriff ermoeglichen.
- `stocks_db.sql` als reproduzierbare Datenbasis nutzbar machen.

Umfang:

- Dokumentieren, wie `stocks_db.sql` lokal in MySQL geladen wird.
- Kleinen Health-Check fuer vorhandene Kerzen, Ticker, Fundamentals und Benchmark-Daten bauen.
- Minimalen Test-Datensatz definieren, falls der Dump zu gross oder sensibel ist.

Tests/Akzeptanz:

- Datenbank kann aus Fixture neu aufgebaut werden.
- Health-Check meldet Anzahl Ticker, Preisreihen, Fundamentals und Benchmark-Verfuegbarkeit.
- Keine externen API-Calls fuer diesen Testpfad.

### AP3: Data-Provider-Schicht

Ziel:

- Rohdatenzugriff von Strategie- und Evaluationslogik trennen.

Umfang:

- `DataProvider`-Interface definieren.
- Ersten Provider fuer bestehende MySQL-/Fixture-Daten bauen.
- Spaeteren yfinance-Provider nur vorbereiten, nicht als Voraussetzung fuer Tests machen.
- Gemeinsame Rueckgabeformate fuer Preise, Fundamentals, Ticker und Benchmarks festlegen.

Tests/Akzeptanz:

- Provider liefert Preisreihen fuer ein Ticker-Set und einen Zeitraum.
- Provider liefert Benchmark-Reihe fuer z. B. `SPY`.
- Unit-Tests oder CLI-Smoke-Test laufen gegen Fixture-Daten.

### AP4: Universen Und Benchmarks

Ziel:

- Anlageuniversum und Benchmark als austauschbare Konfiguration behandeln.

Umfang:

- Tabellen/Modelle fuer `universes`, `universe_members`, `benchmarks` konkretisieren.
- Loader fuer ein erstes Universum bauen, z. B. S&P 500 aus bestehender DB.
- Benchmark-Resolver bauen.

Tests/Akzeptanz:

- CLI oder Test zeigt Mitglieder eines Universums.
- Benchmark kann pro Run eindeutig geladen werden.
- Fehlerfall wird sauber gemeldet, wenn Benchmark-Daten fehlen.

### AP5: Indikator-Engine

Ziel:

- Indikatoren modular berechnen, statt sie fest in eine Pipeline zu giessen.

Umfang:

- `Indicator`-Interface definieren.
- Erste Indikatoren aus der bestehenden Strategie extrahieren:
  - Momentum/Return
  - Relative Staerke
  - einfache Value-/Quality-Kennzahlen, soweit Daten vorhanden sind
- Parameterisierung pro Indikator ermoeglichen.

Tests/Akzeptanz:

- Indikatorberechnung ist fuer denselben Datenstand reproduzierbar.
- Fehlende Daten erzeugen definierte `NULL`/NaN-Behandlung statt stiller Fehlbewertung.
- Mindestens ein kleiner Test mit Fixture-Daten.

### AP6: Erste Strategie Value/Quality/Momentum

Ziel:

- Die bestehende Hauptstrategie als modulare Strategieinstanz nachbauen.

Umfang:

- `Strategy`-Interface definieren.
- Value/Quality/Momentum-Strategie mit konfigurierbaren Gewichten bauen.
- Ranking und Buy-/Sell-relevante Scores erzeugen.
- Ergebnis zunaechst nur als Model Portfolio ausgeben.

Tests/Akzeptanz:

- Strategie erzeugt fuer einen Stichtag eine reproduzierbare Rangliste.
- Gewichte werden validiert und muessen zusammen 1.0 ergeben.
- Vergleich gegen Legacy-Ergebnis fuer einen bekannten Stichtag, soweit Daten vorhanden sind.

### AP7: Evaluation Und Backtest

Ziel:

- Strategien gegen Benchmark evaluieren.

Umfang:

- `strategy_runs` und Ergebnisstruktur implementieren.
- Einfachen Backtest mit Rebalancing, Kostenmodell und Equity Curve bauen.
- Kennzahlen berechnen: Rendite, Benchmark-Rendite, Outperformance, Volatilitaet, Max Drawdown.
- Parameter-Sweeps vorbereiten.

Tests/Akzeptanz:

- Ein Run ist reproduzierbar speicherbar oder als Report ausgebbar.
- Equity Curve und Benchmark Curve haben konsistente Datumsachsen.
- Backtest laeuft komplett gegen Fixture-Daten.

### AP8: Live-System Wieder Anbinden

Ziel:

- Model, Shadow, Real und Execution Gap im neuen System abbilden.

Umfang:

- Bestehende Konzepte aus Legacy uebernehmen:
  - Model Portfolio
  - Shadow Portfolio
  - Real Portfolio
  - Cash Ledger
  - manuelle Trade-Ausfuehrung
- Live-Tabellen von Evaluation-Tabellen trennen.
- Auditierbare Snapshots nur dort speichern, wo sie fuer Live-Entscheidungen noetig sind.

Tests/Akzeptanz:

- Aktives Portfolio zeigt Model, Shadow, Real und Execution Gap.
- Manuelle Trade-Ausfuehrung veraendert Cash und Positionen nachvollziehbar.
- Legacy-Verhalten wird fuer einen Beispielmonat plausibilisiert.

### AP9: CLI Und Operator-Workflows

Ziel:

- Das neue System ohne Weboberflaeche bedienbar machen.

Umfang:

- CLI fuer Fixture-Health, Universum, Strategie-Run, Backtest, Status und Live-Aktionen.
- Klare Fehlerausgaben fuer fehlende Daten, falsche Konfiguration und leere Ergebnisse.
- Bestehende Operator-Dokumentation aktualisieren.

Tests/Akzeptanz:

- `compileall` fuer alle neuen und Legacy-Pakete.
- Smoke-Test: Fixture laden -> Strategie-Run -> Benchmark-Report.
- Status-CLI zeigt verwertbare Ausgabe ohne Weboberflaeche.

### AP10: Weboberflaeche Erst Nach Stabiler Kernlogik

Ziel:

- Eine UI erst bauen, wenn Datenmodell, Evaluation und Live-Workflows stabil sind.

Umfang:

- FastAPI oder vergleichbare schlanke API pruefen.
- UI nur als Client der Kernlogik bauen.
- Keine Fachlogik in die UI verschieben.

Tests/Akzeptanz:

- API-Endpunkte liefern dieselben Ergebnisse wie CLI-Reports.
- UI kann Runs, Portfolios und Status anzeigen, ohne Berechnungslogik zu duplizieren.

## Roadmap

1. Datenmodell und Modulstruktur entwerfen.
2. `stocks_db.sql` als Demo-/Fixture-Datenbasis nutzbar machen.
3. Provider-Schicht fuer bestehende DB/Fixture-Daten und yfinance einfuehren.
4. Indikator-Engine bauen.
5. Erste Strategie Value/Quality/Momentum modularisieren.
6. Evaluation-System mit Backtests, Parameter-Sweeps und Benchmark-Vergleich bauen.
7. Live-System mit Model, Shadow, Real, Execution Gap und manuellen Trades anbinden.
8. Konfiguration versionieren und pro Portfolio steuerbar machen.
9. CLI/Reports stabilisieren.
10. Weboberflaeche erst am Schluss bauen.

## Testing Und Akzeptanz

- `stocks_db.sql` wird als Demo-/Fixture-Datenbank genutzt, damit Ticker, Kerzen und Fundamentals ohne API-Aufrufe verfuegbar sind.
- Erste Akzeptanz: dieselben Rohdaten koennen fuer mehrere Strategien, Universen und Benchmarks genutzt werden.
- Backtest-Akzeptanz: ein Run erzeugt reproduzierbar Metriken, Equity Curve und simulierte Trades.
- Live-Akzeptanz: aktives Portfolio zeigt Model, Shadow, Real und Execution Gap.
- Konfigurations-Akzeptanz: Strategieaenderungen gelten nur ab neuem `valid_from` und zerstoeren keine historischen Ergebnisse.
- Spaetere Weboberflaeche ist nur Client; Fachlogik bleibt im Backend/Kern.

## Annahmen Und Defaults

- Start mit `portfolio_id`; echte Mandantenfaehigkeit mit `tenant_id` wird vorbereitet, aber nicht als erster Zwang umgesetzt.
- MySQL bleibt zunaechst bestehen.
- `stocks_db.sql` wird nicht als neues `init.sql` verwendet, sondern als Test-/Demo-Dump.
- Erste Provider sind bestehende DB/Fixture-Daten und yfinance; weitere APIs kommen ueber Adapter.
- Erste Strategie bleibt Value/Quality/Momentum, wird aber in die neue modulare Strategieform ueberfuehrt.
- Weboberflaeche kommt zuletzt, bevorzugt schlank ueber FastAPI plus einfache UI, sobald Kern und Workflows stabil sind.
