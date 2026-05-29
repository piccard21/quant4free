#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SMOKE_DB="ap15_client_smoke"
START_CAPITAL="10000"
PORTFOLIO_SIZE="7"
MAX_TRADES_PER_MONTH="4"
MAX_SECTOR_POSITIONS="3"
MIN_HOLDING_MONTHS="2"
MAX_FUNDING_SELL_PCT="0.35"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"
CLI_MYSQL_ROOT_PASSWORD=""
CONFIG_DB_NAME="${DB_NAME:-stocks_db}"
BUILD_IMAGE="0"
EXECUTE_TRADES="1"

usage() {
  cat <<USAGE
Usage:
  scripts/client_smoke.sh [options]

Options:
  --db-name <name>                 Isolated smoke database name. Default: ap15_client_smoke
  --start-capital <amount>         Initial cash balance. Default: 10000
  --portfolio-size <n>             Active strategy portfolio size. Default: 7
  --max-trades-per-month <n>       Active strategy trade limit. Default: 4
  --max-sector-positions <n>       Active strategy sector limit. Default: 3
  --min-holding-months <n>         Active strategy minimum holding period. Default: 2
  --max-funding-sell-pct <pct>     Active strategy funding-sell cap. Default: 0.35
  --mysql-root-password <pw>       MySQL root password. Defaults to .env or environment.
  --build                          Build the app image before running smoke CLIs.
  --skip-trade-execution           Stop after trade dry-runs instead of booking smoke trades.
  -h, --help                       Show this help.

The script drops and recreates only the isolated smoke database. It refuses to
run if --db-name equals the configured DB_NAME from .env.
USAGE
}

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
  if ! [[ "$value" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] ${name} must be an integer" >&2
    exit 1
  fi
}

validate_identifier() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "[ERROR] ${name} must contain only letters, digits, and underscores" >&2
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
  docker compose exec -T -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" db mysql -uroot -h127.0.0.1 "${SMOKE_DB}" < "$1"
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

run_app() {
  docker compose run -T --rm \
    -e DB_NAME="${SMOKE_DB}" \
    -e DB_HOST=db \
    -e DB_USER=root \
    -e DB_PASSWORD="${MYSQL_ROOT_PASSWORD}" \
    -e MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD}" \
    app "$@" < /dev/null
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db-name)
      SMOKE_DB="$2"
      shift 2
      ;;
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
    --build)
      BUILD_IMAGE="1"
      shift
      ;;
    --skip-trade-execution)
      EXECUTE_TRADES="0"
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

cd "${REPO_ROOT}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -n "${CLI_MYSQL_ROOT_PASSWORD}" ]]; then
  MYSQL_ROOT_PASSWORD="${CLI_MYSQL_ROOT_PASSWORD}"
fi
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-${DB_PASSWORD:-}}"
CONFIG_DB_NAME="${DB_NAME:-${CONFIG_DB_NAME}}"

validate_identifier "--db-name" "${SMOKE_DB}"
validate_number "--start-capital" "${START_CAPITAL}"
validate_int "--portfolio-size" "${PORTFOLIO_SIZE}"
validate_int "--max-trades-per-month" "${MAX_TRADES_PER_MONTH}"
validate_int "--max-sector-positions" "${MAX_SECTOR_POSITIONS}"
validate_int "--min-holding-months" "${MIN_HOLDING_MONTHS}"
validate_number "--max-funding-sell-pct" "${MAX_FUNDING_SELL_PCT}"

if [[ -z "${MYSQL_ROOT_PASSWORD}" ]]; then
  echo "[ERROR] MYSQL_ROOT_PASSWORD is not set (.env, environment, or --mysql-root-password)" >&2
  exit 1
fi

if [[ "${SMOKE_DB}" == "${CONFIG_DB_NAME}" ]]; then
  echo "[ERROR] smoke database must not equal configured DB_NAME (${CONFIG_DB_NAME})" >&2
  exit 1
fi

export MYSQL_ROOT_PASSWORD

require_cmd docker
require_file docker-compose.yml
require_file init.sql
require_file fixtures/raw_market_data.sql

echo "[INFO] client_smoke=started db=${SMOKE_DB} start_capital=${START_CAPITAL}"
trap 'echo "[ERROR] client_smoke=failed line=${LINENO}" >&2' ERR

run docker compose up -d db
wait_for_db

if [[ "${BUILD_IMAGE}" == "1" ]]; then
  run docker compose build app
fi

mysql_exec "
  DROP DATABASE IF EXISTS \`${SMOKE_DB}\`;
  CREATE DATABASE \`${SMOKE_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
"
echo "[INFO] loading canonical raw-data fixture"
mysql_file fixtures/raw_market_data.sql
echo "[INFO] applying canonical AP14 schema"
mysql_file init.sql

mysql_exec "
  USE \`${SMOKE_DB}\`;
  DELETE FROM live_cash_balances;
  INSERT INTO live_cash_balances (cash_balance, updated_at)
  VALUES (${START_CAPITAL}, NOW());
  UPDATE strategy_instances
  SET
    portfolio_size=${PORTFOLIO_SIZE},
    max_trades_per_month=${MAX_TRADES_PER_MONTH},
    max_sector_positions=${MAX_SECTOR_POSITIONS},
    min_holding_months=${MIN_HOLDING_MONTHS},
    max_funding_sell_pct=${MAX_FUNDING_SELL_PCT}
  WHERE is_active = 1;
"

mysql_exec "
  USE \`${SMOKE_DB}\`;
  SELECT 'assets' AS table_name, COUNT(*) AS row_count FROM assets
  UNION ALL SELECT 'asset_price_bars', COUNT(*) FROM asset_price_bars
  UNION ALL SELECT 'asset_fundamental_reports', COUNT(*) FROM asset_fundamental_reports
  UNION ALL SELECT 'asset_market_caps', COUNT(*) FROM asset_market_caps
  UNION ALL SELECT 'strategy_instances', COUNT(*) FROM strategy_instances
  UNION ALL SELECT 'live_cash_balances', COUNT(*) FROM live_cash_balances;
"

run_app python -m cli.operator_smoke --portfolio-size "${PORTFOLIO_SIZE}"
run_app python -m cli.monthly_run --persist --model-limit "${PORTFOLIO_SIZE}"
run_app python -m cli.live_status --all --limit 10

first_trade="$(
  docker compose exec -T -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" db mysql -uroot -h127.0.0.1 -B -N -e "
    USE \`${SMOKE_DB}\`;
    SELECT as_of_date, ticker, planned_shares, estimated_price, fee
    FROM live_trade_plan_items
    WHERE action = 'BUY' AND is_executable = 1
    ORDER BY execution_order, ticker
    LIMIT 1;
  "
)"

if [[ -z "${first_trade}" ]]; then
  echo "[ERROR] no executable BUY trade found in smoke trade plan" >&2
  exit 1
fi

read -r as_of_date first_ticker first_shares first_price first_fee <<< "${first_trade}"
run_app python -m cli.live_trade \
  --as-of-date "${as_of_date}" \
  --ticker "${first_ticker}" \
  --execution-type BUY \
  --shares "${first_shares}" \
  --price "${first_price}" \
  --fee "${first_fee}" \
  --trade-plan-action BUY \
  --dry-run

run_app python -m cli.live_cash \
  --type deposit \
  --amount 250 \
  --as-of-date "${as_of_date}" \
  --notes "client smoke deposit dry-run" \
  --dry-run

if [[ "${EXECUTE_TRADES}" == "1" ]]; then
  echo "[INFO] executing all executable BUY trades in isolated smoke database"
  while read -r ticker shares price fee; do
    run_app python -m cli.live_trade \
      --as-of-date "${as_of_date}" \
      --ticker "${ticker}" \
      --execution-type BUY \
      --shares "${shares}" \
      --price "${price}" \
      --fee "${fee}" \
      --trade-plan-action BUY \
      --broker smoke-test \
      --notes "isolated client smoke"
  done < <(
    docker compose exec -T -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" db mysql -uroot -h127.0.0.1 -B -N -e "
      USE \`${SMOKE_DB}\`;
      SELECT ticker, planned_shares, estimated_price, fee
      FROM live_trade_plan_items
      WHERE as_of_date = '${as_of_date}' AND action = 'BUY' AND is_executable = 1
      ORDER BY execution_order, ticker;
    "
  )
  run_app python -m cli.live_status --all --limit 10
fi

mysql_exec "
  USE \`${SMOKE_DB}\`;
  SELECT COUNT(*) AS executions FROM live_trade_executions;
  SELECT COUNT(*) AS open_positions FROM live_positions WHERE is_open = 1;
  SELECT cash_balance FROM live_cash_balances ORDER BY id DESC LIMIT 1;
  SELECT balance_after AS latest_ledger_balance FROM live_cash_ledger ORDER BY booked_at DESC, id DESC LIMIT 1;
  SELECT COUNT(*) AS model_rows FROM portfolio_target_items WHERE snapshot_type = 'model';
  SELECT COUNT(*) AS shadow_rows FROM portfolio_target_items WHERE snapshot_type = 'shadow';
"

echo "[INFO] client_smoke=ok db=${SMOKE_DB}"
