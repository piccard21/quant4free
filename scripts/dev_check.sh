#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BUILD_IMAGE="0"
RUN_SMOKE="0"
EXECUTE_SMOKE_TRADES="0"
SMOKE_DB="dev_check_smoke"

usage() {
  cat <<USAGE
Usage:
  scripts/dev_check.sh [options]

Options:
  --build                  Build the app image before running checks.
  --smoke                  Run isolated Docker/MySQL end-to-end smoke.
  --execute-smoke-trades   In smoke mode, book generated BUY trades in the isolated DB.
  --db-name <name>         Isolated smoke DB name. Default: dev_check_smoke
  -h, --help               Show this help.

Default checks are fast and run in the app container:
  - compileall for modular packages
  - pytest tests -m "not integration"

Smoke mode delegates to scripts/client_smoke.sh and never uses the configured
DB_NAME as its smoke database.
USAGE
}

run() {
  echo "[INFO] $*"
  "$@"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] command not found: $1" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)
      BUILD_IMAGE="1"
      shift
      ;;
    --smoke)
      RUN_SMOKE="1"
      shift
      ;;
    --execute-smoke-trades)
      EXECUTE_SMOKE_TRADES="1"
      RUN_SMOKE="1"
      shift
      ;;
    --db-name)
      SMOKE_DB="$2"
      shift 2
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

require_cmd docker

if [[ "${BUILD_IMAGE}" == "1" ]]; then
  run docker compose build app
fi

run docker compose run -T --rm app python -m compileall \
  data universes indicators strategies simulation evaluation live cli shared tests

run docker compose run -T --rm app python -m pytest tests -m "not integration"

if [[ "${RUN_SMOKE}" == "1" ]]; then
  smoke_args=(--db-name "${SMOKE_DB}")
  if [[ "${BUILD_IMAGE}" == "1" ]]; then
    smoke_args+=(--build)
  fi
  if [[ "${EXECUTE_SMOKE_TRADES}" == "0" ]]; then
    smoke_args+=(--skip-trade-execution)
  fi
  run scripts/client_smoke.sh "${smoke_args[@]}"
fi

echo "[INFO] dev_check=ok"
