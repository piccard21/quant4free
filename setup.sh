#!/usr/bin/env bash
set -Eeuo pipefail

MODE=""
START_CAPITAL=""
PORTFOLIO_SIZE=""
MAX_TRADES_PER_MONTH=""
MAX_SECTOR_POSITIONS=""
MIN_HOLDING_MONTHS=""
MAX_FUNDING_SELL_PCT=""
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"
DB_NAME="${DB_NAME:-stocks_db}"
CLI_MYSQL_ROOT_PASSWORD=""
CLI_DB_NAME=""
NO_BUILD="0"
LOAD_FIXTURE="0"

usage() {
  cat <<USAGE
Usage:
  ./setup.sh init --start-capital <amount> [--load-fixture] [--portfolio-size <n>] [--max-trades-per-month <n>] [--max-sector-positions <n>] [--min-holding-months <n>] [--max-funding-sell-pct <pct>] [--mysql-root-password <pw>] [--db-name <name>] [--no-build]
  ./setup.sh rebuild --start-capital <amount> [--portfolio-size <n>] [--max-trades-per-month <n>] [--max-sector-positions <n>] [--min-holding-months <n>] [--max-funding-sell-pct <pct>] [--mysql-root-password <pw>] [--db-name <name>]

Modes:
  init      Reset Docker DB volume, start MySQL, create canonical schema, optionally load raw fixture.
  rebuild   Keep raw market data, clear live/evaluation state, reset cash and strategy overrides.
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

MODE="$1"
shift

case "$MODE" in
  init|rebuild) ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    echo "[ERROR] unknown mode: $MODE" >&2
    usage
    exit 1
    ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --start-capital)
      START_CAPITAL="$2"
      shift 2
      ;;
    --portfolio-size)
      PORTFOLIO_SIZE="$2"
      shift 2
      ;;
    --max-trades-per-month)
      MAX_TRADES_PER_MONTH="$2"
      shift 2
      ;;
    --max-sector-positions)
      MAX_SECTOR_POSITIONS="$2"
      shift 2
      ;;
    --min-holding-months)
      MIN_HOLDING_MONTHS="$2"
      shift 2
      ;;
    --max-funding-sell-pct)
      MAX_FUNDING_SELL_PCT="$2"
      shift 2
      ;;
    --mysql-root-password)
      MYSQL_ROOT_PASSWORD="$2"
      CLI_MYSQL_ROOT_PASSWORD="$2"
      shift 2
      ;;
    --db-name)
      DB_NAME="$2"
      CLI_DB_NAME="$2"
      shift 2
      ;;
    --load-fixture)
      LOAD_FIXTURE="1"
      shift
      ;;
    --no-build)
      NO_BUILD="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

[[ -n "$CLI_MYSQL_ROOT_PASSWORD" ]] && MYSQL_ROOT_PASSWORD="$CLI_MYSQL_ROOT_PASSWORD"
[[ -n "$CLI_DB_NAME" ]] && DB_NAME="$CLI_DB_NAME"

MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"
DB_NAME="${DB_NAME:-stocks_db}"
export MYSQL_ROOT_PASSWORD DB_NAME

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] command not found: $1" >&2
    exit 1
  fi
}

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "[ERROR] missing file: $1" >&2
    exit 1
  fi
}

validate_number() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "[ERROR] ${name} must be numeric" >&2
    exit 1
  fi
}

validate_int() {
  local name="$1"
  local value="$2"
  if [[ -n "$value" ]] && ! [[ "$value" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] ${name} must be an integer" >&2
    exit 1
  fi
}

validate_args() {
  if [[ -z "$START_CAPITAL" ]]; then
    echo "[ERROR] --start-capital is required" >&2
    usage
    exit 1
  fi
  validate_number "--start-capital" "$START_CAPITAL"
  validate_int "--portfolio-size" "$PORTFOLIO_SIZE"
  validate_int "--max-trades-per-month" "$MAX_TRADES_PER_MONTH"
  validate_int "--max-sector-positions" "$MAX_SECTOR_POSITIONS"
  validate_int "--min-holding-months" "$MIN_HOLDING_MONTHS"
  if [[ -n "$MAX_FUNDING_SELL_PCT" ]]; then
    validate_number "--max-funding-sell-pct" "$MAX_FUNDING_SELL_PCT"
  fi
  if [[ -z "$MYSQL_ROOT_PASSWORD" ]]; then
    echo "[ERROR] MYSQL_ROOT_PASSWORD is not set (.env or --mysql-root-password)" >&2
    exit 1
  fi
}

run() {
  echo "[INFO] $*"
  "$@"
}

mysql_exec() {
  docker compose exec -T -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" db mysql -uroot -h127.0.0.1 -e "$1"
}

mysql_file() {
  docker compose exec -T -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" db mysql -uroot -h127.0.0.1 "${DB_NAME}" < "$1"
}

wait_for_db() {
  echo "[INFO] waiting for MySQL..."
  for _ in {1..60}; do
    if docker compose exec -T -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" db mysqladmin ping -uroot -h127.0.0.1 --silent >/dev/null 2>&1; then
      echo "[INFO] MySQL ready"
      return
    fi
    sleep 2
  done
  echo "[ERROR] MySQL not ready" >&2
  exit 1
}

apply_strategy_overrides() {
  local assignments=()
  [[ -n "$PORTFOLIO_SIZE" ]] && assignments+=("portfolio_size=${PORTFOLIO_SIZE}")
  [[ -n "$MAX_TRADES_PER_MONTH" ]] && assignments+=("max_trades_per_month=${MAX_TRADES_PER_MONTH}")
  [[ -n "$MAX_SECTOR_POSITIONS" ]] && assignments+=("max_sector_positions=${MAX_SECTOR_POSITIONS}")
  [[ -n "$MIN_HOLDING_MONTHS" ]] && assignments+=("min_holding_months=${MIN_HOLDING_MONTHS}")
  [[ -n "$MAX_FUNDING_SELL_PCT" ]] && assignments+=("max_funding_sell_pct=${MAX_FUNDING_SELL_PCT}")
  if [[ ${#assignments[@]} -eq 0 ]]; then
    return
  fi

  local set_clause
  set_clause="$(IFS=, ; echo "${assignments[*]}")"
  mysql_exec "
    USE ${DB_NAME};
    UPDATE strategy_instances
    SET ${set_clause}
    WHERE is_active = 1;
  "
}

reset_cash() {
  mysql_exec "
    USE ${DB_NAME};
    DELETE FROM live_cash_balances;
    INSERT INTO live_cash_balances (cash_balance, updated_at)
    VALUES (${START_CAPITAL}, NOW());
  "
}

clear_live_state() {
  mysql_exec "
    USE ${DB_NAME};
    SET FOREIGN_KEY_CHECKS = 0;
    DELETE FROM performance_snapshots;
    DELETE FROM live_cash_ledger;
    DELETE FROM live_trade_executions;
    DELETE FROM live_trade_plan_items;
    DELETE FROM live_trade_plans;
    DELETE FROM live_decision_items;
    DELETE FROM live_rebalance_items;
    DELETE FROM portfolio_target_items;
    DELETE FROM strategy_config_snapshots;
    DELETE FROM live_positions;
    DELETE FROM live_cash_balances;
    SET FOREIGN_KEY_CHECKS = 1;
  "
}

verify_canonical_schema() {
  mysql_exec "
    USE ${DB_NAME};
    SELECT 'assets' AS table_name, COUNT(*) AS row_count FROM assets
    UNION ALL SELECT 'asset_provider_identifiers', COUNT(*) FROM asset_provider_identifiers
    UNION ALL SELECT 'universes', COUNT(*) FROM universes
    UNION ALL SELECT 'universe_members', COUNT(*) FROM universe_members
    UNION ALL SELECT 'asset_price_bars', COUNT(*) FROM asset_price_bars
    UNION ALL SELECT 'asset_fundamental_reports', COUNT(*) FROM asset_fundamental_reports
    UNION ALL SELECT 'asset_market_caps', COUNT(*) FROM asset_market_caps
    UNION ALL SELECT 'live_cash_balances', COUNT(*) FROM live_cash_balances;
  "
}

do_init() {
  require_cmd docker
  require_file docker-compose.yml
  require_file init.sql

  echo "[WARN] init resets Docker containers, volumes, and the configured database."
  read -r -p "Continue? (yes/no): " confirm
  [[ "$confirm" == "yes" ]] || exit 1

  run docker compose down -v --remove-orphans
  run docker rm -f sp500_db sp500_pma sp500_worker || true
  if [[ "$NO_BUILD" == "0" ]]; then
    run docker compose build
  fi
  run docker compose up -d db phpmyadmin
  wait_for_db

  if [[ "$LOAD_FIXTURE" == "1" ]]; then
    require_file fixtures/raw_market_data.sql
    mysql_exec "
      DROP DATABASE IF EXISTS \`${DB_NAME}\`;
      CREATE DATABASE \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
    "
    echo "[INFO] loading canonical raw-data fixture"
    mysql_file fixtures/raw_market_data.sql
    echo "[INFO] reapplying canonical live schema"
    mysql_file init.sql
  fi

  reset_cash
  apply_strategy_overrides
  verify_canonical_schema
  echo "[INFO] setup.sh init complete"
}

do_rebuild() {
  require_cmd docker
  clear_live_state
  reset_cash
  apply_strategy_overrides
  verify_canonical_schema
  echo "[INFO] setup.sh rebuild complete"
}

validate_args

case "$MODE" in
  init) do_init ;;
  rebuild) do_rebuild ;;
esac
