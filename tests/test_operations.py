import sys
import sqlite3
import tarfile
from pathlib import Path
from app import create_app
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from backup import backup
from verify_restore import verify
from package_release import package


def test_health_does_not_expose_data_and_reports_failure(tmp_path):
    app=create_app(tmp_path/'db',test_password='operations-test-password')
    c=app.test_client()
    assert c.get('/healthz').json=={'status':'ok'}
    with sqlite3.connect(app.config['DB_PATH']) as db:db.execute('DROP TABLE notes')
    r=c.get('/healthz')
    assert r.status_code==503 and r.json=={'status':'unavailable'}


def test_recovery_rehearsal_preserves_backup_and_live_sessions(tmp_path):
    app=create_app(tmp_path/'db',test_password='operations-test-password');c=app.test_client()
    r=c.post('/api/login',json={'password':'operations-test-password'})
    c.post('/api/notes',headers={'X-CSRF-Token':r.json['csrf']},json={'body':'복원 확인\n- [ ] 실제 사용자 데이터 아님'})
    target=tmp_path/'backup.sqlite3';backup(app.config['DB_PATH'],target);before=target.read_bytes()
    assert verify(target)=={'notes':1,'attachments':0}
    assert target.read_bytes()==before
    assert c.get('/api/session').status_code==200


def test_source_release_excludes_private_runtime_data(tmp_path):
    output=tmp_path/'release.tar.gz';count=package(output)
    with tarfile.open(output) as archive:
        names=archive.getnames()
        assert len(names)==count
        assert {'hanjul/Dockerfile','hanjul/compose.yaml','hanjul/compose.https.yaml',
                'hanjul/compose.nas.yaml','hanjul/deploy/server/Caddyfile',
                'hanjul/deploy/compose.restore.yaml','hanjul/LICENSE',
                'hanjul/docs/WHY-HANJUL.md','hanjul/scripts/backup-compose.sh',
                'hanjul/deploy/synology/env.example','hanjul/static/editor.js'}<=set(names)
        for name in names:
            parts=Path(name).parts
            assert not {'.data','data','backups','passkey-lab','.env','.git','migration-data'}.intersection(parts)
            assert not name.endswith(('.sqlite3','.sqlite3-wal','.sqlite3-shm'))
    assert output.with_suffix('.gz.sha256').is_file()
