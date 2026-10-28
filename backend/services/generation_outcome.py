"""Small safe operational projection; no raw hook diagnostics enter the browser."""
COUNTERS = ("processed", "drafts_created", "baselines", "unchanged", "refused")
# Only stable known diagnostics may enter private browser metadata. Never echo
# exception strings, record text, URLs, credentials or a syntactically safe but
# unknown reason supplied by an installed hook.
REASONS = frozenset({
    'financial_environment_disabled',
    'invalid_financial_hook_flag',
    'qualified_native_cells_required',
    "financial_adapter_unavailable",
    'duplicate_source_series',
    'source_not_eligible',
    'unresolved_template',
    'committed_evidence_consumed',
    'environment_disabled',
    'evidence_integrity_failed',
    'evidence_version_conflict',
    'fresh_session_required',
    'generation_database_unavailable',
    'generation_deadline_exceeded',
    'generation_dependency_execution_unverified',
    'generation_dependency_failed',
    'generation_disabled',
    'generation_execution_unverified',
    'generation_failed',
    'generation_source_read_failed',
    'generation_timeout_execution_unverified',
    'hook_not_executed',
    'ingestion_not_eligible',
    'invalid_generation_hook_flag',
    'invalid_hook_flag',
    'invalid_record_cohort',
    'invalid_report_hook_flag',
    'native_registry_invalid',
    'native_registry_unavailable',
    'no_new_record_lineage',
    'publisher_date_receipt_unavailable',
    'publisher_date_unavailable',
    'qualified_cob_adapter',
    'recommendation_date_authority_unavailable',
    'record_lineage_unavailable',
    'record_not_publishable',
    'report_contract_unavailable',
    'report_date_authority_unavailable',
    'report_environment_disabled',
    'report_generation_execution_unverified',
    'report_generation_not_started',
    'report_generation_timeout_execution_unverified',
    'report_lineage_unavailable',
    'report_release_regression',
    'report_scope_unavailable',
    'report_source_read_failed',
    'runtime_source_disabled',
    'source_adapter_unavailable',
    'source_chronology_invalid',
    'source_document_unavailable',
    'source_evidence_ineligible',
    'source_extracted_not_publication_qualified',
    'source_lineage_unavailable',
    'source_review_required',
    'unsupported_source',
    'verified_pdf_evidence_required',
})
REFUSAL_REASONS = frozenset({
    'unresolved_template',
    'source_not_eligible',
    'evidence_integrity_failed',
    'evidence_version_conflict',
    'publisher_date_receipt_unavailable',
    'publisher_date_unavailable',
    'record_lineage_unavailable',
    'record_not_publishable',
    'report_release_regression',
    'report_scope_unavailable',
    'source_chronology_invalid',
    'source_document_unavailable',
    'source_evidence_ineligible',
    'source_review_required',
    'verified_pdf_evidence_required',
})


def safe_reason(value):
    return value.lower() if type(value) is str and value.lower() in REASONS else None


def refusal_counts(raw, total):
    if (type(raw) is not dict or len(raw) > len(REFUSAL_REASONS)
            or any(key not in REFUSAL_REASONS or type(value) is not int or not 1 <= value <= 1000
                   for key, value in raw.items()) or sum(raw.values()) != total):
        raise ValueError('Invalid refusal reason counts')
    return dict(raw)


def confirmed_counts(raw, maximum=1000):
    if (type(raw) is not dict or set(raw) != set(COUNTERS)
            or any(type(raw[k]) is not int or not 0 <= raw[k] <= maximum for k in COUNTERS)
            or sum(raw[k] for k in COUNTERS[1:]) != raw['processed']):
        raise ValueError('Invalid confirmed progress')
    return dict(raw)


STATES = ("disabled", "completed", "unavailable", "failed")


def safe_generation_outcome(raw):
    unknown = {"state": "unavailable", "execution_unverified": True, **dict.fromkeys(COUNTERS, None)}
    if type(raw) is not dict or raw.get("state") not in STATES:
        return unknown
    if "execution_unverified" in raw and type(raw["execution_unverified"]) is not bool:
        return unknown
    details = {}
    reason = safe_reason(raw.get('reason'))
    if reason is not None:
        details['reason'] = reason
    if raw.get("execution_unverified") is True:
        if raw["state"] not in {"failed", "unavailable"} or any(raw.get(k) is not None for k in COUNTERS):
            return unknown
        if 'confirmed' in raw:
            try:
                details['confirmed'] = confirmed_counts(raw['confirmed'])
            except ValueError:
                return unknown
        if 'refusal_reasons' in raw:
            try:
                details['refusal_reasons'] = refusal_counts(raw['refusal_reasons'], details['confirmed']['refused'])
            except (KeyError, ValueError):
                return unknown
        return {**unknown, **details, "state": raw["state"]}
    if any(type(raw.get(k)) is not int or not 0 <= raw[k] <= 1000 for k in COUNTERS):
        return unknown
    if sum(raw[k] for k in COUNTERS[1:]) != raw["processed"] or raw["state"] == "completed" and raw["refused"]:
        return unknown
    if 'refusal_reasons' in raw:
        try:
            details['refusal_reasons'] = refusal_counts(raw['refusal_reasons'], raw['refused'])
        except ValueError:
            return unknown
    return {**details, "state": raw["state"], "execution_unverified": False, **{k: raw[k] for k in COUNTERS}}
