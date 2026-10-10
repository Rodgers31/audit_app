const factory = require('/app/frontend/jest.config.js');
module.exports = async () => {
  const base = typeof factory === 'function' ? await factory() : await factory;
  return { ...base, rootDir: '/app/frontend', roots: ['/app/frontend', '/evidence/review-spec/unit-detectors'],
    testMatch: ['/evidence/review-spec/unit-detectors/**/*.test.tsx'],
    moduleDirectories: ['/app/frontend/node_modules', 'node_modules'] };
};
