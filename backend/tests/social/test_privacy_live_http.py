"""Real loopback HTTP smoke; owns its socket/server and closes both."""
import socket
import time
from threading import Thread
import httpx
import uvicorn
from fastapi import FastAPI
from test_privacy_http import client
from test_privacy_support import db, config, signed
from social.privacy.api import DATA_PATH, STATUS_PATH


def test_real_loopback_http_callback_and_status(db,config):
    app=client(db,config).app
    sock=socket.socket()
    sock.bind(('127.0.0.1',0))
    port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False,lifespan='off',ws='none'))
    thread=Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
    thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and time.monotonic()<deadline:
            time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=5) as browser:
            response=browser.post(DATA_PATH,data={'signed_request':signed(config)})
            assert response.status_code==200
            result=response.json()
            assert browser.post(DATA_PATH,data={'signed_request':signed(config)}).json()==result
            status=browser.get(STATUS_PATH,params={'code':result['confirmation_code']})
            assert status.status_code==200 and status.json()['deletion_completed'] is False
            assert browser.get(STATUS_PATH,params={'code':'0'*64}).status_code==404
    finally:
        server.should_exit=True
        thread.join(5)
        sock.close()
    assert not thread.is_alive()
