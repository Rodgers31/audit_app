import original from '/app/frontend/playwright.ci-cohorts.config';
export default { ...original, testDir: '/evidence/controls-tests', webServer: original.webServer.map(server => ({ ...server, cwd: '/app/frontend' })) };
