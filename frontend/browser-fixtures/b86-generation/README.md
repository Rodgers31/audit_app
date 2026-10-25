# Native report browser fixture

Launch the standalone fixture project with the matching frontend dependencies
available read-only. This launcher supplies the inert admin/sessionless auth
aliases required by `Harness.tsx`; rendering the harness inside an arbitrary
Next project without those aliases requires the real product auth provider.

```sh
B86_GENERATION_BROWSER_OUTPUT=/absolute/owned/evidence/browser \
B86_GENERATION_FIXTURE_API=http://127.0.0.1:33802 \
B86_GENERATION_BROWSER_PORT=33586 \
node frontend/browser-fixtures/b86-generation/serve.mjs
```

The explicit loopback API must be an owned fixture running the real admin API
with inert local auth and a prepared local PostgreSQL database. The launcher
proxies only the fixture's generation/account/rule reads, previews and explicit
neutral report detection. It forwards no cookies or bearer tokens. Publishing,
upload, control changes and other commands are refused by the local proxy.
No product route, application auth provider or activation flag is changed.

The generated project and cache live inside the output directory, and its
`fixture-launch.json` records the exact source, auth alias and transport origin.
Stop the launcher to stop its Next child. Keep source/effect receipts before
removing the owned generated project.

Run the standalone render/proxy regression without opening a browser:
`node --test frontend/browser-fixtures/b86-generation/serve.test.mjs`.
