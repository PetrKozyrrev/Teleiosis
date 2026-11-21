#!/bin/sh
set -eu
umask 077
deploy_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export TELEIOSIS_STAGING=1

exec 9>/run/lock/teleiosis-staging-pdf.lock
flock -x -w 120 9

case "${1:-}" in
  cleanup)
    exec sh "$deploy_dir/compose.sh" exec -T api python -m app.pdf_cleanup
    ;;
  backup)
    directory=/var/backups/teleiosis-pdf-daily
    install -d -m 0700 "$directory"
    # Bound disk consumption while preserving existing archives for review.
    used_kib=$(du -sk "$directory" | cut -f1)
    available_kib=$(df -Pk "$directory" | awk 'NR==2 {print $4}')
    test "$available_kib" -gt 5242880
    stored_bytes=$(sh "$deploy_dir/compose.sh" exec -T api python -c '
from pathlib import Path
print(sum(path.stat().st_size for path in Path("/var/lib/teleiosis/pdf").glob("*.pdf")))
')
    test "$((used_kib + stored_bytes / 1024))" -lt 8388608
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    snapshot=$(mktemp -d "$directory/.$stamp.XXXXXX")
    sh "$deploy_dir/backup.sh" "$snapshot/database.dump"
    # Cleanup shares the lock. Final objects are immutable for their database ID.
    sh "$deploy_dir/compose.sh" exec -T api python -c '
from pathlib import Path
import re
import sys
import tarfile
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as archive:
    for path in sorted(Path("/var/lib/teleiosis/pdf").glob("*.pdf")):
        if re.fullmatch("[0-9a-f]{32}[.]pdf", path.name):
            archive.add(path, arcname=path.name, recursive=False)
' > "$snapshot/files.tar.gz"
    tar -tzf "$snapshot/files.tar.gz" >/dev/null
    (cd "$snapshot" && sha256sum database.dump files.tar.gz > SHA256SUMS)
    test ! -e "$directory/$stamp"
    mv -T "$snapshot" "$directory/$stamp"
    printf 'PDF snapshot %s\n' "$directory/$stamp"
    ;;
  *)
    echo 'Usage: staging-pdf-maintenance.sh cleanup|backup' >&2
    exit 2
    ;;
esac
