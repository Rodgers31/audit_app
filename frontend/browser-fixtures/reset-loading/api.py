"""Owned loopback performance fixture; all identities and financial data are synthetic."""
import sys, os, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'backend/tests'))
import legacy_browser_fixture_api as fixture
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
@fixture.main.app.middleware('http')
async def auth_fixture(request, call_next):
    actor = '00000000-0000-4000-8000-000000000001'
    if request.url.path == '/auth/v1/user':
        return JSONResponse(dict(id=actor, aud='authenticated', role='authenticated', email='local@example.invalid', app_metadata={}, user_metadata={}))
    if request.url.path == '/rest/v1/profiles':
        return JSONResponse(dict(id=actor, roles=['admin'], email='local@example.invalid', display_name='Synthetic administrator'))
    return await call_next(request)
fixture.main.app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:33508'], allow_methods=['*'], allow_headers=['*'])
import uvicorn
try:
    uvicorn.run(fixture.main.app, host='127.0.0.1', port=33518)
finally:
    shutil.rmtree(fixture.ROOT)
