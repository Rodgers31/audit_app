import original from './playwright.ci-cohorts.config';

export default {
  ...original,
  testDir: './browser-regressions',
  outputDir: './readiness-results',
  reporter: [['list'], ['html', { outputFolder: './readiness-report', open: 'never' }],
    ['json', { outputFile: './readiness-results/results.json' }]],
};
