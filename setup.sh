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

usage() {
  cat <<USAGE
Usage:
  ./setup.sh init    --start-capital <amount> [--portfolio-size <n>] [--max-trades-per-month <n>] [--max-sector-positions <n>] [--min-holding-months <n>] [--max-funding-sell-pct <pct>] [--mysql-root-password <pw>] [--db-name <name>] [--skip-price-init] [--skip-fundamental-init] [--no-build]
  ./setup.sh rebuild --start-capital <amount> [--portfolio-size <n>] [--max-trades-per-month <n>] [--max-sector-positions <n>] [--min-holding-months <n>] [--max-funding-sell-pct <pct>] [--mysql-root-password <pw>] [--db-name <name>]

Modes:
  init      Kompletter Neuaufbau inkl. Docker Volume Reset, Schema und API-Daten
  rebuild   Neuaufbau ohne API-Calls, behält tickers/prices/fundamentals/market caps/settings

Beispiele:
  ./setup.sh init --start-capital 10000 --portfolio-size 10 --max-trades-per-month 2 --max-sector-positions 2 --min-holding-months 3 --max-funding-sell-pct 0.20
  ./setup.sh rebuild --start-capital 10000 --portfolio-size 10 --max-trades-per-month 2 --max-sector-positions 2 --min-holding-months 3 --max-funding-sell-pct 0.20
USAGE
}

SKIP_PRICE_INIT="0"
SKIP_FUNDAMENTAL_INIT="0"
NO_BUILD="0"

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
    echo "[ERROR] Unbekannter Modus: $MODE" >&2
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
      shift 2
      ;;
    --db-name)
      DB_NAME="$2"
      shift 2
      ;;
    --skip-price-init)
      SKIP_PRICE_INIT="1"
      shift
      ;;
    --skip-fundamental-init)
      SKIP_FUNDAMENTAL_INIT="1"
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
      echo "[ERROR] Unbekannte Option: $1" >&2
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

MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"
DB_NAME="${DB_NAME:-stocks_db}"

if [[ -z "$START_CAPITAL" ]]; then
  echo "[ERROR] --start-capital ist Pflicht." >&2
  usage
  exit 1
fi

if ! [[ "$START_CAPITAL" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "[ERROR] --start-capital muss eine Zahl sein, z. B. 10000 oder 10000.00" >&2
  exit 1
fi

# Optionale Strategie-Settings für Init/Rebuild.
# Leere Werte bedeuten: bestehender DB-/Schema-Default bleibt erhalten.
if [[ -n "$PORTFOLIO_SIZE" ]] && ! [[ "$PORTFOLIO_SIZE" =~ ^[0-9]+$ ]] ; then
  echo "[ERROR] --portfolio-size muss eine ganze Zahl > 0 sein." >&2
  exit 1
fi

if [[ -n "$MAX_TRADES_PER_MONTH" ]] && ! [[ "$MAX_TRADES_PER_MONTH" =~ ^[0-9]+$ ]] ; then
  echo "[ERROR] --max-trades-per-month muss eine ganze Zahl > 0 sein." >&2
  exit 1
fi

if [[ -n "$MAX_SECTOR_POSITIONS" ]] && ! [[ "$MAX_SECTOR_POSITIONS" =~ ^[0-9]+$ ]] ; then
  echo "[ERROR] --max-sector-positions muss eine ganze Zahl > 0 sein." >&2
  exit 1
fi

if [[ -n "$MIN_HOLDING_MONTHS" ]] && ! [[ "$MIN_HOLDING_MONTHS" =~ ^[0-9]+$ ]] ; then
  echo "[ERROR] --min-holding-months muss eine ganze Zahl >= 0 sein." >&2
  exit 1
fi

if [[ -n "$MAX_FUNDING_SELL_PCT" ]] && ! [[ "$MAX_FUNDING_SELL_PCT" =~ ^[0-9]+([.][0-9]+)?$ ]] ; then
  echo "[ERROR] --max-funding-sell-pct muss eine Zahl zwischen 0 und 1 sein, z. B. 0.20" >&2
  exit 1
fi

if [[ -z "$MYSQL_ROOT_PASSWORD" ]]; then
  echo "[ERROR] MYSQL_ROOT_PASSWORD ist nicht gesetzt (.env oder --mysql-root-password)." >&2
  exit 1
fi

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "[ERROR] Datei fehlt: $1" >&2
    exit 1
  fi
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] Befehl nicht gefunden: $1" >&2
    exit 1
  fi
}

run() {
  echo "[INFO] $*"
  "$@"
}

mysql_exec() {
  docker compose exec -T -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" db mysql -uroot -e "$1"
}

mysql_scalar() {
  docker compose exec -T -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" db mysql -N -uroot -e "$1" | tr -d '\r'
}

apply_strategy_overrides() {
  # Schreibt optionale Setup-Parameter in strategy_settings.
  # Wichtig: Das ist nur die aktive Konfiguration. Rebalance-Snapshots frieren
  # diese Werte später unveränderlich in strategy_settings_snapshots ein.
  local assignments=()

  if [[ -n "$PORTFOLIO_SIZE" ]]; then
    assignments+=("portfolio_size=${PORTFOLIO_SIZE}")
  fi

  if [[ -n "$MAX_TRADES_PER_MONTH" ]]; then
    assignments+=("max_trades_per_month=${MAX_TRADES_PER_MONTH}")
  fi

  if [[ -n "$MAX_SECTOR_POSITIONS" ]]; then
    assignments+=("max_sector_positions=${MAX_SECTOR_POSITIONS}")
  fi

  if [[ -n "$MIN_HOLDING_MONTHS" ]]; then
    assignments+=("min_holding_months=${MIN_HOLDING_MONTHS}")
  fi

  if [[ -n "$MAX_FUNDING_SELL_PCT" ]]; then
    assignments+=("max_funding_sell_pct=${MAX_FUNDING_SELL_PCT}")
  fi

  if [[ ${#assignments[@]} -eq 0 ]]; then
    return
  fi

  local set_clause
  set_clause="$(IFS=, ; echo "${assignments[*]}")"

  echo "[INFO] Aktualisiere strategy_settings: ${set_clause}"
  mysql_exec "
    USE ${DB_NAME};
    UPDATE strategy_settings
    SET ${set_clause}
    WHERE is_active = 1;
  "
}

wait_for_db() {
  echo "[INFO] Warte auf MySQL..."
  for _ in {1..60}; do
    status="$(docker inspect --format='{{.State.Health.Status}}' sp500_db 2>/dev/null || true)"
    if [[ "$status" == "healthy" ]]; then
      echo "[INFO] MySQL ready"
      return
    fi
    sleep 2
  done
  echo "[ERROR] MySQL nicht bereit" >&2
  exit 1
}

wait_for_schema() {
  echo "[INFO] Warte auf Schema..."
  for _ in {1..60}; do
    ready="$(docker compose exec -T -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" db mysql -N -uroot -e "
      SELECT COUNT(*)
      FROM information_schema.tables
      WHERE table_schema='${DB_NAME}'
    " 2>/dev/null || echo 0)"

    if [[ "$ready" =~ ^[0-9]+$ ]] && [[ "$ready" -ge 10 ]]; then
      echo "[INFO] Schema ready (${ready} Tabellen)"
      return
    fi
    sleep 2
  done
  echo "[ERROR] Schema nicht vollständig" >&2
  exit 1
}

compile_python() {
  local targets=()
  for path in core research cli shared; do
    [[ -d "$path" ]] && targets+=("$path")
  done

  if [[ ${#targets[@]} -gt 0 ]]; then
    run docker compose run --rm app python -m compileall "${targets[@]}"
    return
  fi

  targets=()
  for path in *.py; do
    [[ -e "$path" ]] && targets+=("$path")
  done

  if [[ ${#targets[@]} -gt 0 ]]; then
    run docker compose run --rm app python -m compileall "${targets[@]}"
  fi
}

run_core_build() {
  run docker compose run --rm app python -m core.build_factor_metrics
  run docker compose run --rm app python -m core.build_factor_scores
  run docker compose run --rm app python -m core.build_portfolio
  run docker compose run --rm app python -m core.build_tradable_shadow
  run docker compose run --rm app python -m core.build_rebalance
  run docker compose run --rm app python -m core.build_trade_plan
}

run_performance_for_trade_plan_date() {
  local target_date
  target_date="$(mysql_scalar "
    USE ${DB_NAME};
    SELECT MAX(as_of_date)
    FROM trade_plan_summary;
  ")"

  if [[ -z "$target_date" || "$target_date" == "NULL" ]]; then
    echo "[ERROR] Konnte keinen Trade-Plan-Stichtag für Performance ermitteln." >&2
    exit 1
  fi

  echo "[INFO] Baue Performance für Stichtag ${target_date}..."
  run docker compose run --rm app python -m cli.research_main performance --as-of-date "$target_date"

  echo "[INFO] Prüfe Status..."
  run docker compose run --rm app python -m cli.show_status --as-of-date "$target_date" --details
}

validate_result() {
  local factor_scores_count
  local portfolio_count
  local trade_plan_count
  local performance_count
  local cash

  factor_scores_count="$(mysql_scalar "USE ${DB_NAME}; SELECT COUNT(*) FROM factor_scores;")"
  portfolio_count="$(mysql_scalar "USE ${DB_NAME}; SELECT COUNT(*) FROM portfolio_snapshots WHERE snapshot_type='shadow';")"
  trade_plan_count="$(mysql_scalar "USE ${DB_NAME}; SELECT COUNT(*) FROM trade_plan_snapshots;")"
  performance_count="$(mysql_scalar "USE ${DB_NAME}; SELECT COUNT(*) FROM performance_snapshots;")"
  cash="$(mysql_scalar "USE ${DB_NAME}; SELECT cash_balance FROM portfolio_cash ORDER BY updated_at DESC, id DESC LIMIT 1;")"

  echo "[INFO] Validierung:"
  echo "       factor_scores=${factor_scores_count}"
  echo "       shadow_positions=${portfolio_count}"
  echo "       trade_plan_rows=${trade_plan_count}"
  echo "       performance_rows=${performance_count}"
  echo "       cash=${cash}"

  if [[ "$factor_scores_count" -le 0 || "$portfolio_count" -le 0 || "$trade_plan_count" -le 0 || "$performance_count" -lt 2 ]]; then
    echo "[ERROR] Validierung fehlgeschlagen." >&2
    exit 1
  fi
}

confirm_init() {
  echo
  echo "[WARN] ACHTUNG: INIT löscht Container, Volumes und komplette Datenbank."
  echo "[WARN] Danach werden Preise/Fundamentals über APIs neu geladen."
  echo "[INFO] Startkapital: ${START_CAPITAL}"
  [[ -n "$PORTFOLIO_SIZE" ]] && echo "[INFO] Portfolio-Größe: ${PORTFOLIO_SIZE}"
  [[ -n "$MAX_TRADES_PER_MONTH" ]] && echo "[INFO] Max Trades/Monat: ${MAX_TRADES_PER_MONTH}"
  [[ -n "$MAX_SECTOR_POSITIONS" ]] && echo "[INFO] Max Positionen/Sektor: ${MAX_SECTOR_POSITIONS}"
  [[ -n "$MIN_HOLDING_MONTHS" ]] && echo "[INFO] Mindesthaltedauer Monate: ${MIN_HOLDING_MONTHS}"
  [[ -n "$MAX_FUNDING_SELL_PCT" ]] && echo "[INFO] Max Funding-Sell pro Position: ${MAX_FUNDING_SELL_PCT}"
  read -r -p "Weiter? (yes/no): " confirm
  [[ "$confirm" == "yes" ]] || exit 1
}

confirm_rebuild() {
  echo
  echo "[WARN] ACHTUNG: REBUILD löscht alle NICHT-API-Daten."
  echo "[WARN] Erhalten bleiben nur:"
  echo "       - tickers"
  echo "       - daily_candles"
  echo "       - financial_reports"
  echo "       - market_cap_snapshots"
  echo "       - strategy_settings"
  echo
  echo "[WARN] Gelöscht werden:"
  echo "       - factor_metrics / factor_scores"
  echo "       - portfolio_snapshots / rebalance_suggestions / decision_log"
  echo "       - trade_plan_summary / trade_plan_snapshots"
  echo "       - performance_snapshots"
  echo "       - trade_executions"
  echo "       - portfolio_positions"
  echo "       - cash_ledger"
  echo "       - portfolio_cash"
  echo
  echo "[INFO] Neues Startkapital: ${START_CAPITAL}"
  [[ -n "$PORTFOLIO_SIZE" ]] && echo "[INFO] Neue Portfolio-Größe: ${PORTFOLIO_SIZE}"
  [[ -n "$MAX_TRADES_PER_MONTH" ]] && echo "[INFO] Neue Max Trades/Monat: ${MAX_TRADES_PER_MONTH}"
  [[ -n "$MAX_SECTOR_POSITIONS" ]] && echo "[INFO] Neue Max Positionen/Sektor: ${MAX_SECTOR_POSITIONS}"
  [[ -n "$MIN_HOLDING_MONTHS" ]] && echo "[INFO] Neue Mindesthaltedauer Monate: ${MIN_HOLDING_MONTHS}"
  [[ -n "$MAX_FUNDING_SELL_PCT" ]] && echo "[INFO] Neues Max Funding-Sell pro Position: ${MAX_FUNDING_SELL_PCT}"
  read -r -p "Weiter? (yes/no): " confirm
  [[ "$confirm" == "yes" ]] || exit 1
}

do_init() {
  require_cmd docker
  require_file docker-compose.yml
  require_file init.sql

  confirm_init

  run docker compose down -v --remove-orphans
  run docker rm -f sp500_db sp500_pma sp500_worker || true
  run docker builder prune -f

  if [[ "$NO_BUILD" == "0" ]]; then
    run docker compose build --no-cache
  else
    echo "[WARN] Docker Build übersprungen"
  fi

  run docker compose up -d db phpmyadmin

  wait_for_db
  wait_for_schema

  echo "[INFO] Setze Startkapital ${START_CAPITAL}"
  mysql_exec "
    USE ${DB_NAME};
    DELETE FROM portfolio_cash;
    INSERT INTO portfolio_cash (cash_balance, updated_at)
    VALUES (${START_CAPITAL}, NOW());
  "

  apply_strategy_overrides

  compile_python

  if [[ "$SKIP_PRICE_INIT" == "0" ]]; then
    run docker compose run --rm app python -m core.sync_prices --mode init
  else
    echo "[WARN] Preis-Initialimport übersprungen"
  fi

  if [[ "$SKIP_FUNDAMENTAL_INIT" == "0" ]]; then
    run docker compose run --rm app python -m core.sync_fundamentals --mode init
  else
    echo "[WARN] Fundamental-Initialimport übersprungen"
  fi

  run_core_build
  run_performance_for_trade_plan_date
  validate_result

  echo "[INFO] setup.sh init fertig."
}

do_rebuild() {
  require_cmd docker
  require_file docker-compose.yml

  confirm_rebuild

  echo "[INFO] Lösche nicht-API-Daten und setze Startkapital..."

  mysql_exec "
    USE ${DB_NAME};
    SET FOREIGN_KEY_CHECKS = 0;

    DELETE FROM performance_snapshots;

    DELETE FROM trade_plan_snapshots;
    DELETE FROM trade_plan_summary;

    DELETE FROM decision_log;
    DELETE FROM rebalance_suggestions;
    DELETE FROM strategy_settings_snapshots;
    DELETE FROM portfolio_snapshots;

    DELETE FROM factor_scores;
    DELETE FROM factor_metrics;

    DELETE FROM trade_executions;
    DELETE FROM portfolio_positions;
    DELETE FROM cash_ledger;
    DELETE FROM portfolio_cash;

    INSERT INTO portfolio_cash (cash_balance, updated_at)
    VALUES (${START_CAPITAL}, NOW());

    SET FOREIGN_KEY_CHECKS = 1;
  "

  apply_strategy_overrides

  compile_python
  run_core_build
  run_performance_for_trade_plan_date
  validate_result

  echo "[INFO] setup.sh rebuild fertig."
}

case "$MODE" in
  init)
    do_init
    ;;
  rebuild)
    do_rebuild
    ;;
esac



