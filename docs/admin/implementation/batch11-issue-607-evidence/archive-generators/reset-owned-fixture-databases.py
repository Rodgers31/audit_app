"""Reset only explicitly owned disposable databases after a preserved setup failure."""
import hashlib
import json
from pathlib import Path
import subprocess

out = Path(__file__).resolve().parent
meta = json.loads(subprocess.check_output(['docker', 'inspect', 'batch11-navigation-postgres']))[0]
assert meta['Id'] == '1b078b7391980bcac8018c65b8556a426875c42667c6c4705d0db253bddb1e11'
assert meta['Config']['Labels']['audit_app.owner'] == 'batch11-navigation'
assert meta['HostConfig']['PortBindings'] in [None, {}]
assert meta['HostConfig']['NetworkMode'] == 'container:3f947fe7ad040d6cb7c99d9bdacce56ce7aec11510a0a31a17a6fe663ccb14f1'
rows = []
for db in ['fixture', 'batch7_coordinator']:
    cmd = ['docker', 'exec', 'batch11-navigation-postgres', 'psql', '-p', '55494', '-U', 'fixture', '-d', db, '-Atc', "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"]
    before = subprocess.check_output(cmd, text=True)
    for sql in ['DROP DATABASE ' + db + ' WITH (FORCE)', 'CREATE DATABASE ' + db + ' OWNER ' + db]:
        command = ['docker', 'exec', 'batch11-navigation-postgres', 'psql', '-p', '55494', '-U', 'fixture', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', sql]
        child = subprocess.run(command, text=True, capture_output=True, timeout=30)
        rows.append({'database': db, 'before_public_tables': before, 'command': command, 'child_exit': child.returncode, 'stdout': child.stdout, 'stderr': child.stderr})
        assert child.returncode == 0
    assert subprocess.check_output(cmd, text=True) == ''
data = {'scope': 'Only disposable databases in exact label/ID/network-verified owned PostgreSQL; no source/fixture code edit', 'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'container_id': meta['Id'], 'executions': rows}
with (out / 'reset-owned-fixture-databases.json').open('x') as f:
    json.dump(data, f, indent=2)
assert json.loads((out / 'reset-owned-fixture-databases.json').read_text()) == data
print(json.dumps(data, indent=2))
