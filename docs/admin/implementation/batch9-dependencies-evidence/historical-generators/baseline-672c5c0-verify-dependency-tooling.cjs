'use strict';

// Run against installed packages after npm ci. These expectations describe
// visible CSS behavior retained by the selector-parser security update.
const assert = require('node:assert/strict');
const path = require('node:path');
const { createRequire } = require('node:module');
const postcss = require('postcss');
const tailwindcss = require('tailwindcss');
const autoprefixer = require('autoprefixer');
// Resolve transitive tooling through its declared caller, even when npm has
// installed it beneath Tailwind instead of hoisting it to the application root.
const tailwindRequire = createRequire(require.resolve('tailwindcss/package.json'));
const nested = tailwindRequire('postcss-nested');
const appConfig = require('../tailwind.config.js');

function expectDeclaration(root, selector, property, value) {
  let found = false;
  root.walkRules((rule) => {
    if (rule.selector.replace(/,\s*/g, ',') !== selector.replace(/,\s*/g, ',')) return;
    rule.walkDecls(property, (declaration) => {
      if (declaration.value === value) found = true;
    });
  });
  assert.ok(found, `Missing ${selector} { ${property}: ${value} }`);
}

async function main() {
  // Each caller has its own dependency range; a root-only parser upgrade can
  // leave vulnerable nested copies installed without breaking an ordinary build.
  for (const [caller, callerRequire] of [
    ['tailwindcss', tailwindRequire],
    ['postcss-nested', createRequire(tailwindRequire.resolve('postcss-nested/package.json'))],
    ['@tailwindcss/typography', createRequire(require.resolve('@tailwindcss/typography/package.json'))],
  ]) {
    const version = callerRequire('postcss-selector-parser/package.json').version;
    assert.equal(version, '7.1.6', `${caller} resolved an unexpected selector parser`);
    assert.ok(callerRequire.resolve('postcss-selector-parser/dist/util/unesc'));
  }

  const classes = 'fixture prose dark:bg-gov-forest md:grid-cols-3 group-hover:text-gov-gold peer-checked:block [&>a:hover]:text-gov-gold';
  const result = await postcss([
    tailwindcss({ ...appConfig, content: [{ raw: classes, extension: 'html' }] }),
    autoprefixer,
  ]).process(
    '@tailwind components; @tailwind utilities; @layer components { .fixture { @apply bg-surface-base text-neutral-text; } }',
    { from: path.join(__dirname, 'dependency-tooling-fixture.css') }
  );

  expectDeclaration(result.root, '.fixture', 'background-color', 'rgb(var(--c-surface-base) / var(--tw-bg-opacity, 1))');
  expectDeclaration(result.root, '.fixture', 'color', 'rgb(var(--c-neutral-text) / var(--tw-text-opacity, 1))');
  expectDeclaration(result.root, '.dark\\:bg-gov-forest:is(.dark *)', 'background-color', 'rgb(23 74 52 / var(--tw-bg-opacity, 1))');
  expectDeclaration(result.root, '.group:hover .group-hover\\:text-gov-gold', 'color', 'rgb(184 135 45 / var(--tw-text-opacity, 1))');
  expectDeclaration(result.root, '.peer:checked ~ .peer-checked\\:block', 'display', 'block');
  expectDeclaration(result.root, '.\\[\\&\\>a\\:hover\\]\\:text-gov-gold>a:hover', 'color', 'rgb(184 135 45 / var(--tw-text-opacity, 1))');
  expectDeclaration(result.root, '.prose :where(a):not(:where([class~="not-prose"],[class~="not-prose"] *))', 'color', 'var(--tw-prose-links)');
  let responsive = false;
  result.root.walkAtRules('media', (atRule) => {
    if (atRule.params !== '(min-width: 768px)') return;
    expectDeclaration(atRule, '.md\\:grid-cols-3', 'grid-template-columns', 'repeat(3, minmax(0, 1fr))');
    responsive = true;
  });
  assert.ok(responsive, 'Missing the medium breakpoint');

  const nestedResult = await postcss([nested]).process(
    '.a, .b { &:hover, & > .c { color: red; } @media (width > 20px) { &:is(.x,.y) { color: blue; } } }',
    { from: undefined }
  );
  expectDeclaration(nestedResult.root, '.a:hover, .a > .c, .b:hover, .b > .c', 'color', 'red');
  expectDeclaration(nestedResult.root, '.a:is(.x,.y), .b:is(.x,.y)', 'color', 'blue');
  console.log('Dependency tooling checks passed: parser resolution, theme tokens, dark/responsive/group/peer/arbitrary selectors, typography, and nesting.');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
