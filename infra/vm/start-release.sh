#!/usr/bin/env bash
set -euo pipefail
release_dir="$(cd "$(dirname "$0")/../.." && pwd)"
export NOD_RELEASE="$(basename "$release_dir")"
cd "$release_dir"
compose=(docker compose -f infra/vm/compose.yaml)
"${compose[@]}" config --quiet
"${compose[@]}" up -d --wait db

# The test runner needs CREATE DATABASE; the production app role does not.
set -a
source /opt/nod/shared/database.env
set +a
NOD_DB_PASSWORD="$POSTGRES_PASSWORD" "${compose[@]}" run --rm --no-deps \
  -e NOD_DB_USER=nod_admin -e NOD_DB_PASSWORD \
  -e NOD_DEBUG=true -e NOD_STORAGE_PROVIDER=local -e NOD_EMAIL_PROVIDER=console \
  -e NOD_ENABLE_DEMO=true -e NOD_TEST_DOCX_PREVIEW=true -v "$release_dir/scripts:/scripts:ro" \
  api python manage.py test tests --verbosity 1
unset POSTGRES_PASSWORD NOD_APP_DB_PASSWORD

"${compose[@]}" run --rm --no-deps api python manage.py migrate --noinput
"${compose[@]}" up -d --wait --wait-timeout 180
umask 077
printf 'NOD_RELEASE=%s\n' "$NOD_RELEASE" > /opt/nod/shared/release.env
ln -sfn "$release_dir" /opt/nod/current
"${compose[@]}" ps
