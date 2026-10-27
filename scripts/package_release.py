"""Build a source-only release using an allowlist. Never package live data or secrets."""
import argparse
import hashlib
import tarfile
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
FILES=('app.py','auth.py','schema.sql','requirements.txt','requirements.lock.txt','requirements-dev.txt','README.md','LICENSE','CONTRIBUTING.md','.gitignore','.env.example','Dockerfile','.dockerignore','compose.yaml','compose.nas.yaml','compose.https.yaml')
DIRECTORIES={'static':{'.js','.css','.html','.svg','.png','.webmanifest'},'scripts':{'.py','.sh'},'docs':{'.md','.json','.png'},'tests':{'.py'},'deploy':{'.md','.example','.yaml','.sh'}}

def package(output):
    paths=[ROOT/name for name in FILES]
    for directory,suffixes in DIRECTORIES.items():
        paths.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts and not p.is_symlink())
    paths.append(ROOT/'deploy/server/Caddyfile')
    if any(not p.is_file() or p.is_symlink() for p in paths):raise ValueError('배포 원본 파일이 없거나 심볼릭 링크입니다.')
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz') as archive:
        for path in sorted(paths):archive.add(path,arcname='hanjul/'+str(path.relative_to(ROOT)),recursive=False)
    with output.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(checksum+'  '+output.name+'\n')
    return len(paths)

if __name__=='__main__':
    p=argparse.ArgumentParser(description='실사용 DB·백업·비밀번호·시험 사이트를 제외한 배포 소스 묶음을 만듭니다.')
    p.add_argument('--output',default='releases/hanjul-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.tar.gz');a=p.parse_args()
    count=package(a.output);print(f'소스 배포 묶음: {Path(a.output).resolve()} · {count}개 파일 · SHA-256 파일 생성')
