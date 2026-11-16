#!/bin/sh
# Official postgres image sources this file only for an empty data directory.
set -eu
psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --no-psqlrc \
    --set=ON_ERROR_STOP=1 --set=app_user="$APP_DB_USER" \
    --set=app_password="$APP_DB_PASSWORD" --set=app_db="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER DATABASE :"app_db" OWNER TO :"app_user";
SQL
