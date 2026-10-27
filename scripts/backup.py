"""Consistent online SQLite backup; attachments are transactionally stored BLOBs."""
import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

def backup(source, destination):
    source=Path(source).resolve(); destination=Path(destination).resolve()
    if not source.is_file(): raise ValueError('원본 데이터베이스가 없습니다.')
    if destination.exists(): raise ValueError('기존 백업을 덮어쓰지 않습니다.')
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    try:
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('백업 무결성 검사 실패')
            counts={table:dst.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('notes','attachments')}
        return counts
    except Exception:
        destination.unlink(missing_ok=True)
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='메모·첨부파일·인증 설정을 함께 일관되게 백업합니다.')
    parser.add_argument('--data-dir',default=os.environ.get('MEMO_DATA_DIR','.data'))
    parser.add_argument('--output',default='backups/hanjul-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3')
    args=parser.parse_args();result=backup(Path(args.data_dir)/'memo.sqlite3',args.output)
    print(f'백업 완료: {Path(args.output).resolve()} · 메모 {result["notes"]}개 · 첨부 {result["attachments"]}개')
