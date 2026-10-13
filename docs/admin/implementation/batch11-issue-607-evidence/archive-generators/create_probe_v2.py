from pathlib import Path
import hashlib,json
ROOT=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
OUT=Path(__file__).resolve().parent
probe=OUT/'probe-tests-v2'; (probe/'utils').mkdir(parents=True,exist_ok=True)
original=(ROOT/'frontend/e2e/smart-back.spec.ts').read_bytes()
hooks='''
test.beforeEach(async ({ context, page }, testInfo) => {
  await context.addInitScript({ path: '/evidence/probe-init-v2.js' });
  const requests: any[] = [];
  (page as any).__b11Requests = requests;
  page.on('response', response => { if (response.url().includes('_rsc')) requests.push({ url: response.url(), status: response.status() }); });
});
test.afterEach(async ({ page }, testInfo) => {
  const events = await page.evaluate(() => (window as any).__b11Navigation ?? []);
  await testInfo.attach('b11-navigation-events', { body: JSON.stringify({ events, requests: (page as any).__b11Requests }, null, 2), contentType: 'application/json' });
});
'''
(probe/'smart-back.spec.ts').write_bytes(original+hooks.encode())
(probe/'utils/selectors.ts').write_bytes((ROOT/'frontend/e2e/utils/selectors.ts').read_bytes())
(OUT/'probe-v2.config.ts').write_text("import original from '/app/frontend/playwright.ci-cohorts.config';\nexport default { ...original, testDir: '/evidence/probe-tests-v2-v2' };\n")
record={'generated_by':Path(__file__).name,'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'original_source_sha256':hashlib.sha256(original).hexdigest(),'original_steps_unchanged':True,'files':{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [probe/'smart-back.spec.ts',probe/'utils/selectors.ts',OUT/'probe-init-v2.js',OUT/'probe-v2.config.ts']}}
with (OUT/'probe-v2-source.json').open('x') as f:json.dump(record,f,indent=2)
assert json.loads((OUT/'probe-v2-source.json').read_text())==record
