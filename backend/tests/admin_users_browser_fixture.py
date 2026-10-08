"""Users lane loopback fixture. Synthetic identities; all provider I/O is fake."""
import os
import sys
import tempfile
from pathlib import Path
allowed = {k:os.environ[k] for k in ('PATH','TMPDIR') if k in os.environ}
os.environ.clear(); os.environ.update(allowed)
os.environ.update(PYTHON_DOTENV_DISABLED='1',DATABASE_URL='postgresql+psycopg2://fixture:fixture@127.0.0.1:55471/fixture')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from copy import deepcopy
from routers import admin_users as subject
import supabase_auth
import database
from models import AdminAuditLog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uuid import UUID
ACTOR='22222222-2222-4222-8222-222222222222'
IDS=[str(UUID(int=i+1)) for i in range(41)]
users=[{'id':uid,'email':f'user{i}@example.invalid','created_at':'2026-10-01T00:00:00Z','app_metadata':{},'user_metadata':{}} for i,uid in enumerate(IDS)]
users.append({'id':ACTOR,'email':'admin@example.invalid','app_metadata':{},'user_metadata':{}})
initial_users=deepcopy(users)
profiles={u['id']:{'id':u['id'],'roles':['admin'] if u['id']==ACTOR else ['citizen'],'display_name':None} for u in users}
initial_profiles=deepcopy(profiles)
def get_user(uid):
    row=next((u for u in users if u['id']==uid),None)
    if row is None:raise subject.supabase_admin.SupabaseAdminError(404,{})
    return row.copy()
def roles(uid,new):
    profiles[uid]['roles']=list(new);return profiles[uid].copy()
def delete(uid):
    users[:]=[u for u in users if u['id']!=uid];profiles.pop(uid,None);return {}
subject.supabase_admin.list_users=lambda *,page=1,per_page=50:{'users':users[(page-1)*per_page:page*per_page]}
subject.supabase_admin.get_user=get_user
subject.supabase_admin.get_profiles=lambda ids:[profiles[uid].copy() for uid in ids if uid in profiles]
subject.supabase_admin.get_profile=lambda uid:profiles.get(uid)
subject.supabase_admin.update_profile_roles=roles
subject.supabase_admin.delete_user=delete
subject.supabase_admin.generate_recovery_link=lambda *a,**k:{'action_link':'https://example.invalid/inert-generated-not-sent'}
subject.supabase_admin.send_password_reset=lambda *a,**k:{}
subject.supabase_admin.count_profiles=lambda **k:len(profiles) if not k else sum('admin' in p['roles'] for p in profiles.values())
supabase_auth._decode_supabase_jwt=lambda token:{'sub':ACTOR,'email':'admin@example.invalid'} if token=='fixture-token' else (_ for _ in ()).throw(Exception('fixture invalid token'))
supabase_auth._fetch_roles=lambda uid:('admin@example.invalid',['admin'])
root=Path(tempfile.mkdtemp(prefix='batch6-users-browser-'))
engine=create_engine('postgresql+psycopg2://fixture:fixture@127.0.0.1:55471/fixture')
AdminAuditLog.__table__.create(engine)
database.SessionLocal=sessionmaker(bind=engine)
app=FastAPI();app.include_router(subject.router)
app.dependency_overrides[database.get_db]=lambda:None
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3151'],allow_methods=['*'],allow_headers=['*'])
@app.post('/fixture/reset')
def reset():
    users[:]=deepcopy(initial_users); profiles.clear(); profiles.update(deepcopy(initial_profiles))
    with database.SessionLocal() as db:
        db.query(AdminAuditLog).delete();db.commit()
    return {'synthetic':True}
@app.get('/fixture/audit')
def audit_rows():
    with database.SessionLocal() as db:
        return [{'action':row.action,'target_id':row.target_id} for row in db.query(AdminAuditLog).order_by(AdminAuditLog.id)]
@app.get('/health')
def health():return {'synthetic':True,'provider':'fake','audit':'disposable postgres'}
@app.get('/auth/v1/user')
def auth_user():return {'id':ACTOR,'email':'admin@example.invalid','aud':'authenticated','role':'authenticated','app_metadata':{},'user_metadata':{}}
@app.get('/rest/v1/profiles')
def profile():return {'id':ACTOR,'email':'admin@example.invalid','display_name':'Fixture admin','roles':['admin']}
@app.get('/api/v1/account/watchlist')
def watchlist():return []
# Assert no fixture can make outbound provider traffic.
httpx.Client.request=lambda *a,**k:(_ for _ in ()).throw(AssertionError('external HTTP blocked by users fixture'))
if __name__=='__main__':
    import uvicorn
    import shutil
    try:uvicorn.run(app,host='127.0.0.1',port=8151)
    finally:AdminAuditLog.__table__.drop(engine);engine.dispose();shutil.rmtree(root)
