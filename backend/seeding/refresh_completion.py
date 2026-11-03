"""Required nightly domains must finish, even when partial writes succeeded.

Other domains retain their documented partial/WARN policy. This check does
not approve source revisions, reconciliation proposals or published figures.
"""
from __future__ import annotations

REQUIRED_DOMAINS = frozenset({'audits', 'fiscal_summary', 'pending_bills'})


def _positive(value):
    return type(value) is int and value > 0


def accepted_records(processed, created, updated):
    """These writers count confirmed unchanged rows as updated too."""
    if any(type(n) is not int or n < 0 for n in (processed, created, updated)):
        return 0
    return processed if created + updated == processed else 0


def fiscal_components_complete(components, accepted_years):
    if (not isinstance(components, dict) or not isinstance(accepted_years, list) or not accepted_years
            or any(not isinstance(y, str) or not y.strip() for y in accepted_years)
            or len(set(accepted_years)) != len(accepted_years)):
        return False
    if any(not isinstance(components.get(key), dict) or components[key].get('state') != 'live'
           for key in ('budget', 'revenue', 'framework')):
        return False
    revenue, framework = components['revenue'], components['framework']
    years = revenue.get('refreshed_years')
    return (isinstance(years, list) and len(years) == len(accepted_years)
            and all(isinstance(y, str) and y.strip() for y in years)
            and len(set(years)) == len(years)
            and set(years) == set(accepted_years)
            and revenue.get('missing_years') == []
            and type(revenue.get('missing_years')) is list
            and framework.get('unreadable_editions') == {}
            and type(framework.get('unreadable_editions')) is dict
            and framework.get('unconfirmed_years') == {}
            and type(framework.get('unconfirmed_years')) is dict)


def audit_inventory_complete(meta, completion, processed):
    """Reconcile the summary against every retained document outcome."""
    documents = meta.get('documents')
    if (not isinstance(documents, list) or not documents
            or not _positive(completion.get('accepted_documents'))
            or type(completion.get('errors')) is not int or completion['errors'] != 0
            or completion.get('deferred') is not False):
        return False
    accepted, records, seen = 0, 0, set()
    for doc in documents:
        if not isinstance(doc, dict) or type(doc.get('doc_id')) is not int or doc['doc_id'] in seen:
            return False
        seen.add(doc['doc_id'])
        outcome = doc.get('extraction_outcome')
        if 'extraction_attempt' in doc:
            return False  # Attempts here are retained failures, not successful reads.
        if outcome == 'not_requested' and doc.get('parser_id') is None:
            continue
        if outcome == 'skipped' and isinstance(doc.get('skipped'), str) and doc['skipped'].strip():
            continue
        if outcome != 'accepted':
            return False
        if doc.get('parser_id') not in ('oag_blue_book', 'oag_county_audit'):
            return False
        stats, loaded = doc.get('extractions'), doc.get('loaded')
        if not isinstance(stats, dict) or not isinstance(loaded, dict):
            return False
        counts = [stats.get(key, 0) for key in ('created', 'skipped', 'existing')]
        loaded_counts = [loaded.get(key) for key in ('processed', 'created', 'updated', 'skipped')]
        if (any(type(n) is not int or n < 0 for n in counts) or not sum(counts)
                or 'partial' in stats and stats['partial'] is not False
                or any(type(n) is not int or n < 0 for n in loaded_counts)
                or not _positive(loaded.get('processed'))
                or sum(counts) != loaded['processed']
                or loaded['created'] + loaded['updated'] > loaded['processed']
                or loaded['skipped'] != 0):
            return False
        accepted += 1
        records += loaded['processed']
    return accepted == completion['accepted_documents'] and records == processed


def _complete(domain, meta, processed):
    completion = meta.get('refresh_completion')
    if not isinstance(completion, dict) or completion.get('complete') is not True:
        return False
    if domain == 'audits':
        return audit_inventory_complete(meta, completion, processed)
    elif domain == 'fiscal_summary':
        if not _positive(completion.get('accepted_records')) or completion['accepted_records'] != processed:
            return False
        years = completion.get('accepted_years')
        return (isinstance(years, list) and len(years) == processed
                and fiscal_components_complete(meta.get('refresh_components'), years))
    else:
        components = meta.get('refresh_components')
        if not isinstance(components, dict):
            return False
        total = 0
        for key in ('national', 'counties'):
            component = components.get(key)
            if (not isinstance(component, dict) or component.get('complete') is not True
                    or not _positive(component.get('records'))
                    or not _positive(component.get('accepted_records'))
                    or component['records'] != component['accepted_records']):
                return False
            total += component['records']
        if components['national'].get('mode') != 'live' or total != processed:
            return False
    return True


def required_refresh_failures(jobs, *, dry_run=False):
    if type(dry_run) is not bool:
        raise ValueError('refresh dry_run must be boolean')
    failures = []
    for job in jobs:
        if job.domain not in REQUIRED_DOMAINS:
            continue
        status = getattr(job.status, 'value', job.status)
        meta = job.meta if isinstance(job.meta, dict) else {}
        reasons = []
        if status != 'completed' or not isinstance(job.errors, list) or job.errors:
            reasons.append('ingestion did not complete without errors')
        if type(job.dry_run) is not bool or job.dry_run != dry_run:
            reasons.append('job execution mode disagrees with the selected plan')
        if not dry_run:
            if meta.get('source_mode') != 'live':
                reasons.append('publisher refresh is incomplete')
            if type(job.items_processed) is not int or job.items_processed <= 0:
                reasons.append('no accepted record inventory')
            if not _complete(job.domain, meta, job.items_processed):
                reasons.append('domain reports incomplete source coverage')
        if reasons:
            failures.append(f"[INCOMPLETE] {job.domain}: " + '; '.join(reasons))
            for document in meta.get('documents', []) if isinstance(meta.get('documents'), list) else []:
                if not isinstance(document, dict):
                    continue
                attempt = document.get('extraction_attempt')
                proposal = attempt.get('proposal') if isinstance(attempt, dict) else None
                if not isinstance(proposal, dict):
                    continue
                # Exact public proposal identity, without the retained finding
                # texts or an unbounded list of affected rows in hosted output.
                sha = proposal.get('candidate_sha256')
                source = proposal.get('source_sha256')
                identity = proposal.get('document_id')
                retired, revised = proposal.get('retire_ids'), proposal.get('update_ids')
                if (type(identity) is int and isinstance(retired, list) and isinstance(revised, list)
                        and all(isinstance(h, str) and len(h) == 64
                                and all(c in '0123456789abcdef' for c in h) for h in (sha, source))):
                    failures.append(f"  held document {identity}: {len(retired)} retirements, "
                                    f"{len(revised)} revisions; source_sha256={source}; candidate_sha256={sha}")
    return failures
