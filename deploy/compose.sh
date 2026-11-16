#!/bin/sh
set -eu
deploy_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TELEIOSIS_ENV_FILE=${TELEIOSIS_ENV_FILE:-"$deploy_dir/.env"}
export TELEIOSIS_ENV_FILE
if [ ! -f "$TELEIOSIS_ENV_FILE" ]; then
    echo 'Missing deploy env file. See docs/deployment.md.' >&2
    exit 1
fi
exec docker compose --env-file "$TELEIOSIS_ENV_FILE" -f "$deploy_dir/compose.yml" "$@"
