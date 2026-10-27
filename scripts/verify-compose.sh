#!/bin/sh
# CI only: a unique Compose project isolates disposable test volumes.
set -eu
project="hanjul-ci-$$"
dc() { docker compose -p "$project" "$@"; }
cleanup() {
    HANJUL_DOMAIN=localhost docker compose -p "$project" -f compose.yaml -f compose.https.yaml -f deploy/compose.restore.yaml down -v --remove-orphans
}
trap cleanup EXIT
dc up -d --build --wait
dc exec -T memo python - <<'PY'
import json
import urllib.request
import urllib.error
from pathlib import Path
password=Path('/data/initial-password.txt').read_text().strip()
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
def call(path, data=None, csrf=None):
    headers={'Content-Type':'application/json'}
    if csrf: headers['X-CSRF-Token']=csrf
    req=urllib.request.Request('http://localhost:8787'+path, data=None if data is None else json.dumps(data).encode(), headers=headers)
    with opener.open(req) as response: return json.load(response)
assert call('/healthz')=={'status':'ok'}
try:
    call('/api/notes')
except urllib.error.HTTPError as exc:
    assert exc.code==401
else:
    raise AssertionError('Notes must require authentication')
session=call('/api/login',{'password':password})
note=call('/api/notes',{'body':'Container persistence verification'},session['csrf'])
Path('/backups/ci-note-id.txt').write_text(note['id'])
PY
dc restart memo
dc up -d --wait
sh scripts/backup-compose.sh -p "$project"
dc exec -T memo sh -c 'cp /backups/hanjul-*.sqlite3 /backups/restore-input.sqlite3'
dc stop memo
dc -f compose.yaml -f deploy/compose.restore.yaml run --rm --no-deps memo python scripts/restore.py /backups/restore-input.sqlite3 --to /data
dc -f compose.yaml -f deploy/compose.restore.yaml up -d --wait
dc -f compose.yaml -f deploy/compose.restore.yaml exec -T memo python - <<'PY'
import sqlite3
from pathlib import Path
with sqlite3.connect('/data/memo.sqlite3') as db:
    assert db.execute('SELECT body FROM notes WHERE id=?',(Path('/backups/ci-note-id.txt').read_text(),)).fetchone()[0]=='Container persistence verification'
    assert db.execute('SELECT count(*) FROM sessions').fetchone()[0]==0
assert not Path('/data/initial-password.txt').exists()
PY
# Exercise the HTTPS override with a localhost certificate, without public DNS.
HANJUL_DOMAIN=localhost dc -f compose.yaml -f compose.https.yaml -f deploy/compose.restore.yaml up -d --wait
curl --fail --insecure --retry 15 --retry-all-errors --retry-delay 2 https://localhost/healthz
HANJUL_DOMAIN=localhost dc -f compose.yaml -f compose.https.yaml -f deploy/compose.restore.yaml exec -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
HANJUL_DOMAIN=localhost dc -f compose.yaml -f compose.https.yaml -f deploy/compose.restore.yaml down
