"""Explicit local maintenance: stop the server and back up the DB first."""
import getpass
import os
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

if __name__=='__main__':
    folder=Path(os.environ.get('MEMO_DATA_DIR','.data')).resolve()
    if not (folder/'memo.sqlite3').is_file(): raise SystemExit('원본 DB가 없습니다.')
    password=getpass.getpass('새 비밀번호 (12자 이상): ')
    if not 12<=len(password)<=1024:raise SystemExit('비밀번호는 12~1024자여야 합니다.')
    if password!=getpass.getpass('새 비밀번호 확인: '):raise SystemExit('비밀번호가 다릅니다.')
    with sqlite3.connect(folder/'memo.sqlite3') as db:
        db.execute("UPDATE settings SET value=? WHERE key='password'",(generate_password_hash(password),))
        db.execute('DELETE FROM sessions')
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='auth_challenges'").fetchone():
            db.execute('DELETE FROM auth_challenges')
    (folder/'initial-password.txt').unlink(missing_ok=True)
    print('비밀번호가 변경되고 모든 웹 세션이 만료되었습니다. API 토큰은 기존대로 유지됩니다.')
