"""Build the checked-in OpenAPI document using only the standard library."""
import json
from pathlib import Path
S={'type':'string'};B={'type':'boolean'};I={'type':'integer'};U={'type':'string','format':'uuid'};D={'type':'string','format':'date-time'}
fields={'title':{'type':'string','maxLength':500},'body':{'type':'string','maxLength':2000000},'tags':{'type':'array','maxItems':50,'items':{'type':'string','minLength':1,'maxLength':80}},'starred':B,'archived':B,'deleted':B,'folder_id':{'type':['string','null'],'format':'uuid'}}
ref=lambda name:{'$ref':'#/components/schemas/'+name}
schemas={
 'CreateNote':{'type':'object','description':'Title or body must contain content; whitespace and empty list/checklist placeholders are rejected.','properties':{'id':U,**fields}},
 'PatchNote':{'type':'object','required':['version'],'properties':{'version':{'type':'integer','minimum':1},**fields}},
 'Attachment':{'type':'object','properties':{'id':U,'note_id':U,'name':S,'mime':S,'size':I,'created_at':D}},
 'Note':{'type':'object','properties':{'id':U,**fields,'version':I,'created_at':D,'updated_at':D,'display_title':S,'attachments':{'type':'array','items':ref('Attachment')}}},
 'Summary':{'type':'object','description':'No full body or attachment payload','properties':{'id':U,**{k:v for k,v in fields.items() if k!='body'},'version':I,'created_at':D,'updated_at':D,'display_title':S,'snippet':S,'thumbnail_url':{'type':['string','null'],'description':'Authenticated URL of the first inline image belonging to this note; null if none'}}},
 'Page':{'type':'object','properties':{'items':{'type':'array','items':ref('Summary')},'total':I,'offset':I,'next_offset':{'type':['integer','null']},'terms':{'type':'array','items':S}}},
 'Error':{'type':'object','properties':{'error':S,'code':S,'current':ref('Note')}}
}
paths={}
def operation(path,method,summary,out=None,body=None,status='200',owner=False,public=False,parameters=None,content_type='application/json'):
    security=[] if public else [{'cookieAuth':[]}] if owner else [{'bearerAuth':[]},{'cookieAuth':[]}]
    op={'summary':summary,'security':security,'responses':{status:{'description':'Success','content':{content_type:{'schema':out or {'type':'object'}}}},**{str(s):{'description':desc,'content':{'application/json':{'schema':ref('Error')}}} for s,desc in [(400,'Invalid input'),(401,'Authentication required'),(403,'Forbidden or CSRF'),(404,'Not found'),(409,'Version conflict; current contains latest note'),(413,'Too large'),(429,'Too many authentication attempts'),(428,'Version required or REAUTH_REQUIRED for sensitive owner actions'),(503,'Storage or server failure')]}}}
    ps=parameters or []
    for name in ['id']:
        if '{'+name+'}' in path:ps=[{'name':name,'in':'path','required':True,'schema':S if path.startswith('/passkeys/') else U}]+ps
    if method not in ('get','head') and not public:
        ps=ps+[{'name':'X-CSRF-Token','in':'header','required':False,'description':'Required with cookie session. Bearer token needs no CSRF header.','schema':S}]
    if ps:op['parameters']=ps
    if body:op['requestBody']={'required':True,'content':body}
    paths.setdefault(path,{})[method]=op
jb=lambda schema:{'application/json':{'schema':schema}}
obj=lambda props,required:{'type':'object','properties':props,'required':required}
queries={'folder_id':{'type':'string','description':'Folder UUID, or none for unfiled notes'},'q':{'type':'string','maxLength':300,'description':'Whitespace AND, case-insensitive English, Korean substring; maximum 12 terms'},'state':{'type':'string','enum':['active','all','starred','archive','trash'],'default':'active'},'sort':{'type':'string','enum':['newest','oldest'],'default':'newest'},'from':D,'to':D,'tag':S,'limit':{'type':'integer','default':40,'minimum':1,'maximum':100},'offset':{'type':'integer','default':0,'minimum':0,'maximum':1000000}}
operation('/folders','get','List folders with non-deleted note counts and unfiled count')
operation('/folders','post','Create folder',body=jb(obj({'name':{'type':'string','minLength':1,'maxLength':80}},['name'])),status='201')
operation('/folders/{id}','patch','Rename folder with optimistic version check',body=jb(obj({'name':{'type':'string','minLength':1,'maxLength':80},'version':I},['name','version'])))
operation('/notes','get','List/search note summaries; from inclusive, to exclusive; archived included in active',ref('Page'),parameters=[{'name':k,'in':'query','schema':v} for k,v in queries.items()])
operation('/notes','post','Create note (write scope)',ref('Note'),jb(ref('CreateNote')),status='201')
operation('/notes/trash','post','Move selected notes to trash atomically; any stale version rejects the batch',obj({'deleted':I},['deleted']),jb(obj({'items':{'type':'array','minItems':1,'maxItems':1000,'items':obj({'id':U,'version':I},['id','version'])}},['items'])))
operation('/notes/{id}','get','Get note and attachment metadata',ref('Note'))
operation('/notes/{id}','patch','Update with optimistic version check (write scope)',ref('Note'),jb(ref('PatchNote')))
operation('/notes/{id}','delete','Move to trash with version check (write scope)',ref('Note'),jb(obj({'version':I},['version'])))
operation('/notes/{id}/copy','post','Create separate copy with duplicated attachments (write scope)',ref('Note'),jb(obj(fields,[])),status='201')
operation('/notes/{id}/attachments','post','Attach file and insert Markdown link atomically; version 0 with note creates a new note (write scope)',ref('Note'),{'multipart/form-data':{'schema':obj({'file':{'type':'string','format':'binary'},'version':I,'offset':{'type':'integer','minimum':0,'description':'Unicode code point offset; defaults to body end'},'note':{'type':'string','description':'JSON note fields for atomic creation with version 0'}},['file','version'])}},status='201')
operation('/attachments/{id}','get','Authenticated attachment bytes',{'type':'string','format':'binary'},content_type='application/octet-stream')
operation('/login','post','Password login; sets HttpOnly cookie',obj({'csrf':S},['csrf']),jb(obj({'password':S,'remember':{'type':'boolean','default':True}},['password'])),public=True)
operation('/session','get','Get session CSRF and instance',obj({'csrf':{'type':['string','null']},'instance':U},['csrf','instance']))
operation('/logout','post','Revoke current browser session')
operation('/password','post','Change password and revoke all browser sessions',body=jb(obj({'password':{'type':'string','minLength':12,'maxLength':1024}},['password'])),owner=True)
operation('/tokens','get','List external token metadata',owner=True)
operation('/tokens','post','Issue external token; secret shown once',obj({'id':U,'token':S},['id','token']),jb(obj({'name':S,'scope':{'type':'string','enum':['read','write']}},['name','scope'])),status='201',owner=True)
operation('/tokens/{id}','delete','Revoke external token',owner=True)
operation('/export','get','Export all notes and attachments as v1 ZIP',{'type':'string','format':'binary'},owner=True,content_type='application/zip')
operation('/import/preview','post','Validate v1 ZIP; preview additions and skips; no note writes',body={'multipart/form-data':{'schema':obj({'file':{'type':'string','format':'binary'}},['file'])}},owner=True)
operation('/import/commit','post','Import preview within 30 minutes; skip existing IDs atomically',obj({'created':I,'skipped':I},['created','skipped']),jb(obj({'preview_id':U},['preview_id'])),owner=True)
operation('/auth/config','get','Public passkey origin and availability',public=True)
operation('/reauth/password','post','Verify password again; rotate session cookie without extending expiry',body=jb(obj({'password':S},['password'])),owner=True)
operation('/sessions','get','List active browser sessions',owner=True)
operation('/sessions/{id}','delete','Revoke browser session; recent verification required',owner=True)
operation('/sessions/revoke-others','post','Revoke all other browser sessions; recent verification required',owner=True)
operation('/passkeys','get','List passkey metadata',owner=True)
operation('/passkeys/{id}','delete','Delete passkey and its login sessions; recent verification required',owner=True)
for purpose in ('register','login','reauth'):
    for step in ('options','verify'):
        body=obj({'remember':{'type':'boolean','default':True}},[]) if step=='options' else obj({'challenge_id':U,'response':{'type':'object','description':'WebAuthn credential JSON with base64url binary fields'},'name':{'type':'string','maxLength':80}},['challenge_id','response'])
        operation('/passkeys/'+purpose+'/'+step,'post','WebAuthn '+purpose+' '+step+'; fixed Origin and one-use challenge; register needs recent verification',body=jb(body),status='201' if purpose=='register' and step=='verify' else '200',owner=purpose!='login',public=purpose=='login',parameters=[{'name':'X-Passkey-Request','in':'header','required':True,'schema':{'type':'string','const':'1'}},{'name':'Origin','in':'header','required':True,'schema':S,'description':'Must equal MEMO_PUBLIC_ORIGIN'}])
doc={'openapi':'3.1.0','info':{'title':'한줄 개인 메모 API','version':'1.1.0','description':'Single-owner notes API. Bearer read scope allows GET; write scope permits note mutations. Token administration/export/import require owner cookie. Cookie mutations require CSRF. Sensitive owner actions require verification within 5 minutes; 428 code REAUTH_REQUIRED prompts password or passkey verification. Remembered sessions last 30 days from login, otherwise 12 hours with session cookie.'},'servers':[{'url':'http://localhost:8787/api'}],'paths':paths,'components':{'securitySchemes':{'bearerAuth':{'type':'http','scheme':'bearer'},'cookieAuth':{'type':'apiKey','in':'cookie','name':'memo_session'}},'schemas':schemas}}
Path('docs/openapi.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
