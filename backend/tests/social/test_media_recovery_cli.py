"""Scoped single-upload operator command and negative controls."""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest
from social.media import maintenance as m

@pytest.fixture
def f(monkeypatch):
 calls=[]
 engine=SimpleNamespace(dispose=lambda:calls.append('dispose'))
 monkeypatch.setattr(m,'create_worker_engine',lambda config:(calls.append('engine') or engine))
 @contextmanager
 def session():calls.append('db_open');yield 'inert-session'
 monkeypatch.setattr(m,'sessionmaker',lambda *a,**k:session)
 monkeypatch.setattr(m,'media_runtime',lambda:'inert-runtime')
 monkeypatch.setattr(m,'MediaService',lambda db,runtime:'inert-service')
 def recover(service,actor,asset,body,request):
  calls.append(('recover',service,actor,asset,body,request))
  return SimpleNamespace(model_dump_json=lambda:'{"state":"ready"}')
 monkeypatch.setattr(m,'recover_retained',recover)
 return calls

def args():return ['--database-url','postgresql://inert@127.0.0.1/inert','--recover-retained-upload',str(uuid4()),'--actor-id',str(uuid4()),'--expected-version','2','--expected-grant-epoch','1','--expected-finalization-epoch','1']

@pytest.mark.parametrize('extra',[['--allow-cleanup'],['--prepare-reconciliation'],['--after-asset-id',str(uuid4())],['--expected-version','true'],['--expected-grant-epoch','-1'],['--expected-finalization-epoch','0'],['--limit','21'],['--actor-id','PRIVATE_INPUT']])
def test_hostile_recovery_cli_refuses_before_engine(f,capsys,extra):
 assert m.main(args()+extra)==1
 assert not f
 out=json.loads(capsys.readouterr().out)
 assert out['error_code']
 assert 'PRIVATE_INPUT' not in json.dumps(out)

def test_explicit_recovery_cli_executes_exact_scoped_single_call_and_disposes(f,capsys):
 values=args()
 assert m.main(values)==0
 call=[x for x in f if isinstance(x,tuple)][0]
 assert call[0]=='recover' and str(call[2])==values[5] and str(call[3])==values[3]
 assert call[4].model_dump()==dict(expected_version=2,expected_grant_epoch=1,expected_finalization_epoch=1)
 assert f[-1]=='dispose'
 assert json.loads(capsys.readouterr().out)=={'state':'ready'}

@pytest.mark.parametrize('values',[['--expected-version','2'],['--actor-id',str(uuid4())],['--expected-grant-epoch','1']])
def test_scope_without_asset_is_invalid(f,values,capsys):
 assert m.main(['--database-url','postgresql://inert@127.0.0.1/inert']+values)==1
 assert not f
 assert json.loads(capsys.readouterr().out)['error_code']=='INVALID_REQUEST'
