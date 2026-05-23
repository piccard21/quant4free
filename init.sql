-- ###########################################################################
-- Quant-System Datenbankschema
-- Task-1 Stand: Core / Research Architektur bereinigt
-- Hinweis:
-- - Core = entscheidungsrelevante Tabellen
-- - Research = Analyse-/Auswertungstabellen
-- - is_active bleibt vorerst erhalten, solange der laufende Code es noch nutzt
-- ###########################################################################

SET NAMES utf8mb4;
SET time_zone = '+00:00';


-- ###########################################################################
-- CORE: Tabelle tickers
-- ###########################################################################
CREATE TABLE IF NOT EXISTS tickers (
    ticker VARCHAR(10) PRIMARY KEY COMMENT 'Eindeutiges Börsenkürzel des Unternehmens, z. B. AAPL oder BRK-B',
    name VARCHAR(255) NOT NULL COMMENT 'Offizieller Firmenname laut Quellen wie Wikipedia oder Yahoo Finance',
    sector VARCHAR(255) COMMENT 'GICS-Sektor des Unternehmens',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1 = aktuell im S&P 500, 0 = entfernt; aktuell noch operative Hilfsspalte',
    first_seen DATETIME COMMENT 'Erstes Auftreten im System',
    last_seen DATETIME COMMENT 'Letzte Bestätigung im Index',
    removed_at DATETIME COMMENT 'Zeitpunkt der Entfernung aus dem Index',
    last_fundamental_update DATETIME COMMENT 'Letztes Update der Fundamentaldaten',

    KEY idx_tickers_is_active (is_active),
    KEY idx_tickers_last_fundamental_update (last_fundamental_update)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Stammdaten aller S&P-500 Unternehmen';


-- ###########################################################################
-- CORE: Tabelle daily_candles
-- ###########################################################################
CREATE TABLE IF NOT EXISTS daily_candles (
    ticker VARCHAR(10) NOT NULL COMMENT 'Ticker (FK)',
    date DATE NOT NULL COMMENT 'Handelstag',
    open DECIMAL(20,4) COMMENT 'Eröffnungskurs',
    high DECIMAL(20,4) COMMENT 'Tageshoch',
    low DECIMAL(20,4) COMMENT 'Tagestief',
    close DECIMAL(20,4) COMMENT 'Schlusskurs',
    volume BIGINT COMMENT 'Handelsvolumen',

    PRIMARY KEY (ticker, date),
    KEY idx_daily_candles_ticker_date_desc (ticker, date DESC),

    CONSTRAINT fk_daily_candles_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Tägliche OHLCV Kursdaten';


-- ###########################################################################
-- CORE: Tabelle financial_reports
-- ###########################################################################
CREATE TABLE IF NOT EXISTS financial_reports (
    ticker VARCHAR(10) NOT NULL COMMENT 'Ticker (FK)',
    report_date DATE NOT NULL COMMENT 'Berichtsdatum',
    report_type ENUM('annual', 'ttm') NOT NULL COMMENT 'Berichtstyp (annual / ttm)',

    revenue BIGINT DEFAULT 0 COMMENT 'Umsatz',
    net_income BIGINT DEFAULT 0 COMMENT 'Nettogewinn',
    ebit BIGINT DEFAULT 0 COMMENT 'Operatives Ergebnis',
    free_cash_flow BIGINT DEFAULT 0 COMMENT 'Freier Cashflow',

    total_debt BIGINT DEFAULT 0 COMMENT 'Gesamtverschuldung',
    total_equity BIGINT DEFAULT 0 COMMENT 'Eigenkapital',
    cash_and_equivalents BIGINT DEFAULT 0 COMMENT 'Liquide Mittel',

    source VARCHAR(50) COMMENT 'Datenquelle',
    imported_at DATETIME COMMENT 'Importzeitpunkt',

    PRIMARY KEY (ticker, report_date, report_type),
    KEY idx_financial_reports_ticker_type_date (ticker, report_type, report_date DESC),

    CONSTRAINT fk_financial_reports_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Fundamentaldaten (Annual + TTM)';


-- ###########################################################################
-- CORE: Tabelle market_cap_snapshots
-- ###########################################################################
CREATE TABLE IF NOT EXISTS market_cap_snapshots (
    ticker VARCHAR(10) NOT NULL COMMENT 'Ticker (FK)',
    date DATE NOT NULL COMMENT 'Datum des Snapshots',
    market_cap BIGINT COMMENT 'Marktkapitalisierung',
    imported_at DATETIME COMMENT 'Importzeitpunkt',

    PRIMARY KEY (ticker, date),
    KEY idx_market_cap_snapshots_ticker_date_desc (ticker, date DESC),

    CONSTRAINT fk_market_cap_snapshots_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Tägliche Market Cap Snapshots';


-- ###########################################################################
-- CORE: Tabelle factor_metrics
-- ###########################################################################
CREATE TABLE IF NOT EXISTS factor_metrics (
    as_of_date DATE NOT NULL COMMENT 'Stichtag der Berechnung (z. B. Monatsende)',
    ticker VARCHAR(10) NOT NULL COMMENT 'Börsenkürzel',
    sector VARCHAR(100) NOT NULL COMMENT 'Sektor für sektorrelative Auswertung',

    price_date DATE COMMENT 'Datum des verwendeten letzten Kurses',
    report_date DATE COMMENT 'Datum des verwendeten Finanzberichts (TTM bevorzugt)',
    market_cap_date DATE COMMENT 'Datum des verwendeten Market Cap Snapshots',

    current_price DECIMAL(20,4) COMMENT 'Letzter Schlusskurs',
    sma_200 DECIMAL(20,4) COMMENT '200-Tage-Durchschnitt',
    trend_positive TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = Preis > 200DMA',

    market_cap BIGINT COMMENT 'Marktkapitalisierung',
    enterprise_value BIGINT COMMENT 'EV = Market Cap + Debt - Cash',

    ev_to_ebit DECIMAL(20,6) COMMENT 'EV / EBIT (niedriger = besser)',
    free_cash_flow_yield DECIMAL(20,6) COMMENT 'FCF / EV (höher = besser)',
    earnings_yield DECIMAL(20,6) COMMENT 'EBIT / EV (höher = besser)',

    roe DECIMAL(20,6) COMMENT 'Return on Equity',
    debt_to_equity DECIMAL(20,6) COMMENT 'Verschuldungsgrad',
    revenue_growth DECIMAL(20,6) COMMENT 'Umsatzwachstum (TTM vs Vorjahr)',

    return_12m DECIMAL(20,6) COMMENT '12-Monats-Rendite',
    return_6m DECIMAL(20,6) COMMENT '6-Monats-Rendite',
    rel_strength_12m DECIMAL(20,6) COMMENT 'Relative Stärke vs Benchmark',

    is_valid TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1 = gültig für Ranking',
    exclusion_reason VARCHAR(255) COMMENT 'Grund für Ausschluss',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',

    PRIMARY KEY (as_of_date, ticker),
    KEY idx_factor_metrics_ticker (ticker),
    KEY idx_factor_metrics_sector (sector),

    CONSTRAINT fk_factor_metrics_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Berechnete Kennzahlen je Ticker und Stichtag (Basis für Scoring)';


-- ###########################################################################
-- CORE: Tabelle factor_scores
-- ###########################################################################
CREATE TABLE IF NOT EXISTS factor_scores (
    as_of_date DATE NOT NULL COMMENT 'Stichtag (identisch mit factor_metrics)',
    ticker VARCHAR(10) NOT NULL COMMENT 'Börsenkürzel',
    sector VARCHAR(100) NOT NULL COMMENT 'Sektor für sektorrelative Scores',

    ev_to_ebit_score DECIMAL(8,4) COMMENT 'Percentile 0-100 (niedriger besser)',
    free_cash_flow_yield_score DECIMAL(8,4) COMMENT 'Percentile 0-100 (höher besser)',
    earnings_yield_score DECIMAL(8,4) COMMENT 'Percentile 0-100 (höher besser)',

    roe_score DECIMAL(8,4) COMMENT 'Percentile 0-100',
    debt_to_equity_score DECIMAL(8,4) COMMENT 'Percentile 0-100 (niedriger besser)',
    revenue_growth_score DECIMAL(8,4) COMMENT 'Percentile 0-100',

    return_12m_score DECIMAL(8,4) COMMENT 'Percentile 0-100 des 12-Monats-Returns',
    return_6m_score DECIMAL(8,4) COMMENT 'Percentile 0-100 des 6-Monats-Returns',
    rel_strength_12m_score DECIMAL(8,4) COMMENT 'Percentile 0-100 der relativen Stärke vs Benchmark',

    value_score DECIMAL(8,4) COMMENT 'Durchschnitt Value Faktoren',
    quality_score DECIMAL(8,4) COMMENT 'Durchschnitt Quality Faktoren',
    momentum_score DECIMAL(8,4) COMMENT 'Momentum-Gesamtscore',

    final_score DECIMAL(8,4) COMMENT 'Gewichteter Gesamtscore',
    final_rank INT COMMENT 'Ranking (1 = bester Wert)',

    trend_positive TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = Preis > 200DMA',
    buy_eligible TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = Rank <= Buy-Threshold UND Trend positiv',
    sell_flag TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = Rank > Sell-Threshold ODER Trend negativ',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',

    PRIMARY KEY (as_of_date, ticker),
    KEY idx_factor_scores_rank (as_of_date, final_rank),
    KEY idx_factor_scores_sector (as_of_date, sector),

    CONSTRAINT fk_factor_scores_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Factor Scores, Percentiles und Ranking je Stichtag';


-- ###########################################################################
-- CORE: Tabelle strategy_settings
-- ###########################################################################
CREATE TABLE IF NOT EXISTS strategy_settings (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Eindeutige ID des Settings-Datensatzes',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Vorerst beibehalten, solange der operative Code aktive Settings so lädt',
    strategy_version VARCHAR(20) NOT NULL DEFAULT 'v1.5' COMMENT 'Strategie-Version, z. B. v1.5',

    value_weight DECIMAL(8,4) NOT NULL COMMENT 'Gewichtung des Value-Faktors',
    quality_weight DECIMAL(8,4) NOT NULL COMMENT 'Gewichtung des Quality-Faktors',
    momentum_weight DECIMAL(8,4) NOT NULL COMMENT 'Gewichtung des Momentum-Faktors',

    momentum_return_weight DECIMAL(8,4) NOT NULL COMMENT 'Gewichtung des Return-Blocks innerhalb des Momentum-Scores',
    momentum_rel_strength_weight DECIMAL(8,4) NOT NULL COMMENT 'Gewichtung der relativen Stärke innerhalb des Momentum-Scores',

    min_price DECIMAL(12,2) NOT NULL COMMENT 'Mindestpreis in USD',
    min_market_cap BIGINT NOT NULL COMMENT 'Minimale Marktkapitalisierung in USD',

    sma_days INT NOT NULL COMMENT 'Länge des gleitenden Durchschnitts für Trendfilter',
    return_lookback_days INT NOT NULL COMMENT 'Lookback für Momentum in Handelstagen',

    buy_rank_threshold INT NOT NULL COMMENT 'Kauf erlaubt bei Rank <= diesem Wert',
    sell_rank_threshold INT NOT NULL COMMENT 'Verkauf bei Rank > diesem Wert',

    portfolio_size INT NOT NULL COMMENT 'Zielgröße des Shadow Portfolios',
    max_sector_positions INT NOT NULL COMMENT 'Maximale Anzahl Aktien pro Sektor',

    min_holding_months INT NOT NULL COMMENT 'Mindesthaltedauer in Monaten',
    max_trades_per_month INT NOT NULL COMMENT 'Maximal erlaubte Positionswechsel pro Monat',

    daily_fundamental_limit INT NOT NULL COMMENT 'Maximal zu aktualisierende Ticker pro Daily-Run',
    fundamental_refresh_hours INT NOT NULL COMMENT 'Mindestabstand zwischen Fundamental-Updates in Stunden',
    tax_rate DECIMAL(8,6) NOT NULL DEFAULT 0.263750 COMMENT 'Pauschale Steuer auf realisierte Gewinne, z. B. 0.26375 für DE ohne Kirche',
    max_funding_sell_pct DECIMAL(8,6) NOT NULL DEFAULT 0.200000 COMMENT 'Variante C: maximaler Anteil einer bestehenden Position, der pro Trade-Plan als Funding-ADJUST_SELL verkauft werden darf',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Letzte Änderung',

    KEY idx_strategy_settings_active (is_active),
    KEY idx_strategy_settings_version (strategy_version)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Zentrale Systemkonfiguration für Strategie und operative Pipeline';


INSERT INTO strategy_settings (
    is_active,
    strategy_version,
    value_weight,
    quality_weight,
    momentum_weight,
    momentum_return_weight,
    momentum_rel_strength_weight,
    min_price,
    min_market_cap,
    sma_days,
    return_lookback_days,
    buy_rank_threshold,
    sell_rank_threshold,
    portfolio_size,
    max_sector_positions,
    min_holding_months,
    max_trades_per_month,
    daily_fundamental_limit,
    fundamental_refresh_hours,
    tax_rate,
    max_funding_sell_pct
)
SELECT
    1,
    'v1.5',
    0.35,
    0.35,
    0.30,
    0.40,
    0.60,
    10.00,
    2000000000,
    200,
    252,
    10,
    20,
    5,
    2,
    3,
    2,
    50,
    20,
    0.263750,
    0.200000
WHERE NOT EXISTS (
    SELECT 1 FROM strategy_settings
);


-- ###########################################################################
-- CORE: Tabelle strategy_settings_snapshots
-- ###########################################################################
CREATE TABLE IF NOT EXISTS strategy_settings_snapshots (
    as_of_date DATE NOT NULL COMMENT 'Stichtag des Rebalance-/Snapshot-Laufs',
    strategy_version VARCHAR(20) NOT NULL COMMENT 'Strategie-Version, z. B. v1.5',

    value_weight DECIMAL(8,4) NOT NULL,
    quality_weight DECIMAL(8,4) NOT NULL,
    momentum_weight DECIMAL(8,4) NOT NULL,

    momentum_return_weight DECIMAL(8,4) NOT NULL,
    momentum_rel_strength_weight DECIMAL(8,4) NOT NULL,

    min_price DECIMAL(12,2) NOT NULL,
    min_market_cap BIGINT NOT NULL,

    sma_days INT NOT NULL,
    return_lookback_days INT NOT NULL,

    buy_rank_threshold INT NOT NULL,
    sell_rank_threshold INT NOT NULL,

    portfolio_size INT NOT NULL,
    max_sector_positions INT NOT NULL,

    min_holding_months INT NOT NULL,
    max_trades_per_month INT NOT NULL,

    daily_fundamental_limit INT NOT NULL,
    fundamental_refresh_hours INT NOT NULL,
    tax_rate DECIMAL(8,6) NOT NULL DEFAULT 0.263750,
    max_funding_sell_pct DECIMAL(8,6) NOT NULL DEFAULT 0.200000,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (as_of_date),
    KEY idx_strategy_settings_snapshots_version (strategy_version)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Eingefrorene Systemkonfiguration je Stichtag';


-- ###########################################################################
-- CORE: Tabelle portfolio_snapshots
-- ###########################################################################
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    as_of_date DATE NOT NULL COMMENT 'Stichtag des Snapshots',
    snapshot_type VARCHAR(20) NOT NULL COMMENT 'Typ des Snapshots, z. B. model oder shadow',
    ticker VARCHAR(10) NOT NULL COMMENT 'Börsenkürzel',

    portfolio_rank INT COMMENT 'Position im Shadow Portfolio',
    source_rank INT COMMENT 'Ursprünglicher Rank aus factor_scores',
    sector VARCHAR(100) COMMENT 'Sektor der Aktie',

    target_weight DECIMAL(10,6) COMMENT 'Zielgewicht im Portfolio',
    final_score DECIMAL(8,4) COMMENT 'Gesamtscore',
    value_score DECIMAL(8,4) COMMENT 'Value Score',
    quality_score DECIMAL(8,4) COMMENT 'Quality Score',
    momentum_score DECIMAL(8,4) COMMENT 'Momentum Score',

    trend_positive TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = Trend positiv',
    buy_eligible TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = kaufbar laut Regelwerk',
    holding_start_date DATE NULL COMMENT 'Startdatum der Position im regelbasierten Tradable Shadow Portfolio',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',

    PRIMARY KEY (as_of_date, snapshot_type, ticker),
    KEY idx_portfolio_snapshots_type_rank (as_of_date, snapshot_type, portfolio_rank),
    KEY idx_portfolio_snapshots_ticker (ticker),

    CONSTRAINT fk_portfolio_snapshots_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Eingefrorene Modellportfolios je Stichtag';


-- ###########################################################################
-- CORE: Tabelle portfolio_positions
-- ###########################################################################
CREATE TABLE IF NOT EXISTS portfolio_positions (
    position_id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Eindeutige ID der realen Position',
    ticker VARCHAR(10) NOT NULL COMMENT 'Börsenkürzel',
    shares DECIMAL(20,6) NOT NULL COMMENT 'Anzahl gehaltener Aktien',
    buy_price DECIMAL(20,6) COMMENT 'Einstandspreis je Aktie',
    opened_at DATETIME NOT NULL COMMENT 'Eröffnungszeitpunkt der Position',
    closed_at DATETIME COMMENT 'Schließungszeitpunkt der Position',
    is_open TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1 = offene Position, 0 = geschlossen',
    notes VARCHAR(255) COMMENT 'Optionale Notiz zur Position',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Letzte Änderung',

    KEY idx_portfolio_positions_open (is_open, opened_at),
    KEY idx_portfolio_positions_ticker (ticker),

    CONSTRAINT fk_portfolio_positions_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE RESTRICT

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Reales Portfolio mit manuell erfassten Positionen';


-- ###########################################################################
-- CORE: Tabelle portfolio_cash
-- ###########################################################################
CREATE TABLE IF NOT EXISTS portfolio_cash (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Technische ID des Cash-Eintrags',
    cash_balance DECIMAL(20,6) NOT NULL COMMENT 'Aktuell verfügbarer Cash-Bestand des realen Portfolios',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Zeitpunkt der letzten manuellen Pflege oder System-Aktualisierung',

    KEY idx_portfolio_cash_updated_at (updated_at)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Aktueller Cash-Bestand des realen Portfolios';


INSERT INTO portfolio_cash (cash_balance, updated_at)
SELECT 0.000000, NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM portfolio_cash
);


-- ###########################################################################
-- CORE: Tabelle rebalance_suggestions
-- ###########################################################################
CREATE TABLE IF NOT EXISTS rebalance_suggestions (
    as_of_date DATE NOT NULL COMMENT 'Stichtag des Rebalance-Laufs',
    ticker VARCHAR(10) NOT NULL COMMENT 'Börsenkürzel',
    sector VARCHAR(100) COMMENT 'Sektor der Aktie',  -- <-- hier hinzugefügt
    action VARCHAR(20) NOT NULL COMMENT 'BUY, SELL oder HOLD',
    reason VARCHAR(255) COMMENT 'Begründung der Aktion',

    source_rank INT COMMENT 'Rank aus factor_scores bzw. Shadow Portfolio',
    target_weight DECIMAL(10,6) COMMENT 'Zielgewicht bei Kauf/Halten',
    current_shares DECIMAL(20,6) COMMENT 'Aktuelle Stückzahl im realen Portfolio',

    opened_at DATE COMMENT 'Eröffnungsdatum der realen Position',
    holding_days INT COMMENT 'Bisherige Haltedauer in Tagen',
    min_hold_ok TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1 = Mindesthaltedauer erfüllt',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',

    PRIMARY KEY (as_of_date, ticker),
    KEY idx_rebalance_suggestions_action (as_of_date, action),
    KEY idx_rebalance_suggestions_ticker (ticker),

    CONSTRAINT fk_rebalance_suggestions_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE,

    CONSTRAINT fk_rebalance_suggestions_settings_snapshot
        FOREIGN KEY (as_of_date)
        REFERENCES strategy_settings_snapshots(as_of_date)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Eingefrorene Rebalance-Vorschläge';

-- ###########################################################################
-- CORE: Tabelle decision_log
-- ###########################################################################
CREATE TABLE IF NOT EXISTS decision_log (
    as_of_date DATE NOT NULL COMMENT 'Stichtag des Rebalance-Laufs',
    ticker VARCHAR(10) NOT NULL COMMENT 'Börsenkürzel',

    action VARCHAR(20) NOT NULL COMMENT 'BUY, SELL oder HOLD',
    reason VARCHAR(255) COMMENT 'Begründung der Entscheidung',

    source_rank INT COMMENT 'Rank aus factor_scores bzw. Shadow Portfolio',
    final_score DECIMAL(8,4) COMMENT 'Gesamtscore',
    value_score DECIMAL(8,4) COMMENT 'Value Score',
    quality_score DECIMAL(8,4) COMMENT 'Quality Score',
    momentum_score DECIMAL(8,4) COMMENT 'Momentum Score',

    trend_positive TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = Trend positiv',
    holding_days INT COMMENT 'Bisherige Haltedauer in Tagen',
    min_hold_ok TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1 = Mindesthaltedauer erfüllt',

    strategy_version VARCHAR(20) COMMENT 'Verwendete Strategie-Version beim Rebalance',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',

    PRIMARY KEY (as_of_date, ticker),
    KEY idx_decision_log_action (as_of_date, action),
    KEY idx_decision_log_strategy (strategy_version),
    KEY idx_decision_log_ticker (ticker),

    CONSTRAINT fk_decision_log_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE,

    CONSTRAINT fk_decision_log_settings_snapshot
        FOREIGN KEY (as_of_date)
        REFERENCES strategy_settings_snapshots(as_of_date)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Vollständiges Entscheidungsprotokoll je Stichtag';


-- ###########################################################################
-- CORE: Tabelle trade_plan_summary
-- ###########################################################################
CREATE TABLE IF NOT EXISTS trade_plan_summary (
    as_of_date DATE NOT NULL COMMENT 'Stichtag des Trade-Plan-Laufs',

    portfolio_value_before DECIMAL(20,6) NOT NULL COMMENT 'Gesamtwert vor geplanter Umsetzung',
    invested_value_before DECIMAL(20,6) NOT NULL COMMENT 'Marktwert aller offenen realen Positionen',
    cash_before DECIMAL(20,6) NOT NULL COMMENT 'Verfügbarer Cash vor Trade-Simulation',
    cash_after DECIMAL(20,6) NOT NULL COMMENT 'Verfügbarer Cash nach geplanter Simulation',

    bucket_size DECIMAL(20,6) NOT NULL COMMENT 'Ziel-Bucketgröße je Position',
    target_positions INT NOT NULL COMMENT 'Zielgröße des Portfolios laut Settings',
    positions_before INT NOT NULL COMMENT 'Anzahl offener realer Positionen vor Simulation',
    positions_after INT NOT NULL COMMENT 'Anzahl Positionen nach ausführbaren geplanten Trades',

    total_sell_gross DECIMAL(20,6) NOT NULL COMMENT 'Bruttowert aller geplanten SELLs',
    total_buy_gross DECIMAL(20,6) NOT NULL COMMENT 'Bruttowert aller geplanten BUYs',
    total_fees DECIMAL(20,6) NOT NULL COMMENT 'Summe aller berücksichtigten Handelskosten',

    executable_buys INT NOT NULL COMMENT 'Anzahl ausführbarer BUYs',
    executable_sells INT NOT NULL COMMENT 'Anzahl ausführbarer SELLs',
    skipped_trades INT NOT NULL COMMENT 'Anzahl nicht ausführbarer Trade-Ideen',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',

    PRIMARY KEY (as_of_date),
    KEY idx_trade_plan_summary_positions (positions_before, positions_after),

    CONSTRAINT fk_trade_plan_summary_settings_snapshot
        FOREIGN KEY (as_of_date)
        REFERENCES strategy_settings_snapshots(as_of_date)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Zusammenfassung der konkreten Trade-Plan-Simulation je Stichtag';


-- ###########################################################################
-- CORE: Tabelle trade_plan_snapshots
-- ###########################################################################
CREATE TABLE IF NOT EXISTS trade_plan_snapshots (
    as_of_date DATE NOT NULL COMMENT 'Stichtag des Trade-Plan-Laufs',
    ticker VARCHAR(10) NOT NULL COMMENT 'Börsenkürzel',

    action VARCHAR(20) NOT NULL COMMENT 'BUY, SELL, HOLD, ADJUST_BUY oder ADJUST_SELL',
    reason VARCHAR(255) COMMENT 'Fachlicher Grund für die Aktion',
    execution_order INT COMMENT 'Geplante Reihenfolge der Umsetzung',

    source_rank INT COMMENT 'Quell-Ranking aus factor_scores / Shadow Portfolio',
    target_weight DECIMAL(10,6) COMMENT 'Zielgewicht aus Shadow Portfolio bzw. Rebalance',

    current_shares DECIMAL(20,6) COMMENT 'Aktuell offene Stückzahl vor Simulation',
    planned_shares DECIMAL(20,6) COMMENT 'Geplante Stückzahl der Order',
    estimated_price DECIMAL(20,6) COMMENT 'Verwendeter Referenzpreis für die Simulation',

    gross_amount DECIMAL(20,6) COMMENT 'Bruttobetrag der Order vor Gebühren',
    fee DECIMAL(20,6) NOT NULL DEFAULT 0.000000 COMMENT 'Berücksichtigte fixe Handelskosten',
    net_amount DECIMAL(20,6) COMMENT 'Nettoeffekt der Order inklusive Gebühren',

    bucket_size DECIMAL(20,6) COMMENT 'Zum Stichtag berechnete Ziel-Bucketgröße',
    cash_before DECIMAL(20,6) COMMENT 'Cash-Bestand unmittelbar vor dieser simulierten Order',
    cash_after DECIMAL(20,6) COMMENT 'Cash-Bestand unmittelbar nach dieser simulierten Order',

    is_executable TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = Trade in der Simulation umsetzbar',
    skip_reason VARCHAR(255) COMMENT 'Grund, warum ein Trade nicht ausgeführt wird',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',

    PRIMARY KEY (as_of_date, ticker),
    KEY idx_trade_plan_snapshots_action (as_of_date, action),
    KEY idx_trade_plan_snapshots_exec_order (as_of_date, execution_order),
    KEY idx_trade_plan_snapshots_source_rank (as_of_date, source_rank),
    KEY idx_trade_plan_snapshots_executable (as_of_date, is_executable),

    CONSTRAINT fk_trade_plan_snapshots_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE,

    CONSTRAINT fk_trade_plan_snapshots_settings_snapshot
        FOREIGN KEY (as_of_date)
        REFERENCES strategy_settings_snapshots(as_of_date)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Konkrete, kapitalabhängige Order-Ideen je Stichtag';


-- ###########################################################################
-- CORE: Tabelle trade_executions
-- ###########################################################################
CREATE TABLE IF NOT EXISTS trade_executions (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Technische ID der echten Trade-Ausführung',
    as_of_date DATE NOT NULL COMMENT 'Bezug zum Trade-Plan-/Rebalance-Stichtag',
    ticker VARCHAR(10) NOT NULL COMMENT 'Börsenkürzel',

    execution_type ENUM('BUY','SELL') NOT NULL COMMENT 'Tatsächliche Ausführungsrichtung',
    trade_plan_action ENUM('BUY','SELL','ADJUST_BUY','ADJUST_SELL') COMMENT 'Bezug zur geplanten Trade-Plan-Aktion',
    executed_at DATETIME NOT NULL COMMENT 'Tatsächlicher Ausführungszeitpunkt',

    shares DECIMAL(20,6) NOT NULL COMMENT 'Tatsächlich ausgeführte Stückzahl',
    price DECIMAL(20,6) NOT NULL COMMENT 'Tatsächlicher Ausführungspreis je Aktie',
    gross_amount DECIMAL(20,6) NOT NULL COMMENT 'Bruttobetrag der Ausführung',
    fee DECIMAL(20,6) NOT NULL DEFAULT 0.000000 COMMENT 'Tatsächliche Gebühr',
    net_amount DECIMAL(20,6) NOT NULL COMMENT 'Nettoeffekt der Ausführung inkl. Gebühr',
    realized_profit DECIMAL(20,6) NULL COMMENT 'Realisierter Gewinn/Verlust der Ausführung, nur relevant für SELL',
    tax_amount DECIMAL(20,6) NOT NULL DEFAULT 0.000000 COMMENT 'Abgezogene Steuer auf realisierten Gewinn',

    broker VARCHAR(100) COMMENT 'Optionaler Brokername',
    notes VARCHAR(255) COMMENT 'Optionale Notiz',
    trade_plan_execution_order INT COMMENT 'Optionale Referenz auf die geplante Ausführungsreihenfolge',
    status ENUM('executed','skipped','cancelled') NOT NULL DEFAULT 'executed' COMMENT 'Status der manuellen Erfassung',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',

    UNIQUE KEY uq_trade_executions_once (as_of_date, ticker, execution_type, executed_at),
    KEY idx_trade_executions_asof_ticker (as_of_date, ticker),
    KEY idx_trade_executions_status (status),
    KEY idx_trade_executions_executed_at (executed_at),

    CONSTRAINT fk_trade_executions_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE RESTRICT,

    CONSTRAINT fk_trade_executions_settings_snapshot
        FOREIGN KEY (as_of_date)
        REFERENCES strategy_settings_snapshots(as_of_date)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Historie der echten, manuell erfassten Trade-Ausführungen';


-- ###########################################################################
-- CORE: Tabelle cash_ledger
-- ###########################################################################
CREATE TABLE IF NOT EXISTS cash_ledger (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Technische ID des Cash-Ledger-Eintrags',
    booked_at DATETIME NOT NULL COMMENT 'Buchungszeitpunkt',
    as_of_date DATE NOT NULL COMMENT 'Bezug zum Rebalance-/Trade-Plan-Stichtag',
    ticker VARCHAR(10) COMMENT 'Optionaler Bezug zu einem Ticker',

    entry_type ENUM('trade_buy','trade_sell','tax_payment','deposit','withdrawal','correction') NOT NULL COMMENT 'Art der Cash-Bewegung: BUY negativ, SELL positiv, tax_payment negativ',
    amount DECIMAL(20,6) NOT NULL COMMENT 'Cash-Veränderung: BUY negativ, SELL positiv, tax_payment negativ',
    balance_after DECIMAL(20,6) NOT NULL COMMENT 'Cash-Bestand nach dieser Buchung',

    trade_execution_id INT COMMENT 'Optionaler FK auf die auslösende Trade-Ausführung',
    notes VARCHAR(255) COMMENT 'Optionale Notiz',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',

    KEY idx_cash_ledger_booked_at (booked_at),
    KEY idx_cash_ledger_as_of_date (as_of_date),
    KEY idx_cash_ledger_trade_execution (trade_execution_id),

    CONSTRAINT fk_cash_ledger_settings_snapshot
        FOREIGN KEY (as_of_date)
        REFERENCES strategy_settings_snapshots(as_of_date)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_cash_ledger_ticker
        FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE RESTRICT,

    CONSTRAINT fk_cash_ledger_trade_execution
        FOREIGN KEY (trade_execution_id) REFERENCES trade_executions(id)
        ON DELETE SET NULL
        ON UPDATE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='CORE: Historie aller Cash-Bewegungen des realen Portfolios';


-- ###########################################################################
-- RESEARCH: Tabelle performance_snapshots
-- ###########################################################################
CREATE TABLE IF NOT EXISTS performance_snapshots (
    as_of_date DATE NOT NULL COMMENT 'Stichtag',
    portfolio_type VARCHAR(20) NOT NULL COMMENT 'shadow oder real',

    portfolio_value DECIMAL(20,6) NOT NULL COMMENT 'Gesamtwert Portfolio',
    invested_value DECIMAL(20,6) NOT NULL COMMENT 'Investierter Anteil',
    cash_value DECIMAL(20,6) NOT NULL COMMENT 'Cash Anteil',

    position_count INT NOT NULL DEFAULT 0 COMMENT 'Anzahl Positionen',
    priced_positions INT NOT NULL DEFAULT 0 COMMENT 'Positionen mit Preis',
    missing_price_count INT NOT NULL DEFAULT 0 COMMENT 'Positionen ohne Preis',

    realized_profit_total DECIMAL(20,6) NOT NULL DEFAULT 0.000000 COMMENT 'Kumulierte realisierte Gewinne/Verluste bis zum Stichtag',
    taxable_profit_total DECIMAL(20,6) NOT NULL DEFAULT 0.000000 COMMENT 'Kumulierte steuerpflichtige Gewinne bis zum Stichtag',
    tax_paid_total DECIMAL(20,6) NOT NULL DEFAULT 0.000000 COMMENT 'Kumuliert gezahlte Steuern bis zum Stichtag',

    daily_return DECIMAL(20,6) NULL COMMENT 'Tagesrendite',
    cumulative_return DECIMAL(20,6) NULL COMMENT 'Kumulierte Rendite',
    drawdown DECIMAL(20,6) NULL COMMENT 'Drawdown',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Erstellungszeitpunkt',

    PRIMARY KEY (as_of_date, portfolio_type),
    KEY idx_performance_type_date (portfolio_type, as_of_date)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='RESEARCH: Performance Snapshots für Shadow und Real Portfolio';




