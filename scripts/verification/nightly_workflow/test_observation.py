"""Preparation is inert and may never imply hosted execution/acceptance."""
import pytest
import observation as o


@pytest.mark.parametrize('kind',o.KINDS)
def test_preparation_binds_distinct_plan_and_only_read_only_capture(kind):
    packet=o.prepare(kind,'1234','1','a'*40,opendata='true' if kind=='weekly' else 'false',
                     replay_of='1233' if kind=='replay' else None)
    assert packet['production_accepted'] is False
    assert packet['verdict']=='PREPARED_NOT_EXECUTED_NOT_ACCEPTED'
    assert all(argv[:2]==['gh','api'] and all(word not in argv for word in ['POST','PATCH','PUT','DELETE','--method']) for argv in packet['read_only_capture_argv'])
    assert all('1234/attempts/1' in argv[-1] for argv in packet['read_only_capture_argv'])
    assert len(packet['plan']['domains'])==(16 if kind=='weekly' else 15)
    assert packet['plan']['bootstrap'] is (kind=='weekly')
    assert packet['event']==('schedule' if kind in ('daily','weekly') else 'workflow_dispatch')
    assert packet['source_inputs'] and packet['holds']


@pytest.mark.parametrize('bad',[None,True,0,'0','../1','1/attempts/2',float('nan')])
def test_unbound_run_identity_cannot_prepare(bad):
    with pytest.raises(ValueError):o.prepare('daily',bad,'1','a'*40)


def test_ordinary_schema_cannot_widen_or_replay_same_run():
    with pytest.raises(ValueError):o.prepare('daily','1234','1','a'*40,opendata='true')
    with pytest.raises(ValueError):o.prepare('replay','1234','1','a'*40,replay_of='1234')
