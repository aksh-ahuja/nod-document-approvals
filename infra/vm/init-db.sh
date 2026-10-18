#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 --set=app_password="$NOD_APP_DB_PASSWORD" <<'SQL'
CREATE ROLE nod LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER DATABASE nod OWNER TO nod;
GRANT ALL ON SCHEMA public TO nod;
SQL
