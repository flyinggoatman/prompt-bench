#!/usr/bin/env bash
#
# Back up Prompt Bench's live data: the members database, the codes database
# and the uploaded packs. Safe while the server runs: the members database is
# copied with SQLite's online backup, never with cp.
#
#   deploy/backup.sh [site-dir] [backup-dir]
#
# Defaults: the folder this script is run from, and /root/backups/prompt-bench-data.
# Keeps the newest 14 backups. Run it from cron, for example nightly:
#   15 3 * * * /mnt/html-site/deploy/backup.sh /mnt/html-site >> /root/backups/prompt-bench-data/backup.log 2>&1
#
# Restore: stop the container, copy members-<stamp>.db over data/members.db
# (and delete data/members.db-wal and data/members.db-shm), untar the uploads
# archive over uploads/, start the container.
set -euo pipefail
{
site="${1:-$(pwd)}"
dest="${2:-/root/backups/prompt-bench-data}"
stamp="$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "$dest"
chmod 700 "$dest"

if [ -f "$site/data/members.db" ]; then
  python3 - "$site/data/members.db" "$dest/members-$stamp.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True)
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close(); src.close()
PY
  chmod 600 "$dest/members-$stamp.db"
  echo "backup: members database -> members-$stamp.db"
fi

if [ -d "$site/uploads" ]; then
  tar -czf "$dest/uploads-$stamp.tar.gz" -C "$site" uploads
  chmod 600 "$dest/uploads-$stamp.tar.gz"
  echo "backup: uploads -> uploads-$stamp.tar.gz"
fi

# Keep the newest 14 of each.
for kind in members uploads; do
  ls -1t "$dest"/"$kind"-* 2>/dev/null | tail -n +15 | while IFS= read -r old; do rm -f -- "$old"; done
done
exit 0
}
