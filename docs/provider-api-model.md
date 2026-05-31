# Provider-, API- und Source-Binding-Modell

Stand: AP20 abgeschlossen.

AP19 ist ein Design- und Dokumentationsschnitt. Er schaerft AP18 um die
konkrete Frage, wie Universen, Daten-Capabilities und externe APIs/Provider
zusammenspielen. AP19 fuehrt keine Schema- oder Codeaenderungen ein.

## Problemstellung

Ein Universum ist keine API. `sp500_active` beschreibt eine Asset-Auswahl,
nicht automatisch Yahoo Finance. Ein Krypto-Universum kann z. B. ueber Binance,
CoinGecko oder einen kommerziellen Anbieter geladen werden. Ein
Nasdaq-100-Universum kann seine Mitgliedschaft von einem Anbieter beziehen,
Preise von einem zweiten Anbieter und Fundamentaldaten von einem dritten.

Das Framework muss daher vier Konzepte getrennt behandeln:

| Konzept | Verantwortung |
|---|---|
| Universe | Welche Assets gehoeren zu einem Zeitpunkt dazu? |
| Provider | Welche externe oder interne Datenquelle wird abgefragt? |
| Provider Config | Wie wird ein Provider fachlich konfiguriert, ohne Secrets zu speichern? |
| Capability | Welche Datenfaehigkeit liefert oder verlangt ein Baustein? |

## Zielbild

Strategien, Indikatoren, Benchmarks und Live-Workflows deklarieren
Capabilities. Provider deklarieren, welche Capabilities sie fuer welche
Assetklassen, Maerkte, Granularitaeten und Identifier liefern koennen. Ein Lauf
ist nur gueltig, wenn Universe, Provider-Bindings, vorhandene Daten und
Strategieanforderungen zusammenpassen.

Beispiele:

| Fall | Gueltiges Binding |
|---|---|
| S&P 500 VQM | Membership: Wikipedia oder kommerzieller Index-Provider; Preise: Yahoo oder kommerzieller Market-Data-Provider; Fundamentals: Yahoo/SimFin/kommerzieller Anbieter. |
| Nasdaq 100 VQM | Membership: Nasdaq/kommerzieller Anbieter; Preise und Fundamentals muessen Equity-Capabilities liefern. |
| Krypto Momentum | Membership: Binance/CoinGecko/CSV; Preise: Binance; keine `fundamentals.equity_reports`. |
| Providerwechsel | Neuer Provider ist austauschbar, wenn er dieselben Pflicht-Capabilities, Identifier-Abdeckung, Granularitaet und Mindestfelder liefert. |

## Source-of-Truth Je Datenart

Ein Portfolio- oder Strategie-Run braucht explizite Source-Bindings pro
Datenart. Ein Provider kann mehrere Rollen haben, muss es aber nicht.

| Source Role | Beispiel-Capability | Beispiel-Provider |
|---|---|---|
| `membership` | `universe.membership` | Wikipedia S&P 500, Nasdaq API, Binance top symbols, CSV |
| `prices` | `prices.daily_ohlcv` | Yahoo Finance, Binance, Polygon, Alpha Vantage, CSV |
| `fundamentals` | `fundamentals.equity_reports` | Yahoo Finance, SimFin, FactSet, Intrinio |
| `market_caps` | `market_caps` | Yahoo Finance, CoinGecko, commercial market-data API |
| `classification` | `classification.equity_sector` | Yahoo Finance, GICS provider, commercial fundamentals API |
| `benchmark_prices` | `prices.daily_ohlcv` | Same as prices or a dedicated benchmark provider |

Der Default-Pfad darf weiterhin einfache Defaults verwenden. Fachlich muss er
aber als Binding verstanden werden, nicht als fest verdrahtete Yahoo-Annahme.

## Provider-Capabilities

Provider-Capabilities beschreiben nicht nur, dass ein Provider eine API hat,
sondern was der normalisierte Adapter verlaesslich liefern kann.

Mindestfelder:

| Feld | Bedeutung |
|---|---|
| `provider_key` | Stabiler technischer Schluessel, z. B. `yfinance`, `binance`, `simfin`, `csv`. |
| `source_role` | Rolle im Lauf, z. B. `prices`, `fundamentals`, `membership`. |
| `capability_key` | Gelieferte Capability, z. B. `prices.daily_ohlcv`. |
| `asset_classes` | Unterstuetzte Assetklassen, z. B. `equity`, `crypto`. |
| `markets` | Optionaler Markt-/Boersenbereich, z. B. `US`, `NASDAQ`, `BINANCE_SPOT`. |
| `granularity` | Daily, intraday, quarterly, annual, snapshot usw. |
| `required_fields` | Normalisierte Mindestfelder, die der Adapter liefern muss. |
| `identifier_scheme` | Welche IDs der Provider erwartet und liefert. |
| `coverage_policy` | Erwartete Mindestabdeckung im Universum. |
| `freshness_policy` | Erwartete Aktualitaet der Daten. |
| `license_note` | Fachliche Einschränkungen, z. B. nur privat, nicht redistribution. |

Provider-Capabilities sind die Grundlage fuer austauschbare APIs. Zwei Provider
sind nur dann austauschbar, wenn ihre normalisierten Capabilities den
Anforderungen des Laufs entsprechen.

## Identifier- und Symbolmodell

Provider verwenden unterschiedliche Symbole. Das Framework braucht langfristig
ein internes Asset-Modell mit provider-spezifischen Identifiern.

| Ebene | Zweck |
|---|---|
| `asset_id` | Interner stabiler Schluessel. |
| `canonical_symbol` | Menschlich lesbares internes Symbol, eindeutig im Framework. |
| `display_symbol` | Operator-Anzeige, z. B. `AAPL` oder `BTC-USD`. |
| `provider_symbol` | Symbol beim jeweiligen Provider, z. B. `BRK-B`, `BRK.B`, `BTCUSDT`. |
| `provider_asset_id` | Optionaler stabiler Provider-Identifier. |
| `exchange`/`market` | Disambiguierung bei Symbolkollisionen. |
| `quote_currency` | Bewertungswaehrung fuer Preise und Portfolio-Bewertung. |

AP21 fuehrt die erste technische Identifier-Basis ein. `assets` enthaelt die
internen Asset-Metadaten, und `asset_provider_identifiers` speichert
provider-spezifische Symbole und optionale stabile Provider-IDs. Der
Capability-Checker kann optional pruefen, ob fuer die relevanten Ticker und
Source-Rollen Provider-Identifier vorhanden sind.

AP22 nutzt diese Identifier-Basis im modularen Sync: Preis- und
Fundamental-Sync fragen externe Provider mit `provider_symbol` ab und
persistieren die normalisierten Daten wieder unter dem internen `ticker`.

## Binding-Regeln

Ein Lauf besteht aus einer expliziten Kombination von Strategie, Universum,
Benchmark und Source-Bindings.

Beispielhafte Konfiguration:

```text
strategy=value_quality_momentum
universe=sp500_active
benchmark=spy
sources.membership=wikipedia_sp500
sources.prices=yfinance
sources.fundamentals=yfinance
sources.market_caps=yfinance
sources.classification=yfinance
```

Krypto-Beispiel:

```text
strategy=crypto_momentum
universe=crypto_top_liquid
benchmark=btc
sources.membership=binance_spot
sources.prices=binance_spot
sources.market_caps=coingecko
```

Regeln:

- Ein Universum darf nicht implizit entscheiden, welche Provider verwendet
  werden.
- Eine Strategie darf nicht direkt von einem Provider abhaengen.
- Ein Provider darf mehrere Source-Rollen uebernehmen, wenn er die
  Capabilities liefert.
- Eine Source-Rolle darf optional leer sein, wenn keine verlangte Capability
  davon abhaengt.
- Fehlende Pflicht-Capabilities muessen vor dem Lauf als Operator-Fehler
  sichtbar werden.
- Optionale Capabilities duerfen diagnostiziert werden, aber nicht
  stillschweigend zur Pflicht werden.

## Austauschbarkeit

Ein Providerwechsel ist fachlich gueltig, wenn alle folgenden Punkte erfuellt
sind:

- Die Pflicht-Capabilities des Laufs werden weiter geliefert.
- Die Daten besitzen die benoetigte Granularitaet und Mindesthistorie.
- Die normalisierten Felder entsprechen den Erwartungen der Indikatoren und
  Strategien.
- Das Identifier-Mapping deckt die benoetigten Universe-Mitglieder und
  Benchmarks ab.
- Die Abdeckung und Freshness liegen innerhalb der Policy.
- Lizenz- oder Nutzungsbeschraenkungen widersprechen dem Lauf nicht.

Nicht gueltig ist z. B. ein Wechsel von Yahoo-Fundamentals auf Binance, wenn
die gewaehlte Aktienstrategie weiter `fundamentals.equity_reports` verlangt.

## Operator-Fehler

Fehler sollen die ungueltige Kombination benennen, nicht nur eine leere
DataFrame-Folge erzeugen.

Beispiele:

```text
strategy=value_quality_momentum cannot run with universe=crypto_top_liquid:
missing capability fundamentals.equity_reports for asset_class=crypto
```

```text
provider=binance_spot cannot satisfy source_role=fundamentals:
missing capability fundamentals.equity_reports
```

```text
provider=yfinance cannot price asset=BTCUSDT for market=BINANCE_SPOT:
missing provider identifier mapping
```

## Umsetzungslinie

AP19 blieb Design. AP20 hat die technische Umsetzung begonnen:

1. Erledigt in AP20: Capability- und Provider-Definitionen als
   Python-Konstanten/Dataclasses einfuehren, ohne Schemaaenderung.
2. Erledigt in AP20: Default-Bindings fuer den aktuellen AP14/AP17-Pfad
   beschreiben:
   `sp500_active`, `spy`, `value_quality_momentum`, `mysql_fixture`/`yfinance`.
3. Erledigt in AP20: Strategie-, Indikator-, Benchmark- und Live-Anforderungen
   deklarieren.
4. Erledigt in AP20: Read-only Checker bauen, der Provider-Bindings gegen
   Anforderungen prueft.
5. Erledigt in AP20: Negative Tests fuer inkompatible Provider-/Universums-
   Kombinationen ergaenzen.
6. Erledigt in AP21: provider-spezifische Identifier in das Schema
   ueberfuehren.
7. Erledigt in AP22: Provider-Symbole im Preis- und Fundamental-Sync
   verwenden.
8. Spaetere APs koennen `data_providers`, `provider_configs` und echte
   Multi-Provider-Syncs in das Schema ueberfuehren.

## AP19-AP21-Abgrenzung

Nicht Teil von AP19-AP21:

- keine neue API-Anbindung
- keine Aenderung der produktiven Sync-CLIs
- keine Aenderung am laufenden S&P-500-Default-Pfad

AP19 ist abgeschlossen: Provider/API-Bindings, Source-of-Truth je Datenart,
Provider-Capabilities, Identifier-Anforderungen, Austauschbarkeitsregeln und
die angepasste AP20-Implementierungslinie sind dokumentiert. AP20 ist
abgeschlossen: `shared.capabilities` validiert den aktuellen Default-Pfad
read-only und prueft negative Provider-/Source-Binding-Faelle. AP21 ist
abgeschlossen: `asset_provider_identifiers` bildet provider-spezifische
Symbole/IDs ab, und der Capability-Check kann Identifier-Coverage optional
auswerten. AP22 ist abgeschlossen: der modulare Sync nutzt Provider-Symbole
fuer API-Zugriffe und mappt Ergebnisse auf interne Ticker zurueck.
