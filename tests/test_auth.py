import json
import secrets
import sqlite3
import time
import pytest
from app import create_app
from auth import digest, REMEMBER_SECONDS, FRESH_SECONDS

@pytest.fixture
def setup(tmp_path):
    app=create_app(tmp_path/'auth-db',test_password='safe-test-password')
    app.config['PUBLIC_ORIGIN']='http://localhost'
    return app,app.test_client(),tmp_path

def login(c,remember=True):
    r=c.post('/api/login',json={'password':'safe-test-password','remember':remember});assert r.status_code==200
    return r,{'X-CSRF-Token':r.json['csrf']}

def expire_fresh(app):
    with sqlite3.connect(app.config['DB_PATH']) as db:db.execute('UPDATE sessions SET reauth_at=0')

def test_30_day_choice_and_absolute_expiry(setup):
    app,c,_=setup;r,h=login(c)
    assert REMEMBER_SECONDS-5<r.json['expires']-time.time()<=REMEMBER_SECONDS
    assert 'HttpOnly' in r.headers['Set-Cookie'] and 'SameSite=Strict' in r.headers['Set-Cookie']
    expiry=r.json['expires'];c.get('/api/notes');assert c.get('/api/session').json['expires']==expiry
    second=app.test_client();r2,_=login(second,False);assert 'Max-Age' not in r2.headers['Set-Cookie'] and r2.json['expires']-time.time()<12*3600+1
    with sqlite3.connect(app.config['DB_PATH']) as db:db.execute('UPDATE sessions SET expires=0')
    assert c.get('/api/notes').status_code==401

def test_recent_auth_required_but_notes_still_save(setup):
    app,c,_=setup;_,h=login(c);expire_fresh(app)
    assert c.post('/api/notes',json={'body':'기록은 계속'},headers=h).status_code==201
    for path,method,body in [('/api/export','get',None),('/api/tokens','post',{'name':'tool','scope':'read'}),('/api/password','post',{'password':'another-password'}),('/api/sessions/revoke-others','post',{})]:
        r=getattr(c,method)(path,json=body,headers=h)
        assert r.status_code==428 and r.json['code']=='REAUTH_REQUIRED'
    assert c.post('/api/reauth/password',json={'password':'wrong'},headers=h).status_code==401
    assert c.get('/api/export').status_code==428
    old_cookie=c.get_cookie('memo_session').value
    r=c.post('/api/reauth/password',json={'password':'safe-test-password'},headers=h);assert r.status_code==200
    assert c.get_cookie('memo_session').value!=old_cookie
    copied=app.test_client();copied.set_cookie('memo_session',old_cookie);assert copied.get('/api/notes').status_code==401
    assert c.get('/api/export').status_code==200

def test_device_revocation_and_readonly_token_isolation(setup):
    app,c,_=setup;_,h=login(c);other=app.test_client();login(other)
    listed=c.get('/api/sessions').json['items'];assert len(listed)==2
    assert all('hash' not in s and 'csrf' not in s for s in listed)
    oid=next(s['id'] for s in listed if not s['current'])
    assert c.delete('/api/sessions/'+oid,headers=h).status_code==200
    assert other.get('/api/notes').status_code==401
    token=c.post('/api/tokens',json={'name':'tool','scope':'write'},headers=h).json['token']
    bearer={'Authorization':'Bearer '+token}
    for path in ['/api/passkeys','/api/sessions','/api/export']:
        assert app.test_client().get(path,headers=bearer).status_code==403

def test_challenge_binding_expiry_csrf_and_single_use(setup):
    app,c,_=setup;_,h=login(c);ph={**h,'Origin':'http://localhost','X-Passkey-Request':'1'}
    assert c.post('/api/passkeys/register/options',json={},headers=h).status_code==403
    assert c.post('/api/passkeys/register/options',json={},headers={**ph,'Origin':'https://evil.test'}).status_code==403
    opt=c.post('/api/passkeys/register/options',json={},headers=ph).json
    assert opt['options']['authenticatorSelection']['userVerification']=='required'
    assert opt['options']['authenticatorSelection']['residentKey']=='required'
    other=app.test_client();_,oh=login(other)
    payload={'challenge_id':opt['challenge_id'],'response':{}}
    assert other.post('/api/passkeys/register/verify',json=payload,headers={**ph,**oh}).status_code==409
    assert c.post('/api/passkeys/register/verify',json=payload,headers=ph).status_code==400
    assert c.post('/api/passkeys/register/verify',json=payload,headers=ph).status_code==409
    r=c.post('/api/passkeys/login/options',json={},headers=ph);opts=r.json
    stranger=app.test_client()
    assert stranger.post('/api/passkeys/login/verify',json={'challenge_id':opts['challenge_id'],'response':{}},headers=ph).status_code==409
    with sqlite3.connect(app.config['DB_PATH']) as db:db.execute('UPDATE auth_challenges SET expires=0')
    assert c.post('/api/passkeys/login/verify',json={'challenge_id':opts['challenge_id'],'response':{}},headers=ph).status_code==409

def test_revoking_passkey_revokes_its_sessions(setup):
    app,c,_=setup;_,h=login(c);raw=secrets.token_urlsafe(32)
    with sqlite3.connect(app.config['DB_PATH']) as db:
        db.execute('INSERT INTO passkeys VALUES(?,?,?,?,?,?,?,?,?)',('key',b'public',0,'phone','localhost',time.time(),None,'single_device',0))
        db.execute('INSERT INTO sessions(hash,csrf,expires,id,passkey_id) VALUES(?,?,?,?,?)',(digest(raw),'csrf',time.time()+86400,'other-session','key'))
    other=app.test_client();other.set_cookie('memo_session',raw);assert other.get('/api/notes').status_code==200
    assert c.delete('/api/passkeys/key',headers=h).status_code==200
    assert other.get('/api/notes').status_code==401
    assert c.get('/api/notes').status_code==200

def test_existing_schema_migration_preserves_session_and_memo(setup):
    app,c,p=setup;_,h=login(c);note=c.post('/api/notes',json={'body':'마이그레이션 보존'},headers=h).json
    raw=c.get_cookie('memo_session').value
    with sqlite3.connect(app.config['DB_PATH']) as db:
        db.execute('ALTER TABLE sessions RENAME TO saved_sessions')
        db.execute('CREATE TABLE sessions(hash TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL)')
        db.execute('INSERT INTO sessions SELECT hash,csrf,expires FROM saved_sessions');db.execute('DROP TABLE saved_sessions')
    migrated=create_app(p/'auth-db');mc=migrated.test_client();mc.set_cookie('memo_session',raw)
    assert mc.get('/api/notes/'+note['id']).json['body']=='마이그레이션 보존'
    assert mc.get('/api/export').status_code==428
    assert mc.get('/api/sessions').json['items'][0]['current']

def test_password_change_revokes_sessions_but_keeps_passkeys(setup):
    app,c,_=setup;_,h=login(c)
    with sqlite3.connect(app.config['DB_PATH']) as db:db.execute('INSERT INTO passkeys VALUES(?,?,?,?,?,?,?,?,?)',('key',b'public',0,'phone','localhost',time.time(),None,'single_device',0))
    assert c.post('/api/password',json={'password':'my-new-password'},headers=h).status_code==200
    assert c.get('/api/notes').status_code==401
    assert c.post('/api/login',json={'password':'my-new-password'}).status_code==200
    assert len(c.get('/api/passkeys').json['items'])==1


def test_https_proxy_origin_and_cookie(setup):
    app,_,_=setup
    app.config['PUBLIC_ORIGIN']='https://notes.example.test'
    c=app.test_client()
    # TLS terminates at a reverse proxy; original Host remains, internal hop is HTTP.
    r=c.get('/api/auth/config',base_url='http://notes.example.test')
    assert r.json['passkeys_available'] is True
    assert c.get('/api/auth/config',base_url='http://wrong.example.test').json['passkeys_available'] is False
    r=c.post('/api/passkeys/login/options',base_url='http://notes.example.test',headers={'Origin':'https://notes.example.test','X-Passkey-Request':'1'},json={})
    assert r.status_code==200 and 'Secure;' in r.headers['Set-Cookie']
    assert c.post('/api/passkeys/login/options',base_url='http://notes.example.test',headers={'Origin':'http://notes.example.test','X-Passkey-Request':'1'},json={}).status_code==403
