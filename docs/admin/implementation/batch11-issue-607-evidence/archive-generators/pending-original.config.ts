import original from '/app/frontend/playwright.ci-cohorts.config';
export default { ...original, testDir: '/evidence/pending-original-tests', webServer: original.webServer.map(server => ({ ...server, cwd: '/app/frontend' })) };
