#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export NOD_DEBUG=true NOD_DB_ENGINE="${NOD_DB_ENGINE:-sqlite}" NOD_EMAIL_PROVIDER=console
.venv/bin/python backend/manage.py test tests --verbosity 1
npm --prefix frontend test
npm --prefix frontend run build
