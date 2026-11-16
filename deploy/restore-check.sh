#!/bin/sh
# Restore only to a newly created disposable database, never into the live database.
set -eu
deploy_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -ne 2 ] || [ ! -r "$1" ]; then
    echo 'Usage: sh deploy/restore-check.sh backup.dump teleiosis_restore_test_ID' >&2
    exit 2
fi
archive=$1
restore_db=$2
case "$restore_db" in
    teleiosis_restore_test_*) ;;
    *) echo 'Target must start with teleiosis_restore_test_.' >&2; exit 2 ;;
esac
case "$restore_db" in
    *[!a-z0-9_]*)
        echo 'Target must use a-z, 0-9, _, and be shorter than 64 characters.' >&2; exit 2 ;;
esac
if [ "${#restore_db}" -ge 64 ]; then
    echo 'Target must be shorter than 64 characters.' >&2
    exit 2
fi
sh "$deploy_dir/compose.sh" exec -T db sh -ec '
    test "$1" != "$POSTGRES_DB"
    export PGPASSWORD="$POSTGRES_PASSWORD"
    # Without --if-not-exists: fail rather than restore into an existing database.
    createdb --host=127.0.0.1 --username="$POSTGRES_USER" --template=template0 "$1"
' restore "$restore_db"
sh "$deploy_dir/compose.sh" exec -T db sh -ec '
    export PGPASSWORD="$POSTGRES_PASSWORD"
    exec pg_restore --host=127.0.0.1 --username="$POSTGRES_USER" --dbname="$1" \
        --single-transaction --exit-on-error --no-owner --no-acl
' restore "$restore_db" < "$archive"
sh "$deploy_dir/compose.sh" exec -T db sh -ec '
    export PGPASSWORD="$POSTGRES_PASSWORD"
    exec psql --host=127.0.0.1 --username="$POSTGRES_USER" --dbname="$1" --no-psqlrc \
        --set=ON_ERROR_STOP=1 --tuples-only \
        --command="SELECT version_num FROM alembic_version; SELECT count(*) FROM users; SELECT count(*) FROM contents;"
' restore "$restore_db"
echo 'Restore drill completed. Disposable database retained for inspection; see runbook.'
