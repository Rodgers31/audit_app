"""Actual local Uvicorn/audit emitters, with a matched unsafe positive control.

This certifies process-level filtering only. It cannot observe hosting ingress,
security/CDN records, platform traces, configured drains or their copies.
"""
import io
import logging
import socket
import threading
import time

import httpx
from fastapi import FastAPI
import uvicorn

from middleware.security import AuditLogMiddleware, SecurityHeadersMiddleware, logger as audit_logger
from social.connections.api import service
from social.connections.config import MetaConfig
from social.connections.direct_api import router
from social.connections.service import ConnectionService
from social.http_policy import SocialNoStoreMiddleware
from social.privacy.access_logs import install_private_access_filter


def test_real_emitters_preserve_positive_control_without_callback_query():
    class NoDB:
        def __getattr__(self,name): raise AssertionError('Held transport reached DB')
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[service]=lambda:ConnectionService(NoDB(),MetaConfig())
    @app.get('/ordinary-positive')
    def positive():return {'observed':True}
    app.add_middleware(AuditLogMiddleware);app.add_middleware(SecurityHeadersMiddleware);app.add_middleware(SocialNoStoreMiddleware)
    access_logger=logging.getLogger('uvicorn.access');install_private_access_filter()
    access,audit=io.StringIO(),io.StringIO();handlers=[]
    for logger,stream in [(access_logger,access),(audit_logger,audit)]:
        handler=logging.StreamHandler(stream);handler.setFormatter(logging.Formatter('%(message)s'));logger.addHandler(handler);handlers.append((logger,handler,logger.level));logger.setLevel(logging.DEBUG)
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(8)
    server=uvicorn.Server(uvicorn.Config(app,log_config=None,access_log=True,lifespan='off',timeout_keep_alive=1))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.01)
        assert server.started
        origin='http://127.0.0.1:'+str(sock.getsockname()[1])
        with httpx.Client(trust_env=False,timeout=3) as client:
            assert client.get(origin+'/ordinary-positive?probe=INERT-correlation-control').status_code==200
            response=client.get(origin+'/api/v1/social/oauth/meta/callback?code=INERT-collector-code&state=INERT-collector-state')
            assert response.status_code==503 and 'history.replaceState' in response.text
        lines=access.getvalue().splitlines()
        assert len(lines)==2 and 'INERT-correlation-control' in lines[0]
        assert '503' in lines[1] and '/api/v1/social/oauth/meta/[redacted]' in lines[1]
        assert all(v not in access.getvalue()+audit.getvalue() for v in ('INERT-collector-code','INERT-collector-state'))
        assert 'INERT-correlation-control' in audit.getvalue() and '[redacted]' in audit.getvalue()
    finally:
        server.should_exit=True;thread.join(3);sock.close()
        for logger,handler,level in handlers:logger.removeHandler(handler);logger.setLevel(level)
    assert not thread.is_alive()
