#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /opt/nod/current
set -a
source /opt/nod/shared/release.env
set +a
mkdir -p /opt/nod/backups
backup="/opt/nod/backups/nod-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose -f infra/vm/compose.yaml exec -T db pg_dump -U nod_admin -d nod | gzip > "$backup.partial"
mv "$backup.partial" "$backup"
gzip -t "$backup"
docker compose -f infra/vm/compose.yaml exec -T api python -c '
import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nod_central_service.settings")
django.setup()
from azure.storage.blob import ContentSettings
from utils.storage.factory import get_document_storage
blob = get_document_storage().client.get_blob_client("backups/" + sys.argv[1])
blob.upload_blob(sys.stdin.buffer, overwrite=False, content_settings=ContentSettings(content_type="application/gzip"))
' "$(basename "$backup")" < "$backup"
find /opt/nod/backups -maxdepth 1 -type f -name 'nod-*.sql.gz' -mtime +7 -delete
echo 'Nod database backup completed.'
