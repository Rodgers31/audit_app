// Executed by the PostgreSQL HTTP regression. Compile the real service,
// request helper, endpoints and Axios configuration without a Next build.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const assert = require('node:assert/strict');
const ts = require('typescript');
const axios = require('axios');
const root = path.resolve(__dirname, '../..');
const loaded = new Map();
function load(file) {
  file = path.resolve(file);
  if (loaded.has(file)) return loaded.get(file).exports;
  const instance = new Module(file, module);
  loaded.set(file, instance);
  instance.filename = file;
  instance.paths = Module._nodeModulePaths(path.dirname(file));
  const nativeRequire = instance.require.bind(instance);
  instance.require = (name) => {
    // The real Axios request interceptor is server-side here; auth must not run.
    if (name === '@/lib/supabase/client') return { createClient() { throw new Error('Unexpected browser authentication'); } };
    if (name.startsWith('@/')) return load(path.join(root, name.slice(2) + '.ts'));
    if (name.startsWith('.')) {
      const target = path.resolve(path.dirname(file), name);
      if (fs.existsSync(target + '.ts')) return load(target + '.ts');
    }
    return nativeRequire(name);
  };
  const source = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
    fileName: file,
  }).outputText;
  instance._compile(source, file);
  return instance.exports;
}
async function main() {
  const [base, county, expectedFile, outputFile] = process.argv.slice(2);
  process.env.NEXT_PUBLIC_API_URL = base;
  process.env.NODE_ENV = 'test';
  if (process.argv[6] === 'county-debt') {
    const { getCounty, getCounties } = load(path.join(root, 'lib/api/counties.ts'));
    const expected = JSON.parse(fs.readFileSync(expectedFile, 'utf8'));
    const detail = await getCounty(county);
    const list = (await getCounties()).find(item => item.name === detail.name);
    assert.ok(list);
    for (const mapped of [detail, list]) {
      assert.equal(mapped.debt ?? null, expected.total_debt);
      assert.equal(mapped.totalDebt ?? null, expected.total_debt);
      assert.equal(mapped.totalDebtAbsentReason, expected.total_debt_absent_reason);
      assert.equal(mapped.debtCurrency, expected.debt_currency);
      assert.equal(mapped.debtAsAt, expected.debt_as_at);
      assert.equal(mapped.debtAccountingBasis, expected.debt_accounting_basis);
      assert.equal(mapped.debtCoverage, expected.debt_coverage);
    }
    if (outputFile) fs.writeFileSync(outputFile, JSON.stringify({ expected, detail, list }, null, 2));
    console.log('PASS actual counties.ts → apiGet → Axios → PostgreSQL/FastAPI HTTP; debt zero/absence/metadata');
    return;
  }
  const { getBudgetAllocation } = load(path.join(root, 'lib/api/budget.ts'));
  const expected = JSON.parse(fs.readFileSync(expectedFile, 'utf8'));
  const result = await getBudgetAllocation(county, '1900/01');
  // The legacy query is deliberately unsupported: selected period is explicit.
  if (outputFile) fs.writeFileSync(outputFile, JSON.stringify({ expected, result: result === undefined ? 'UNDEFINED' : result }, null, 2));
  assert.deepEqual(result, expected);
  await assert.rejects(() => getBudgetAllocation('not-a-county'), error => error.response?.status === 404);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(() => getBudgetAllocation(county, undefined, controller.signal), error => axios.isCancel(error));
  console.log('PASS actual budget.ts → apiGet → Axios → PostgreSQL/FastAPI HTTP; selected period, 404, cancellation');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
