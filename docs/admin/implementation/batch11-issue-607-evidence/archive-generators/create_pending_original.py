from pathlib import Path
import hashlib,json
ROOT=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app');OUT=Path(__file__).resolve().parent
probe=OUT/'pending-original-tests';(probe/'utils').mkdir(parents=True)
original=(ROOT/'frontend/e2e/smart-back.spec.ts').read_bytes()
hooks='''
const pending = new Map<any, { release: () => void; requests: any[] }>();
test.beforeEach(async ({ context, page }) => {
  await context.addInitScript({ path: '/evidence/probe-init-v2.js' });
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const requests: any[] = [];
  pending.set(page, { release, requests });
  await page.route(url => url.pathname === '/counties' && url.searchParams.get('p') === '2' && url.searchParams.has('_rsc'), async route => {
    const response = await route.fetch();
    requests.push({ kind: 'real-server-response', url: route.request().url(), status: response.status() });
    await gate;
    await route.fulfill({ response });
  });
});
test.afterEach(async ({ page }, testInfo) => {
  const state = pending.get(page)!;
  const beforeRelease = await page.evaluate(() => ({ url: location.href, y: scrollY, height: document.documentElement.scrollHeight, rows: document.querySelectorAll('table tbody tr').length, events: (window as any).__b11Navigation ?? [] }));
  state.release();
  await page.unrouteAll({ behavior: 'wait' });
  await testInfo.attach('b11-pending-original', { body: JSON.stringify({ beforeRelease, requests: state.requests }, null, 2), contentType: 'application/json' });
});
'''
(probe/'smart-back.spec.ts').write_bytes(original+hooks.encode());(probe/'utils/selectors.ts').write_bytes((ROOT/'frontend/e2e/utils/selectors.ts').read_bytes())
(OUT/'pending-original.config.ts').write_text("import original from '/app/frontend/playwright.ci-cohorts.config';\nexport default { ...original, testDir: '/evidence/pending-original-tests', webServer: original.webServer.map(server => ({ ...server, cwd: '/app/frontend' })) };\n")
r={'generated_by':Path(__file__).name,'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'original_sha256':hashlib.sha256(original).hexdigest(),'original_steps_unchanged':True,'files':{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [probe/'smart-back.spec.ts',probe/'utils/selectors.ts',OUT/'pending-original.config.ts',OUT/'probe-init-v2.js']}}
with (OUT/'pending-original-source.json').open('x') as f:json.dump(r,f,indent=2)
assert json.loads((OUT/'pending-original-source.json').read_text())==r
