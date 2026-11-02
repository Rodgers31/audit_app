const frontend = '/Users/roger/.codex/worktrees/admin-social-release-check/audit_app/frontend';
const nextJest = require(frontend + '/node_modules/next/jest');
module.exports = nextJest({ dir: frontend })({
  rootDir: frontend,
  roots: [__dirname],
  modulePaths: [frontend + '/node_modules'],
  testMatch: [__dirname + '/*.independent.test.tsx'],
  testEnvironment: frontend + '/node_modules/jest-environment-jsdom',
  setupFilesAfterEnv: [frontend + '/jest.setup.js'],
  moduleNameMapper: { '^@/(.*)$': frontend + '/$1' },
});
