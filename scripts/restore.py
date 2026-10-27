"""Restore to an EMPTY data directory; never overwrite an existing installation."""
import argparse
import os
import sqlite3
from pathlib import Path
from backup import backup

def restore(source, destination):
    target=Path(destination).resolve()
    if target.exists() and any(target.iterdir()): raise ValueError('복원 대상은 비어 있는 새 디렉터리여야 합니다.')
    target.mkdir(parents=True,exist_ok=True,mode=0o700)
    counts=backup(source,target/'memo.sqlite3')
    with sqlite3.connect(target/'memo.sqlite3') as db:
        db.execute('DELETE FROM sessions')
        db.execute('DELETE FROM imports')
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='auth_challenges'").fetchone():
            db.execute('DELETE FROM auth_challenges')
    return counts

if __name__=='__main__':
    p=argparse.ArgumentParser(description='새 빈 데이터 폴더에 백업을 복원합니다. 기존 비밀번호와 API 토큰이 유지되고 웹 세션은 만료됩니다.')
    p.add_argument('backup');p.add_argument('--to',required=True)
    a=p.parse_args();r=restore(a.backup,a.to)
    print(f'복원 완료: {Path(a.to).resolve()} · 메모 {r["notes"]}개 · 첨부 {r["attachments"]}개')
