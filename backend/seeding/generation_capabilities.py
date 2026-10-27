"""Reviewed draft adapters, independent of ingestion selection or source rollout.

A registered ingester is not an eligible announcement producer. Keep absent
scope/date/current-authority contracts explicit; never fall back to a financial
fact relabelled as a neutral report. This module performs no imports or I/O.
"""
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class DraftCapability:
    domain: str
    financial: bool = False
    reports: bool = False
    reason: str = 'report_contract_unavailable'
    records_reader: str | None = None
    financial_reader: str | None = None
    report_reader: str | None = None


# All 15 legacy native domains, plus the three explicit opt-ins. Only CoB county
# budgets currently bind exact lineage, qualified scope and retained full dates.
CAPABILITIES = MappingProxyType({c.domain: c for c in (
    DraftCapability('counties_budget', financial=True, reports=True, reason='qualified_cob_adapter',
        records_reader='read_county_budget_record_ids', financial_reader='read_county_budget_observation',
        report_reader='read_county_report_observation'),
    DraftCapability('audits', reports=True, reason='financial_adapter_unavailable', records_reader='read_native_report_record_ids', report_reader='read_audit_report_observation'),
    DraftCapability('economic_indicators', reason='report_lineage_unavailable'),
    DraftCapability('population', reason='report_date_authority_unavailable'),
    DraftCapability('county_officials', reason='report_contract_unavailable'),
    DraftCapability('national_debt', reason='report_date_authority_unavailable'),
    DraftCapability('national_budget', reports=True, reason='financial_adapter_unavailable', records_reader='read_native_report_record_ids', report_reader='read_national_report_observation'),
    DraftCapability('pending_bills', reports=True, reason='financial_adapter_unavailable', records_reader='read_native_report_record_ids', report_reader='read_pending_bills_report_observation'),
    DraftCapability('debt_timeline', reason='report_lineage_unavailable'),
    DraftCapability('fiscal_summary', reason='report_lineage_unavailable'),
    DraftCapability('revenue_by_source', reports=True, reason='financial_adapter_unavailable', records_reader='read_native_report_record_ids', report_reader='read_revenue_report_observation'),
    DraftCapability('learning_hub', reason='report_contract_unavailable'),
    DraftCapability('stalled_projects', reason='report_date_authority_unavailable'),
    DraftCapability('national_gdp', reason='report_date_authority_unavailable'),
    DraftCapability('imf_weo', reason='report_lineage_unavailable'),
    DraftCapability('county_borrowing', reason='report_date_authority_unavailable'),
    DraftCapability('cra', reason='recommendation_date_authority_unavailable'),
    DraftCapability('opendata', reason='source_extracted_not_publication_qualified'),
)})


def capability(domain):
    if type(domain) is not str:
        raise ValueError('Known source domain required')
    return CAPABILITIES.get(domain, DraftCapability(domain, reason='unsupported_source'))


def skipped_generation(domain, *, dry_run, source_mode, completed):
    """Cheap receipt on the ingestion transaction; no social schema access.

    Pending is deliberately uncertain: a process exit or failed receipt write
    after the financial commit must not look like zero generated effects.
    """
    import os
    if __package__.startswith('backend.'):
        from backend.services.generation_outcome import COUNTERS
    else:
        from services.generation_outcome import COUNTERS
    selected = capability(domain)
    flag = os.environ.get('SOCIAL_GENERATION_HOOK_ENABLED', 'false')
    def phase(reports):
        if dry_run is not False or completed is not True or source_mode != 'live':
            state, reason = 'unavailable', 'ingestion_not_eligible'
        elif flag == 'false':
            state, reason = 'disabled', 'environment_disabled'
        elif flag != 'true':
            state, reason = 'unavailable', 'invalid_generation_hook_flag'
        elif not (selected.reports if reports else selected.financial):
            state, reason = 'unavailable', selected.reason
        elif reports and os.environ.get('SOCIAL_REPORT_GENERATION_ENABLED', 'false') != 'true':
            report_flag = os.environ.get('SOCIAL_REPORT_GENERATION_ENABLED', 'false')
            state, reason = ('disabled', 'report_environment_disabled') if report_flag == 'false' else ('unavailable', 'invalid_report_hook_flag')
        else:
            return {'state':'unavailable', 'reason':'hook_not_executed', 'execution_unverified':True,
                    **dict.fromkeys(COUNTERS, None)}
        return {'state':state, 'reason':reason, **dict.fromkeys(COUNTERS, 0)}
    return {'post_commit_generation':phase(False), 'post_commit_report_generation':phase(True)}
