# Plan: Neues Quant-System

## Umsetzungsstand

Stand: AP4 ist abgeschlossen. Naechster Schritt ist AP5.

Erledigt:

AP4:

- Linux-Standard-venv `.venv` eingerichtet und Requirements installiert.
- `pip check` erfolgreich ausgefuehrt.
- Docker/Compose-Zugriff stabilisiert; `sp500_db` laeuft healthy, `sp500_worker` und `sp500_pma` laufen.
- Bereinigte Rohdaten-Fixture `fixtures/raw_market_data.sql` erzeugt.
- Lokale `stocks_db` aus `fixtures/raw_market_data.sql` neu aufgebaut.
- Vollstaendigen Legacy-Dump `stocks_db.sql` entfernt, damit Trade-, Cash- und Portfolio-Historie nicht als Standard-Fixture im Repo bleibt.
- `cli.data_status --details` erweitert:
  - trennt `financial_reports.annual` und `financial_reports.ttm`.
  - zeigt `report_dates` getrennt von `imported`.
- Lokale und Container-Smoke-Checks fuer `cli.data_status --details` und `cli.framework_status --benchmark-ticker SPY` erfolgreich ausgefuehrt.
- Hinweis festgehalten: Legacy-Health ist gegen die bereinigte Rohdaten-Fixture kein Standardcheck mehr, weil Legacy-/Live-Tabellen bewusst fehlen.

AP3:

- Standardisierte Python-Contracts fuer austauschbare Framework-Bausteine eingefuehrt:
  - `data.provider.DataProvider`
  - `universes.base.UniverseLoader`
  - `indicators.base.Indicator`
  - `strategies.base.Strategy`
  - `evaluation.benchmarks.Benchmark`
- Gemeinsame Kontext-/Resultattypen angelegt:
  - `indicators.base.IndicatorResult`
  - `strategies.base.StrategyContext`
  - `strategies.base.StrategyResult`
  - `evaluation.benchmarks.BenchmarkSpec`
- Ersten Fixture-/MySQL-Provider `FixtureDataProvider` auf Basis von `RawDataRepository` implementiert.
- Erstes Universum `ActiveTickerUniverse` auf Basis von `tickers.is_active = 1` implementiert.
- Benchmark-Zugriff `ProviderBenchmark` ueber den Provider-Contract implementiert.
- Smoke-Test-CLI `cli.framework_status` fuer Provider, Universum und Benchmark angelegt.
- Keine Schema-Migration und keine Aenderung an `legacy/current_system/`.

AP2:

- Neue modulare DB-Verbindung in `shared/db.py` angelegt.
- Read-only Rohdatenmodelle fuer `tickers`, `daily_candles`, `financial_reports` und `market_cap_snapshots` in `data/models.py` angelegt.
- Fixture-kompatible Loader in `data/repository.py` implementiert:
  - Ticker-Liste und einzelne Ticker.
  - Kerzen-Zeitreihen und letzte Kerze je Ticker.
  - Fundamentaldaten-Zeitreihen und letzter Report je Ticker.
  - Market-Cap-Zeitreihen und letzter Snapshot je Ticker.
- Smoke-Test-CLI `cli.data_status` fuer Rohdatenverfuegbarkeit angelegt.
- Keine Schema-Migration und keine Aenderung an `legacy/current_system/`.

AP1:

- Datenmodell-Entwurf und Schema-Plan in `docs/data-model.md` dokumentiert.
- Bestehende Tabellen aus `init.sql` und dem ehemaligen Full-Dump `stocks_db.sql` in Rohdaten, Legacy-Settings, Legacy-Snapshots, Live-Betrieb und Research eingeordnet.
- Zieltabellen fuer Mandanten, Portfolios, Universen, Benchmarks, Strategieinstanzen, Evaluation-Runs und Live-Betrieb festgelegt.
- Migrationsreihenfolge AP2 bis AP6 definiert.
- Entscheidung festgehalten: `init.sql` bleibt vorerst Legacy-kompatibel; AP1 fuehrt noch keine Schema-Migration aus.

AP0:

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

Geprueft AP0:

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

- AP5: Universen und Benchmarks als austauschbare Konfiguration konkretisieren.

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
- Tests und Experimente ohne API-Zugriff mit `fixtures/raw_market_data.sql` ermoeglichen.
- Weboberflaeche erst ganz am Schluss bauen, wenn Kern, Datenmodell und Workflows stabil sind.

## Behalten, Aendern, Weglassen

### Behalten

- Rohdatenbasis aus `tickers`, `daily_candles`, `financial_reports`, `market_cap_snapshots`.
- Docker/MySQL-Grundsetup.
- Manuelle Trade-Erfassung.
- Cash-/Trade-Historie.
- Performance-Vergleich gegen Benchmark.
- Bereinigte Rohdaten-Fixture `fixtures/raw_market_data.sql` als Test- und Demo-Datenbasis.

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

Objektorientierung wird nur fuer austauschbare Konzepte eingesetzt: `Strategy`, `Indicator`, `DataProvider`, `UniverseLoader`, `Benchmark`, `PortfolioSimulator`, `CostModel`, `TaxModel`, `ExperimentRunner`. Massendaten bleiben in SQL/DataFrames.

Die austauschbaren Konzepte bekommen klare Python-Schnittstellen, bevorzugt als `typing.Protocol` oder, falls gemeinsame Basislogik noetig ist, als abstrakte Basisklassen. Neue Module sollen dadurch nicht nur in passenden Ordnern liegen, sondern einen expliziten Vertrag erfuellen:

- `DataProvider`: liefert Rohdaten wie Preise, Fundamentals, Ticker und Benchmark-Zeitreihen.
- `UniverseLoader`: liefert die Mitglieder eines Anlageuniversums fuer einen Stichtag.
- `Indicator`: berechnet aus definierten Eingabedaten reproduzierbare Kennzahlen.
- `Strategy`: erzeugt aus Kontext, Universum, Daten und Indikatoren Rankings, Signale oder Model-Portfolios.
- `Benchmark`: beschreibt und laedt die Vergleichsreihe fuer Evaluation und Reporting.
- `PortfolioSimulator`, `CostModel`, `TaxModel`: simulieren Umsetzung, Kosten und Steuereffekte.

Jede Schnittstelle dokumentiert Eingaben, Rueckgabeformat, Fehlerverhalten und minimale Validierung. Fuer tabellarische Massendaten bleiben `pandas.DataFrame` und SQL-nahe Datenzugaenge erlaubt; der Vertrag legt aber Spalten, Datentypen und Semantik fest.

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
fixtures/raw_market_data.sql
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
- `fixtures/raw_market_data.sql` als reproduzierbare Rohdatenbasis nutzbar machen.

Umfang:

- Dokumentieren, wie `fixtures/raw_market_data.sql` lokal in MySQL geladen wird.
- Kleinen Health-Check fuer vorhandene Kerzen, Ticker, Fundamentals und Benchmark-Daten bauen.
- Minimalen Test-Datensatz definieren, falls der Dump zu gross oder sensibel ist.

Tests/Akzeptanz:

- Datenbank kann aus Fixture neu aufgebaut werden.
- Health-Check meldet Anzahl Ticker, Preisreihen, Fundamentals und Benchmark-Verfuegbarkeit.
- Keine externen API-Calls fuer diesen Testpfad.

### AP3: Modul-Contracts Und Data-Provider-Schicht

Ziel:

- Die neue Modularitaet ueber klare Schnittstellen standardisieren.
- Rohdatenzugriff von Strategie- und Evaluationslogik trennen.
- Sicherstellen, dass neue Strategien, Indikatoren, Universen und Provider einen bekannten Vertrag erfuellen.

Umfang:

- `Protocol`- oder ABC-basierte Basis-Schnittstellen definieren:
  - `DataProvider`
  - `UniverseLoader`
  - `Indicator`
  - `Strategy`
  - `Benchmark`
- Ersten Provider fuer bestehende MySQL-/Fixture-Daten bauen.
- Spaeteren yfinance-Provider nur vorbereiten, nicht als Voraussetzung fuer Tests machen.
- Gemeinsame Rueckgabeformate fuer Preise, Fundamentals, Ticker und Benchmarks festlegen.
- Gemeinsame Kontext-/Resultattypen skizzieren, z. B. `StrategyContext`, `StrategyResult`, `IndicatorResult`.
- Schnittstellen mit kurzen Docstrings dokumentieren: erwartete Eingaben, Rueckgaben, Fehlerfaelle.

Tests/Akzeptanz:

- Neue Contract-Module sind importierbar und mit `compileall` geprueft.
- Ein Beispiel-Provider und ein Beispiel-Universe-Loader erfuellen die definierten Schnittstellen.
- Provider liefert Preisreihen fuer ein Ticker-Set und einen Zeitraum.
- Provider liefert Benchmark-Reihe fuer z. B. `SPY`.
- Unit-Tests oder CLI-Smoke-Test laufen gegen Fixture-Daten.

### AP4: Linux-Umzug Und Lokale Toolchain

Status: abgeschlossen.

Ausloeser:

- In AP3 gab es Entwicklungs- und Toolchain-Probleme unter Windows mit WSL.
- Bevor weitere Fachlogik gebaut wird, zieht die Entwicklung auf eine stabile Linux-Umgebung um.

Ziel:

- Die Entwicklungsumgebung vollstaendig auf Linux ausrichten, bevor weitere Fachlogik gebaut wird.
- Eine reproduzierbare lokale Basis fuer venv, Requirements, Docker, MySQL und Fixture-Daten herstellen.

Umfang:

- Windows-venv nicht weiter als Projektstandard verwenden.
- Linux-venv `.venv` als Standard festlegen.
- `requirements.txt` in der Linux-venv installieren und mit `pip check` pruefen.
- Docker-/Compose-Zugriff auf der Linux-Umgebung stabilisieren.
- `.env.example`, `.env` und `docker-compose.yml` so abgleichen, dass `MYSQL_ROOT_PASSWORD`, `DB_NAME`, `DB_USER` und `DB_PASSWORD` sicher gesetzt sind.
- DB-Container mit frischem Volume neu erstellen.
- Fixture-/Demo-Daten laden oder den init-Pfad eindeutig dokumentieren.
- AP3-Smoke-Commands lokal gegen die Linux-venv und gegen Docker ausfuehren.

Tests/Akzeptanz:

- `.venv/bin/python -m pip install -r requirements.txt` laeuft erfolgreich.
- `.venv/bin/python -m pip check` meldet keine kaputten Abhaengigkeiten.
- `.venv/bin/python -m compileall data universes indicators strategies simulation evaluation live cli shared` laeuft erfolgreich.
- `docker compose up -d db` startet MySQL healthy.
- `docker compose run --rm app python -m cli.data_status --details` laeuft gegen die lokale DB.
- `docker compose run --rm app python -m cli.framework_status --benchmark-ticker SPY` laeuft gegen die lokale DB.

Aktueller Linux-Befund:

- `.venv-linux` wurde entfernt; der Linux-Standard ist jetzt `.venv`.
- `.venv` ist angelegt und hat funktionierendes pip mit installierten Requirements.
- `.venv/bin/python -m pip check` meldet keine kaputten Abhaengigkeiten.
- Lokale und Container-Compilechecks fuer Legacy und neue Paketstruktur laufen erfolgreich.
- Docker/Compose funktioniert ausserhalb der Sandbox; `sp500_db` ist healthy,
  `sp500_worker` und `sp500_pma` laufen.
- `fixtures/raw_market_data.sql` ist in die lokale `stocks_db` geladen.
- Die lokale `stocks_db` enthaelt nach AP4 bewusst nur noch die vier Rohdatentabellen
  `tickers`, `daily_candles`, `financial_reports` und `market_cap_snapshots`.
- Der vollstaendige Legacy-Dump `stocks_db.sql` wurde nach erfolgreicher
  Fixture-Erzeugung und Smoke-Pruefung geloescht, um Trade-, Cash- und
  Portfolio-Historie nicht als Standard-Fixture zu behalten.
- Lokale und Container-Smoke-Checks fuer `cli.data_status --details` und
  `cli.framework_status --benchmark-ticker SPY` laufen erfolgreich.
- `cli.data_status --details` zeigt Fundamentaldaten jetzt nach `annual` und
  `ttm` getrennt mit `report_dates` und `imported`, damit Report-Stichtage
  nicht mit Import-Zeitpunkten verwechselt werden.
- Legacy-Health lief vor der Bereinigung mit dem Full-Dump. Nach Umstellung auf
  die Rohdaten-Fixture ist Legacy-Health nicht mehr der AP4-Standardcheck, weil
  Legacy-/Live-Snapshot-, Cash- und Portfolio-Tabellen bewusst fehlen.

### AP5: Universen Und Benchmarks

Status: naechster Schritt.

Ziel:

- Anlageuniversum und Benchmark als austauschbare Konfiguration behandeln.

Umfang:

- Tabellen/Modelle fuer `universes`, `universe_members`, `benchmarks` konkretisieren.
- Loader fuer ein erstes Universum bauen, z. B. S&P 500 aus bestehender DB, gemaess `UniverseLoader`-Contract.
- Benchmark-Resolver bauen, gemaess `Benchmark`-/`DataProvider`-Contract.

Tests/Akzeptanz:

- CLI oder Test zeigt Mitglieder eines Universums.
- Benchmark kann pro Run eindeutig geladen werden.
- Fehlerfall wird sauber gemeldet, wenn Benchmark-Daten fehlen.

### AP6: Indikator-Engine

Ziel:

- Indikatoren modular berechnen, statt sie fest in eine Pipeline zu giessen.

Umfang:

- `Indicator`-Contract aus AP3 verwenden und bei Bedarf konkretisieren.
- Erste Indikatoren aus der bestehenden Strategie extrahieren:
  - Momentum/Return
  - Relative Staerke
  - einfache Value-/Quality-Kennzahlen, soweit Daten vorhanden sind
- Parameterisierung pro Indikator ermoeglichen.

Tests/Akzeptanz:

- Indikatorberechnung ist fuer denselben Datenstand reproduzierbar.
- Fehlende Daten erzeugen definierte `NULL`/NaN-Behandlung statt stiller Fehlbewertung.
- Mindestens ein kleiner Test mit Fixture-Daten.

### AP7: Erste Strategie Value/Quality/Momentum

Ziel:

- Die bestehende Hauptstrategie als modulare Strategieinstanz nachbauen.

Umfang:

- `Strategy`-Contract aus AP3 verwenden und bei Bedarf konkretisieren.
- Value/Quality/Momentum-Strategie mit konfigurierbaren Gewichten bauen.
- Ranking und Buy-/Sell-relevante Scores erzeugen.
- Ergebnis zunaechst nur als Model Portfolio ausgeben.

Tests/Akzeptanz:

- Strategie erzeugt fuer einen Stichtag eine reproduzierbare Rangliste.
- Gewichte werden validiert und muessen zusammen 1.0 ergeben.
- Vergleich gegen Legacy-Ergebnis fuer einen bekannten Stichtag, soweit Daten vorhanden sind.

### AP8: Evaluation Und Backtest

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

### AP9: Live-System Wieder Anbinden

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

### AP10: CLI Und Operator-Workflows

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

### AP11: Weboberflaeche Erst Nach Stabiler Kernlogik

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
2. `fixtures/raw_market_data.sql` als bereinigte Demo-/Fixture-Datenbasis nutzbar machen.
3. Standardisierte Modul-Contracts fuer Provider, Universen, Benchmarks, Indikatoren und Strategien einfuehren.
4. Linux-Umzug und lokale Toolchain stabilisieren: venv, Requirements, Docker, MySQL und Fixture-Daten.
5. Provider-/Universums-/Benchmark-Schicht auf stabiler Linux-Basis weiter konkretisieren.
6. Indikator-Engine bauen.
7. Erste Strategie Value/Quality/Momentum modularisieren.
8. Evaluation-System mit Backtests, Parameter-Sweeps und Benchmark-Vergleich bauen.
9. Live-System mit Model, Shadow, Real, Execution Gap und manuellen Trades anbinden.
10. Konfiguration versionieren und pro Portfolio steuerbar machen.
11. CLI/Reports stabilisieren.
12. Weboberflaeche erst am Schluss bauen.

## Testing Und Akzeptanz

- `fixtures/raw_market_data.sql` wird als Demo-/Fixture-Datenbank genutzt, damit Ticker, Kerzen und Fundamentals ohne API-Aufrufe verfuegbar sind.
- Erste Akzeptanz: dieselben Rohdaten koennen fuer mehrere Strategien, Universen und Benchmarks genutzt werden.
- Backtest-Akzeptanz: ein Run erzeugt reproduzierbar Metriken, Equity Curve und simulierte Trades.
- Live-Akzeptanz: aktives Portfolio zeigt Model, Shadow, Real und Execution Gap.
- Konfigurations-Akzeptanz: Strategieaenderungen gelten nur ab neuem `valid_from` und zerstoeren keine historischen Ergebnisse.
- Spaetere Weboberflaeche ist nur Client; Fachlogik bleibt im Backend/Kern.

## Annahmen Und Defaults

- Start mit `portfolio_id`; echte Mandantenfaehigkeit mit `tenant_id` wird vorbereitet, aber nicht als erster Zwang umgesetzt.
- MySQL bleibt zunaechst bestehen.
- `fixtures/raw_market_data.sql` wird nicht als neues `init.sql` verwendet, sondern als bereinigte Test-/Demo-Fixture.
- Erste Provider sind bestehende DB/Fixture-Daten und yfinance; weitere APIs kommen ueber Adapter.
- Erste Strategie bleibt Value/Quality/Momentum, wird aber in die neue modulare Strategieform ueberfuehrt.
- Weboberflaeche kommt zuletzt, bevorzugt schlank ueber FastAPI plus einfache UI, sobald Kern und Workflows stabil sind.
