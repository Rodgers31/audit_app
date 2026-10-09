"""Loopback Operations browser fixture: real routes, isolated DB, inert auth."""
import atexit
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_allowed = {key:os.environ[key] for key in ('PATH','HOME','TMPDIR') if key in os.environ}
os.environ.clear()
os.environ.update(_allowed)
root = Path(tempfile.mkdtemp(prefix='auditgava-operations-batch6-browser-'))
atexit.register(lambda: shutil.rmtree(root))
os.environ.update(PYTHON_DOTENV_DISABLED='1', DATABASE_URL=f'sqlite:///{root / "fixture.sqlite"}')
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
import database
import supabase_auth
from models import IngestionJob, IngestionStatus
from routers import admin, etl_admin

# Reject external transports before any auth handler/route can use one.
def blocked(*args, **kwargs):
    raise RuntimeError('External HTTP is disabled in the Operations fixture')
httpx.HTTPTransport.handle_request = blocked
httpx.AsyncHTTPTransport.handle_async_request = blocked
ADMIN = '00000000-0000-4000-8000-000000000001'
VIEWER = '00000000-0000-4000-8000-000000000002'
def claims(token):
    try:
        if not token.endswith('.inert-signature'):
            raise ValueError('Not an inert token')
        body = json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
        if body['sub'] not in (ADMIN,VIEWER):
            raise ValueError('Unknown inert identity')
        return body
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid fixture credential') from None
supabase_auth._decode_supabase_jwt = claims
supabase_auth._fetch_roles = lambda uid: ('operations@example.invalid',['admin'] if uid == ADMIN else ['user'])
IngestionJob.__table__.create(database.engine)
now = datetime.now(timezone.utc).replace(tzinfo=None)
with database.SessionLocal() as db:
    for i in range(45):
        db.add(IngestionJob(domain='audits' if i % 2 else 'counties_budget',
            status=IngestionStatus.FAILED if i % 3 == 0 else IngestionStatus.COMPLETED,
            dry_run=i % 4 == 0, started_at=now-timedelta(minutes=i),
            finished_at=now-timedelta(minutes=i)+timedelta(seconds=3),
            items_processed=i,items_created=i//2,items_updated=i//3,
            errors=['PRIVATE_DIAGNOSTIC'] if i % 3 == 0 else [],
            meta={'source_mode':'fixture','private':'PRIVATE_METADATA'}))
    db.commit()
app = FastAPI()
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3152'],allow_methods=['GET','POST'],allow_headers=['*'])
app.include_router(admin.router)
app.include_router(etl_admin.router)
@app.get('/health')
def health():
    return {'synthetic':True,'database':'disposable SQLite','port':8152}
@app.get('/auth/v1/user')
def user(request:Request):
    claim=claims(request.headers.get('authorization','').removeprefix('Bearer '))
    return {'id':claim['sub'],'aud':'authenticated','role':'authenticated','email':'operations@example.invalid',
        'app_metadata':{},'user_metadata':{},'created_at':'2026-01-01T00:00:00Z'}
@app.get('/rest/v1/profiles')
def profiles(request:Request):
    uid=claims(request.headers.get('authorization','').removeprefix('Bearer '))['sub']
    profile={'id':uid,'email':'operations@example.invalid','display_name':'Inert Operations Admin',
        'roles':['admin'] if uid==ADMIN else ['user']}
    return profile if 'object+json' in request.headers.get('accept','') else [profile]
if __name__=='__main__':
    import uvicorn
    print('Operations fixture: isolated SQLite, synthetic identities, real routers, external HTTP blocked, 127.0.0.1:8152',flush=True)
    uvicorn.run(app,host='127.0.0.1',port=8152)
