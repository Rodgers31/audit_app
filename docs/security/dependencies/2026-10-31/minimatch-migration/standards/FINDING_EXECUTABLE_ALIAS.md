P2 — metadata-only runtime resolution can certify a different executable

Confirmed on helper SHA256 `fdf4ca8f015192138cc443b5c2e630e333cc20d70400cbf6e562ce47e0eb5047` and manifest `8afa0ebe8c3441b63e9ef216e86159d8297d6cea00c660fd3e62dc74986beac2`. The source is preserved in `apply-tooling-repairs-before-entry-binding.cjs.txt`. The result is recorded in `metadata-alias-resolution-results.json`.

The eight new guards resolve `dependency/package.json` and check that canonical metadata path, matching lock record, name and version. Node can resolve that metadata and the executable module to different package folders. In a wholly owned fixture, add an untracked `node_modules/eslint/node_modules/minimatch` directory. Give it a relative `package.json` symlink to the genuine root modern minimatch 11 metadata. At the metadata's advertised CommonJS entry under the shadow directory, place the exact original minimatch 3.1.5 implementation and its genuine old brace helpers, with a local CommonJS package-type marker.

For the actual copied ESLint caller, `createRequire(caller).resolve('minimatch/package.json')` returns `node_modules/minimatch/package.json`, while `resolve('minimatch')` and `require('minimatch')` select `node_modules/eslint/node_modules/minimatch/dist/commonjs/index.js`. That executable SHA256 is `746849f267c4868a53729225bd85c7dccd387712136fb305fcc0a3eadd4a3d9d`, identical to the preserved original 3.1.5 source. Its callable matching executes and `makeRe` remains a function.

Despite this, `applyRepairs(root, {check:true})` returns a successful seven-package repair verdict, zero absent packages and zero changes. No lock, repair metadata or candidate source was altered. The fixture adds a physical untracked shadow outside the seven full package inventories. This is a malformed-install verification false green, not evidence of an attack in the clean installed tree or a public request exploit.

Exact reproduction:

```
/Users/roger/.codex/visualizations/2026/10/31/01a193b2-b534-7a01-8250-1edf848b9ba5/dependencies/runtime/node-v24.22.1-darwin-arm64/bin/node /Users/roger/.codex/visualizations/2026/10/31/01a193b2-b534-7a01-8250-1edf848b9ba5/dependencies/minimatch-migration/standards/resolution_probe.cjs
```

The ordinary fixture's positive check runs in a separate child, preventing Node resolution caches from masking the subsequent physical mutation. `alias-mechanism-proof.json` separately demonstrates the Node resolver behavior using only previously owned copies.

Bind both the metadata and actual executable resolution to the same reviewed named package folder and expected entry, and inspect the actual entry's regular path. Keep the current modern graph positive and add a permanent test that fails with the metadata-only helper. Final disposition and unchanged-probe re-verification are recorded in the final review report; this file preserves the original finding.
