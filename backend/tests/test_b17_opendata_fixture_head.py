"""A new mapping head must retain the audit ancestor and unique-head guard."""
from types import SimpleNamespace
import pytest
from tests.admin_audit_epoch import ephemeral_database as fixture


def test_actual_current_graph_is_one_audit_descendant():
    assert fixture.head() == 'e621b17a0001'
    config = fixture.Config(str(fixture.BACKEND / 'alembic.ini'))
    config.set_main_option('script_location', str(fixture.BACKEND / 'alembic'))
    graph = fixture.ScriptDirectory.from_config(config)
    lineage = [r.revision for r in graph.walk_revisions(base='base', head=fixture.head())]
    assert lineage[:3] == ['e621b17a0001', 'a706b17a0001', 'a705b15a0001']
    assert 'a611b12a0001' in lineage


@pytest.mark.parametrize('heads,lineage,allowed', [
    ([], [], False),
    (['first', 'second'], ['a611b12a0001'], False),
    ([False], ['a611b12a0001'], False),
    ([''], ['a611b12a0001'], False),
    (['unrelated'], ['unrelated'], False),
    (['a611b12a0001'], ['a611b12a0001'], True),
    (['descendant'], ['descendant', 'a705b15a0001', 'a611b12a0001'], True),
])
def test_single_head_and_required_audit_lineage_are_both_enforced(monkeypatch, heads, lineage, allowed):
    graph = SimpleNamespace(get_heads=lambda: heads,
        walk_revisions=lambda **kw: [SimpleNamespace(revision=r) for r in lineage])
    monkeypatch.setattr(fixture.ScriptDirectory, 'from_config', lambda config: graph)
    if allowed: assert fixture.head() == heads[0]
    else:
        with pytest.raises(RuntimeError, match='audit descendant'): fixture.head()
