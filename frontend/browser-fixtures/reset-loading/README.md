# Reset auth-loading layout regression

This isolated Chrome test requires a local **production** frontend built from the
checkout under examination. It holds the real AuthProvider profile read, observes
the loading state, then releases it and verifies the ready form. No password is
submitted. The auth identity and all API data are synthetic.

From the repository root, start the existing public-route fixture through the
local adapter (Python environment must contain the backend requirements):

```sh
PYTHONDONTWRITEBYTECODE=1 python frontend/browser-fixtures/reset-loading/api.py
```

In another terminal, from `frontend`, build and start with these explicit inert
values (use a clean checkout without `.env*` files):

```sh
export NEXT_TELEMETRY_DISABLED=1
export NEXT_PUBLIC_API_URL=http://127.0.0.1:33518
export NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:33518
export NEXT_PUBLIC_SUPABASE_ANON_KEY=synthetic-browser-anon-key
npm run build
npm run start -- --hostname 127.0.0.1 --port 33508
```

Then, from `frontend`:

```sh
node node_modules/playwright/cli.js test --config browser-fixtures/reset-loading/playwright.config.ts
```

The adapter uses loopback ports 33518/33508 and the existing disposable SQLite
fixture with external HTTP blocked and seeding/warmup disabled. Stop the owned
servers after testing; the Python adapter removes its disposable database on
shutdown. This tests layout during loading, not Supabase access, real recovery
credentials, production LCP, or admin audit pagination. Existing Jest runner
policy excludes `browser-fixtures`, so this file is not a Jest test.
