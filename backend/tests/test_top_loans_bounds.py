"""Actual top-loans handler over an owned bounded query port."""
from decimal import Decimal
from inspect import unwrap
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def fixture_client(monkeypatch, *, cached=False):
    import main
    from models import Loan
    import services.figure_qualification as figures
    monkeypatch.setattr(figures, 'qualify_rows', lambda db, table, rows:{row.id:{} for row in rows})
    calls = []
    row = Loan(id=1,entity_id=1,lender='Owned local loan',principal=Decimal('100'),
               outstanding=Decimal('80'),currency='KES')
    class Query:
        def __init__(self, model): self.model,self.bound = model,None
        def filter(self, *args): return self
        def first(self): return SimpleNamespace(id=1)
        def count(self): return 1000
        def order_by(self, *args): return self
        def limit(self, value): self.bound=value;return self
        def all(self):
            assert self.bound is not None and 1 <= self.bound <= 100, 'Unbounded loan-row transfer reached the query port'
            calls.append(self.bound)
            return [row]
    db = SimpleNamespace(query=lambda model:Query(model))
    app = FastAPI()
    app.add_api_route('/top',main.get_top_loans if cached else unwrap(main.get_top_loans),methods=['GET'])
    app.dependency_overrides[main.get_db] = lambda:db
    return TestClient(app),calls


@pytest.mark.parametrize('limit', [-1,0,101,2147483647])
def test_invalid_top_loan_cohorts_are_refused_before_query(monkeypatch, limit):
    client,calls = fixture_client(monkeypatch)
    with client:
        assert client.get('/top',params={'limit':limit}).status_code == 422
    assert calls == []


def test_top_loan_sql_transfer_is_bounded_while_total_retains_coverage(monkeypatch):
    client,calls = fixture_client(monkeypatch)
    with client:
        response = client.get('/top',params={'limit':3})
    assert response.status_code == 200,response.text
    assert response.json()['total_available'] == 1000
    assert len(response.json()['loans']) == 1
    assert calls == [3]


def test_actual_cached_top_loans_route_serves_cold_and_warm_requests(monkeypatch):
    import main
    values = {}
    cache = SimpleNamespace(get=lambda key:values.get(key),set=lambda key,value,ttl:values.__setitem__(key,value))
    monkeypatch.setattr(main,'redis_cache',cache)
    client,calls = fixture_client(monkeypatch,cached=True)
    with client:
        first = client.get('/top',params={'limit':3})
        second = client.get('/top',params={'limit':3})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert calls == [3]
