"""Boundary regressions from independent Spec/Standards review; no live I/O."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import time

import pytest

from social.contracts import ReconciliationResult
from social.worker.runner import SocialWorker
from social.platform_budget import x_global_budget_enabled


@pytest.mark.parametrize('value', [None, {}, {'x_budget_microusd': True}, {'x_budget_microusd': False},
    {'x_budget_microusd': '1'}, {'x_budget_microusd': 1.0}, {'x_budget_microusd': 0}, {'x_budget_microusd': -1}])
def test_x_global_gate_requires_a_positive_integer(value):
    assert x_global_budget_enabled(value) is False


def test_x_global_gate_accepts_explicit_positive_budget():
    assert x_global_budget_enabled({'x_budget_microusd': 1}) is True


@pytest.mark.parametrize('seconds,aware,expected', [(241,True,'reconciling'), (None,True,'outcome_unknown'),
    (301,True,'reconciling'), (302,True,'outcome_unknown'), (0,True,'outcome_unknown'),
    (-1,True,'outcome_unknown'), (30,False,'outcome_unknown')])
def test_bounded_reconciliation_wait_never_authorizes_a_mutation(seconds,aware,expected):
    now=datetime(2026,10,16,tzinfo=timezone.utc)
    next_at=now+timedelta(seconds=seconds) if seconds is not None else None
    if next_at is not None and not aware:
        next_at=next_at.replace(tzinfo=None)
    worker=object.__new__(SocialWorker)
    saved=[]
    async def save(*args,**kwargs):
        saved.append(kwargs)
    worker._save=save
    result=ReconciliationResult.model_construct(outcome='still_reconciling',next_action_at=next_at,evidence={'code':'X_LOOKUP_WINDOW_NOT_COVERED'})
    asyncio.run(worker._reconciliation(None,None,{'last_attempt':None,'database_now':now},result,time.monotonic()))
    assert saved[0]['state']==expected
    assert saved[0].get('next_action')==('reconcile' if expected=='reconciling' else None)
    assert saved[0]['extra_receipt']['absence_proof'] is None
    assert saved[0]['delay']==(max(30,seconds) if expected=='reconciling' else None)
