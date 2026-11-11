"""Weekly coverage cannot silently widen the ordinary importer."""
import pytest
from common import Refusal
from acceptance_plans import plan_from_original


def ordinary():
    from seeding.source_plan import LEGACY_DOMAINS
    return dict(domains=list(LEGACY_DOMAINS), bootstrap=False, dry_run=False,
                audits_review='', reacquire_pending_pdf=False, audits_source_acceptance='')


def test_ordinary_and_weekly_are_separately_typed():
    value = ordinary()
    assert plan_from_original(value).bootstrap is False
    weekly = dict(value, domains=['opendata', *value['domains']], bootstrap=True)
    with pytest.raises(Refusal): plan_from_original(weekly)
    assert plan_from_original(weekly, 'weekly-bootstrap-native').bootstrap is True
    with pytest.raises(Refusal): plan_from_original(value, 'weekly-bootstrap-native')


@pytest.mark.parametrize('field,value', [('domains', []), ('domains', ['audits']),
    ('domains', None), ('bootstrap', True), ('bootstrap', 0), ('dry_run', True),
    ('audits_review', 'oag-2542-20261026'), ('reacquire_pending_pdf', True)])
def test_partial_or_special_plan_cannot_be_ordinary_success(field, value):
    data = ordinary(); data[field] = value
    with pytest.raises((Refusal, ValueError)): plan_from_original(data)


def test_ordinary_structural_importer_does_not_admit_bootstrap(envelope):
    # The existing envelope fixture supplies correctly bound originals; only
    # this widened execution scope changes, so a hash mismatch is not the guard.
    import copy
    import operational
    from common import identity, read_json
    path, original, put, save = envelope
    value = copy.deepcopy(original)
    plan = read_json(path.parent/value['plan']['original']['path'])
    plan['bootstrap'] = True
    value['plan'] = {'sha256':identity(plan),'original':put('bootstrap-plan.json',plan)}
    with pytest.raises(Refusal, match='ordinary|bootstrap|full15'):
        operational.validate(save(value))


from test_operational import envelope


def test_weekly_envelope_has_a_distinct_supported_importer(envelope):
    import copy
    import operational
    from common import identity, read_json
    path, value, put, save = envelope
    value = copy.deepcopy(value)
    plan = read_json(path.parent/value['plan']['original']['path'])
    plan.update(domains=['opendata',*sorted(plan['domains'])],bootstrap=True)
    value['schema']='nightly-weekly-operational-envelope-v1'
    value['plan']={'sha256':identity(plan),'original':put('weekly-plan.json',plan)}
    row=copy.deepcopy(value['domains'][0]);row.update(domain='opendata',job_id=16,status='accepted')
    value['domains'].append(row)
    pg=read_json(path.parent/value['pg']['inventory']['path'])
    pg.append(dict(domain='opendata',job_id=16,run_id=100,attempt=1,processed=1,created=0,updated=0))
    value['pg']['inventory']=put('weekly-pg.json',pg)
    with pytest.raises(Refusal):operational.validate(save(value))
    assert operational.validate_weekly(path)['schema']=='nightly-weekly-operational-envelope-v1'
