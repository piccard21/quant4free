#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TEST_DB="${Q4F_TEST_DB_NAME:-quant4free_test}"
CLI_TEST_DB=""
BUILD_IMAGE="0"
TEST_MYSQL_ROOT_PASSWORD="${Q4F_TEST_MYSQL_ROOT_PASSWORD:-q4f_test_password}"
CLI_TEST_MYSQL_ROOT_PASSWORD=""

usage() {
  cat <<USAGE
Usage:
  scripts/db_integration_tests.sh [options]

Options:
  --db-name <name>             Isolated MySQL test database. Default: quant4free_test
  --mysql-root-password <pw>   Test MySQL root password. Default: q4f_test_password
  --build                      Build the app image before running tests.
  -h, --help                   Show this help.

The runner starts the db_test Compose service. The pytest fixture drops and
recreates only the isolated test database on that service.
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

validate_identifier() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "[ERROR] ${name} must contain only letters, digits, and underscores" >&2
    exit 1
  fi
}

wait_for_db() {
  echo "[INFO] waiting for MySQL..."
  for _ in {1..60}; do
    if docker compose --profile test exec -T -e MYSQL_PWD="${TEST_MYSQL_ROOT_PASSWORD}" db_test mysqladmin ping -uroot -h127.0.0.1 --silent >/dev/null 2>&1; then
      echo "[INFO] MySQL ready"
      return
    fi
    sleep 2
  done
  echo "[ERROR] MySQL not ready" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db-name)
      TEST_DB="$2"
      CLI_TEST_DB="$2"
      shift 2
      ;;
    --mysql-root-password)
      TEST_MYSQL_ROOT_PASSWORD="$2"
      CLI_TEST_MYSQL_ROOT_PASSWORD="$2"
      shift 2
      ;;
    --build)
      BUILD_IMAGE="1"
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

if [[ -z "${CLI_TEST_DB}" ]]; then
  TEST_DB="${Q4F_TEST_DB_NAME:-${TEST_DB}}"
fi
if [[ -n "${CLI_TEST_MYSQL_ROOT_PASSWORD}" ]]; then
  TEST_MYSQL_ROOT_PASSWORD="${CLI_TEST_MYSQL_ROOT_PASSWORD}"
else
  TEST_MYSQL_ROOT_PASSWORD="${Q4F_TEST_MYSQL_ROOT_PASSWORD:-${TEST_MYSQL_ROOT_PASSWORD}}"
fi
CONFIG_DB_NAME="${DB_NAME:-stocks_db}"

validate_identifier "--db-name" "${TEST_DB}"
if [[ "${TEST_DB,,}" != *test* ]]; then
  echo "[ERROR] test database name must contain 'test': ${TEST_DB}" >&2
  exit 1
fi
if [[ "${TEST_DB}" == "${CONFIG_DB_NAME}" ]]; then
  echo "[ERROR] test database must not equal configured DB_NAME (${CONFIG_DB_NAME})" >&2
  exit 1
fi
if [[ -z "${TEST_MYSQL_ROOT_PASSWORD}" ]]; then
  echo "[ERROR] test MySQL root password is empty" >&2
  exit 1
fi

require_cmd docker

export Q4F_TEST_DB_NAME="${TEST_DB}"
export Q4F_TEST_MYSQL_ROOT_PASSWORD="${TEST_MYSQL_ROOT_PASSWORD}"

run docker compose --profile test up -d db_test
wait_for_db

if [[ "${BUILD_IMAGE}" == "1" ]]; then
  run docker compose build app
fi

run docker compose --profile test run -T --rm --no-deps \
  -e Q4F_TEST_DB_HOST=db_test \
  -e Q4F_TEST_DB_USER=root \
  -e Q4F_TEST_DB_PASSWORD="${TEST_MYSQL_ROOT_PASSWORD}" \
  -e Q4F_TEST_DB_NAME="${TEST_DB}" \
  -e DB_NAME="${CONFIG_DB_NAME}" \
  app python -m pytest tests -m integration

echo "[INFO] db_integration_tests=ok db=${TEST_DB}"
