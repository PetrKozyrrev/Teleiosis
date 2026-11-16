#!/bin/sh
# One archive, created without overwriting an existing backup; no automatic deletion.
set -eu
umask 077
deploy_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -ne 1 ]; then
    echo 'Usage: sh deploy/backup.sh /secure/path/new-backup.dump' >&2
    exit 2
fi
archive=$1
partial="${archive}.partial"
# noclobber also refuses pre-existing symlinks. Leave failed partials for diagnosis.
(set -C; : > "$partial") || exit 1
sh "$deploy_dir/compose.sh" exec -T db sh -ec \
    'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump --host=127.0.0.1 --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner --no-acl' > "$partial"
# Validate archive structure, then publish atomically without replacing an old dump.
sh "$deploy_dir/compose.sh" exec -T db pg_restore --list < "$partial" > /dev/null
ln "$partial" "$archive"
unlink "$partial"
echo 'Backup created and archive index checked. A restore drill is still required.'
