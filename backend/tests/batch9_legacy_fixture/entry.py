"""Call supported legacy entry paths in a separate OS process."""
import asyncio
import os
import sys
from datetime import datetime

from etl.database_loader import DatabaseLoader
from etl.kenya_pipeline import KenyaDataPipeline

async def main():
    entry = sys.argv[1]
    loader = DatabaseLoader()
    record = {"title": "Owned inert audit", "url": "https://fixture.invalid/legacy.pdf", "file_path": "inert",
              "publisher": "Inert fixture", "doc_type": "audit", "fetch_date": datetime.now(), "md5": "owned-legacy", "metadata": {}}
    findings = [{"finding_text": "legacy inert finding", "severity": "info", "entity": {"canonical_name": "Inert entity", "type": "agency"}}]
    if entry == "document":
        await loader.load_audit_findings_document(record, findings)
    elif entry == "pipeline":
        result = await KenyaDataPipeline(storage_path=os.environ["BACKFILL_STORAGE"]).download_and_process_document(
            {"url": "https://fixture.invalid/report.pdf", "source_key": "oag", "title": "Owned inert audit", "source": "Inert fixture", "doc_type": "audit"})
        if not result:
            raise RuntimeError("Pipeline refused/failed")
    elif entry == "country":
        await loader.ensure_country_exists("ZZZ")
    elif entry == "entity":
        await loader.ensure_entity_exists({"canonical_name": "Manual inert", "type": "agency"}, 1)
    elif entry == "period":
        await loader.ensure_fiscal_period_exists({"label": "INERT", "start_date": datetime(2024, 1, 1).date(), "end_date": datetime(2024, 12, 31).date()}, 1)
    elif entry == "session":
        from models import Audit, Severity
        db = loader.get_db_session()
        try:
            db.add(Audit(entity_id=1, period_id=1, source_document_id=1, finding_text="legacy inert finding", severity=Severity.INFO, provenance=[]))
            db.commit()
        finally:
            db.close()
    elif entry == "worker-once":
        from etl.worker import run_once
        run_once({"BACKFILL_SOURCES": "oag"})
    elif entry == "scheduler-once":
        from etl.scheduler import run_once
        await run_once()
    print("BATCH9_LEGACY_RETURN", entry, flush=True)

asyncio.run(main())
