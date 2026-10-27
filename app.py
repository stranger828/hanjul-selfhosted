"""한줄: single-owner, portable notes. SQLite is the authoritative store."""
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import tempfile
import time
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, g, send_file, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
from auth import install_auth, migrate_auth

ROOT = Path(__file__).resolve().parent
MAX_BODY = 2_000_000
MAX_ATTACHMENT = 20 * 1024 * 1024
MAX_IMPORT = 256 * 1024 * 1024
IMAGE_MARKDOWN = re.compile(r'!\[([^\]]*)\]\(([^\s)]+)(?: "[^"\r\n]*")?\)')
EDITOR_MARKUP = re.compile(r'</?(?:strong|s|table|tbody|tr|td|th)>|<(?:td|th)(?: rowspan="[1-9]\d{0,2}")?(?: colspan="[1-9]\d?")?>|<table(?: data-width="(?:[2-9]\d|100)")?(?: data-height="[1-9]\d{1,4}")?>|<span data-size="(?:12|14|17|20|24|32|40)">|</span>|<br>')

def visible_body(body):
    return EDITOR_MARKUP.sub(lambda m: '\n' if m[0] in ('</tr>', '<br>') else ' ' if m[0] in ('</td>', '</th>') else '', body)

def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')

def uid(value):
    try:
        if str(uuid.UUID(value)) != value: raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise ValueError('올바른 UUID가 필요합니다.')

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def timestamp(value):
    if not isinstance(value, str): raise ValueError('날짜 형식이 올바르지 않습니다.')
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not d.tzinfo: raise ValueError('날짜에는 시간대가 필요합니다.')
    return d.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')

def folder_name(value):
    if not isinstance(value, str): raise ValueError('폴더 이름을 입력해 주세요.')
    value = unicodedata.normalize('NFC', value).strip()
    if not 1 <= len(value) <= 80: raise ValueError('폴더 이름은 1~80자로 입력해 주세요.')
    return value

def validate_note(data):
    out = {}
    for key in ('title', 'body'):
        val = data.get(key, '')
        if not isinstance(val, str) or len(val) > (500 if key == 'title' else MAX_BODY):
            raise ValueError('제목은 500자, 본문은 200만 자까지 저장할 수 있습니다.')
        out[key] = unicodedata.normalize('NFC', val)
    tags = data.get('tags', [])
    if not isinstance(tags, list) or len(tags) > 50 or any(not isinstance(t,str) or not t.strip() or len(t)>80 for t in tags):
        raise ValueError('태그는 80자 이하, 최대 50개입니다.')
    out['folder_id'] = uid(data['folder_id']) if data.get('folder_id') is not None else None
    out['tags'] = list(dict.fromkeys(t.strip() for t in tags))
    for key in ('starred','archived','deleted'):
        val = data.get(key, False)
        if not isinstance(val, bool): raise ValueError('상태 값은 true 또는 false여야 합니다.')
        out[key] = val
    return out

def has_note_content(note):
    body=re.sub(r'^\s*[-*](?:\s+\[[ xX]\])?\s*$', '', visible_body(note['body']), flags=re.MULTILINE)
    if re.search(r'<table(?: |>)',note['body']): return True
    return bool(re.sub(r'[\s\u200b\ufeff]', '', note['title'] + body))

def create_app(data_dir=None, test_password=None):
    app = Flask(__name__, static_folder=None)
    folder = Path(data_dir or os.environ.get('MEMO_DATA_DIR', ROOT / '.data')).resolve()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    dbpath = folder / 'memo.sqlite3'
    app.config.update(MAX_CONTENT_LENGTH=MAX_IMPORT, DATA_DIR=str(folder), DB_PATH=str(dbpath), TESTING=False)
    def connect():
        db = sqlite3.connect(dbpath, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db
    with connect() as db:
        db.executescript((ROOT / 'schema.sql').read_text())
        if not db.execute("SELECT 1 FROM settings WHERE key='password'").fetchone():
            password = test_password or secrets.token_urlsafe(18)
            db.execute('INSERT INTO settings VALUES (?,?)', ('password', generate_password_hash(password)))
            if not test_password:
                fd = os.open(folder / 'initial-password.txt', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
                with os.fdopen(fd,'w') as f: f.write(password + '\n')
        if not db.execute("SELECT 1 FROM settings WHERE key='instance'").fetchone():
            db.execute('INSERT INTO settings VALUES (?,?)', ('instance', str(uuid.uuid4())))
        if 'folder_id' not in {r[1] for r in db.execute('PRAGMA table_info(notes)')}:
            db.execute('ALTER TABLE notes ADD COLUMN folder_id TEXT REFERENCES folders(id)')
        db.execute('CREATE INDEX IF NOT EXISTS notes_folder ON notes(folder_id, deleted, updated_at DESC)')
        migrate_auth(db)
    os.chmod(dbpath, 0o600)
    def getdb():
        if 'db' not in g: g.db = connect()
        return g.db
    @app.teardown_appcontext
    def close_db(exc):
        if 'db' in g: g.db.close()
    def error(message, status=400, **kw):
        return jsonify(error=message, **kw), status
    install_auth(app, getdb, folder)
    @app.after_request
    def security(res):
        res.headers['Cache-Control'] = 'no-store'
        res.headers['X-Content-Type-Options'] = 'nosniff'
        res.headers['X-Frame-Options'] = 'DENY'
        res.headers['Permissions-Policy'] = 'publickey-credentials-create=(self), publickey-credentials-get=(self)'
        res.headers['Referrer-Policy'] = 'no-referrer'
        res.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        return res
    @app.errorhandler(Exception)
    def handle_error(exc):
        if isinstance(exc, HTTPException): return error(exc.description,exc.code)
        if isinstance(exc,(ValueError, KeyError, TypeError, zipfile.BadZipFile)): return error(str(exc) or '잘못된 요청입니다.')
        app.logger.exception('Request failed')
        return error('서버 저장 또는 조회에 실패했습니다. 로컬 초안을 보존하고 다시 시도해 주세요.',503)
    @app.get('/healthz')
    def health():
        try:
            getdb().execute('SELECT id FROM notes LIMIT 1').fetchone()
            return jsonify(status='ok')
        except sqlite3.Error:
            return jsonify(status='unavailable'),503
    @app.get('/')
    def index(): return send_from_directory(ROOT / 'static','index.html')
    @app.get('/static/<path:name>')
    def static(name): return send_from_directory(ROOT / 'static',name)
    def note_row(note_id):
        r=getdb().execute('SELECT * FROM notes WHERE id=?',(note_id,)).fetchone()
        if not r: from flask import abort; abort(404,description='메모를 찾을 수 없습니다.')
        return r
    def serialize(r, full=True):
        d=dict(r);d['tags']=json.loads(d['tags'])
        for k in ('starred','archived','deleted'): d[k]=bool(d[k])
        lines=(re.sub(r'^\s*(?:#+(?:\s|$)|[-*]\s(?:\[[ xX]\]\s)?)','',line).strip() for line in visible_body(IMAGE_MARKDOWN.sub('',d['body'])).splitlines())
        d['display_title']=d['title'].strip() or next((line[:100] for line in lines if line),'사진 메모' if IMAGE_MARKDOWN.search(d['body']) else '표 메모' if re.search(r'<table(?: |>)',d['body']) else '빈 메모')
        if full:
            d['attachments']=[dict(a) for a in getdb().execute('SELECT id,note_id,name,mime,length(data) AS size,created_at FROM attachments WHERE note_id=?',(d['id'],))]
        return d
    def check_folder(db, folder_id):
        if folder_id is not None and not db.execute('SELECT 1 FROM folders WHERE id=?', (folder_id,)).fetchone():
            raise ValueError('폴더를 찾을 수 없습니다. 목록을 새로고침해 주세요.')
    def insert_note(db,d):
        check_folder(db, d['folder_id'])
        db.execute('INSERT INTO notes(id,title,body,created_at,updated_at,tags,starred,archived,deleted,version,folder_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   (d['id'],d['title'],d['body'],d['created_at'],d['updated_at'],json.dumps(d['tags'],ensure_ascii=False),d['starred'],d['archived'],d['deleted'],d['version'],d['folder_id']))
    @app.get('/api/folders')
    def list_folders():
        db=getdb()
        rows=db.execute('SELECT f.id,f.name,f.version,count(n.id) AS count FROM folders f LEFT JOIN notes n ON n.folder_id=f.id AND n.deleted=0 GROUP BY f.id ORDER BY f.name COLLATE NOCASE,f.id').fetchall()
        unfiled=db.execute('SELECT count(*) FROM notes WHERE folder_id IS NULL AND deleted=0').fetchone()[0]
        return jsonify(items=[dict(r) for r in rows],unfiled=unfiled)
    @app.post('/api/folders')
    def create_folder():
        name=folder_name(request.get_json().get('name')); fid=str(uuid.uuid4())
        with getdb() as db: db.execute('INSERT INTO folders(id,name) VALUES (?,?)',(fid,name))
        return jsonify(id=fid,name=name,version=1,count=0),201
    @app.patch('/api/folders/<fid>')
    def rename_folder(fid):
        raw=request.get_json();name=folder_name(raw.get('name'))
        if type(raw.get('version')) is not int: return error('수정 버전(version)이 필요합니다.',428)
        db=getdb()
        with db:
            result=db.execute('UPDATE folders SET name=?,version=version+1 WHERE id=? AND version=?',(name,uid(fid),raw['version']))
            current=db.execute('SELECT id,name,version FROM folders WHERE id=?',(fid,)).fetchone()
            if not current: return error('폴더를 찾을 수 없습니다.',404)
            if not result.rowcount: return error('다른 기기에서 폴더 이름을 수정했습니다. 최신 이름을 확인해 주세요.',409,current=dict(current))
        return jsonify(dict(current))
    @app.get('/api/notes')
    def list_notes():
        db=getdb(); q=unicodedata.normalize('NFC',request.args.get('q','')).strip()
        if len(q)>300: raise ValueError('검색어는 300자까지 입력해 주세요.')
        terms=list(dict.fromkeys(q.lower().split()))
        if len(terms)>12: raise ValueError('검색어는 12개 이하로 입력해 주세요.')
        state=request.args.get('state','active')
        clauses=['n.deleted=?'];params=[1 if state=='trash' else 0]
        if state=='active': pass
        elif state=='archive': clauses.append('n.archived=1')
        elif state=='starred': clauses.append('n.starred=1')
        elif state not in ('trash','all'): raise ValueError('목록 상태가 올바르지 않습니다.')
        if 'folder_id' in request.args:
            folder_id=request.args['folder_id']
            if folder_id=='none': clauses.append('n.folder_id IS NULL')
            else:
                clauses.append('n.folder_id=?');params.append(uid(folder_id))
        longs=[t for t in terms if len(t)>=3]
        if longs:
            clauses.append('n.rowid IN (SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?)')
            params.append(' AND '.join('"'+t.replace('"','""')+'"' for t in longs))
        for term in terms:
            clauses.append("(instr(lower(n.title),?)>0 OR instr(lower(n.body),?)>0)");params.extend([term,term])
        if request.args.get('tag'):
            clauses.append('EXISTS (SELECT 1 FROM json_each(n.tags) WHERE value=?)');params.append(request.args['tag'])
        for key,op in [('from','>='),('to','<')]:
            if request.args.get(key): clauses.append('n.updated_at '+op+' ?');params.append(timestamp(request.args[key]))
        limit=max(1,min(int(request.args.get('limit',40)),100)); offset=max(0,min(int(request.args.get('offset',0)),1_000_000))
        order='ASC' if request.args.get('sort')=='oldest' else 'DESC'
        where=' AND '.join(clauses)
        count=db.execute('SELECT count(*) FROM notes n WHERE '+where,params).fetchone()[0]
        rows=db.execute('SELECT n.* FROM notes n WHERE '+where+f' ORDER BY n.updated_at {order},n.id {order} LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
        # Fetch only attachment IDs for this page, never image BLOBs or one query per note.
        images={}
        if rows:
            placeholders=','.join('?' for _ in rows)
            for a in db.execute(f"SELECT id,note_id FROM attachments WHERE note_id IN ({placeholders}) AND mime IN ('image/png','image/jpeg','image/gif','image/webp')",[r['id'] for r in rows]):
                images.setdefault(a['note_id'],set()).add('/api/attachments/'+a['id'])
        items=[]
        for r in rows:
            d=serialize(r,False);original=d.pop('body')
            d['thumbnail_url']=next((m[2] for m in IMAGE_MARKDOWN.finditer(original) if m[2] in images.get(d['id'],set())),None)
            body=visible_body(IMAGE_MARKDOWN.sub('',original)).strip();low=body.lower()
            positions=[low.find(t) for t in terms if low.find(t)>=0]
            start=max(0,min(positions)-55) if positions else 0
            d['snippet']=('…' if start else '')+body[start:start+240]+('…' if len(body)>start+240 else '')
            items.append(d)
        return jsonify(items=items,total=count,offset=offset,next_offset=offset+limit if offset+limit<count else None,terms=terms)
    @app.post('/api/notes')
    def create_note():
        raw=request.get_json();d=validate_note(raw);d.update(id=uid(raw['id']) if raw.get('id') else str(uuid.uuid4()),created_at=now(),updated_at=now(),version=1)
        if not has_note_content(d): return error('빈 메모는 저장하지 않습니다.')
        db=getdb()
        try:
            with db: insert_note(db,d)
        except sqlite3.IntegrityError:
            if db.execute('SELECT 1 FROM notes WHERE id=?',(d['id'],)).fetchone():
                return error('동일 ID의 메모가 이미 있습니다. 서버 내용을 확인해 주세요.',409,current=serialize(note_row(d['id'])))
            raise
        return jsonify(serialize(note_row(d['id']))),201
    @app.post('/api/notes/<note_id>/copy')
    def copy_note(note_id):
        d=validate_note(request.get_json());db=getdb();nid=str(uuid.uuid4());stamp=now()
        with db:
            db.execute('BEGIN IMMEDIATE')
            note_row(note_id)
            attachments=db.execute('SELECT * FROM attachments WHERE note_id=?',(note_id,)).fetchall()
            if not has_note_content(d) and not attachments: return error('빈 메모는 저장하지 않습니다.')
            clones=[]
            for a in attachments:
                aid=str(uuid.uuid4());d['body']=d['body'].replace('/api/attachments/'+a['id'],'/api/attachments/'+aid)
                clones.append((aid,nid,a['name'],a['mime'],a['data'],stamp))
            d.update(id=nid,created_at=stamp,updated_at=stamp,version=1)
            insert_note(db,d)
            db.executemany('INSERT INTO attachments VALUES (?,?,?,?,?,?)',clones)
        return jsonify(serialize(note_row(nid))),201
    @app.get('/api/notes/<note_id>')
    def get_note(note_id):
        row=note_row(note_id)
        if request.args.get('known_version')==str(row['version']):
            return jsonify(id=note_id,version=row['version'],unchanged=True)
        return jsonify(serialize(row))
    @app.patch('/api/notes/<note_id>')
    def update_note(note_id):
        raw=request.get_json();old=serialize(note_row(note_id))
        if type(raw.get('version')) is not int: return error('수정 버전(version)이 필요합니다.',428)
        d=validate_note({**old,**raw});db=getdb()
        if not has_note_content(d) and not old['attachments'] and (d['title'] != old['title'] or d['body'] != old['body']):
            return error('빈 메모는 저장하지 않습니다. 기존 내용은 유지됩니다.')
        with db:
            check_folder(db, d['folder_id'])
            result=db.execute('UPDATE notes SET title=?,body=?,tags=?,starred=?,archived=?,deleted=?,folder_id=?,updated_at=?,version=version+1 WHERE id=? AND version=?',
                (d['title'],d['body'],json.dumps(d['tags'],ensure_ascii=False),d['starred'],d['archived'],d['deleted'],d['folder_id'],now(),note_id,raw['version']))
        if not result.rowcount: return error('다른 탭이나 기기에서 수정했습니다. 내용을 확인해 주세요.',409,current=serialize(note_row(note_id)))
        return jsonify(serialize(note_row(note_id)))
    @app.delete('/api/notes/<note_id>')
    def trash_note(note_id):
        raw=request.get_json();version=raw.get('version')
        if type(version) is not int: return error('수정 버전(version)이 필요합니다.',428)
        db=getdb();note_row(note_id)
        with db: result=db.execute('UPDATE notes SET deleted=1,updated_at=?,version=version+1 WHERE id=? AND version=?',(now(),note_id,version))
        if not result.rowcount: return error('수정 충돌입니다.',409,current=serialize(note_row(note_id)))
        return jsonify(serialize(note_row(note_id)))
    @app.post('/api/notes/trash')
    def trash_notes():
        items=request.get_json().get('items')
        if not isinstance(items,list) or not 1 <= len(items) <= 1000:
            return error('삭제할 메모를 1~1,000개 선택해 주세요.')
        versions={}
        for item in items:
            nid=uid(item['id'])
            if type(item.get('version')) is not int or nid in versions:
                return error('메모 ID와 수정 버전을 확인해 주세요.')
            versions[nid]=item['version']
        db=getdb()
        with db:
            db.execute('BEGIN IMMEDIATE')
            for nid,version in versions.items():
                row=db.execute('SELECT version,deleted FROM notes WHERE id=?',(nid,)).fetchone()
                if not row or row['version']!=version or row['deleted']:
                    return error('선택한 메모가 다른 곳에서 변경되었습니다. 목록을 확인하고 다시 선택해 주세요.',409)
            stamp=now()
            db.executemany('UPDATE notes SET deleted=1,updated_at=?,version=version+1 WHERE id=?',[(stamp,nid) for nid in versions])
        return jsonify(deleted=len(versions))
    @app.post('/api/notes/<note_id>/attachments')
    def attach(note_id):
        f=request.files.get('file')
        if not f: raise ValueError('첨부파일이 필요합니다.')
        data=f.read(MAX_ATTACHMENT+1)
        if len(data)>MAX_ATTACHMENT: return error('첨부파일은 20MB까지 가능합니다.',413)
        version=int(request.form.get('version',-1)); aid=str(uuid.uuid4()); name=Path(f.filename.replace('\\','/')).name[:200] or 'attachment'
        mime='application/octet-stream'
        if data.startswith(b'\x89PNG\r\n\x1a\n'): mime='image/png'
        elif data.startswith(b'\xff\xd8\xff'): mime='image/jpeg'
        elif data[:6] in (b'GIF87a',b'GIF89a'): mime='image/gif'
        elif data[:4]==b'RIFF' and data[8:12]==b'WEBP': mime='image/webp'
        db=getdb()
        with db:
            db.execute('BEGIN IMMEDIATE')
            uid(note_id)
            old=db.execute('SELECT * FROM notes WHERE id=?',(note_id,)).fetchone()
            fresh=old is None and version==0 and 'note' in request.form
            if fresh:
                old=validate_note(json.loads(request.form['note']))
            elif old is None:
                return error('메모를 찾을 수 없습니다.',404)
            elif old['version']!=version:
                return error('첨부 중 수정 충돌입니다.',409,current=serialize(old))
            label=re.sub(r'[\[\]\\\r\n]','_',name)
            offset=int(request.form.get('offset',len(old['body'])))
            if not 0 <= offset <= len(old['body']): raise ValueError('첨부 위치가 올바르지 않습니다.')
            # Keep an attachment inside a formatted run or table cell on one source line.
            stack=[]
            for token in EDITOR_MARKUP.finditer(old['body'][:offset]):
                tag=token[0]
                if tag=='<br>': continue
                tag_name=re.match(r'</?(\w+)',tag)[1]
                if tag.startswith('</'):
                    if stack and stack[-1]==tag_name: stack.pop()
                else: stack.append(tag_name)
            separator='<br>' if stack else '\n'
            addition=f'{separator}{"!" if mime.startswith("image/") else ""}[{label}](/api/attachments/{aid}){separator}'
            body=old['body'][:offset]+addition+old['body'][offset:]
            if len(body)>MAX_BODY: raise ValueError('본문 길이 제한을 초과합니다.')
            if fresh:
                old.update(id=note_id,body=body,created_at=now(),updated_at=now(),version=1)
                insert_note(db,old)
            else:
                db.execute('UPDATE notes SET body=?,version=version+1,updated_at=? WHERE id=?',(body,now(),note_id))
            db.execute('INSERT INTO attachments VALUES (?,?,?,?,?,?)',(aid,note_id,name,mime,data,now()))
        return jsonify(serialize(note_row(note_id))),201
    @app.get('/api/attachments/<aid>')
    def attachment(aid):
        a=getdb().execute('SELECT * FROM attachments WHERE id=?',(aid,)).fetchone()
        if not a: return error('첨부파일을 찾을 수 없습니다.',404)
        res=send_file(io.BytesIO(a['data']),mimetype=a['mime'],download_name=a['name'],as_attachment=not a['mime'].startswith('image/'))
        res.headers['Content-Security-Policy']="default-src 'none'; sandbox"
        return res
    @app.get('/api/tokens')
    def tokens_list(): return jsonify(items=[dict(r) for r in getdb().execute('SELECT id,name,scope,created_at FROM tokens ORDER BY created_at DESC')])
    @app.post('/api/tokens')
    def tokens_create():
        d=request.get_json()
        if d.get('scope') not in ('read','write') or not isinstance(d.get('name'),str) or not 1<=len(d['name'])<=100: raise ValueError('이름과 읽기/쓰기 권한을 지정해 주세요.')
        raw='memo_'+secrets.token_urlsafe(32);tid=str(uuid.uuid4())
        with getdb() as db: db.execute('INSERT INTO tokens VALUES (?,?,?,?,?)',(tid,d['name'],digest(raw),d['scope'],now()))
        return jsonify(id=tid,token=raw),201
    @app.delete('/api/tokens/<tid>')
    def tokens_delete(tid):
        with getdb() as db: db.execute('DELETE FROM tokens WHERE id=?',(tid,))
        return jsonify(ok=True)
    @app.get('/api/export')
    def export():
        db=getdb();db.execute('BEGIN')
        output=tempfile.SpooledTemporaryFile(max_size=8*1024*1024)
        notes=[]
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            for row in db.execute('SELECT * FROM notes ORDER BY id'):
                n=serialize(row); n.pop('display_title'); n['markdown_path']=f'notes/{n["id"]}.md'
                body=n['body']
                for a in n['attachments']:
                    ext={'image/png':'.png','image/jpeg':'.jpg','image/gif':'.gif','image/webp':'.webp'}.get(a['mime'],'.bin')
                    a['path']=f'attachments/{n["id"]}/{a["id"]}{ext}'
                    data=db.execute('SELECT data FROM attachments WHERE id=?',(a['id'],)).fetchone()[0]
                    a['sha256']=hashlib.sha256(data).hexdigest();z.writestr(a['path'],data)
                    body=body.replace('/api/attachments/'+a['id'],'../'+a['path'])
                n.pop('body');z.writestr(n['markdown_path'],body);notes.append(n)
            z.writestr('manifest.json',json.dumps({'format':'hanjul-notes','format_version':1,'exported_at':now(),'folders':[dict(r) for r in db.execute('SELECT id,name,version FROM folders ORDER BY id')],'notes':notes},ensure_ascii=False,indent=2))
            z.writestr('RESTORE.md','# 한줄 백업 형식 v1\n\nnotes/*.md는 UTF-8 Markdown입니다. 첨부파일은 상대 경로로 연결됩니다.\nmanifest.json은 ID, 날짜, 태그, 상태, 버전, 첨부 관계 및 SHA-256을 보존합니다.\n한줄 → 설정 → ZIP 가져오기 → 결과 미리보기 → 확인. 같은 ID는 건너뛰며 덮어쓰지 않습니다.\n비밀번호·세션·API 토큰은 이 내보내기에 포함되지 않습니다.\n')
        db.rollback();output.seek(0)
        res=send_file(output,mimetype='application/zip',download_name='hanjul-'+now()[:10]+'.zip',as_attachment=True)
        res.call_on_close(output.close);return res
    def parse_import(data):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos=z.infolist()
            if len(infos)>50000 or sum(x.file_size for x in infos)>MAX_IMPORT: raise ValueError('압축을 푼 크기는 256MB, 파일은 5만 개까지 가능합니다.')
            names=[i.filename for i in infos]
            if len(names)!=len(set(names)) or any(n.startswith('/') or '\\' in n or '..' in n.split('/') for n in names): raise ValueError('안전하지 않은 ZIP 경로입니다.')
            manifest=json.loads(z.read('manifest.json'))
            if manifest.get('format')!='hanjul-notes' or manifest.get('format_version')!=1: raise ValueError('한줄 내보내기 형식 v1만 지원합니다.')
            rows=manifest.get('notes')
            if not isinstance(rows,list) or len(rows)>20000: raise ValueError('메모 개수가 올바르지 않습니다.')
            folders=manifest.get('folders',[])
            if not isinstance(folders,list) or len(folders)>20000: raise ValueError('폴더 개수가 올바르지 않습니다.')
            folder_map={}
            for f in folders:
                fid=uid(f['id'])
                if fid in folder_map: raise ValueError('중복 폴더 ID입니다.')
                folder_map[fid]=folder_name(f['name'])
            parsed=[];seen=set();aseen=set()
            for n in rows:
                nid=uid(n['id'])
                if nid in seen: raise ValueError('중복 메모 ID입니다.')
                seen.add(nid)
                if n['markdown_path']!=f'notes/{nid}.md': raise ValueError('Markdown 경로가 올바르지 않습니다.')
                body=z.read(n['markdown_path']).decode('utf-8'); attachments=[]
                for a in n.get('attachments',[]):
                    aid=uid(a['id'])
                    if aid in aseen or a['note_id']!=nid: raise ValueError('첨부파일 관계가 올바르지 않습니다.')
                    aseen.add(aid)
                    if not re.fullmatch(r'attachments/'+re.escape(nid)+'/'+re.escape(aid)+r'\.(png|jpg|gif|webp|bin)',a['path']): raise ValueError('첨부 경로가 올바르지 않습니다.')
                    blob=z.read(a['path'])
                    if len(blob)>MAX_ATTACHMENT or hashlib.sha256(blob).hexdigest()!=a['sha256']: raise ValueError('첨부파일 크기 또는 체크섬이 다릅니다.')
                    if a['mime'] not in ('image/png','image/jpeg','image/gif','image/webp','application/octet-stream'): raise ValueError('지원하지 않는 첨부 형식입니다.')
                    if not isinstance(a['name'],str) or len(a['name'])>200: raise ValueError('첨부파일 이름이 올바르지 않습니다.')
                    attachments.append({**a,'data':blob,'created_at':timestamp(a['created_at'])})
                    body=body.replace('../'+a['path'],'/api/attachments/'+aid)
                d=validate_note({**n,'body':body});d.update(id=nid,created_at=timestamp(n['created_at']),updated_at=timestamp(n['updated_at']),version=n['version'],attachments=attachments)
                if type(d['version']) is not int or not 1<=d['version']<2**53: raise ValueError('버전이 올바르지 않습니다.')
                if d['folder_id'] is not None and d['folder_id'] not in folder_map: raise ValueError('메모의 폴더 관계가 올바르지 않습니다.')
                parsed.append(d)
            return parsed,folder_map
    @app.post('/api/import/preview')
    def import_preview():
        f=request.files.get('file')
        if not f: raise ValueError('ZIP 파일을 선택해 주세요.')
        data=f.read(MAX_IMPORT+1)
        if len(data)>MAX_IMPORT: return error('ZIP 파일은 256MB까지 가능합니다.',413)
        rows,_=parse_import(data);db=getdb();existing={r[0] for r in db.execute('SELECT id FROM notes')}
        fresh=[n for n in rows if n['id'] not in existing]
        aid_existing={r[0] for r in db.execute('SELECT id FROM attachments')}
        if any(a['id'] in aid_existing for n in fresh for a in n['attachments']): raise ValueError('기존 첨부 ID와 충돌합니다. 가져오지 않았습니다.')
        pid=str(uuid.uuid4())
        with db:
            db.execute('DELETE FROM imports WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO imports VALUES (?,?,?)',(pid,data,time.time()+1800))
        return jsonify(preview_id=pid,total=len(rows),create=len(fresh),skip=len(rows)-len(fresh),attachments=sum(len(n['attachments']) for n in fresh),policy='동일 ID는 건너뜁니다. 기존 내용을 덮어쓰지 않습니다.',sample=[{'id':n['id'],'title':n['title'] or n['body'][:70]} for n in fresh[:8]])
    @app.post('/api/import/commit')
    def import_commit():
        db=getdb();pid=request.get_json()['preview_id'];created=skipped=0
        with db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT data FROM imports WHERE id=? AND expires>?',(pid,time.time())).fetchone()
            if not row: return error('가져오기 미리보기가 만료되었습니다.',410)
            rows,folders=parse_import(row['data'])
            for fid,name in folders.items():
                db.execute('INSERT OR IGNORE INTO folders(id,name) VALUES (?,?)',(fid,name))
            for n in rows:
                if db.execute('SELECT 1 FROM notes WHERE id=?',(n['id'],)).fetchone(): skipped+=1;continue
                insert_note(db,n)
                for a in n['attachments']: db.execute('INSERT INTO attachments VALUES (?,?,?,?,?,?)',(a['id'],n['id'],a['name'],a['mime'],a['data'],a['created_at']))
                created+=1
            db.execute('DELETE FROM imports WHERE id=?',(pid,))
        return jsonify(created=created,skipped=skipped)
    return app

if __name__ == '__main__':
    from waitress import serve
    app=create_app()
    print('한줄 실행: '+app.config['PUBLIC_ORIGIN'],flush=True)
    print('최초 비밀번호 파일: '+app.config['DATA_DIR']+'/initial-password.txt',flush=True)
    serve(app,host=os.environ.get('MEMO_HOST','127.0.0.1'),port=int(os.environ.get('PORT','8787')),threads=4,max_request_body_size=MAX_IMPORT)
