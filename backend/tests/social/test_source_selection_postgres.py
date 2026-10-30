"""Owned current-head PG; actual native writer and committed reader controls."""
from sqlalchemy import event,func,select
from test_b83_generation_postgres import pg,no_publication
from test_native_financial_changes_postgres import ingest_revenue
from test_api_admin import make_client
from social.generation.models import SourceCursor,SourceEvent
from social.models import SocialPost,SocialCommandReceipt


def test_actual_source_navigation_is_private_readonly_and_binds_current_job(pg,tmp_path,monkeypatch):
    factory,engine=pg
    job,record=ingest_revenue(factory,tmp_path,monkeypatch)
    client=make_client(engine);path='/api/v1/admin/social/generation/source-records'
    statements=[]
    def trace(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(engine,'before_cursor_execute',trace)
    try:
        response=client.get(path,params=dict(domain='revenue_by_source',ingestion_id=job,reports='false'))
    finally:event.remove(engine,'before_cursor_execute',trace)
    assert response.status_code==200,response.text
    result=response.json();assert record in result['record_ids'] and result['total']>=5
    assert response.headers['cache-control']=='private, no-store'
    assert any('REPEATABLE READ READ ONLY' in sql for sql in statements)
    assert not any(sql.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','ALTER','CREATE')) for sql in statements)
    with factory() as db:
        for model in (SourceCursor,SourceEvent,SocialPost,SocialCommandReceipt):
            assert db.scalar(select(func.count()).select_from(model))==0
    newer,_=ingest_revenue(factory,tmp_path,monkeypatch,extra=b'<!-- newer source -->')
    assert client.get(path,params=dict(domain='revenue_by_source',ingestion_id=job)).status_code==422
    assert client.get(path,params=dict(domain='pending_bills',ingestion_id=newer)).status_code==422
    assert client.get(path,params=dict(domain='revenue_by_source',ingestion_id=newer)).status_code==200
    private=make_client(engine,authenticated=False).get(path,params=dict(domain='revenue_by_source',ingestion_id=newer))
    assert private.status_code in (401,403) and private.headers['cache-control']=='private, no-store'
    no_publication(factory)
