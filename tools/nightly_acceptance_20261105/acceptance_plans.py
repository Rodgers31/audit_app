"""Separate ordinary15 and weekly/bootstrap/native plan contracts."""
from common import fields, require


def plan_from_original(value, kind='full15'):
    from seeding.source_plan import SourcePlan, LEGACY_DOMAINS, validate_plan
    fields(value, ('domains', 'bootstrap', 'dry_run', 'audits_review',
                   'reacquire_pending_pdf', 'audits_source_acceptance'))
    require(type(value['domains']) is list and bool(value['domains'])
            and all(type(d) is str for d in value['domains'])
            and len(set(value['domains'])) == len(value['domains']), 'nonempty unique plan inventory required')
    plan = SourcePlan(**dict(value, domains=tuple(value['domains'])))
    try: validate_plan(plan)
    except ValueError as exc: raise ValueError('native source plan refused: ' + str(exc)) from exc
    require(plan.dry_run is False and plan.audits_review == ''
            and plan.reacquire_pending_pdf is False and plan.audits_source_acceptance == '',
            'special/manual/dry-run plan cannot substitute for ordinary acceptance')
    if kind == 'full15':
        require(plan.domains == LEGACY_DOMAINS and plan.bootstrap is False,
                'ordinary full15 requires its exact unexpanded daily plan')
    elif kind == 'weekly-bootstrap-native':
        require(plan.domains == ('opendata', *LEGACY_DOMAINS) and plan.bootstrap is True,
                'weekly adapter requires explicit OpenData plus full15 and bootstrap')
    else:
        require(False, 'unknown typed acceptance plan')
    return plan
