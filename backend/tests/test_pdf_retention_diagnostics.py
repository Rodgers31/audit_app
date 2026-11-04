"""Actual retained-PDF refusal/fallback calls; all DB/provider access is inert."""
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from seeding import retained_report_receipts
from seeding.pdf_evidence import receipt_for_pdf
from seeding.native_report_authority import capture_pdf_report
from services.receipt_retention import RetentionScope, safe_retention_summary
from services.receipt_storage_errors import ReceiptStorageError
from services.response_receipts import capture_response, capture_retained_pdf

URL = 'https://www.oagkenya.go.ke/inert-diagnostic.pdf'
BODY = b'%PDF-1.4\ninert parser input\n%%EOF'


class RecordingStore:
    storage_scope = 'inert-local-test'

    def __init__(self, *, fail_read=False):
        self.values, self.fail_read = {}, fail_read

    def put(self, body):
        key = hashlib.sha256(body).hexdigest()
        self.values[key] = body
        return key

    def read(self, key):
        if self.fail_read:
            raise OSError('inert-private-provider-body-must-not-enter-diagnostics')
        return self.values[key]


def refuse(monkeypatch, exc):
    def denied(*args, **kwargs):
        raise exc
    monkeypatch.setattr(retained_report_receipts, 'verified_retained_pdf', denied)


def invoke(tmp_path, store):
    path = tmp_path/'cached.pdf'
    path.write_bytes(BODY)
    client = SimpleNamespace(receipt_store=store, download_receipt=lambda url: None)
    receipt = receipt_for_pdf(client, None, path, URL, 'inert-parser-v1',
        session=object(), context=SimpleNamespace(job_id=3645, dry_run=False), domain='audits')
    return path, receipt


def old_counts(summary):
    return {k:v for k,v in summary.items() if k != 'diagnostics'}


@pytest.mark.parametrize('error,reason', [
    ('No persisted original PDF acquisition','origin_missing'),
    ('Original retained HTTP acquisition required','origin_invalid'),
    ('Original acquisition is stale or unordered','origin_stale'),
    ('Current source edition differs','edition_changed'),
    ('Retained storage destination changed','destination_changed'),
    ('Retained provider bytes differ','readback_mismatch'),
    ('inert-secret https://private.example/key?token=never-echo','authority_refused_unknown'),
], ids=['missing-origin','invalid-origin','stale-origin','changed-edition','changed-destination','readback-mismatch','untrusted-error'])
def test_actual_refusal_then_local_retention_stays_missing_and_without_authority(tmp_path, monkeypatch, error, reason):
    refuse(monkeypatch, ValueError(error))
    scope=RetentionScope()
    try:
        path, receipt=invoke(tmp_path, RecordingStore())
        summary=scope.summary()
        assert old_counts(summary)==dict(state='missing_bytes',observed=2,retained=1,missing=1,recovered=0,retry_requests=0)
        assert receipt['byte_check']['status']=='matched'
        assert receipt['acquisition_kind']=='local_cached_bytes'
        assert receipt['status'] is None and receipt['acquired_at'] is None
        authority, refusal=capture_pdf_report(path, receipt, domain='audits')
        assert authority is None and refusal=='native_report_date_or_scope_unavailable'
        assert summary.get('diagnostics')=={
            'retained_pdf_restore':{reason:1},'local_pdf_fallback':{'bytes_retained':1}}
        encoded=json.dumps(summary)
        assert 'inert-secret' not in encoded and 'https://' not in encoded and 'token=' not in encoded
        assert '3645' not in encoded  # This refusal API supplies no trusted source/document identity.
        assert safe_retention_summary(summary)==summary
    finally:
        scope.close()


def test_local_fallback_readback_failure_is_a_separate_phase(tmp_path,monkeypatch):
    refuse(monkeypatch, ValueError('No persisted original PDF acquisition'))
    scope=RetentionScope()
    try:
        _, receipt=invoke(tmp_path, RecordingStore(fail_read=True))
        summary=scope.summary()
        assert old_counts(summary)==dict(state='missing_bytes',observed=2,retained=0,missing=2,recovered=0,retry_requests=0)
        assert receipt['byte_check']['status']=='missing'
        assert summary.get('diagnostics')=={
            'retained_pdf_restore':{'origin_missing':1},'local_pdf_fallback':{'bytes_missing':1}}
        assert 'inert-private-provider-body' not in json.dumps(summary)
    finally:
        scope.close()


def test_provider_error_propagates_without_a_local_authority_fallback(tmp_path,monkeypatch):
    refuse(monkeypatch, ReceiptStorageError('Receipt storage transport failed'))
    scope=RetentionScope()
    try:
        with pytest.raises(ReceiptStorageError):invoke(tmp_path,RecordingStore())
        summary=scope.summary()
        assert old_counts(summary)==dict(state='missing_bytes',observed=1,retained=0,missing=1,recovered=0,retry_requests=0)
        assert summary.get('diagnostics')=={'retained_pdf_restore':{'storage_failed':1}}
    finally:
        scope.close()


def test_unknown_non_value_error_still_propagates_without_echo(tmp_path,monkeypatch):
    refuse(monkeypatch, RuntimeError('inert-secret-provider-body'))
    scope=RetentionScope()
    try:
        with pytest.raises(RuntimeError):invoke(tmp_path,RecordingStore())
        summary=scope.summary()
        assert summary['missing']==1 and summary['retained']==0
        assert summary.get('diagnostics')=={'retained_pdf_restore':{'unexpected_error':1}}
        assert 'inert-secret-provider-body' not in json.dumps(summary)
    finally:
        scope.close()


def test_matched_restore_does_not_invent_a_missing_or_fallback_capture(tmp_path,monkeypatch):
    store=RecordingStore()
    response=httpx.Response(200,content=BODY,headers={'content-type':'application/pdf'},request=httpx.Request('GET',URL))
    original=capture_response(response,store,source_kind='pdf')
    monkeypatch.setattr(retained_report_receipts,'verified_retained_pdf',lambda *a,**k:(dict(original),store))
    scope=RetentionScope()
    try:
        _,receipt=invoke(tmp_path,store)
        summary=scope.summary()
        assert old_counts(summary)==dict(state='confirmed',observed=1,retained=1,missing=0,recovered=0,retry_requests=0)
        assert receipt['status']==200 and receipt.get('acquisition_kind') is None
        assert summary.get('diagnostics')=={'retained_pdf_restore':{'matched':1}}
    finally:
        scope.close()


def test_existing_direct_retained_refusal_is_still_a_missing_capture(monkeypatch):
    refuse(monkeypatch,ValueError('No persisted original PDF acquisition'))
    scope=RetentionScope()
    try:
        with pytest.raises(ValueError):
            capture_retained_pdf(None,None,None,domain='audits',url=URL,body=BODY)
        summary=scope.summary()
        assert old_counts(summary)==dict(state='missing_bytes',observed=1,retained=0,missing=1,recovered=0,retry_requests=0)
        assert summary.get('diagnostics')=={'retained_pdf_restore':{'origin_missing':1}}
    finally:
        scope.close()


def test_nested_scopes_do_not_borrow_diagnostics(tmp_path,monkeypatch):
    refuse(monkeypatch,ValueError('No persisted original PDF acquisition'))
    outer=RetentionScope()
    try:
        inner=RetentionScope()
        try:
            invoke(tmp_path,RecordingStore())
            assert inner.summary().get('diagnostics')=={
                'retained_pdf_restore':{'origin_missing':1},'local_pdf_fallback':{'bytes_retained':1}}
        finally:inner.close()
        assert outer.summary()==dict(state='not_observed',observed=0,retained=0,missing=0,recovered=0,retry_requests=0)
    finally:outer.close()


@pytest.mark.parametrize('diagnostics',[
    {'retained_pdf_restore':{'https://private.example':1}},
    {'retained_pdf_restore':{'origin_missing':True}},
    {'retained_pdf_restore':{'origin_missing':-1}},
    {'retained_pdf_restore':{'origin_missing':2}},
    {'retained_pdf_restore':{}},
    {'retained_pdf_restore':{'origin_missing':0}},
    {'unknown_phase':{'origin_missing':1}},
],ids=['unknown-reason','boolean','negative','exceeds-observed','empty-phase','zero-count','unknown-phase'])
def test_untrusted_diagnostics_cannot_be_echoed_or_certified(diagnostics):
    raw=dict(state='missing_bytes',observed=1,retained=0,missing=1,recovered=0,retry_requests=0,diagnostics=diagnostics)
    assert safe_retention_summary(raw)=={'state':'unverified'}


def test_legacy_summary_shape_remains_accepted_without_invented_diagnostics():
    raw=dict(state='missing_bytes',observed=1,retained=0,missing=1,recovered=0,retry_requests=0)
    assert safe_retention_summary(raw)==raw


def test_admin_projection_keeps_the_existing_six_field_retention_contract():
    from routers.admin_operations import safe_job_metadata
    counts=dict(state='missing_bytes',observed=2,retained=1,missing=1,recovered=0,retry_requests=0)
    detailed={**counts,'diagnostics':{'retained_pdf_restore':{'origin_missing':1},
                                    'local_pdf_fallback':{'bytes_retained':1}}}
    assert safe_job_metadata({'receipt_retention': detailed})=={'receipt_retention':counts}


@pytest.mark.parametrize('reason,missing,accepted', [
    ('origin_missing', 0, False), ('matched', 0, True), ('matched', 1, True),
], ids=['impossible-confirmed-failure', 'matched-confirmed', 'matched-later-downgraded'])
def test_diagnostic_failure_counts_cannot_contradict_retention(reason, missing, accepted):
    raw=dict(state='missing_bytes' if missing else 'confirmed', observed=1,
             retained=1-missing, missing=missing, recovered=0, retry_requests=0,
             diagnostics={'retained_pdf_restore': {reason: 1}})
    assert safe_retention_summary(raw)==(raw if accepted else {'state':'unverified'})
