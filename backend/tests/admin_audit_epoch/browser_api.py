"""Owned loopback browser fixture using the migration and production router."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

BACKEND=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BACKEND))
if os.getenv('ISSUE611_OWNED_POSTGRES')!='1' or os.getenv('PYTHON_DOTENV_DISABLED')!='1':
    raise RuntimeError('Explicit owned fixture and disabled dotenv required')
port=os.getenv('ISSUE611_PG_PORT','55534')
if port not in ('55534','55545'):raise RuntimeError('Explicit permitted epoch port required')
API_PORT,UI_PORT=(18045,13045) if port=='55545' else (18034,13034)

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
import supabase_admin
from database import get_db
from models import AdminAuditLog
from routers.admin_audit_log import PRIVATE, router
from supabase_auth import _decode_supabase_jwt

ACTOR='00000000-0000-4000-8000-000000000001'
name='batch12_audit_browser_'+uuid4().hex
roles=[name+'_r',name+'_w']
created_roles=[]
admin=create_engine(f'postgresql+psycopg2://inert:inert@127.0.0.1:{port}/issue611',isolation_level='AUTOCOMMIT')
owner=reader=writer=None
created=False
cleaned=False


def cleanup():
    global cleaned
    if cleaned:return
    for engine in (reader,writer,owner):
        if engine is not None:engine.dispose()
    with admin.connect() as c:
        if created:c.execute(text(f'DROP DATABASE "{name}"'))
        for role in created_roles:
            if c.scalar(text('SELECT EXISTS(SELECT FROM pg_roles WHERE rolname=:r)'),{'r':role}):
                c.execute(text(f'DROP ROLE "{role}"'))
        if c.scalar(text('SELECT EXISTS(SELECT FROM pg_database WHERE datname=:n)'),{'n':name}):
            raise RuntimeError('Owned browser database cleanup unverified')
        if c.scalar(text('SELECT EXISTS(SELECT FROM pg_roles WHERE rolname=ANY(:roles))'),{'roles':roles}):
            raise RuntimeError('Owned browser role cleanup unverified')
    cleaned=True


try:
    with admin.connect() as c:
        identity=c.execute(text("SELECT current_database(),current_user,pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()")).one()
        if identity!=('issue611','inert','inert'):raise RuntimeError('Owned epoch database identity required')
        if int(c.scalar(text('SELECT pg_current_xact_id()::text')))<=2**32:raise RuntimeError('Actual epoch one required')
        c.execute(text(f'CREATE DATABASE "{name}" OWNER inert'));created=True
    url=admin.url.set(database=name).render_as_string(hide_password=False)
    result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=BACKEND,
        env={'PATH':os.environ['PATH'],'DATABASE_URL':url,'PYTHON_DOTENV_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(BACKEND)},
        capture_output=True,text=True,timeout=90)
    if result.returncode:raise RuntimeError('Owned browser migration failed: '+result.stderr)
    owner=create_engine(url)
    with owner.begin() as c:
        if c.scalar(text('SELECT version_num FROM alembic_version'))!='a611b12a0001':raise RuntimeError('Owned browser migration head mismatch')
        if c.scalar(text('SELECT certified FROM admin_audit_storage')) is not False:raise RuntimeError('Migration unexpectedly certified storage')
        scope=c.scalar(text('SELECT incarnation::text FROM admin_audit_storage'))
        c.execute(text('UPDATE admin_audit_storage SET certified=true'))
    with admin.connect() as c:
        for role,group in zip(roles,('audit_log_reader','audit_log_writer')):
            c.execute(text(f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD \'inert\''))
            created_roles.append(role)
            c.execute(text(f'GRANT {group} TO "{role}"'))
    reader=create_engine(make_url(url).set(username=roles[0]),isolation_level='REPEATABLE READ')
    writer=create_engine(make_url(url).set(username=roles[1]))
    os.environ['ADMIN_AUDIT_INCARNATION']=scope
    os.environ['ADMIN_AUDIT_BOOKMARK_KEY']='ab'*32
    os.environ.pop('ADMIN_AUDIT_DATABASE_URL',None)
    with sessionmaker(bind=writer)() as db:
        for i in range(28):
            db.add(AdminAuditLog(actor_id=ACTOR,action='etl.trigger',target_type='etl_source',target_id='cob',
                payload={'job_id':i+1,'dry_run':True,'access_token':'INERT_SECRET'},created_at=datetime.now(timezone.utc)))
        db.commit()
except BaseException:
    cleanup();admin.dispose();raise

supabase_admin.get_profile=lambda uid:{'id':uid,'roles':['admin'] if uid==ACTOR else ['citizen'],'email':'admin@example.invalid'}


@asynccontextmanager
async def lifespan(app):
    try:yield
    finally:cleanup();admin.dispose()


app=FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[f'http://127.0.0.1:{UI_PORT}'],allow_methods=['GET','POST'],allow_headers=['*'])
app.include_router(router)


def sessions():
    with sessionmaker(bind=reader)() as db:yield db


app.dependency_overrides[get_db]=sessions


def identity(request):
    bearer=request.headers.get('authorization','')
    if not bearer.startswith('Bearer '):raise HTTPException(401)
    return _decode_supabase_jwt(bearer[7:])['sub']


@app.get('/health')
def health():
    with owner.connect() as c:return {'fixture':'issue611-durable','snapshot':c.scalar(text('SELECT pg_current_snapshot()::text'))}


@app.get('/rest/v1/profiles')
def profiles(request:Request):
    return JSONResponse(supabase_admin.get_profile(identity(request)),headers=PRIVATE)


@app.get('/auth/v1/user')
def user(request:Request):
    return {'id':identity(request),'aud':'authenticated','role':'authenticated','email':'admin@example.invalid',
        'app_metadata':{},'user_metadata':{},'created_at':datetime.now(timezone.utc).isoformat()}


@app.post('/__fixture/unavailable')
def unavailable():
    with owner.begin() as c:c.execute(text('UPDATE admin_audit_storage SET certified=false'))
    return JSONResponse({'ready':False},headers=PRIVATE)


@app.post('/__fixture/restore-ready')
def restore_ready():
    with owner.begin() as c:c.execute(text('UPDATE admin_audit_storage SET certified=true'))
    return JSONResponse({'ready':True},headers=PRIVATE)


@app.post('/__fixture/cleanup')
def cleanup_endpoint():
    cleanup()
    return {'tables':0,'roles':0}


if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=API_PORT)
