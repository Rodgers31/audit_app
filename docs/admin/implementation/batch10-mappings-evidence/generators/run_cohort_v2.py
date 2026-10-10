import importlib.util,sys
from pathlib import Path
p=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('record',p/'record_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
if sys.argv[1].startswith('minimum'): m.PYTHON=p/'minimum/bin/python'
url='postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker'
files=['test_batch10_etl_mappings.py','test_batch10_etl_mappings_process.py','test_batch10_etl_mappings_migration.py','test_batch7_etl_postgres.py','test_batch7_etl_process.py','test_batch7_etl_contract.py','test_batch7_etl_adversarial.py','test_batch7_etl_review.py','test_batch8_native_exclusion.py','test_batch8_exclusion_review.py','test_batch8_exclusion_scope.py','test_batch8_exclusion_sqlite.py','test_admin_operations_lane.py','test_admin_operations_adversarial.py','test_admin_operations_review_regressions.py','test_etl_admin_endpoints.py','test_web_ingestion_ownership.py','test_ingestion_query_transfer.py','test_seeding_cli_budget.py','test_seeding_utils.py']
raise SystemExit(m.run('cohort-'+sys.argv[1],['-m','pytest',*['backend/tests/'+f for f in files],'-q','-p','no:cacheprovider','--junitxml='+str(p/('cohort-'+sys.argv[1]+'-junit.xml'))],extra={'DATABASE_URL':url,'BATCH7_ETL_TEST_DATABASE_URL':url,'BATCH7_ETL_ADVERSARIAL_DATABASE_URL':url,'BATCH7_ETL_REVIEW_DATABASE_URL':url}))
