# Assetklassen, Universen und Daten-Capabilities

Stand: AP20 abgeschlossen.

AP18 ist ein Design- und Dokumentationsschnitt. Er legt die fachlichen
Begriffe und die Migrationslinie fuer mehrere Assetklassen fest, fuehrt aber
noch keine Schema- oder Codeaenderungen ein. AP19 ergaenzt dieses Modell um
Provider-/API-Bindings und Source-of-Truth-Regeln. Details stehen in
[Provider-, API- und Source-Binding-Modell](provider-api-model.md).

## Zielbild

Das Framework soll Universen nicht mehr implizit als Aktienlisten behandeln.
Ein Universum ist eine Auswahl von Assets. Welche Daten fuer diese Assets
verfuegbar sein muessen, ergibt sich aus den Anforderungen der Strategie, der
Indikatoren, des Benchmarks und des operativen Workflows.

Beispiele:

| Universum | Assetklasse | Erwartete Daten |
|---|---|---|
| `sp500_active` | Aktien | Preise, Fundamentaldaten, Market Caps |
| `nasdaq100_active` | Aktien | Preise, Fundamentaldaten, Market Caps |
| `crypto_top_liquid` | Krypto | Preise, optional Market Caps, keine Aktienfundamentals |
| `cash_usd` | Cash | Cash-Bestand, keine Preisbars fuer Strategie-Ranking |
| kuenftige ETF-Universen | ETFs | Preise, optional AUM/Holdings, keine Unternehmensfundamentals |

## Begriffe

### Asset

Ein Asset ist ein handelbares oder bewertbares Objekt im Asset-Katalog. Der
aktuelle AP14-Katalog `assets` ist noch aktiennah, soll aber fachlich als
allgemeiner Asset-Katalog verstanden werden.

Langfristig relevante Asset-Metadaten:

| Feldidee | Bedeutung |
|---|---|
| `asset_class` | Grobe Klasse wie `equity`, `etf`, `crypto`, `cash`, `fx`, `future`. |
| `symbol`/`ticker` | Menschlich sichtbares Symbol im jeweiligen Markt. |
| `canonical_symbol` | Eindeutiges internes Symbol, falls Provider-Symbole kollidieren. |
| `name` | Anzeigename. |
| `quote_currency` | Bewertungswaehrung, z. B. `USD`. |
| `exchange` | Handelsplatz, sofern relevant. |
| `sector`/`industry` | Nur fuer Assetklassen, bei denen diese Klassifikation sinnvoll ist. |
| Provider-IDs | Provider-spezifische Kennungen fuer Yahoo, SimFin, CoinGecko usw. |

AP18 aendert die Tabelle noch nicht. Die Felder sind die dokumentierte
Zielrichtung fuer einen spaeteren Implementierungs-AP.

### Assetklasse

Eine Assetklasse beschreibt nicht nur eine Anzeigegruppe, sondern auch die
typischen Datenarten und Validierungsregeln:

| Assetklasse | Preisbars | Fundamentaldaten | Market Caps | Typische Zusatzdaten |
|---|---:|---:|---:|---|
| `equity` | ja | ja | ja | Sector/Industry, Splits, Dividenden |
| `etf` | ja | nein | optional | AUM, Holdings, Expense Ratio |
| `crypto` | ja | nein | optional | Supply, Network Metrics, Exchange Volume |
| `cash` | nein | nein | nein | Cash-Ledger, FX-Rate falls Fremdwaehrung |
| `fx` | ja | nein | nein | Zins-/Carry-Daten optional |
| `future` | ja | nein | nein | Contract Specs, Roll-Regeln |

### Universum

Ein Universum ist eine historisierbare Mitgliedschaft von Assets. Es sagt nicht
automatisch, welche Datenarten vorhanden sein muessen.

Ein gutes Universumsmodell trennt daher:

| Ebene | Verantwortung |
|---|---|
| Universe Definition | Name, Schluessel, Beschreibung, Mitgliedschaftsquelle. |
| Universe Membership | Welche Assets gehoeren zu welchem Zeitpunkt dazu? |
| Universe Policy | Zulassungsregeln wie Liquiditaet, Assetklasse, Waehrung oder Mindesthistorie. |
| Data Requirements | Welche Capabilities braucht ein konkreter Strategie- oder Indikatorlauf? |

Die heutige `sp500_active`-Definition bleibt der Default. Fachlich ist sie
kuenftig ein Aktienuniversum, dessen aktuelle Strategie Preise,
Fundamentaldaten und Market Caps benoetigt.

## Data-Capabilities

Eine Data-Capability ist eine benannte Datenfaehigkeit, die von Repositories,
Providern, Indikatoren, Strategien oder Live-Workflows verlangt werden kann.
Sie ist nicht identisch mit einer Tabelle: Mehrere Tabellen koennen eine
Capability liefern, und eine Tabelle kann mehrere Capabilities unterstuetzen.
Eine Capability ist auch nicht identisch mit einer API: Yahoo Finance, Binance,
SimFin, CSV oder ein kommerzieller Anbieter sind Provider, die bestimmte
Capabilities fuer bestimmte Assetklassen und Source-Rollen liefern koennen.

Vorgeschlagene Capability-Schluessel:

| Capability | Aktuelle Quelle | Zweck |
|---|---|---|
| `prices.daily_ohlcv` | `asset_price_bars` | Taegliche Preisbars fuer Ranking, Backtest, Benchmark und Live-Bewertung. |
| `fundamentals.equity_reports` | `asset_fundamental_reports` | Unternehmenskennzahlen fuer Value- und Quality-Faktoren. |
| `market_caps` | `asset_market_caps` | Groessenfilter und kapitalisierungsbezogene Kennzahlen. |
| `classification.equity_sector` | `assets.sector` | Sector-Limits und Reporting fuer Aktien. |
| `live.cash` | `live_cash_ledger`, `live_cash_balances` | Operative Cash-Bewertung. |
| `live.positions` | `live_positions` | Reale Positionen und Execution-Gap. |
| `crypto.market_data` | spaeter | Krypto-spezifische Market-Data-Ergaenzungen. |
| `crypto.network_metrics` | spaeter | On-chain- oder Netzwerkmetriken. |
| `etf.holdings` | spaeter | ETF-Zusammensetzung. |

Capability-Metadaten sollten spaeter mindestens beschreiben:

| Metadatum | Bedeutung |
|---|---|
| `key` | Stabiler Capability-Schluessel. |
| `asset_classes` | Assetklassen, fuer die die Capability sinnvoll ist. |
| `provider_keys` | Provider, die diese Capability liefern koennen. |
| `storage_tables` | Kanonische Tabellen oder Materialisierungen. |
| `granularity` | Daily, quarterly, annual, snapshot, ledger usw. |
| `freshness_policy` | Erwartete Aktualitaet, z. B. Handelstag oder Quartalsbericht. |
| `coverage_policy` | Erforderliche Abdeckung, z. B. 95 Prozent des Universums. |
| `required_fields` | Fachlich benoetigte Mindestspalten. |

## Provider- und API-Bindings

AP19 praezisiert: Ein Universum waehlt Assets aus, aber nicht automatisch die
API. Provider werden pro Datenrolle gebunden. Dadurch kann z. B. ein
S&P-500-Universum seine Membership aus Wikipedia oder einem kommerziellen
Index-Provider beziehen, Preise aus Yahoo oder einem Market-Data-Provider und
Fundamentaldaten aus SimFin oder einem kommerziellen Fundamental-Provider.

Beispielhafte Source-Rollen:

| Source Role | Typische Capability | Beispiel-Provider |
|---|---|---|
| `membership` | `universe.membership` | Wikipedia, Nasdaq API, Binance, CSV |
| `prices` | `prices.daily_ohlcv` | Yahoo Finance, Binance, Polygon, CSV |
| `fundamentals` | `fundamentals.equity_reports` | Yahoo Finance, SimFin, FactSet |
| `market_caps` | `market_caps` | Yahoo Finance, CoinGecko, commercial API |
| `classification` | `classification.equity_sector` | Yahoo Finance, GICS provider |
| `benchmark_prices` | `prices.daily_ohlcv` | Yahoo Finance, Binance, commercial API |

Ein Providerwechsel ist nur gueltig, wenn der neue Provider dieselben
Pflicht-Capabilities, normalisierten Mindestfelder, Granularitaet,
Datenabdeckung, Freshness und Identifier-Abdeckung fuer den konkreten Lauf
erfuellt.

## Strategie- und Indikatoranforderungen

Strategien sollen ihre Datenanforderungen explizit machen. Indikatoren koennen
ebenfalls Capabilities anmelden, die von der Strategie aggregiert werden.

Beispiel fuer die aktuelle Value/Quality/Momentum-Strategie:

| Baustein | Benoetigte Capabilities |
|---|---|
| Momentum Return | `prices.daily_ohlcv` |
| Relative Strength | `prices.daily_ohlcv`, Benchmark-Preise |
| Earnings Yield | `fundamentals.equity_reports`, `market_caps` |
| Free Cash Flow Yield | `fundamentals.equity_reports`, `market_caps` |
| Return on Equity | `fundamentals.equity_reports` |
| Debt to Equity | `fundamentals.equity_reports` |
| Sector Limits | `classification.equity_sector` |
| Live Performance | `prices.daily_ohlcv`, `live.cash`, `live.positions` |

Daraus folgt: Die aktuelle Strategie ist eine Aktienstrategie. Sie darf nicht
unveraendert auf ein reines Krypto-Universum angewendet werden, weil dort
`fundamentals.equity_reports` und `classification.equity_sector` nicht fachlich
verfuegbar sind.

## Validierungsmodell

Vor einem Strategie- oder Live-Lauf soll spaeter eine Capability-Pruefung
stattfinden:

1. Universum zum Stichtag laden.
2. Assetklassen und Basis-Metadaten der Mitglieder bestimmen.
3. Strategie-, Indikator-, Benchmark- und Live-Anforderungen sammeln.
4. Explizite Source-Bindings fuer Membership, Preise, Fundamentals,
   Market-Caps, Klassifikation und Benchmark bestimmen.
5. Gegen Provider- und Repository-Capabilities pruefen.
6. Datenabdeckung, Identifier-Mapping und Mindesthistorie pruefen.
7. Bei fehlenden Pflichtdaten mit einer klaren Operator-Meldung abbrechen.
8. Optionale Daten als Diagnose ausgeben, aber nicht stillschweigend erzwingen.

Beispielhafte Fehlermeldung:

```text
strategy=value_quality_momentum cannot run on universe=crypto_top_liquid:
missing required capability fundamentals.equity_reports for asset_class=crypto
```

## Migrationslinie

AP18/AP19 definierten das Zielbild. AP20 hat die ersten drei Schritte als
schemafreie Python-Validierung umgesetzt. Die weitere Umsetzung kann in kleinen
APs erfolgen:

1. Erledigt in AP20: Capability-Konstanten und einfache Python-Contracts
   dokumentationsnah einfuehren, ohne DB-Schema zu aendern.
2. Erledigt in AP20: Requirements fuer Strategie, Indikatoren, Benchmarks und
   Live-Workflows deklarieren.
3. Erledigt in AP20: Einen read-only Capability- und Provider-Checker bauen,
   der die vorhandenen AP14-Tabellen sowie Default-Bindings prueft und fuer den
   aktuellen Default-Pfad gruen ist.
4. `assets` um Assetklassen- und Symbol-Metadaten erweitern.
5. Historisierte `universes`/`universe_members` als echte Tabellen einfuehren,
   falls Code-Konfiguration nicht mehr reicht.
6. Provider-Capabilities pro Datenquelle beschreiben.
7. Neue Assetklassen wie Krypto erst anbinden, wenn deren Minimal-Capability
   und Fixture-Pfad definiert sind.

## AP18-AP20-Abgrenzung

Nicht Teil von AP18-AP20:

- keine Migration von `init.sql`
- keine neuen Tabellen
- keine persistente Aenderung der Repository- oder Strategie-Contracts
- keine neue Provider-Anbindung
- keine Krypto-Implementierung

AP18 ist abgeschlossen: Begriffe, Capability-Matrix, Validierungslogik und
Migrationslinie sind dokumentiert. AP19 ist abgeschlossen: Provider- und
API-Bindings sind dokumentiert. AP20 ist abgeschlossen: `shared.capabilities`
enthaelt den read-only Capability- und Provider-Checker fuer den aktuellen
Default-Pfad sowie negative Capability-/Provider-Faelle.
