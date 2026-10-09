"""Owned, subprocess-only sources and registry; product entry points stay real."""
import os

if os.getenv("BATCH9_LEGACY_INERT") == "true":
    try:
        import socket
        import time
        from pathlib import Path
        from types import SimpleNamespace
        from sqlalchemy import event, text
        from sqlalchemy.orm import Session
        from database import SessionLocal
        from models import Audit, Severity
        from seeding.registries import REGISTRY, load_builtin_domains
        from seeding.types import DomainRunResult

        assert os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://") == "postgresql+psycopg2://batch9_legacy:batch9-inert-local@127.0.0.1:55491/batch9-legacy-etl-af79"
        original_connect = socket.socket.connect
        def loopback_only(sock, address):
            if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", 55491):
                raise RuntimeError("External transport forbidden by owned fixture")
            return original_connect(sock, address)
        socket.socket.connect = loopback_only

        def marker(stage, writer):
            with SessionLocal.begin() as db:
                db.execute(text("INSERT INTO batch9_legacy_markers VALUES (:stage,:writer,:pid)"),
                           {"stage": stage, "writer": writer, "pid": os.getpid()})
            print(f"BATCH9_ALIVE {writer} {stage} pid={os.getpid()}", flush=True)

        def mode(writer):
            with SessionLocal() as db:
                return db.scalar(text("SELECT mode FROM batch9_legacy_control WHERE writer=:w"), {"w": writer})

        def await_release(writer):
            deadline = time.monotonic() + 35
            while mode(writer) != "normal":
                if time.monotonic() > deadline:
                    raise RuntimeError("Owned control timed out")
                time.sleep(.04)

        load_builtin_domains()
        REGISTRY._handlers.clear()
        def native(session, settings, context):
            marker("entered", "native")
            phase = mode("native")
            if phase == "before":
                await_release("native")
            session.add(Audit(entity_id=1, period_id=1, finding_text="native inert finding",
                              severity=Severity.INFO, source_document_id=1, provenance=[]))
            if phase == "after" and not context.dry_run:
                session.commit()
                marker("committed", "native")
                await_release("native")
            return DomainRunResult(domain=context_domain, dry_run=context.dry_run, items_processed=1, items_created=1)
        context_domain = os.environ.get("BATCH9_NATIVE_DOMAIN", "audits")
        REGISTRY.register(context_domain, native)

        @event.listens_for(Session, "before_commit")
        def legacy_before_commit(session):
            if not any(isinstance(row, Audit) and row.finding_text == "legacy inert finding" for row in session.new):
                return
            session.info["batch9_audit"] = True
            marker("entered", "legacy")
            if mode("legacy") == "before":
                await_release("legacy")

        @event.listens_for(Session, "after_commit")
        def legacy_after_commit(session):
            if session.info.pop("batch9_audit", False):
                marker("committed", "legacy")
                if mode("legacy") == "after":
                    await_release("legacy")

        # Native seeding is already imported from backend; root etl now takes precedence.
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        # Inert transport/parser inputs; actual download, manifest and loader code runs.
        from etl.kenya_pipeline import KenyaDataPipeline
        original_init = KenyaDataPipeline.__init__
        doc = {"url": "https://fixture.invalid/report.pdf", "source_key": "oag",
               "title": "Owned inert audit", "source": "Inert fixture", "doc_type": "audit"}
        finding = {"finding_text": "legacy inert finding", "severity": "info",
                   "entity": {"canonical_name": "Inert entity", "type": "agency"}}
        def inert_init(self, *args, **kwargs):
            if not args and not kwargs.get("storage_path"):
                kwargs["storage_path"] = os.environ["BACKFILL_STORAGE"]
            original_init(self, *args, **kwargs)
            self.discover_budget_documents = lambda source: [dict(doc)]
            self.http.get = lambda *a, **kw: SimpleNamespace(content=b"%PDF-owned-inert-batch9", headers={"content-type": "application/pdf"}, raise_for_status=lambda: None)
            self.extractor.extract_with_fallback = lambda path: {"confidence": 1., "tables": []}
            self.audit_parser.parse = lambda *a: [dict(finding)]
            self.data_validator.validate_audit_data = lambda item: SimpleNamespace(is_valid=True, confidence=1., warnings=[])
            self._maybe_upload_to_s3 = lambda *a: None
            self.scheduler = SimpleNamespace(get_schedule_summary=lambda: {"efficiency": {"skip_percentage": 0}}, should_run=lambda source: (source == "oag", "inert"), get_next_run=lambda source: ("none", "inert"))
        KenyaDataPipeline.__init__ = inert_init
        print(f"BATCH9_CONFIG domain={context_domain} dispatch={os.getenv('ADMIN_ETL_DISPATCH_ENABLED')} run_on_start={os.getenv('ETL_RUN_ON_START', 'true')} python={__import__('sys').version.split()[0]}", flush=True)
    except BaseException:
        import traceback
        traceback.print_exc()
        os._exit(70)
