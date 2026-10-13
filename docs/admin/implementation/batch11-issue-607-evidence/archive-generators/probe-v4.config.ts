import original from '/app/frontend/playwright.ci-cohorts.config';
export default { ...original, testDir: '/evidence/probe-tests-v2', webServer: original.webServer.map(server => ({ ...server, cwd: '/app/frontend' })) };
