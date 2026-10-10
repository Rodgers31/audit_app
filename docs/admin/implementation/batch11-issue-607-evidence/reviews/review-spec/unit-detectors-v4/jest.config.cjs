const factory = require('/app/frontend/jest.config.js');
module.exports = async () => {
  const base = typeof factory === 'function' ? await factory() : await factory;
  return { ...base, rootDir: '/app/frontend', roots: ['/app/frontend', '/evidence/review-spec/unit-detectors-v4'],
    testMatch: ['/evidence/review-spec/unit-detectors-v4/**/*.test.tsx'],
    moduleDirectories: ['/app/frontend/node_modules', 'node_modules'] };
};
