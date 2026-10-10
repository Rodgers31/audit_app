"""Real child controls for the current replay, using owned inert fixtures only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PREFIX = os.environ.get('BATCH10_REPLAY_PREFIX') == '1'
NODE = Path(os.environ['BATCH10_REPLAY_TEST_NODE']).resolve()
PYTHON = [sys.executable, *(['-O'] if sys.flags.optimize else [])]
DECOYS = {'DATABASE_URL': 'postgresql://toy:toy@db.example.invalid/toy',
          'SUPABASE_SERVICE_ROLE_KEY': 'toy-service-role', 'AWS_SECRET_ACCESS_KEY': 'toy-cloud-secret',
          'PROVIDER_ENDPOINT': 'https://provider.example.invalid', 'NODE_OPTIONS': '--no-warnings',
          'NEXT_PUBLIC_API_URL': 'https://api.example.invalid', 'INTERNAL_API_URL': 'https://internal.example.invalid',
          'NEXT_PUBLIC_SUPABASE_URL': 'https://supabase.example.invalid', 'PYTHONPATH': '/toy/python',
          'HTTPS_PROXY': 'http://proxy.example.invalid', 'npm_config_registry': 'https://registry.example.invalid'}


class ReplayControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='batch10-current-replay-')
        self.addCleanup(self.temp.cleanup)
        self.own = Path(self.temp.name)
        self.repo = self.own / 'repo'
        self.pkg = self.repo / 'docs/admin/implementation/batch10-investigation-replay'
        self.pkg.mkdir(parents=True)
        self.out = self.own / 'output'
        self.out.mkdir()
        source = REPO / 'docs/admin/implementation/batch10-dependencies-evidence/run.py' if PREFIX else HERE / 'run_v2.py'
        self.runner = self.pkg / 'run_v2.py'
        self.runner.write_bytes(source.read_bytes())
        if not PREFIX:
            shutil.copyfile(HERE / 'replay_env.py', self.pkg / 'replay_env.py')
        for command in (['git', 'init', '-q'], ['git', 'add', '.'],
                        ['git', '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture']):
            subprocess.run(command, cwd=self.repo, check=True, capture_output=True)
        self.env = {'PATH': str(NODE.parent) + os.pathsep + os.defpath,
                    'BATCH10_DEPENDENCIES_OUTPUT': str(self.out), 'PYTHONDONTWRITEBYTECODE': '1', **DECOYS}

    def run_child(self, code, cwd=None):
        return subprocess.run([*PYTHON, str(self.runner), 'control', str(cwd or self.repo), *PYTHON, '-c', code],
                              env=self.env, capture_output=True, timeout=30)

    def test_recorder_drops_ambient_credentials_endpoints_and_loader_inputs(self):
        result = self.run_child('import json,os;print(json.dumps(dict(os.environ)))')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        observed = json.loads((self.out / 'control.stdout').read_bytes())
        for key in DECOYS:
            if key.startswith('NEXT_PUBLIC_') or key == 'INTERNAL_API_URL':
                self.assertEqual(observed[key], 'http://127.0.0.1:18014')
            else:
                self.assertNotIn(key, observed, 'ambient decoy leaked into actual child: ' + key)

    def test_recorder_external_candidate_need_not_be_git(self):
        candidate = self.own / 'candidate'
        candidate.mkdir()
        self.assertFalse((candidate / '.git').exists())
        result = self.run_child('from pathlib import Path;Path("package-lock.json").write_text("new input")', candidate)
        self.assertEqual(result.returncode, 1, result.stderr.decode())
        receipt = json.loads((self.out / 'control.json').read_bytes())
        self.assertEqual(receipt['exit'], 0)
        self.assertFalse(receipt['source_stable'])
        self.assertIn(str((candidate / 'package-lock.json').resolve()), receipt['input_after']['files'])
        self.assertEqual(receipt['source_before']['head'], subprocess.check_output(['git','rev-parse','HEAD'],cwd=self.repo,text=True).strip())

    def test_recorder_allows_unloaded_dotenv_template(self):
        (self.repo / '.env.example').write_text('DATABASE_URL=toy-template')
        result = self.run_child('print("actual inert child")')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertTrue(json.loads((self.out / 'control.json').read_bytes())['source_stable'])

    def test_recorder_refuses_ancestor_git_repository(self):
        # A nested uninitialized checkout must not discover its parent's Git repository.
        nested = self.repo / 'nested'
        nestedpkg = nested / 'docs/admin/implementation/batch10-investigation-replay'
        shutil.copytree(self.pkg, nestedpkg)
        result = subprocess.run([*PYTHON, str(nestedpkg / 'run_v2.py'), 'control', str(nested), *PYTHON,
                                 '-c', 'from pathlib import Path;Path("executed").touch()'], env=self.env, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'exact independent Git checkout', result.stderr)
        self.assertFalse((nested / 'executed').exists())

    def test_recorder_refuses_output_in_source(self):
        self.env['BATCH10_DEPENDENCIES_OUTPUT'] = str(self.repo)
        result = self.run_child('from pathlib import Path;Path("executed").touch()')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'external output directory', result.stderr)
        self.assertFalse((self.repo / 'executed').exists())

    def test_recorder_refuses_dotenv_and_inherited_output_before_child(self):
        (self.repo / '.env.local').write_text('DATABASE_URL=toy')
        result = self.run_child('from pathlib import Path;Path("executed").touch()')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'dotenv input refused', result.stderr)
        self.assertFalse((self.repo / 'executed').exists())
        (self.repo / '.env.local').unlink()
        (self.out / 'control.stdout').write_text('retained bytes')
        result = self.run_child('from pathlib import Path;Path("executed").touch()')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.repo / 'executed').exists())
        self.assertEqual((self.out / 'control.stdout').read_text(), 'retained bytes')

    def test_preview_sanitizes_both_server_and_browser_children(self):
        frontend = self.repo / 'frontend'
        frontend.mkdir()
        (frontend / '.env.example').write_text('DATABASE_URL=toy-template')
        bins = self.own / 'bin'
        bins.mkdir()
        # A real owned server exercises fetch/CSS/cleanup. Both npm launches are inert fixture commands.
        npm = bins / 'npm'
        npm.write_text('#!' + str(NODE) + '\n' + '''
const fs=require('node:fs');
console.log(JSON.stringify({fixture_environment:process.env,fixture_mode:process.argv[3]}));
if(process.argv[3]==='start'){
 const http=require('node:http');const port=Number(process.argv.at(-1));
 const server=http.createServer((q,s)=>{if(q.url==='/fixture.css'){s.setHeader('content-type','text/css');s.end('x'.repeat(1100));}
 else{s.end('<link href="/fixture.css" rel="stylesheet">');}});
 server.listen(port,'127.0.0.1');process.on('SIGTERM',()=>server.close(()=>process.exit(0)));
}
''')
        npm.chmod(0o755)
        source = REPO / 'docs/admin/implementation/batch10-dependencies-evidence/preview.cjs' if PREFIX else HERE / 'preview_v2.cjs'
        preview = self.own / 'preview.cjs'
        preview.write_bytes(source.read_bytes())
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**self.env, 'PATH': str(bins) + os.pathsep + str(NODE.parent) + os.pathsep + os.defpath}
        # v2 requires an explicit runtime executable instead of inheriting arbitrary PATH.
        args = [str(NODE), str(preview), str(frontend), str(port)]
        if not PREFIX:
            args += [str(self.out), str(npm)]
        args += ['browser']
        result = subprocess.run(args, env=env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        lines = [json.loads(line) for line in result.stdout.decode().splitlines() if line.startswith('{')]
        cleanup = next(x for x in lines if x.get('check') == 'preview-owned-cleanup')
        server = next(json.loads(line) for line in cleanup['log'].splitlines() if line.startswith('{'))
        browser = next(x for x in lines if x.get('fixture_mode') == 'verify:dependency-browser')
        for child in (server, browser):
            observed = child['fixture_environment']
            for key in DECOYS:
                if key.startswith('NEXT_PUBLIC_') or key == 'INTERNAL_API_URL':
                    self.assertEqual(observed[key], 'http://127.0.0.1:18014')
                else:
                    self.assertNotIn(key, observed, 'ambient decoy leaked into preview child: ' + key)
        self.assertTrue(cleanup['listenerAbsent'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
