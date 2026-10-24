"""Subprocess fixture: only bounded source transport is injected; CLI stays real."""
import os
if os.environ.get('B66_SOURCE_CHILD') == 'true':
    try:
        from datetime import datetime, timezone
        from pathlib import Path
        import socket
        import time
        from urllib.parse import urlsplit
        import httpx
        from sqlalchemy import text, event
        from sqlalchemy.orm import Session
        target = urlsplit(os.environ['DATABASE_URL'])
        if (target.hostname != '127.0.0.1' or target.port != 56973 or target.username != 'batch11_602'
                or target.password != 'inert-owned-602' or not target.path.startswith('/batch11_602_')):
            raise RuntimeError('Unowned fixture target refused')
        original_connect = socket.socket.connect
        def local_only(sock, address):
            if not isinstance(address, tuple) or address[:2] != ('127.0.0.1',56973):
                raise RuntimeError('Nonfixture transport refused')
            return original_connect(sock,address)
        socket.socket.connect = local_only
        from database import SessionLocal
        from seeding.domains.opendata import discovery as d, source
        from models import Extraction
        original_discover = d.discover
        payload = (Path(__file__).resolve().parents[2] / 'fixtures/opendata/Chapter-5-Public-Finance.xlsx').read_bytes()
        def mode():
            with SessionLocal() as db: return db.scalar(text('SELECT mode FROM batch11_control'))
        def barrier():
            end = time.monotonic()+25
            while time.monotonic() < end:
                if mode() == 'normal': return
                time.sleep(.03)
            raise RuntimeError('Owned discovery barrier deadline')
        def respond(request):
            state = mode()
            if str(request.url) == d.INDEX:
                with SessionLocal.begin() as db:
                    owners = db.execute(text("SELECT c.id,c.command_id FROM seeding_domain_claims c JOIN ingestion_jobs j ON j.metadata->>'seeding_claim_id'=c.id::text WHERE c.domain='opendata' AND c.entered_at IS NOT NULL AND c.returned_at IS NULL AND c.released_at IS NULL AND j.domain='opendata' AND j.status='RUNNING' LIMIT 2")).all()
                    if len(owners) != 1: raise RuntimeError('Exact live owner missing before discovery')
                    db.execute(text("INSERT INTO batch11_markers(stage,claim_id,command_id) VALUES ('discovery',:claim,:command)"), {'claim':owners[0].id,'command':owners[0].command_id})
                if state == 'before': barrier()
            if state == 'failure': return httpx.Response(503)
            if str(request.url) == d.INDEX:
                body = f'<a href="{source.REPORT_URL}">Survey</a>'.encode(); kind = 'text/html'
            elif str(request.url) == source.REPORT_URL:
                body = f'<a href="{source.URL}">Chapter5</a>'.encode(); kind = 'text/html'
            elif str(request.url) == source.URL:
                body = payload + (b'unknown-reissue' if state == 'candidate' else b''); kind = source.CONTENT_TYPE
            else: raise RuntimeError('Unexpected fixture source URL')
            return httpx.Response(200, headers={'content-type':kind,'etag':'"owned-v1"'}, stream=httpx.ByteStream(body))
        def discover(settings,previous=None,**kwargs):
            return original_discover(settings,previous,transport=httpx.MockTransport(respond))
        d.discover = discover
        @event.listens_for(Session, 'before_flush')
        def write(session, ctx, instances):
            if any(isinstance(row, Extraction) for row in session.new):
                session.info['b66_wrote'] = True
                if mode() == 'partial': raise RuntimeError('Owned partial persistence failure')
        @event.listens_for(Session, 'after_commit')
        def after(session):
            if session.info.pop('b66_wrote',False) and mode() == 'after':
                with SessionLocal.begin() as db:
                    db.execute(text("INSERT INTO batch11_markers(stage) VALUES ('after')"))
                barrier()
    except BaseException:
        os.write(2,b'B66 fixture initialization failed\n')
        os._exit(70)
