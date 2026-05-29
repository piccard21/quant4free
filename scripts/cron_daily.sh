#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

echo "daily_run=started at=$(date -Is)"
trap 'echo "daily_run=failed at=$(date -Is) line=${LINENO}" >&2' ERR
docker compose run --rm app python -m cli.daily_run "$@"
echo "daily_run=ok at=$(date -Is)"
