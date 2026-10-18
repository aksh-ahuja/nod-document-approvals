#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export NOD_DEBUG=true NOD_EMAIL_PROVIDER=console NOD_ENABLE_DEMO=true
mkdir -p .local
nod_e2e_run_dir="$(mktemp -d "$PWD/.local/nod-e2e-XXXXXX")"
export NOD_DB_ENGINE=sqlite NOD_SQLITE_PATH="$nod_e2e_run_dir/db.sqlite3"
export NOD_STORAGE_PROVIDER=local NOD_UPLOAD_ROOT="$nod_e2e_run_dir/uploads"
export NOD_CSRF_TRUSTED_ORIGINS="http://127.0.0.1:${NOD_E2E_WEB_PORT:-5173}"
.venv/bin/python backend/manage.py migrate --noinput
.venv/bin/python backend/manage.py seed_demo
.venv/bin/python backend/manage.py process_uploads &
worker_pid=$!
.venv/bin/python backend/manage.py runserver "127.0.0.1:${NOD_E2E_API_PORT:-8000}" --noreload &
api_pid=$!
trap 'kill "$worker_pid" "$api_pid" 2>/dev/null || true' EXIT INT TERM
wait "$api_pid"
