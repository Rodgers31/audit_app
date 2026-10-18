"""Replace only public input transport; native CLI/parser/writer remain real."""
import os

if os.environ.get("B17_OPENDATA_FIXTURE") == "true":
    try:
        from datetime import datetime, timezone
        from hashlib import sha256
        from pathlib import Path
        import socket
        import time
        from urllib.parse import urlsplit

        target = urlsplit(os.environ["DATABASE_URL"])
        if target.hostname != "127.0.0.1" or not target.path.startswith("/batch11_602_") or target.port in (55530, 55532, 55534):
            raise ValueError("Unowned fixture database refused")
        allowed = {(target.hostname, target.port), ("127.0.0.1", int(os.environ.get("BATCH11_602_API_PORT", "18031")))}
        original_connect = socket.socket.connect
        def owned_only(sock, address):
            if not isinstance(address, tuple) or address[:2] not in allowed:
                raise RuntimeError("Unowned transport refused")
            return original_connect(sock, address)
        socket.socket.connect = owned_only
        from sqlalchemy import event, text
        from sqlalchemy.orm import Session
        from database import SessionLocal
        from seeding.domains.opendata import source
        from models import Extraction

        payload = Path(__file__).resolve().parents[3] / "backend/tests/fixtures/opendata/Chapter-5-Public-Finance.xlsx"
        # parents[3] is repository root; an explicit known source fixture, never
        # an ambient caller path or a substitute financial value.
        raw = payload.read_bytes()
        if sha256(raw).hexdigest() != "887712acdb8ec673f96d6d0fd14491a5861b0450d2ffcf49aedde093a257a5d5":
            raise ValueError("Official fixture bytes changed")
        def mode():
            with SessionLocal() as db:
                return db.scalar(text("SELECT mode FROM batch11_control"))
        def barrier():
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                if mode() == "normal":
                    return
                time.sleep(.03)
            raise RuntimeError("Owned source barrier deadline")
        def fetch():
            with SessionLocal.begin() as db:
                owner = db.execute(text("SELECT c.id,c.command_id FROM seeding_domain_claims c JOIN ingestion_jobs j ON j.metadata->>'seeding_claim_id'=c.id::text WHERE c.domain='opendata' AND c.entered_at IS NOT NULL AND c.returned_at IS NULL AND c.released_at IS NULL AND j.domain='opendata' AND j.status='RUNNING' LIMIT 2")).all()
                if len(owner) != 1:
                    raise AssertionError("No exact durable owner before source transport")
                db.execute(text("INSERT INTO batch11_markers(stage,claim_id,command_id) VALUES ('before',:claim,:command)"), {"claim": owner[0].id, "command": owner[0].command_id})
            state = mode()
            if state == "before":
                barrier()
            if state == "failure":
                raise source.OpenDataSourceRefused("Owned source input unavailable")
            return (b"not a workbook" if state == "malformed" else raw), datetime.now(timezone.utc)
        source.fetch_publication = fetch
        @event.listens_for(Session, "before_flush")
        def writes(session, context, instances):
            if any(isinstance(row, Extraction) for row in session.new):
                session.info["batch11_opendata_wrote"] = True
        @event.listens_for(Session, "after_commit")
        def after_commit(session):
            if session.info.pop("batch11_opendata_wrote", False) and mode() == "after":
                with SessionLocal.begin() as db:
                    db.execute(text("INSERT INTO batch11_markers(stage) VALUES ('after')"))
                barrier()
    except BaseException:
        os.write(2, b"Batch11 owned fixture initialization failed\n")
        os._exit(70)
