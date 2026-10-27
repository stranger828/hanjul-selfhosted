#!/bin/sh
# Run from the repository root. Pass any Compose -f / -p options as arguments.
set -eu
umask 077
name="hanjul-$(date -u +%Y%m%dT%H%M%SZ)-$$.sqlite3"
docker compose "$@" exec -T memo python scripts/backup.py --output "/backups/$name"
docker compose "$@" exec -T memo python scripts/verify_restore.py "/backups/$name"
mkdir -p backups
docker compose "$@" cp "memo:/backups/$name" "backups/$name"
chmod 600 "backups/$name"
printf 'Backup verified and copied to backups/%s\n' "$name"
