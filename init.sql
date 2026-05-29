-- Quant framework canonical AP14 schema.
-- This schema intentionally does not create the frozen legacy tables.

SET NAMES utf8mb4;
SET time_zone = '+00:00';


-- ###########################################################################
-- Raw market data
-- ###########################################################################

CREATE TABLE IF NOT EXISTS assets (
    ticker VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    sector VARCHAR(255),
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    first_seen DATETIME,
    last_seen DATETIME,
    removed_at DATETIME,
    last_fundamental_update DATETIME,

    KEY idx_assets_is_active (is_active),
    KEY idx_assets_last_fundamental_update (last_fundamental_update)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Canonical asset master data';


CREATE TABLE IF NOT EXISTS asset_price_bars (
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(20,4),
    high DECIMAL(20,4),
    low DECIMAL(20,4),
    close DECIMAL(20,4),
    volume BIGINT,

    PRIMARY KEY (ticker, date),
    KEY idx_asset_price_bars_ticker_date_desc (ticker, date DESC),

    CONSTRAINT fk_asset_price_bars_asset
        FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Canonical daily OHLCV price bars';


CREATE TABLE IF NOT EXISTS asset_fundamental_reports (
    ticker VARCHAR(10) NOT NULL,
    report_date DATE NOT NULL,
    report_type ENUM('annual', 'ttm') NOT NULL,

    revenue BIGINT DEFAULT 0,
    net_income BIGINT DEFAULT 0,
    ebit BIGINT DEFAULT 0,
    free_cash_flow BIGINT DEFAULT 0,
    total_debt BIGINT DEFAULT 0,
    total_equity BIGINT DEFAULT 0,
    cash_and_equivalents BIGINT DEFAULT 0,

    source VARCHAR(50),
    imported_at DATETIME,

    PRIMARY KEY (ticker, report_date, report_type),
    KEY idx_asset_fundamental_reports_ticker_type_date (ticker, report_type, report_date DESC),

    CONSTRAINT fk_asset_fundamental_reports_asset
        FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Canonical annual and TTM fundamental reports';


CREATE TABLE IF NOT EXISTS asset_market_caps (
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    market_cap BIGINT,
    imported_at DATETIME,

    PRIMARY KEY (ticker, date),
    KEY idx_asset_market_caps_ticker_date_desc (ticker, date DESC),

    CONSTRAINT fk_asset_market_caps_asset
        FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Canonical market-cap time series';


-- ###########################################################################
-- Strategy configuration
-- ###########################################################################

CREATE TABLE IF NOT EXISTS strategy_instances (
    id INT AUTO_INCREMENT PRIMARY KEY,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    strategy_version VARCHAR(20) NOT NULL DEFAULT 'v1.5',

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
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    KEY idx_strategy_instances_active (is_active),
    KEY idx_strategy_instances_version (strategy_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Canonical versioned operational strategy configuration';


INSERT INTO strategy_instances (
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
    SELECT 1 FROM strategy_instances
);


CREATE TABLE IF NOT EXISTS strategy_config_snapshots (
    as_of_date DATE NOT NULL,
    strategy_version VARCHAR(20) NOT NULL,

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
    KEY idx_strategy_config_snapshots_version (strategy_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Frozen operational configuration per live run date';


-- ###########################################################################
-- Model, shadow, rebalance, and trade plans
-- ###########################################################################

CREATE TABLE IF NOT EXISTS portfolio_target_items (
    as_of_date DATE NOT NULL,
    snapshot_type VARCHAR(20) NOT NULL,
    ticker VARCHAR(10) NOT NULL,

    portfolio_rank INT,
    source_rank INT,
    sector VARCHAR(100),
    target_weight DECIMAL(10,6),
    final_score DECIMAL(8,4),
    value_score DECIMAL(8,4),
    quality_score DECIMAL(8,4),
    momentum_score DECIMAL(8,4),
    trend_positive TINYINT(1) NOT NULL DEFAULT 0,
    buy_eligible TINYINT(1) NOT NULL DEFAULT 0,
    holding_start_date DATE NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (as_of_date, snapshot_type, ticker),
    KEY idx_portfolio_target_items_type_rank (as_of_date, snapshot_type, portfolio_rank),
    KEY idx_portfolio_target_items_ticker (ticker),

    CONSTRAINT fk_portfolio_target_items_asset
        FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Frozen model and shadow target portfolio items';


CREATE TABLE IF NOT EXISTS live_rebalance_items (
    as_of_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    sector VARCHAR(100),
    action VARCHAR(20) NOT NULL,
    reason VARCHAR(255),
    source_rank INT,
    target_weight DECIMAL(10,6),
    current_shares DECIMAL(20,6),
    opened_at DATE,
    holding_days INT,
    min_hold_ok TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (as_of_date, ticker),
    KEY idx_live_rebalance_items_action (as_of_date, action),
    KEY idx_live_rebalance_items_ticker (ticker),

    CONSTRAINT fk_live_rebalance_items_asset
        FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE,
    CONSTRAINT fk_live_rebalance_items_config
        FOREIGN KEY (as_of_date) REFERENCES strategy_config_snapshots(as_of_date)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Frozen live rebalance actions';


CREATE TABLE IF NOT EXISTS live_decision_items (
    as_of_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    action VARCHAR(20) NOT NULL,
    reason VARCHAR(255),
    source_rank INT,
    final_score DECIMAL(8,4),
    value_score DECIMAL(8,4),
    quality_score DECIMAL(8,4),
    momentum_score DECIMAL(8,4),
    trend_positive TINYINT(1) NOT NULL DEFAULT 0,
    holding_days INT,
    min_hold_ok TINYINT(1) NOT NULL DEFAULT 1,
    strategy_version VARCHAR(20),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (as_of_date, ticker),
    KEY idx_live_decision_items_action (as_of_date, action),
    KEY idx_live_decision_items_strategy (strategy_version),
    KEY idx_live_decision_items_ticker (ticker),

    CONSTRAINT fk_live_decision_items_asset
        FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE,
    CONSTRAINT fk_live_decision_items_config
        FOREIGN KEY (as_of_date) REFERENCES strategy_config_snapshots(as_of_date)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Frozen live decision log items';


CREATE TABLE IF NOT EXISTS live_trade_plans (
    as_of_date DATE NOT NULL,
    portfolio_value_before DECIMAL(20,6) NOT NULL,
    invested_value_before DECIMAL(20,6) NOT NULL,
    cash_before DECIMAL(20,6) NOT NULL,
    cash_after DECIMAL(20,6) NOT NULL,
    bucket_size DECIMAL(20,6) NOT NULL,
    target_positions INT NOT NULL,
    positions_before INT NOT NULL,
    positions_after INT NOT NULL,
    total_sell_gross DECIMAL(20,6) NOT NULL,
    total_buy_gross DECIMAL(20,6) NOT NULL,
    total_fees DECIMAL(20,6) NOT NULL,
    executable_buys INT NOT NULL,
    executable_sells INT NOT NULL,
    skipped_trades INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (as_of_date),
    KEY idx_live_trade_plans_positions (positions_before, positions_after),

    CONSTRAINT fk_live_trade_plans_config
        FOREIGN KEY (as_of_date) REFERENCES strategy_config_snapshots(as_of_date)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Concrete capital-aware live trade plan summary';


CREATE TABLE IF NOT EXISTS live_trade_plan_items (
    as_of_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    action VARCHAR(20) NOT NULL,
    reason VARCHAR(255),
    execution_order INT,
    source_rank INT,
    target_weight DECIMAL(10,6),
    current_shares DECIMAL(20,6),
    planned_shares DECIMAL(20,6),
    estimated_price DECIMAL(20,6),
    gross_amount DECIMAL(20,6),
    fee DECIMAL(20,6) NOT NULL DEFAULT 0.000000,
    net_amount DECIMAL(20,6),
    bucket_size DECIMAL(20,6),
    cash_before DECIMAL(20,6),
    cash_after DECIMAL(20,6),
    is_executable TINYINT(1) NOT NULL DEFAULT 0,
    skip_reason VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (as_of_date, ticker),
    KEY idx_live_trade_plan_items_action (as_of_date, action),
    KEY idx_live_trade_plan_items_exec_order (as_of_date, execution_order),
    KEY idx_live_trade_plan_items_source_rank (as_of_date, source_rank),
    KEY idx_live_trade_plan_items_executable (as_of_date, is_executable),

    CONSTRAINT fk_live_trade_plan_items_asset
        FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE,
    CONSTRAINT fk_live_trade_plan_items_config
        FOREIGN KEY (as_of_date) REFERENCES strategy_config_snapshots(as_of_date)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Concrete live trade plan items';


-- ###########################################################################
-- Real portfolio, executions, and cash
-- ###########################################################################

CREATE TABLE IF NOT EXISTS live_positions (
    position_id INT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    shares DECIMAL(20,6) NOT NULL,
    buy_price DECIMAL(20,6),
    opened_at DATETIME NOT NULL,
    closed_at DATETIME,
    is_open TINYINT(1) NOT NULL DEFAULT 1,
    notes VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    KEY idx_live_positions_open (is_open, opened_at),
    KEY idx_live_positions_ticker (ticker),

    CONSTRAINT fk_live_positions_asset
        FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Canonical manually maintained real portfolio positions';


CREATE TABLE IF NOT EXISTS live_cash_balances (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cash_balance DECIMAL(20,6) NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY idx_live_cash_balances_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Canonical real portfolio cash balance snapshots';


INSERT INTO live_cash_balances (cash_balance, updated_at)
SELECT 0.000000, NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM live_cash_balances
);


CREATE TABLE IF NOT EXISTS live_trade_executions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    as_of_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    execution_type ENUM('BUY','SELL') NOT NULL,
    trade_plan_action ENUM('BUY','SELL','ADJUST_BUY','ADJUST_SELL'),
    executed_at DATETIME NOT NULL,
    shares DECIMAL(20,6) NOT NULL,
    price DECIMAL(20,6) NOT NULL,
    gross_amount DECIMAL(20,6) NOT NULL,
    fee DECIMAL(20,6) NOT NULL DEFAULT 0.000000,
    net_amount DECIMAL(20,6) NOT NULL,
    realized_profit DECIMAL(20,6) NULL,
    tax_amount DECIMAL(20,6) NOT NULL DEFAULT 0.000000,
    broker VARCHAR(100),
    notes VARCHAR(255),
    trade_plan_execution_order INT,
    status ENUM('executed','skipped','cancelled') NOT NULL DEFAULT 'executed',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_live_trade_executions_once (as_of_date, ticker, execution_type, executed_at),
    KEY idx_live_trade_executions_asof_ticker (as_of_date, ticker),
    KEY idx_live_trade_executions_status (status),
    KEY idx_live_trade_executions_executed_at (executed_at),

    CONSTRAINT fk_live_trade_executions_asset
        FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE RESTRICT,
    CONSTRAINT fk_live_trade_executions_config
        FOREIGN KEY (as_of_date) REFERENCES strategy_config_snapshots(as_of_date)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Canonical manual real trade executions';


CREATE TABLE IF NOT EXISTS live_cash_ledger (
    id INT AUTO_INCREMENT PRIMARY KEY,
    booked_at DATETIME NOT NULL,
    as_of_date DATE NOT NULL,
    ticker VARCHAR(10),
    entry_type ENUM('trade_buy','trade_sell','tax_payment','deposit','withdrawal','correction') NOT NULL,
    amount DECIMAL(20,6) NOT NULL,
    balance_after DECIMAL(20,6) NOT NULL,
    trade_execution_id INT,
    notes VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY idx_live_cash_ledger_booked_at (booked_at),
    KEY idx_live_cash_ledger_as_of_date (as_of_date),
    KEY idx_live_cash_ledger_trade_execution (trade_execution_id),

    CONSTRAINT fk_live_cash_ledger_config
        FOREIGN KEY (as_of_date) REFERENCES strategy_config_snapshots(as_of_date)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_live_cash_ledger_asset
        FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE RESTRICT,
    CONSTRAINT fk_live_cash_ledger_trade_execution
        FOREIGN KEY (trade_execution_id) REFERENCES live_trade_executions(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Canonical cash ledger for the real portfolio';


-- ###########################################################################
-- Research/reporting compatibility
-- ###########################################################################

CREATE TABLE IF NOT EXISTS performance_snapshots (
    as_of_date DATE NOT NULL,
    portfolio_type VARCHAR(20) NOT NULL,
    portfolio_value DECIMAL(20,6) NOT NULL,
    invested_value DECIMAL(20,6) NOT NULL,
    cash_value DECIMAL(20,6) NOT NULL,
    position_count INT NOT NULL DEFAULT 0,
    priced_positions INT NOT NULL DEFAULT 0,
    missing_price_count INT NOT NULL DEFAULT 0,
    realized_profit_total DECIMAL(20,6) NOT NULL DEFAULT 0.000000,
    taxable_profit_total DECIMAL(20,6) NOT NULL DEFAULT 0.000000,
    tax_paid_total DECIMAL(20,6) NOT NULL DEFAULT 0.000000,
    daily_return DECIMAL(20,6) NULL,
    cumulative_return DECIMAL(20,6) NULL,
    drawdown DECIMAL(20,6) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (as_of_date, portfolio_type),
    KEY idx_performance_snapshots_type_date (portfolio_type, as_of_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Research performance snapshots';
