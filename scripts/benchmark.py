"""Repeatable synthetic 10,000-note benchmark, always in a TemporaryDirectory."""
import json
import statistics
import sys
import tempfile
import time
import sqlite3
import uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app

def run():
    with tempfile.TemporaryDirectory(prefix='hanjul-benchmark-') as temp:
        app=create_app(temp,test_password='benchmark-password')
        db=sqlite3.connect(app.config['DB_PATH']);rows=[]
        for i in range(10000):
            stamp=(datetime(2020,1,1,tzinfo=timezone.utc)+timedelta(minutes=i)).isoformat(timespec='microseconds').replace('+00:00','Z')
            # Mixed short notes, long drafts, URLs, and common Korean words.
            base=['회의에서 생각한 업무 방향과 다음 주 자료 정리. 할 일은 간단하게 적어둔다. ', '오늘 산책에서 떠오른 문장과 개인적인 생각을 기록해둔다. ', 'https://example.org/reference Python 코드와 자료 링크. '][i%3]
            body=(base*(1 if i%10==0 else 450 if i%100==1 else 22))+f'\n고유기록번호{i:05d}'
            if i%47==0:body+='\n프로젝트별 회의록 검토'
            rows.append((str(uuid.uuid4()),'',body,stamp,stamp,'[]',i%19==0,0,0,1))
        start=time.perf_counter()
        with db:db.executemany('INSERT INTO notes VALUES (?,?,?,?,?,?,?,?,?,?)',rows)
        db.execute('PRAGMA optimize');db.close();seed=time.perf_counter()-start
        c=app.test_client();c.post('/api/login',json={'password':'benchmark-password'})
        queries={'list_first':{},'list_offset_9960':{'offset':9960},'korean_3plus':{'q':'프로젝트별'},'korean_2char_common':{'q':'생각'},'korean_1char_common':{'q':'일'},'multi_term':{'q':'젝트 회의록'},'english_case':{'q':'PYTHON'},'no_match':{'q':'존재하지않는단어'}}
        report={'notes':10000,'sqlite':sqlite3.sqlite_version,'body_characters':sum(len(r[2]) for r in rows),'seed_seconds':round(seed,3),'database_mb':round(Path(app.config['DB_PATH']).stat().st_size/1024**2,2),'runs_per_query':25,'results':{}}
        for name,args in queries.items():
            c.get('/api/notes',query_string=args);timings=[]
            for _ in range(25):
                start=time.perf_counter();res=c.get('/api/notes',query_string=args);timings.append((time.perf_counter()-start)*1000)
                assert res.status_code==200,res.json
                assert len(res.json['items'])<=40 and all('body' not in n for n in res.json['items'])
            report['results'][name]={'p50_ms':round(statistics.median(timings),2),'p95_ms':round(sorted(timings)[23],2),'matches':res.json['total'],'response_bytes':len(res.data)}
        print(json.dumps(report,ensure_ascii=False,indent=2))
        Path('docs/benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':run()
