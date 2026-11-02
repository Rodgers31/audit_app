"""Run the actual ETL loader against its supported driver and numeric models."""
from sqlalchemy import inspect
from etl import database_loader


def test_etl_uses_real_models_without_importing_the_api_framework():
    assert inspect(database_loader.Country).local_table.name == 'countries'
    assert inspect(database_loader.SourceDocument).local_table.name == 'source_documents'


def test_bare_postgresql_url_keeps_the_installed_psycopg2_driver():
    loader = database_loader.DatabaseLoader('postgresql://postgres:fixture@127.0.0.1:62124/social_domain_test')
    try:
        assert loader.engine.dialect.driver == 'psycopg2'
    finally:
        loader.engine.dispose()


def test_actual_http_source_clients_are_installed():
    from etl import pending_bills_extractor, resilient_scraper
    assert pending_bills_extractor.httpx.__version__
    assert resilient_scraper.httpx.__version__
