"""Independent adversarial persisted-readback controls (owned synthetic DBs only)."""
import pytest
from datetime import datetime,timezone
from sqlalchemy import text,select
from test_county_borrowing_producer import specimen,persist,summary,effects
from county_borrowing_fixture import borrowing_pg,owned
from seeding.domains.county_borrowing import writer,run
from seeding import county_borrowing_contract as contract
from services.county_borrowing_coverage import county_borrowing_coverage
from models import Entity,SourceDocument,Extraction


def test_persist_must_refuse_trigger_changed_balance(borrowing_pg,specimen):
    _,factory=borrowing_pg
    with factory.begin() as db:
        db.execute(text("""CREATE FUNCTION b83_review_change_stock() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.outstanding := 999.00; RETURN NEW; END $$"""))
        db.execute(text("""CREATE TRIGGER b83_review_change_stock BEFORE INSERT ON county_debt_observations FOR EACH ROW EXECUTE FUNCTION b83_review_change_stock()"""))
    with owned(factory) as ctx:
        with pytest.raises((ValueError,RuntimeError),match='readback|differs|persisted'):
            stats=persist(factory,ctx,specimen)
            print('TRIGGER_STOCK_ACCEPTED',stats,'public_reader_total=',summary(factory)['total_debt'],flush=True)
    assert summary(factory)['total_debt'] is None


def test_persist_must_refuse_trigger_changed_extraction(borrowing_pg,specimen):
    _,factory=borrowing_pg
    with factory.begin() as db:
        db.execute(text("""CREATE FUNCTION b83_review_change_extraction() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.extracted_json := jsonb_set(NEW.extracted_json, '{reason}', '\"forged persisted content\"'::jsonb); RETURN NEW; END $$"""))
        db.execute(text("""CREATE TRIGGER b83_review_change_extraction BEFORE INSERT ON extractions FOR EACH ROW EXECUTE FUNCTION b83_review_change_extraction()"""))
    with owned(factory) as ctx:
        with pytest.raises((ValueError,RuntimeError),match='readback|differs|persisted'):
            stats=persist(factory,ctx,specimen)
            with factory() as db: print('TRIGGER_EXTRACTION_ACCEPTED',stats,'stored_reason=',db.scalar(select(Extraction)).extracted_json['reason'],flush=True)


def test_coverage_must_refuse_tampered_source_md5(borrowing_pg,specimen):
    _,factory=borrowing_pg
    with owned(factory) as ctx:persist(factory,ctx,specimen)
    with factory.begin() as db:
        doc=db.scalar(select(SourceDocument));doc.md5='0'*32
    with factory() as db:
        county=db.scalar(select(Entity).where(Entity.slug=='kisii-county'))
        with pytest.raises((ValueError,RuntimeError),match='provenance'):
            result=county_borrowing_coverage(db,[county.id])
            print('CHANGED_MD5_ACCEPTED',result[ county.id ]['status'],flush=True)


def test_empty_edition_registry_must_not_claim_live_success(borrowing_pg,specimen,monkeypatch):
    _,factory=borrowing_pg
    monkeypatch.setattr(contract,'EDITIONS',{})
    with owned(factory) as ctx:
        with factory.begin() as db:
            with pytest.raises((ValueError,RuntimeError),match='edition|empty|source'):
                result=run(db,specimen[2],ctx)
                print('EMPTY_EDITIONS_ACCEPTED',result.model_dump(),flush=True)

from services.financial_publication import county_debt_summary

@pytest.mark.parametrize('status',['dated_explicit_zero','selected_instrument_stock','not_reported_in_checked_source'])
def test_coverage_status_cannot_create_evidence_from_empty_stock(status):
    out=county_debt_summary([],source_coverage={'status':status,'complete_liability_coverage':False,'sources':[]})
    assert out['total_debt'] is None
    assert out['debt_source_coverage']['status']=='withheld_or_conflicting'

@pytest.mark.parametrize('field,value',[('http_status',500),('last_verified_at',None),('content_type','text/html')])
def test_coverage_requires_the_complete_source_identity(borrowing_pg,specimen,field,value):
    _,factory=borrowing_pg
    with owned(factory) as ctx:persist(factory,ctx,specimen)
    with factory.begin() as db:
        doc=db.scalar(select(SourceDocument));setattr(doc,field,value)
    with factory() as db:
        county=db.scalar(select(Entity).where(Entity.slug=='kisii-county'))
        with pytest.raises((ValueError,RuntimeError),match='provenance'):
            county_borrowing_coverage(db,[county.id])
"""Independent identity-set and deferred-trigger extensions to the original attacks."""
import pytest
from sqlalchemy import text
from test_county_borrowing_producer import specimen,persist,summary,effects
from county_borrowing_fixture import borrowing_pg,owned


def test_unrequested_source_bound_stock_must_refuse(borrowing_pg,specimen):
    _,factory=borrowing_pg
    with factory.begin() as db:
        db.execute(text("""CREATE FUNCTION b83_review_extra_stock() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE extra integer;
        BEGIN
          IF pg_trigger_depth()=1 THEN
            INSERT INTO county_debt_instruments(entity_id,identity_namespace,instrument_reference,lender,issue_date,currency,debt_category)
              SELECT entity_id,identity_namespace,instrument_reference||'-extra',lender,issue_date,currency,debt_category
              FROM county_debt_instruments WHERE id=NEW.instrument_id RETURNING id INTO extra;
            INSERT INTO county_debt_observations(instrument_id,as_at,source_document_id,principal,outstanding,interest_rate,page_ref,basis,provenance,revision,quarantine_reason)
              VALUES(extra,NEW.as_at,NEW.source_document_id,1000,999,NULL,NEW.page_ref,NEW.basis,NEW.provenance,1,NULL);
          END IF;
          RETURN NEW;
        END $$"""))
        db.execute(text("""CREATE TRIGGER b83_review_extra_stock AFTER INSERT ON county_debt_observations FOR EACH ROW EXECUTE FUNCTION b83_review_extra_stock()"""))
    with owned(factory) as ctx:
        with pytest.raises((ValueError,RuntimeError),match='readback|differs|persisted'):
            result=persist(factory,ctx,specimen)
            print('EXTRA_STOCK_ACCEPTED',result,'effects=',effects(factory),'public_reader_total=',summary(factory)['total_debt'],flush=True)

@pytest.mark.parametrize('dry_run',[True,False])
@pytest.mark.parametrize('field,value,diagnostic',[
    ('interest_rate','1000.000','interest rate'),
    ('identity_namespace',' invalid ','canonical'),
    ('lender','','nonempty'),
    ('as_at','2019-06-30','precede'),
])
def test_dry_run_and_live_use_the_same_pure_instrument_validation(borrowing_pg,specimen,dry_run,field,value,diagnostic):
    _,factory=borrowing_pg
    specimen[0]['instruments'][0][field]=value
    with owned(factory,dry_run) as ctx:
        with pytest.raises(ValueError,match=diagnostic):persist(factory,ctx,specimen)
    assert effects(factory)==(0,0,0,0)

@pytest.mark.parametrize('dry_run',[True,False])
@pytest.mark.parametrize('identity_kind',['county','source_document'])
def test_stored_negative_identity_refuses_preview_and_live(borrowing_pg,specimen,dry_run,identity_kind):
    from models import Country
    from services.receipt_store import configured_receipt_store
    _,factory=borrowing_pg
    before=(0,0,0,0)
    if identity_kind=='county':
        with factory.begin() as db:db.execute(text("UPDATE entities SET id=-100 WHERE slug='kisii-county'"))
    else:
        spec,body,settings=specimen
        configured_receipt_store(settings).put(body)
        with factory.begin() as db:
            country=db.scalar(select(Country).where(Country.iso_code=='KEN'))
            stamp=datetime.now(timezone.utc)
            db.add(SourceDocument(id=-200,**contract.document_fields(spec['id'],country.id),
                meta=contract.document_metadata(spec['id']),fetch_date=stamp,
                last_verified_at=stamp,last_seen_at=stamp,created_at=stamp))
        before=(1,0,0,0)
    with owned(factory,dry_run) as ctx:
        with pytest.raises(ValueError,match='positive integer'):
            persist(factory,ctx,specimen)
    assert effects(factory)==before
