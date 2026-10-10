import importlib.util,sys
from pathlib import Path
p=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('record',p/'record_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
if sys.argv[1].startswith('minimum'): m.PYTHON=p/'minimum/bin/python'
raise SystemExit(m.run('legacy-'+sys.argv[1],['-m','pytest','backend/tests/test_batch9_legacy_etl_ownership.py','backend/tests/test_batch9_legacy_etl_sessions.py','backend/tests/test_batch9_legacy_receipt_integrity.py','backend/tests/test_batch9_bootstrap_ownership.py','backend/tests/test_batch9_bootstrap_sessions.py','backend/tests/test_batch9_bootstrap_fixture_safety.py','-q','-p','no:cacheprovider','--junitxml='+str(p/('legacy-'+sys.argv[1]+'-junit.xml'))]))
