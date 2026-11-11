"""Run the existing offline native corpus and job probes on a candidate image."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

from common import identity, publish, require
from hosted_runner_observation import PROBE, isolated
import native_corpus
import native_jobs
import runtime


def checked(argv, *, env=None, cwd=None, timeout=60):
    return subprocess.run(argv, env=env, cwd=cwd, check=True, capture_output=True,
                          text=True, timeout=timeout).stdout


def qualification():
    require(os.environ == native_jobs.LOCAL_ENV, 'child environment differs')
    isolation = json.loads(checked([sys.executable, '-I', '-c', PROBE]))
    # A network-none namespace may have kernel tunnel devices that are down.
    # Require loopback to be the only active interface and no non-loopback routes.
    isolation['inactive_interfaces'] = [
        name for name in isolation['network_interfaces']
        if not int(Path('/sys/class/net', name, 'flags').read_text(), 16) & 1
    ]
    isolation['network_interfaces'] = [
        name for name in isolation['network_interfaces'] if name not in isolation['inactive_interfaces']
    ]
    require(isolated(isolation) and len(Path('/proc/net/route').read_text().splitlines()) == 1
            and all(line.split()[-1] == 'lo' for line in Path('/proc/net/ipv6_route').read_text().splitlines()),
            'child isolation differs')
    cpuinfo = isolation.pop('cpuinfo')
    cpu = {key.strip(): value.strip() for key, value in
           (line.split(':', 1) for line in cpuinfo.splitlines() if ':' in line)
           if key.strip() in native_jobs.CPU_FIELDS}
    native_jobs.verify_cpu(cpu, cpuinfo)
    python = sys.executable
    require(python == '/opt/ingestion/bin/python' and sys.prefix == '/opt/ingestion',
            'wrong fixed production runtime')
    installed = runtime.validate_runtime(runtime.verify(runtime.ROOT / 'backend/ingestion-runtime.lock.json'))
    require(len(installed['packages']) == 86, 'wrong production package count')
    retained = Path('/retained.pdf')
    scratch = Path('/tmp/qualification')
    scratch.mkdir(exist_ok=True)
    mode = 'optimized' if sys.flags.optimize else 'normal'
    probes = {}
    for job, (arguments, expected) in native_jobs.PROBES.items():
        env = {**native_jobs.LOCAL_ENV, 'GITHUB_JOB': job}
        if job == 'seed':
            env.update(SEED_PLAN_EVENT='workflow_dispatch', SEED_PLAN_DOMAIN='audits',
                       SEED_PLAN_DRY_RUN='true')
        argv = list(arguments) if arguments[0].startswith('/') else [python, *arguments]
        output = checked(argv, env=env, cwd='/source/backend', timeout=30)
        native_jobs.verify_probe_output(job, output, expected)
        corpus = native_corpus.run(scratch / (mode + '-' + job), retained, '/source/backend')
        probes[job] = {'probe_sha256': identity(output), 'cases': corpus['cases']}
    scan = scratch / (mode + '-seed') / 'owned-scan.pdf'
    sys.path.insert(0, '/source/backend')
    from seeding.native_ocr import read_page
    ocr = read_page(scan, 1)
    require('AUDIT 2025 SAMBURU 310327' in ocr, 'application OCR lost source numbers')
    import pypdfium2 as pdf
    text_hash = hashlib.sha256()
    characters = 0
    with pdf.PdfDocument(retained) as document:
        for page in document:
            try:
                textpage = page.get_textpage()
                try:
                    value = textpage.get_text_range()
                finally:
                    textpage.close()
                characters += len(value)
                text_hash.update(value.encode())
                text_hash.update(bytes(1))
            finally:
                page.close()
        pages = len(document)
    fixture = scratch / (mode + '-git')
    fixture.mkdir()
    git = ['/usr/bin/git', '-C', str(fixture)]
    checked([*git, 'init', '-q'])
    (fixture / 'owned').write_text('owned qualification fixture\n')
    checked([*git, 'add', 'owned'])
    checked([*git, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
             'commit', '-qm', 'owned qualification fixture'])
    require(checked([*git, 'status', '--porcelain']) == '', 'Git fixture worktree differs')
    require(len(checked([*git, 'rev-parse', 'HEAD']).strip()) == 40, 'Git fixture commit differs')
    require((pages, characters, text_hash.hexdigest()) ==
            (915, 2027634, 'db754688aa4c88fa69908266a41aad28a03e603027226d0fce877fa81c27cc72'),
            'full retained text differs')
    native = installed['native']
    tesseract = native['tesseract']['version'].splitlines()[0]
    require(tesseract == 'tesseract 5.5.4' and
            all(native[tool]['version'].startswith(tool + ' version 26.11.0')
                for tool in ('pdftoppm', 'pdftotext', 'pdfinfo'))
            and 'Temurin-21.0.13+9' in native['java']['version']
            and checked(['/usr/bin/git', '--version']).strip() == 'git version 2.56.1',
            'candidate tool versions differ')
    publish(scratch / (mode + '-summary.json'), {
        'scope': 'OFFLINE_NATIVE_CANDIDATE', 'writer_admission': 'HELD', 'mode': mode,
        'runtime_sha256': identity(installed), 'packages': len(installed['packages']),
        'native_sha256': identity(native), 'isolation': isolation,
        'cpu_independent_runtime_sha256': identity({
            **installed, 'native': {
                **native, 'tesseract': {**native['tesseract'], 'version': tesseract},
            },
        }),
        'tools': {tool: native[tool] for tool in ('tesseract', 'java', 'pdftoppm', 'pdftotext', 'pdfinfo')},
        'git': {'version': checked(['/usr/bin/git', '--version']).strip(),
                'sha256': runtime.sha256('/usr/bin/git')},
        'cpu': cpu, 'probes': probes, 'app_ocr_sha256': identity(ocr),
        'text': {'pages': pages, 'characters': characters, 'sha256': text_hash.hexdigest()},
        'maxrss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    })


if __name__ == '__main__':
    qualification()
