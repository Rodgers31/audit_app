"""Capture a fresh independent Spec replay with helper and runtime readbacks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
p = argparse.ArgumentParser()
p.add_argument('--checkout', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--container', required=True)
p.add_argument('--docker-host', required=True)
a = p.parse_args()
repo, output = a.checkout.resolve(), a.output.absolute()
parent = output.parent
prefix = output.name
assert parent.is_dir() and not output.exists()
replay = repo / 'docs/admin/implementation/batch11-issue-607-evidence/tools/replay.py'
helpers = [replay, replay.with_name('verify_packet.py'), Path(__file__).resolve()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    with (parent / (prefix + '-' + name)).open('x') as f:
        json.dump(value, f, indent=2)


env = {'PATH': os.environ['PATH'], 'DOCKER_HOST': a.docker_host, 'PYTHONDONTWRITEBYTECODE': '1'}
before = {str(path): sha(path) for path in helpers}
identity = subprocess.check_output(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], cwd=repo, text=True).splitlines()
runtime_path = '/opt/b11/node-v22.23.3-linux-x64/bin:/opt/b11/python/bin:/usr/local/bin:/usr/bin:/bin'
runtime_source = """const fs=require('node:fs'),crypto=require('node:crypto'),os=require('node:os');const {chromium}=require('@playwright/test');const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');(async()=>{const b=await chromium.launch();const c=await b.newContext({viewport:{width:1280,height:720}});const p=await c.newPage();console.log(JSON.stringify({node:process.version,arch:process.arch,platform:process.platform,kernel:os.release(),nodeExecutable:process.execPath,nodeSha:sha(process.execPath),playwright:require('@playwright/test/package.json').version,chromium:b.version(),chromiumExecutable:chromium.executablePath(),chromiumSha:sha(chromium.executablePath()),viewport:await p.evaluate(()=>({width:innerWidth,height:innerHeight}))}));await b.close()})().catch(e=>{console.error(e);process.exit(1)});"""
runtime_cmd = [shutil.which('docker'), 'exec', a.container, 'env', '-i', 'PATH=' + runtime_path, 'HOME=/evidence/home', 'PLAYWRIGHT_BROWSERS_PATH=/ms-playwright', 'node', '-e', runtime_source]
runtime = subprocess.run(runtime_cmd, cwd=repo / 'frontend', env=env, text=True, capture_output=True, timeout=60)
write('runtime.json', {'command': runtime_cmd, 'child_exit': runtime.returncode, 'stdout': runtime.stdout, 'stderr': runtime.stderr})
assert runtime.returncode == 0
readback = json.loads(runtime.stdout)
assert readback['node'] == 'v22.23.3' and readback['arch'] == 'x64' and readback['platform'] == 'linux'
assert readback['playwright'] == '1.58.2' and readback['chromium'] == '145.0.7632.6'
assert readback['viewport'] == {'width': 1280, 'height': 720}
command = [sys.executable, str(replay), '--checkout', str(repo), '--output', str(output), '--container', a.container, '--docker-host', a.docker_host, '--mode', 'original-100']
start = time.time()
with (parent / (prefix + '-driver.log')).open('x') as f:
    result = subprocess.run(command, cwd=repo, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=1260)
after = {str(path): sha(path) for path in helpers}
receipt = {'head': identity[0], 'tree': identity[1], 'command': command, 'child_exit': result.returncode, 'started': start, 'ended': time.time(), 'reviewer_runtime': {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform()}, 'helper_hashes_before': before, 'helper_hashes_after': after, 'helper_changed': before != after, 'driver_log_sha256': sha(parent / (prefix + '-driver.log')), 'fresh_output': str(output), 'scope': 'Independent fresh local production-config original case; no hosted or production acceptance.'}
write('driver-receipt.json', receipt)
assert result.returncode == 0 and before == after
assert json.loads((parent / (prefix + '-driver-receipt.json')).read_text()) == receipt
print(json.dumps(receipt, indent=2))
