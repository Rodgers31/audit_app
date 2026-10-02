// One allowlist for Playwright, the built frontend and fixture API children.
// Provider credentials and inherited app configuration are never forwarded.
export function legacyEnvironment(source = process.env) {
  const env = Object.fromEntries(['PATH', 'HOME', 'TMPDIR', 'CI', 'PLAYWRIGHT_BROWSERS_PATH',
    'BROWSER_TEST_PYTHON'].filter(key => source[key]).map(key => [key, source[key]]));
  return { ...env, NEXT_TELEMETRY_DISABLED: '1', PYTHON_DOTENV_DISABLED: '1',
    PYTHONDONTWRITEBYTECODE: '1', NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8141',
    NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:8141',
    NEXT_PUBLIC_SUPABASE_ANON_KEY: 'synthetic-browser-anon-key',
    REVALIDATE_SECRET: 'synthetic-browser-secret' };
}
