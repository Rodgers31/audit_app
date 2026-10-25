"""A matching PDF alone cannot authorize unrelated configured contract facts."""
import pytest

from county_borrowing_fixture import borrowing_pg, owned  # noqa: F401
from test_county_borrowing_producer import specimen, persist, summary, effects  # noqa: F401
from seeding import county_borrowing_contract as contract


def test_valid_writer_control(borrowing_pg, specimen):
    _, factory = borrowing_pg
    with owned(factory) as ctx:
        persist(factory, ctx, specimen)
    assert summary(factory)['total_debt'] == 20


@pytest.mark.parametrize('field,value', [
    ('outstanding', '21.00'),
    ('instrument_reference', 'INVENTED-REFERENCE'),
    ('issue_date', '2021-02-03T00:00:00'),
])
def test_unwitnessed_mapping_cannot_write_even_with_matching_pdf(
    borrowing_pg, specimen, field, value,
):
    _, factory = borrowing_pg
    record = specimen[0]['instruments'][0]
    record.pop('source_evidence', None)
    record[field] = value
    with owned(factory) as ctx:
        with pytest.raises(contract.CountyBorrowingRefused, match='source evidence'):
            persist(factory, ctx, specimen)
    assert effects(factory) == (0, 0, 0, 0)


@pytest.mark.parametrize('dry_run', [True, False])
@pytest.mark.parametrize('field,value', [
    ('outstanding', '21.00'), ('principal', '200.00'),
    ('instrument_reference', 'INVENTED-REFERENCE'),
    ('lender', 'Other Bank'), ('issue_date', '2021-02-03T00:00:00'),
    ('as_at', '2025-07-01'),
])
def test_mapping_cannot_diverge_from_its_retained_witness(
    borrowing_pg, specimen, dry_run, field, value,
):
    _, factory = borrowing_pg
    specimen[0]['instruments'][0][field] = value
    with owned(factory, dry_run) as ctx:
        with pytest.raises(contract.CountyBorrowingRefused, match='source evidence'):
            persist(factory, ctx, specimen)
    assert effects(factory) == (0, 0, 0, 0)
    assert not (specimen[2].storage_path / 'response-receipts').exists()


@pytest.mark.parametrize('evidence', [None, {}, [], True, {'fields': {}}])
def test_direct_guard_refuses_unknown_evidence_shapes(specimen, evidence):
    from seeding.county_borrowing_mapping_evidence import validate_mapping_source_evidence
    specimen[0]['instruments'][0]['source_evidence'] = evidence
    with pytest.raises(contract.CountyBorrowingRefused, match='source evidence'):
        validate_mapping_source_evidence(specimen[0]['instruments'], specimen[1])


@pytest.mark.parametrize('raw', [None, True, -1, float('nan'), float('inf'), '', '20e0', '-20.00', '2,0.00'])
def test_source_money_requires_an_explicit_nonnegative_decimal(specimen, raw):
    from seeding.county_borrowing_mapping_evidence import validate_mapping_source_evidence
    specimen[0]['instruments'][0]['source_evidence']['fields']['outstanding'] = raw
    with pytest.raises(contract.CountyBorrowingRefused, match='source evidence'):
        validate_mapping_source_evidence(specimen[0]['instruments'], specimen[1])


def test_witness_must_be_visible_in_the_actual_payload(specimen):
    from seeding.county_borrowing_mapping_evidence import validate_mapping_source_evidence
    from county_borrowing_fixture import pdf_bytes
    with pytest.raises(contract.CountyBorrowingRefused, match='source evidence'):
        validate_mapping_source_evidence(specimen[0]['instruments'], pdf_bytes(['Another source page']))


def test_positive_witness_is_retained_in_extraction(borrowing_pg, specimen):
    from sqlalchemy import select
    from models import Extraction
    _, factory = borrowing_pg
    with owned(factory) as ctx:
        persist(factory, ctx, specimen)
    with factory() as db:
        stored = db.scalar(select(Extraction)).extracted_json['instruments'][0]['source_evidence']
        assert stored == specimen[0]['instruments'][0]['source_evidence']


@pytest.mark.parametrize('field,value', [
    ('outstanding', '0.00'), ('principal', '0.00'),
    ('instrument_reference', 'SYNTH'), ('lender', 'Bank'),
])
def test_coherent_mapping_and_witness_edits_cannot_splice_source_tokens(specimen, field, value):
    from seeding.county_borrowing_mapping_evidence import validate_mapping_source_evidence
    record = specimen[0]['instruments'][0]
    record[field] = record['source_evidence']['fields'][field] = value
    with pytest.raises(contract.CountyBorrowingRefused, match='source evidence'):
        validate_mapping_source_evidence(specimen[0]['instruments'], specimen[1])


def test_principal_and_outstanding_cannot_swap_labels(specimen):
    from seeding.county_borrowing_mapping_evidence import validate_mapping_source_evidence
    record = specimen[0]['instruments'][0]
    for field, value in [('principal', '20.00'), ('outstanding', '100.00')]:
        record[field] = record['source_evidence']['fields'][field] = value
    with pytest.raises(contract.CountyBorrowingRefused, match='source evidence'):
        validate_mapping_source_evidence(specimen[0]['instruments'], specimen[1])


def test_source_nonzero_fraction_is_never_rounded_away(specimen):
    from seeding.county_borrowing_mapping_evidence import validate_mapping_source_evidence
    from county_borrowing_fixture import pdf_bytes
    evidence = specimen[0]['instruments'][0]['source_evidence']
    raw = '20.00000000000000000000000000001'
    evidence['statement'] = evidence['statement'].replace('Outstanding: 20.00', 'Outstanding: ' + raw)
    evidence['fields']['outstanding'] = raw
    with pytest.raises(contract.CountyBorrowingRefused, match='source evidence'):
        validate_mapping_source_evidence(specimen[0]['instruments'], pdf_bytes([evidence['statement']]))


@pytest.mark.parametrize('label', ['Outstanding', 'Principal', 'As at', 'Contract reference'])
def test_duplicate_label_cannot_select_a_different_field(specimen, label):
    from seeding.county_borrowing_mapping_evidence import validate_mapping_source_evidence
    from county_borrowing_fixture import pdf_bytes
    evidence = specimen[0]['instruments'][0]['source_evidence']
    evidence['statement'] += ' ' + label + ': 0;'
    with pytest.raises(contract.CountyBorrowingRefused, match='source evidence'):
        validate_mapping_source_evidence(specimen[0]['instruments'], pdf_bytes([evidence['statement']]))
