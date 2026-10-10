from pathlib import Path
import hashlib,json
ROOT=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
OUT=Path(__file__).resolve().parent
probe=OUT/'gated-tests';(probe/'utils').mkdir(parents=True)
original=(ROOT/'frontend/e2e/smart-back.spec.ts').read_bytes()
hooks='''
test.beforeEach(async ({ context, page }) => {
  await context.addInitScript({ path: '/evidence/probe-init-v2.js' });
  const requests: any[] = [];
  (page as any).__b11Requests = requests;
  page.on('response', response => { if (response.url().includes('_rsc')) requests.push({ kind: 'response', url: response.url(), status: response.status() }); });
  await page.route(url => url.pathname === '/counties' && url.searchParams.get('p') === '2' && url.searchParams.has('_rsc'), async route => {
    requests.push({ kind: 'gate:started', url: route.request().url() });
    const response = await route.fetch();
    requests.push({ kind: 'gate:server-complete', status: response.status() });
    await page.getByText(/Showing\\s+11[–\\-]20\\s+of/).waitFor({ state: 'visible', timeout: 4000 });
    requests.push({ kind: 'gate:release', url: page.url() });
    await route.fulfill({ response });
  });
});
test.afterEach(async ({ page }, testInfo) => {
  const events = await page.evaluate(() => (window as any).__b11Navigation ?? []);
  await testInfo.attach('b11-navigation-events', { body: JSON.stringify({ events, requests: (page as any).__b11Requests }, null, 2), contentType: 'application/json' });
});
'''
(probe/'smart-back.spec.ts').write_bytes(original+hooks.encode());(probe/'utils/selectors.ts').write_bytes((ROOT/'frontend/e2e/utils/selectors.ts').read_bytes())
(OUT/'gated.config.ts').write_text("import original from '/app/frontend/playwright.ci-cohorts.config';\nexport default { ...original, testDir: '/evidence/gated-tests' };\n")
r={'generated_by':Path(__file__).name,'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'original_sha256':hashlib.sha256(original).hexdigest(),'original_steps_unchanged':True,'files':{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [probe/'smart-back.spec.ts',probe/'utils/selectors.ts',OUT/'gated.config.ts',OUT/'probe-init-v2.js']}}
with (OUT/'gated-source.json').open('x') as f:json.dump(r,f,indent=2)
assert json.loads((OUT/'gated-source.json').read_text())==r
