"""Single-owner sessions and WebAuthn; no biometric data or private keys are stored."""
import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from urllib.parse import urlsplit
from flask import request, jsonify, g, abort
from werkzeug.security import check_password_hash, generate_password_hash
from webauthn import (generate_registration_options, verify_registration_response,
                      generate_authentication_options, verify_authentication_response, options_to_json)
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, ResidentKeyRequirement,
                                     UserVerificationRequirement, PublicKeyCredentialDescriptor)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

REMEMBER_SECONDS = 30 * 86400
SESSION_SECONDS = 12 * 3600
FRESH_SECONDS = 5 * 60
CHALLENGE_SECONDS = 5 * 60
ALGORITHMS = [COSEAlgorithmIdentifier.ECDSA_SHA_256, COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256]

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def migrate_auth(db):
    """Add columns to v1 sessions without deleting notes, attachments, or existing sessions."""
    columns={r[1] for r in db.execute('PRAGMA table_info(sessions)')}
    for name,definition in {'id':'TEXT','created_at':'REAL NOT NULL DEFAULT 0',
            'last_seen':'REAL NOT NULL DEFAULT 0','reauth_at':'REAL NOT NULL DEFAULT 0',
            'device_name':"TEXT NOT NULL DEFAULT '기존 브라우저'",'passkey_id':'TEXT',
            'remember':'INTEGER NOT NULL DEFAULT 1'}.items():
        if name not in columns: db.execute(f'ALTER TABLE sessions ADD COLUMN {name} {definition}')
    for row in db.execute('SELECT hash FROM sessions WHERE id IS NULL').fetchall():
        db.execute('UPDATE sessions SET id=? WHERE hash=?',(str(uuid.uuid4()),row[0]))
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS sessions_id ON sessions(id)')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS passkeys (
      id TEXT PRIMARY KEY, public_key BLOB NOT NULL, sign_count INTEGER NOT NULL,
      name TEXT NOT NULL, rp_id TEXT NOT NULL, created_at REAL NOT NULL,
      last_used REAL, device_type TEXT NOT NULL, backed_up INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS auth_challenges (
      id TEXT PRIMARY KEY, challenge BLOB NOT NULL, purpose TEXT NOT NULL,
      binding TEXT NOT NULL, expires REAL NOT NULL, remember INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS auth_challenges_expiry ON auth_challenges(expires);
    ''')
    db.commit()

def install_auth(app, getdb, folder):
    origin=os.environ.get('MEMO_PUBLIC_ORIGIN','http://localhost:8787').rstrip('/')
    url=urlsplit(origin)
    if not url.hostname or url.username or url.query or url.fragment or url.path or (url.scheme!='https' and not(url.scheme=='http' and url.hostname=='localhost')):
        raise ValueError('MEMO_PUBLIC_ORIGIN은 경로 없는 HTTPS 주소 또는 http://localhost 주소여야 합니다.')
    app.config.setdefault('PUBLIC_ORIGIN',origin)
    app.config.setdefault('REAUTH_SECONDS',FRESH_SECONDS)
    def error(message,status=400,**extras): return jsonify(error=message,**extras),status
    def rp(): return urlsplit(app.config['PUBLIC_ORIGIN']).hostname
    def secure(): return app.config['PUBLIC_ORIGIN'].startswith('https://') or os.environ.get('MEMO_SECURE_COOKIE')=='1'
    def need_fresh():
        if not getattr(g,'owner',False): return error('웹 로그인이 필요합니다.',403)
        if g.auth_session['reauth_at'] < time.time()-app.config['REAUTH_SECONDS']:
            return error('이 작업을 진행하려면 본인 확인이 필요합니다.',428,code='REAUTH_REQUIRED')
    public={'/api/login','/api/auth/config','/api/passkeys/login/options','/api/passkeys/login/verify'}
    owner_paths=('/api/tokens','/api/import','/api/export','/api/password','/api/passkeys','/api/sessions','/api/reauth')
    @app.before_request
    def authenticate():
        if not request.path.startswith('/api/'): return
        if request.path.startswith(('/api/passkeys','/api/reauth','/api/login','/api/password')):
            request.max_content_length=65536
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin_header=request.headers.get('Origin')
            allowed={app.config['PUBLIC_ORIGIN']} if secure() else {app.config['PUBLIC_ORIGIN'],request.host_url.rstrip('/')}
            if origin_header and origin_header not in allowed: return error('허용되지 않은 요청 출처입니다.',403)
        if request.path in public: return
        db=getdb();bearer=request.headers.get('Authorization','');g.owner=False
        if bearer.startswith('Bearer '):
            token=db.execute('SELECT scope FROM tokens WHERE hash=?',(digest(bearer[7:]),)).fetchone()
            if not token:return error('유효한 인증 토큰이 필요합니다.',401)
            g.scope=token['scope']
            if request.method not in ('GET','HEAD') and g.scope!='write':return error('읽기 전용 토큰입니다.',403)
        else:
            s=db.execute('SELECT * FROM sessions WHERE hash=? AND expires>?',(digest(request.cookies.get('memo_session','')),time.time())).fetchone()
            if not s:return error('로그인이 필요합니다.',401)
            g.owner=True;g.scope='write';g.csrf=s['csrf'];g.auth_session=s
            if request.method not in ('GET','HEAD') and not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),s['csrf']):
                return error('요청 인증이 만료됐습니다. 새로고침해 주세요.',403)
            if s['last_seen']<time.time()-300:
                with db:db.execute('UPDATE sessions SET last_seen=? WHERE hash=?',(time.time(),s['hash']))
        if request.path.startswith(owner_paths) and not g.owner:return error('이 기능은 웹 로그인에서만 사용할 수 있습니다.',403)
        sensitive=(request.path=='/api/export' or request.path.startswith('/api/import') or request.path=='/api/password'
                   or (request.path.startswith(('/api/tokens','/api/sessions')) and request.method not in ('GET','HEAD'))
                   or request.path.startswith('/api/passkeys/register')
                   or (request.path.startswith('/api/passkeys/') and request.method=='DELETE'))
        if sensitive:return need_fresh()

    failures={}
    def password_ok(password):
        key=request.remote_addr;recent=[t for t in failures.get(key,[]) if t>time.time()-300];failures[key]=recent
        if len(recent)>=10:abort(429,description='로그인 시도가 많습니다. 5분 뒤 다시 시도해 주세요.')
        if not isinstance(password,str) or len(password)>1024 or not check_password_hash(getdb().execute("SELECT value FROM settings WHERE key='password'").fetchone()[0],password):
            recent.append(time.time());return False
        failures.pop(key,None);return True
    def remember_value(data):
        value=data.get('remember',True)
        if type(value) is not bool:raise ValueError('로그인 유지 설정이 올바르지 않습니다.')
        return value
    def device_name():
        ua=request.headers.get('User-Agent','')
        os_name='Android' if 'Android' in ua else 'iPhone/iPad' if any(x in ua for x in ('iPhone','iPad')) else 'Windows' if 'Windows' in ua else 'Mac' if 'Macintosh' in ua else '브라우저'
        browser='Edge' if 'Edg/' in ua else 'Chrome' if 'Chrome/' in ua else 'Firefox' if 'Firefox/' in ua else 'Safari' if 'Safari/' in ua else ''
        return (os_name+' · '+browser).strip(' ·')
    def set_session_cookie(response,raw,expires,remember):
        response.set_cookie('memo_session',raw,httponly=True,samesite='Strict',secure=secure(),max_age=max(1,int(expires-time.time())) if remember else None)
        return response
    def issue_session(remember=True,passkey_id=None):
        raw=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);stamp=time.time();sid=str(uuid.uuid4());expires=stamp+(REMEMBER_SECONDS if remember else SESSION_SECONDS)
        with getdb() as db:
            db.execute('DELETE FROM sessions WHERE expires<? OR hash=?',(stamp,digest(request.cookies.get('memo_session',''))))
            db.execute('INSERT INTO sessions(hash,csrf,expires,id,created_at,last_seen,reauth_at,device_name,passkey_id,remember) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (digest(raw),csrf,expires,sid,stamp,stamp,stamp,device_name(),passkey_id,int(remember)))
        return set_session_cookie(jsonify(csrf=csrf,expires=expires,remember=remember),raw,expires,remember)
    def renew_verification():
        # Rotate the bearer cookie, preserve expiry and CSRF for other tabs of this session.
        s=g.auth_session;raw=secrets.token_urlsafe(32)
        with getdb() as db:
            changed=db.execute('UPDATE sessions SET hash=?,reauth_at=?,last_seen=? WHERE hash=? AND expires>?',(digest(raw),time.time(),time.time(),s['hash'],time.time())).rowcount
        if not changed:return error('로그인이 만료되었습니다.',401)
        return set_session_cookie(jsonify(csrf=s['csrf'],reauthenticated=True),raw,s['expires'],s['remember'])

    @app.get('/api/auth/config')
    def config():
        return jsonify(passkey_origin=app.config['PUBLIC_ORIGIN'],passkeys_available=request.host==urlsplit(app.config['PUBLIC_ORIGIN']).netloc,remember_days=30)
    @app.post('/api/login')
    def login():
        d=request.get_json() or {};remember=remember_value(d)
        if not password_ok(d.get('password','')):return error('비밀번호를 확인해 주세요.',401)
        return issue_session(remember)
    @app.get('/api/session')
    def session_info():
        s=getattr(g,'auth_session',None)
        return jsonify(csrf=getattr(g,'csrf',None),instance=getdb().execute("SELECT value FROM settings WHERE key='instance'").fetchone()[0],
            session_id=s['id'] if s else None,expires=s['expires'] if s else None,reauth_until=s['reauth_at']+app.config['REAUTH_SECONDS'] if s else None)
    @app.post('/api/logout')
    def logout():
        with getdb() as db:db.execute('DELETE FROM sessions WHERE hash=?',(digest(request.cookies.get('memo_session','')),))
        r=jsonify(ok=True);r.delete_cookie('memo_session',secure=secure(),httponly=True,samesite='Strict');return r
    @app.post('/api/reauth/password')
    def reauth_password():
        if not password_ok((request.get_json() or {}).get('password','')):return error('비밀번호를 확인해 주세요.',401)
        return renew_verification()
    @app.post('/api/password')
    def password_change():
        d=request.get_json();password=d.get('password')
        if not isinstance(password,str) or not 12<=len(password)<=1024:return error('새 비밀번호는 12~1024자여야 합니다.')
        with getdb() as db:
            db.execute("UPDATE settings SET value=? WHERE key='password'",(generate_password_hash(password),))
            db.execute('DELETE FROM sessions');db.execute('DELETE FROM auth_challenges')
        (folder/'initial-password.txt').unlink(missing_ok=True)
        r=jsonify(ok=True);r.delete_cookie('memo_session');return r
    @app.get('/api/sessions')
    def sessions():
        rows=getdb().execute('SELECT id,device_name,created_at,last_seen,expires,remember FROM sessions WHERE expires>? ORDER BY last_seen DESC',(time.time(),)).fetchall()
        return jsonify(items=[{**dict(r),'current':r['id']==g.auth_session['id']} for r in rows])
    @app.delete('/api/sessions/<sid>')
    def revoke_session(sid):
        with getdb() as db:db.execute('DELETE FROM sessions WHERE id=?',(sid,))
        return jsonify(ok=True,current=sid==g.auth_session['id'])
    @app.post('/api/sessions/revoke-others')
    def revoke_others():
        with getdb() as db:db.execute('DELETE FROM sessions WHERE id<>?',(g.auth_session['id'],))
        return jsonify(ok=True)
    @app.get('/api/passkeys')
    def passkeys():
        rows=getdb().execute('SELECT id,name,rp_id,created_at,last_used FROM passkeys ORDER BY created_at DESC').fetchall()
        return jsonify(items=[dict(r) for r in rows],origin=app.config['PUBLIC_ORIGIN'])
    @app.delete('/api/passkeys/<kid>')
    def revoke_passkey(kid):
        with getdb() as db:
            db.execute('DELETE FROM sessions WHERE passkey_id=?',(kid,));db.execute('DELETE FROM passkeys WHERE id=?',(kid,))
            db.execute('DELETE FROM auth_challenges')
        return jsonify(ok=True,current=getattr(g,'auth_session')['passkey_id']==kid)

    def ceremony_allowed():
        if request.headers.get('Origin')!=app.config['PUBLIC_ORIGIN'] or request.headers.get('X-Passkey-Request')!='1':
            abort(403,description='패스키는 설정된 앱 주소에서 직접 실행해 주세요.')
    def get_user_id():
        return uuid.UUID(getdb().execute("SELECT value FROM settings WHERE key='instance'").fetchone()[0]).bytes
    def begin_challenge(options,purpose,remember=False):
        stamp=time.time();cid=str(uuid.uuid4());flow=secrets.token_urlsafe(32)
        binding=digest(flow) if purpose=='login' else g.auth_session['id']
        db=getdb()
        with db:
            db.execute('DELETE FROM auth_challenges WHERE expires<?',(stamp,))
            count=db.execute('SELECT count(*) FROM auth_challenges').fetchone()[0]
            if count>=200:abort(429,description='진행 중인 인증 요청이 많습니다. 잠시 후 다시 시도해 주세요.')
            db.execute('INSERT INTO auth_challenges VALUES(?,?,?,?,?,?)',(cid,options.challenge,purpose,binding,stamp+CHALLENGE_SECONDS,int(remember)))
        res=jsonify(challenge_id=cid,options=json.loads(options_to_json(options)))
        if purpose=='login':res.set_cookie('memo_pk_flow',flow,max_age=CHALLENGE_SECONDS,httponly=True,secure=secure(),samesite='Strict',path='/api/passkeys/login')
        return res
    def consume(d,purpose):
        cid=d.get('challenge_id');binding=digest(request.cookies.get('memo_pk_flow','')) if purpose=='login' else g.auth_session['id']
        if not isinstance(cid,str):abort(400,description='인증 요청이 올바르지 않습니다.')
        db=getdb()
        with db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM auth_challenges WHERE id=? AND purpose=? AND binding=?',(cid,purpose,binding)).fetchone()
            if row:db.execute('DELETE FROM auth_challenges WHERE id=?',(cid,))
        if not row or row['expires']<time.time():abort(409,description='인증 요청이 만료됐거나 이미 사용됐습니다. 다시 시도해 주세요.')
        return row
    @app.post('/api/passkeys/register/options')
    def registration_options():
        ceremony_allowed();rows=getdb().execute('SELECT id FROM passkeys WHERE rp_id=?',(rp(),)).fetchall()
        if len(rows)>=20:return error('패스키는 최대 20개까지 등록할 수 있습니다.')
        options=generate_registration_options(rp_id=rp(),rp_name='한줄 개인 메모',user_id=get_user_id(),user_name='내 메모',user_display_name='한줄 개인 메모',timeout=120000,
            authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.REQUIRED,user_verification=UserVerificationRequirement.REQUIRED),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(r['id'])) for r in rows],supported_pub_key_algs=ALGORITHMS)
        return begin_challenge(options,'register')
    @app.post('/api/passkeys/register/verify')
    def registration_verify():
        ceremony_allowed();d=request.get_json();challenge=consume(d,'register')
        try:v=verify_registration_response(credential=d['response'],expected_challenge=challenge['challenge'],expected_rp_id=rp(),expected_origin=app.config['PUBLIC_ORIGIN'],require_user_presence=True,require_user_verification=True,supported_pub_key_algs=ALGORITHMS)
        except Exception:return error('패스키 등록 응답을 검증하지 못했습니다.',400)
        name=d.get('name') or device_name()
        if not isinstance(name,str) or len(name)>80:return error('기기 이름은 80자 이하로 입력해 주세요.')
        kid=bytes_to_base64url(v.credential_id)
        try:
            with getdb() as db:db.execute('INSERT INTO passkeys VALUES(?,?,?,?,?,?,?,?,?)',(kid,v.credential_public_key,v.sign_count,name,rp(),time.time(),None,v.credential_device_type.value,int(v.credential_backed_up)))
        except sqlite3.IntegrityError:return error('이미 등록한 패스키입니다.',409)
        return jsonify(id=kid,registered=True),201
    @app.post('/api/passkeys/<purpose>/options')
    def authentication_options(purpose):
        if purpose not in ('login','reauth'):abort(404)
        ceremony_allowed();d=request.get_json();remember=remember_value(d)
        # Discoverable credentials avoid revealing the owner's credential IDs at login.
        options=generate_authentication_options(rp_id=rp(),user_verification=UserVerificationRequirement.REQUIRED,timeout=120000)
        return begin_challenge(options,purpose,remember)
    @app.post('/api/passkeys/<purpose>/verify')
    def authentication_verify(purpose):
        if purpose not in ('login','reauth'):abort(404)
        ceremony_allowed();d=request.get_json();challenge=consume(d,purpose);response=d.get('response') or {}
        kid=response.get('id');key=getdb().execute('SELECT * FROM passkeys WHERE id=? AND rp_id=?',(kid,rp())).fetchone()
        if not key:return error('등록된 패스키가 아닙니다. 비밀번호로 로그인해 주세요.',401)
        try:
            user_handle=response.get('response',{}).get('userHandle')
            if not user_handle or base64url_to_bytes(user_handle)!=get_user_id():raise ValueError('wrong user')
            v=verify_authentication_response(credential=response,expected_challenge=challenge['challenge'],expected_rp_id=rp(),expected_origin=app.config['PUBLIC_ORIGIN'],credential_public_key=key['public_key'],credential_current_sign_count=key['sign_count'],require_user_verification=True)
        except Exception:return error('패스키 서명 또는 사용자 확인을 검증하지 못했습니다.',401)
        with getdb() as db:
            n=db.execute('UPDATE passkeys SET sign_count=?,last_used=? WHERE id=? AND sign_count=?',(v.new_sign_count,time.time(),kid,key['sign_count'])).rowcount
        if not n:return error('패스키가 삭제됐거나 다른 인증과 충돌했습니다. 다시 시도해 주세요.',409)
        if purpose=='reauth':return renew_verification()
        res=issue_session(bool(challenge['remember']),kid);res.delete_cookie('memo_pk_flow',path='/api/passkeys/login');return res
