"""Integrated users writer must retain the common bounded audit policy."""
import json
from types import SimpleNamespace
import pytest
import database
import admin_users_provider

@pytest.mark.parametrize('action,payload',[
 ('users.update_roles',{'old':['citizen','PRIVATE_POLICY_MARKER'],'new':['admin']}),
 ('users.send_reset',{'email':'fixture@example.invalid','redirect_to':'https://fixture.invalid/PRIVATE_POLICY_MARKER','token':'PRIVATE_POLICY_MARKER'}),
 ('users.delete',{'deleted_email':'PRIVATE_POLICY_MARKER','deleted_created_at':'invalid','nested':{'password':'PRIVATE_POLICY_MARKER'}}),
 ('future.action',{'token':'PRIVATE_POLICY_MARKER'}),
])
def test_users_writer_redacts_before_storage(monkeypatch,action,payload):
 rows=[]
 class Store:
  def add(self,row): rows.append(row)
  def commit(self): pass
  def rollback(self): pass
  def close(self): pass
 monkeypatch.setattr(database,'SessionLocal',Store)
 assert admin_users_provider.record_admin_action(None,actor=SimpleNamespace(id='inert',email=None),action=action,payload=payload) is True
 assert len(rows)==1
 assert 'PRIVATE_POLICY_MARKER' not in json.dumps(rows[0].payload)
 if action=='users.update_roles': assert rows[0].payload=={'old':['citizen','[redacted role]'],'new':['admin']}
