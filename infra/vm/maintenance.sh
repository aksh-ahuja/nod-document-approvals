#!/usr/bin/env bash
set -euo pipefail
cd /opt/nod/current
set -a
source /opt/nod/shared/release.env
set +a
docker compose -f infra/vm/compose.yaml exec -T api python manage.py clearsessions
docker compose -f infra/vm/compose.yaml exec -T api python manage.py cleanup_auth
