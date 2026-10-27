"""Rehearse recovery in a disposable directory without changing the source or live DB."""
import argparse
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from restore import restore

TABLES=('folders','notes','attachments','settings','tokens','passkeys')

def fingerprint(path,table):
    digest=hashlib.sha256();count=0
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        if not db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone():return None
        for row in db.execute('SELECT * FROM '+table+' ORDER BY 1'):
            for value in row:
                data=b'bytes:'+value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
                digest.update(len(data).to_bytes(8,'big'));digest.update(data)
            count+=1
    return count,digest.digest()

def verify(source,temp_dir=None):
    source=Path(source).resolve()
    with tempfile.TemporaryDirectory(prefix='hanjul-restore-check-',dir=temp_dir) as temp:
        target=Path(temp)/'restored'
        counts=restore(source,target)
        for table in TABLES:
            if fingerprint(source,table)!=fingerprint(target/'memo.sqlite3',table):raise ValueError('복원 데이터 불일치: '+table)
        with sqlite3.connect(target/'memo.sqlite3') as db:
            for table in ('sessions','imports','auth_challenges'):
                if db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():
                    if db.execute('SELECT count(*) FROM '+table).fetchone()[0]:raise ValueError('임시 인증/가져오기 데이터가 남았습니다: '+table)
        return counts

if __name__=='__main__':
    p=argparse.ArgumentParser(description='임시 폴더에 복원 후 메모·첨부·인증 설정의 내용 일치를 검증합니다. 원본과 실사용 DB는 변경하지 않습니다.')
    p.add_argument('backup');p.add_argument('--temp-dir',help='복원 임시 파일을 둘 충분한 여유 공간의 폴더');a=p.parse_args();result=verify(a.backup,a.temp_dir)
    print(f'복원 검증 통과 · 메모 {result["notes"]}개 · 첨부 {result["attachments"]}개 · 원본 일치 · 임시 세션 정리 확인')
