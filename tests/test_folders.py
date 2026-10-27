import io
from pathlib import Path
import json
import sqlite3
import uuid
import zipfile
import pytest
from app import create_app

@pytest.fixture
def owner(tmp_path):
    app=create_app(tmp_path/'db',test_password='folder-test-password')
    c=app.test_client();r=c.post('/api/login',json={'password':'folder-test-password'})
    return app,c,{'X-CSRF-Token':r.json['csrf']}

def test_folder_assignment_counts_rename_conflicts_and_auth(owner):
    app,c,h=owner
    assert app.test_client().get('/api/folders').status_code==401
    assert c.post('/api/folders',json={'name':'금지'}).status_code==403
    f=c.post('/api/folders',json={'name':'  여행  '},headers=h).json
    assert f['name']=='여행'
    other=c.post('/api/folders',json={'name':'일'},headers=h).json
    n=c.post('/api/notes',json={'body':'여행 준비','folder_id':f['id']},headers=h).json
    assert n['folder_id']==f['id']
    assert c.get('/api/notes?folder_id='+f['id']).json['total']==1
    renamed=c.patch('/api/folders/'+f['id'],json={'name':'여행 계획','version':1},headers=h)
    assert renamed.json['version']==2
    assert c.patch('/api/folders/'+f['id'],json={'name':'오래된 수정','version':1},headers=h).status_code==409
    assert c.get('/api/notes/'+n['id']).json['folder_id']==f['id']
    n=c.patch('/api/notes/'+n['id'],json={'folder_id':other['id'],'version':n['version'],'archived':True},headers=h).json
    counts={f['name']:f['count'] for f in c.get('/api/folders').json['items']}
    assert counts=={'여행 계획':0,'일':1}
    assert c.patch('/api/notes/'+n['id'],json={'folder_id':f['id'],'version':1},headers=h).status_code==409
    assert c.patch('/api/notes/'+n['id'],json={'folder_id':str(uuid.uuid4()),'version':n['version']},headers=h).status_code==400
    n=c.patch('/api/notes/'+n['id'],json={'deleted':True,'version':n['version']},headers=h).json
    assert all(f['count']==0 for f in c.get('/api/folders').json['items'])
    assert c.get('/api/notes?state=trash&folder_id='+other['id']).json['total']==1
    n=c.patch('/api/notes/'+n['id'],json={'deleted':False,'folder_id':None,'version':n['version']},headers=h).json
    assert c.get('/api/folders').json['unfiled']==1
    assert c.get('/api/notes?folder_id=none').json['total']==1
    assert c.post('/api/folders',json={'name':' '},headers=h).status_code==400
    assert c.post('/api/folders',json={'name':'x'*81},headers=h).status_code==400
    token=c.post('/api/tokens',json={'name':'folder read','scope':'read'},headers=h).json['token']
    anon=app.test_client();auth={'Authorization':'Bearer '+token}
    assert anon.get('/api/folders',headers=auth).status_code==200
    assert anon.post('/api/folders',json={'name':'금지'},headers=auth).status_code==403

def test_existing_database_migrates_without_rewriting_notes(tmp_path):
    data=tmp_path/'legacy';data.mkdir();nid=str(uuid.uuid4())
    with sqlite3.connect(data/'memo.sqlite3') as db:
        db.execute("CREATE TABLE notes(id TEXT PRIMARY KEY,title TEXT NOT NULL DEFAULT '',body TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,tags TEXT NOT NULL DEFAULT '[]',starred INTEGER NOT NULL DEFAULT 0,archived INTEGER NOT NULL DEFAULT 0,deleted INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1)")
        db.executescript((Path(__file__).resolve().parents[1]/'schema.sql').read_text())
        db.execute('INSERT INTO notes VALUES (?,?,?,?,?,?,?,?,?,?)',(nid,'기존 제목','기존 본문','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','["보존"]',1,0,0,7))
    app=create_app(data,test_password='folder-test-password')
    create_app(data,test_password='folder-test-password')
    with sqlite3.connect(app.config['DB_PATH']) as db:
        r=db.execute('SELECT body,tags,version,folder_id FROM notes').fetchone()
        assert r==('기존 본문','["보존"]',7,None)
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT count(*) FROM notes_fts WHERE notes_fts MATCH ?', ('"기존 본문"',)).fetchone()[0]==1

def test_folders_survive_export_import_and_backup(owner,tmp_path):
    app,c,h=owner
    f=c.post('/api/folders',json={'name':'내 폴더'},headers=h).json
    empty=c.post('/api/folders',json={'name':'빈 폴더'},headers=h).json
    n=c.post('/api/notes',json={'body':'보존할 메모','folder_id':f['id']},headers=h).json
    copy=c.post('/api/notes/'+n['id']+'/copy',json=n,headers=h).json
    assert copy['folder_id']==f['id']
    exported=c.get('/api/export').data
    other=create_app(tmp_path/'other',test_password='folder-test-password');oc=other.test_client()
    oh={'X-CSRF-Token':oc.post('/api/login',json={'password':'folder-test-password'}).json['csrf']}
    preview=oc.post('/api/import/preview',data={'file':(io.BytesIO(exported),'notes.zip')},headers=oh)
    assert preview.status_code==200
    result=oc.post('/api/import/commit',json={'preview_id':preview.json['preview_id']},headers=oh)
    assert result.json['created']==2
    assert {x['id']:x['count'] for x in oc.get('/api/folders').json['items']}=={f['id']:2,empty['id']:0}
    assert oc.get('/api/notes/'+n['id']).json['folder_id']==f['id']
    # Reimport never overwrites an existing folder's newer name.
    oc.patch('/api/folders/'+f['id'],json={'name':'새 이름','version':1},headers=oh)
    preview=oc.post('/api/import/preview',data={'file':(io.BytesIO(exported),'notes.zip')},headers=oh).json
    oc.post('/api/import/commit',json={'preview_id':preview['preview_id']},headers=oh)
    assert '새 이름' in [x['name'] for x in oc.get('/api/folders').json['items']]
    from test_operations import backup,verify
    path=tmp_path/'copy.sqlite3';backup(app.config['DB_PATH'],path)
    assert verify(path)=={'notes':2,'attachments':0}
