import io
import json
import sqlite3
import uuid
import zipfile
import base64
import pytest
from app import create_app

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1sAAAAASUVORK5CYII=')

@pytest.fixture
def env(tmp_path):
    app=create_app(tmp_path/'source',test_password='test-password-1234');app.config['TESTING']=True
    client=app.test_client(); r=client.post('/api/login',json={'password':'test-password-1234'});h={'X-CSRF-Token':r.json['csrf']}
    return app,client,h,tmp_path

def make(c,h,**kw):
    r=c.post('/api/notes',json={'body':'제목 없는 생각\n프로젝트 회의록과 여행 기록 Python',**kw},headers=h)
    assert r.status_code==201,r.json
    return r.json

def test_untitled_persistence_and_fields(env):
    app,c,h,p=env;n=make(c,h,tags=['업무','생각'],starred=True)
    assert n['title']=='' and n['display_title']=='제목 없는 생각'
    other=create_app(p/'source').test_client();login=other.post('/api/login',json={'password':'test-password-1234'})
    assert login.status_code==200
    r=other.get('/api/notes/'+n['id']).json
    assert r['body']==n['body'] and r['tags']==['업무','생각'] and r['starred'] and r['version']==1

def test_search(env):
    app,c,h,p=env
    n=make(c,h);make(c,h,body='여행만 있는 기록');make(c,h,body='앞문장 '*200+'특별한숨은문장 마무리')
    for q in ['젝트 회의','python 여행','프로젝트 Python','생각','회','PYTHON','목 없']:
        r=c.get('/api/notes',query_string={'q':q});assert r.status_code==200,r.json
        assert r.json['total']==1,q
    r=c.get('/api/notes',query_string={'q':'숨은문장'}).json
    assert '숨은문장' in r['items'][0]['snippet']
    assert 'body' not in r['items'][0]
    assert c.get('/api/notes?q=없는말').json['total']==0
    make(c,h,body='100% abc_def "quoted" * 하나')
    for q in ['100%','abc_def','"quoted"','*']:
        assert c.get('/api/notes',query_string={'q':q}).json['total']==1
    r=c.get('/api/notes',query_string={'from':'2099-01-01T00:00:00Z'}).json;assert r['total']==0
    r=c.get('/api/notes?limit=1').json;assert len(r['items'])==1 and r['next_offset']==1
    r2=c.get('/api/notes?limit=1&offset=1').json;assert r2['items'][0]['id']!=r['items'][0]['id']

def test_conflict_trash_restore(env):
    app,c,h,p=env;n=make(c,h);url='/api/notes/'+n['id']
    assert c.patch(url,json={'body':'새 내용','version':1},headers=h).json['version']==2
    r=c.patch(url,json={'body':'과거 내용','version':1},headers=h);assert r.status_code==409 and r.json['current']['body']=='새 내용'
    assert c.patch(url,json={'body':'버전 없음'},headers=h).status_code==428
    assert c.delete(url,json={'version':1},headers=h).status_code==409
    assert c.delete(url,json={'version':2},headers=h).json['deleted']
    assert c.get('/api/notes').json['total']==0
    assert c.get('/api/notes?state=trash').json['total']==1
    r=c.patch(url,json={'deleted':False,'version':3},headers=h);assert r.json['version']==4
    assert c.get('/api/notes').json['total']==1

def test_attachment_auth_collision_and_atomic_conflict(env):
    app,c,h,p=env;n=make(c,h);url='/api/notes/'+n['id']+'/attachments'
    r=c.post(url,data={'version':'1','file':(io.BytesIO(PNG),'같은이름.png')},headers=h);assert r.status_code==201
    n=r.json;a=n['attachments'][0]
    r=c.post(url,data={'version':'1','file':(io.BytesIO(PNG),'같은이름.png')},headers=h);assert r.status_code==409
    assert len(c.get('/api/notes/'+n['id']).json['attachments'])==1
    r=c.post(url,data={'version':'2','file':(io.BytesIO(PNG),'같은이름.png')},headers=h);assert r.status_code==201
    assert len({x['id'] for x in r.json['attachments']})==2
    assert c.get('/api/attachments/'+a['id']).data==PNG
    anon=app.test_client()
    for path in ['/api/notes','/api/notes/'+n['id'],'/api/attachments/'+a['id'],'/api/export','/api/tokens']:
        assert anon.get(path).status_code==401
    assert anon.post('/api/notes',json={'body':'bad'}).status_code==401
    assert c.post('/api/notes',json={'body':'csrf'}).status_code==403
    assert c.post('/api/notes',json={'body':'csrf'},headers={**h,'Origin':'https://evil.example'}).status_code==403
    r=c.post(url,data={'version':'3','file':(io.BytesIO(b'<script>alert(1)</script>'),'x.html')},headers=h)
    a=r.json['attachments'][-1];res=c.get('/api/attachments/'+a['id']);assert 'attachment' in res.headers['Content-Disposition'] and res.mimetype=='application/octet-stream'

def test_token_scopes_and_revocation(env):
    app,c,h,p=env;n=make(c,h)
    for scope in ['read','write']:
        t=c.post('/api/tokens',json={'name':scope,'scope':scope},headers=h).json
        headers={'Authorization':'Bearer '+t['token']};a=app.test_client()
        assert a.get('/api/notes',headers=headers).status_code==200
        assert a.post('/api/notes',json={'body':'외부'},headers=headers).status_code==(403 if scope=='read' else 201)
        assert a.post('/api/tokens',json={'name':'nested','scope':'write'},headers=headers).status_code==403
        assert a.get('/api/export',headers=headers).status_code==403
        assert c.delete('/api/tokens/'+t['id'],headers=h).status_code==200
        assert a.get('/api/notes',headers=headers).status_code==401
    assert 'hash' not in str(c.get('/api/tokens').json)

def test_roundtrip_and_duplicate_policy(env):
    app,c,h,p=env;n=make(c,h,tags=['한글','work'],archived=True,starred=True,deleted=True)
    n=c.post('/api/notes/'+n['id']+'/attachments',data={'version':'1','file':(io.BytesIO(PNG),'그림.png')},headers=h).json
    exported=c.get('/api/export').data
    with zipfile.ZipFile(io.BytesIO(exported)) as z:
        m=json.loads(z.read('manifest.json'));body=z.read('notes/'+n['id']+'.md').decode()
        assert '../attachments/' in body and '/api/attachments/' not in body
        assert m['format_version']==1 and z.read(m['notes'][0]['attachments'][0]['path'])==PNG
    other=create_app(p/'target',test_password='target-password');d=other.test_client();dh={'X-CSRF-Token':d.post('/api/login',json={'password':'target-password'}).json['csrf']}
    for iteration in [0,1]:
        preview=d.post('/api/import/preview',data={'file':(io.BytesIO(exported),'notes.zip')},headers=dh)
        assert preview.status_code==200,preview.json
        assert preview.json['create']==1-iteration and preview.json['skip']==iteration
        assert d.get('/api/notes?state=trash').json['total']==iteration # preview has no writes to notes
        result=d.post('/api/import/commit',json={'preview_id':preview.json['preview_id']},headers=dh)
        assert result.json['created']==1-iteration
    restored=d.get('/api/notes/'+n['id']).json
    for key in ['id','title','body','created_at','updated_at','tags','starred','archived','deleted','version','attachments']:
        assert restored[key]==n[key],key
    assert d.get('/api/attachments/'+n['attachments'][0]['id']).data==PNG
    assert d.post('/api/import/commit',json={'preview_id':preview.json['preview_id']},headers=dh).status_code==410

def test_malicious_import_and_transaction_rollback(env):
    app,c,h,p=env
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:z.writestr('../bad','hello');z.writestr('manifest.json','{}')
    assert c.post('/api/import/preview',data={'file':(io.BytesIO(stream.getvalue()),'bad.zip')},headers=h).status_code==400
    assert c.get('/api/notes').json['total']==0

def test_database_save_failure_reports_failure(env):
    app,c,h,p=env;n=make(c,h)
    with sqlite3.connect(app.config['DB_PATH']) as db:
        db.execute("CREATE TRIGGER fail_update BEFORE UPDATE ON notes BEGIN SELECT RAISE(ABORT, 'test storage failure'); END")
    r=c.patch('/api/notes/'+n['id'],json={'version':1,'body':'저장 실패 내용'},headers=h)
    assert r.status_code==503
    assert c.get('/api/notes/'+n['id']).json['body']==n['body']

def test_online_backup_and_restore(env):
    import sys
    sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]/'scripts'))
    from backup import backup
    from restore import restore
    app,c,h,p=env;n=make(c,h)
    n=c.post('/api/notes/'+n['id']+'/attachments',data={'version':'1','file':(io.BytesIO(PNG),'same.png')},headers=h).json
    assert backup(app.config['DB_PATH'],p/'backup.sqlite3')=={'notes':1,'attachments':1}
    assert restore(p/'backup.sqlite3',p/'restored')=={'notes':1,'attachments':1}
    app2=create_app(p/'restored');c2=app2.test_client();assert c2.post('/api/login',json={'password':'test-password-1234'}).status_code==200
    assert c2.get('/api/notes/'+n['id']).json==n
    assert c2.get('/api/attachments/'+n['attachments'][0]['id']).data==PNG
    with pytest.raises(ValueError):restore(p/'backup.sqlite3',p/'restored')

def test_copy_preserves_attachment_ownership(env):
    app,c,h,p=env;n=make(c,h)
    n=c.post('/api/notes/'+n['id']+'/attachments',data={'version':'1','file':(io.BytesIO(PNG),'same.png')},headers=h).json
    copy=c.post('/api/notes/'+n['id']+'/copy',json={**n,'body':n['body']+'\n충돌한 내용'},headers=h)
    assert copy.status_code==201
    copied=copy.json
    assert copied['id']!=n['id'] and copied['attachments'][0]['note_id']==copied['id']
    assert copied['attachments'][0]['id']!=n['attachments'][0]['id']
    assert n['attachments'][0]['id'] not in copied['body']
    assert c.get('/api/attachments/'+copied['attachments'][0]['id']).data==PNG

def test_import_failure_rolls_back_entire_batch(env):
    app,c,h,p=env;make(c,h,title='good');make(c,h,title='fail')
    exported=c.get('/api/export').data
    target=create_app(p/'rollback-target',test_password='rollback-password');tc=target.test_client()
    th={'X-CSRF-Token':tc.post('/api/login',json={'password':'rollback-password'}).json['csrf']}
    preview=tc.post('/api/import/preview',data={'file':(io.BytesIO(exported),'backup.zip')},headers=th).json
    with sqlite3.connect(target.config['DB_PATH']) as db:
        db.execute("CREATE TRIGGER reject_note BEFORE INSERT ON notes WHEN new.title='fail' BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    result=tc.post('/api/import/commit',json={'preview_id':preview['preview_id']},headers=th)
    assert result.status_code==503
    assert tc.get('/api/notes').json['total']==0

def test_import_checksum_rejection(env):
    app,c,h,p=env;n=make(c,h)
    c.post('/api/notes/'+n['id']+'/attachments',data={'version':'1','file':(io.BytesIO(PNG),'image.png')},headers=h)
    exported=c.get('/api/export').data;stream=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(exported)) as src,zipfile.ZipFile(stream,'w') as dst:
        for name in src.namelist():dst.writestr(name,b'corrupted' if name.startswith('attachments/') else src.read(name))
    result=c.post('/api/import/preview',data={'file':(io.BytesIO(stream.getvalue()),'broken.zip')},headers=h)
    assert result.status_code==400 and '체크섬' in result.json['error']


def test_known_version_polling_is_authenticated_and_includes_remote_changes(env):
    app,c,h,p=env;n=make(c,h);url='/api/notes/'+n['id']
    assert app.test_client().get(url+'?known_version=1').status_code==401
    assert c.get(url+'?known_version=1').json=={'id':n['id'],'version':1,'unchanged':True}
    c.patch(url,json={'version':1,'body':'다른 기기 수정','tags':['변경']},headers=h)
    changed=c.get(url+'?known_version=1').json
    assert changed['body']=='다른 기기 수정' and changed['tags']==['변경'] and changed['version']==2
    c.delete(url,json={'version':2},headers=h)
    assert c.get(url+'?known_version=2').json['deleted']
