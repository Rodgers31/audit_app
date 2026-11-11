"""Inert official-origin bodies, real SQLAlchemy country/entity writes."""
import copy
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from models import Country,Entity,EntityType,SourceDocument
from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient
from seeding.types import DomainRunContext
from seeding.extractors.cog_governors import KENYAN_COUNTIES,SOURCE_URL
from test_cog_governors import page,_synthetic

@compiles(JSONB,'sqlite')
def jsonb_sqlite(*args,**kwargs):return 'JSON'

def test_same_named_foreign_county_cannot_replace_kenya_or_be_mutated(tmp_path,monkeypatch):
    import seeding.domains.county_officials as domain
    path=tmp_path/'owned.sqlite'
    engine=create_engine('sqlite:///'+str(path))
    for model in (Country,Entity,SourceDocument):model.__table__.create(engine)
    try:
        with Session(engine) as db:
            kenya=Country(iso_code='KEN',name='Kenya',currency='KES',timezone='Africa/Nairobi',default_locale='en')
            other=Country(iso_code='UGA',name='Uganda',currency='UGX',timezone='Africa/Kampala',default_locale='en')
            db.add_all([kenya,other]);db.flush()
            rows=[]
            for county in KENYAN_COUNTIES:
                row=Entity(country_id=kenya.id,type=EntityType.COUNTY,canonical_name=county+' County',slug=county.lower().replace(' ','-'),meta={'governor':'Previous Kenya Name'})
                db.add(row);rows.append(row)
            foreign=Entity(country_id=other.id,type=EntityType.COUNTY,canonical_name=KENYAN_COUNTIES[0]+' County',slug='foreign-county',meta={'governor':'Foreign Governor','deputy_governor':'Foreign Deputy'})
            db.add(foreign);db.commit()
            before=copy.deepcopy(foreign.meta)
            roster=page([(_synthetic(c),c) for c in KENYAN_COUNTIES])
            deputies=page([(_synthetic(c).replace('Mwangi','Wanjiru'),c) for c in KENYAN_COUNTIES])
            settings=SeedingSettings(_env_file=None,storage_path=tmp_path,http_cache_enabled=False,rate_limit='1000/sec',max_retries=1,retry_backoff=.001)
            client=SeedingHttpClient(settings,client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,text=roster if str(req.url)==SOURCE_URL else deputies))))
            monkeypatch.setattr(domain,'create_http_client',lambda _:client)
            result=domain.run(db,settings,DomainRunContext(None,False));db.commit()
            assert result.items_processed==47 and not result.errors
            print('foreign_before',before,'foreign_after',foreign.meta,'kenya_first',rows[0].meta)
            assert foreign.meta==before
            assert all(row.meta['governor']!='Previous Kenya Name' for row in rows)
    finally:
        engine.dispose();path.unlink(missing_ok=True)
