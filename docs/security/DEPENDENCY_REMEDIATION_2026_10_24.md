# Dependency remediation — 24 October 2026

This branch starts at main `804c16e2fa34522d66e695e7c4739af29c232ebc`. It prepares dependency fixes without merging, deploying, applying migrations or enabling features. Drafts #790 and #792 remain separate and unchanged. The older dirty primary checkout and its virtual environments are preserved; their old installed packages are not repaired by a change to this branch.

## Frontend changes and validation

| Package | Before → after | Purpose |
| --- | --- | --- |
| Next.js, Next environment/SWC packages, ESLint config/plugin | 15.5.27 → 15.5.28 | Security patch; framework, compiler and lint versions remain aligned. |
| follow-redirects | 1.16.0 → 1.16.1 | Correct credential stripping for array-form headers and literal matching of custom sensitive-header names. An exact transitive override keeps the reviewed security patch in the lockfile. |

The lockfile changes only those thirteen package entries. The accepted baseline had two affected package roots; fresh candidate full and production npm audits each report zero. This is JavaScript package coverage, not a claim about OS libraries, deployed artifacts or every application vulnerability.

A clean baseline and candidate both passed TypeScript, lint, production build and all 174 Jest suites (2,428 passed tests, one existing skip). Candidate dependency boundary checks also passed. Public build configuration used inert fixture URLs; expected backend connection failures against loopback port 9 were present in both successful builds. Verification used an isolated official Node 22.23.4 download with its published SHA-256; the shared Node installation was not changed.

The new redirect tests use two owned loopback servers, one redirect, inert credentials and bounded request/test timeouts. They confirm the origin receives the credentials, the target receives the public header, and sensitive headers are absent at the target. Both tests fail on the original 1.16.0 package because credentials reach the target, then pass on 1.16.1. No real credential or external server is involved.

### Release changes and optional adoption

- Next 15.5.28 is a security release for [SVG image optimization](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw) and [Server Action denial of service](https://github.com/vercel/next.js/security/advisories/GHSA-p3m5-59mp-jv5r). Its [release notes](https://github.com/vercel/next.js/releases/tag/v15.5.28) introduce no product feature to enable. Keep the existing Sharp 0.35.5 pin and existing image restrictions. No Next 16 upgrade or codemod is included.
- follow-redirects 1.16.1 fixes [array-form credential stripping](https://github.com/follow-redirects/follow-redirects/security/advisories/GHSA-q3jh-wrc6-jgq8) and [custom sensitive-header escaping](https://github.com/follow-redirects/follow-redirects/security/advisories/GHSA-8r9p-f939-6h3c). There is no GitHub release object for this tag; the [tag comparison](https://github.com/follow-redirects/follow-redirects/compare/v1.16.0...v1.16.1) records both fixes. Existing application Axios headers are object-form and use the built-in Authorization header. No new header API or redirect feature is needed in the app.
- The existing `next lint` command is deprecated before Next 16; both baseline and candidate print that notice. A separate small maintenance change could move the scripts to the ESLint CLI before a future framework major. This predates 15.5.28 and is not required for this security patch.
- Local Node 22.19.0 predates the [21 October Node security release](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases). Validation uses fixed 22.23.4. Updating the development/hosting runtime remains operational work; npm advisory counts do not cover the Node binary.

## Serving backend inventory

A bounded read-only Web Shell command inspected package metadata on Render service `srv-d6hr3t5m5p6s73bomqu0`, deployment `dep-dbeijv5g1s2s73fnf1eg`, instance ending `kkk69`. Both dashboard and shell identify commit `804c16e2fa34522d66e695e7c4739af29c232ebc`. The shell's requirements SHA-256 matches this baseline's source. The command had an eight-second kill timeout, imported no application modules, printed no credentials and performed no installs or application/database writes. Normal shell history may retain the command.

The selected instance reports Python 3.12.15, OpenSSL 3.5.7 and 84 installed package metadata entries. Its framework/image/crypto versions include FastAPI 0.156.4, Starlette 1.9.0, multipart 0.0.32, Pillow 13.0.0, cryptography 50.0.2, Requests 2.34.2 and urllib3 2.8.0. Those are newer than the previously audited local environments. This is one observed serving instance at the recorded time, not a guarantee about every replica or future deployment.

A fresh exact-version OSV query for those 84 entries matches pip 25.0.1, python-jose 3.5.0 and ecdsa 0.19.2. Package matches are not demonstrated application exploits: ecdsa's timing finding concerns signing/key generation/ECDH, while this app verifies tokens; python-jose's DER key-confusion finding still needs a vulnerable calling pattern. The dependency replacement and installer update are addressed in the backend phase of this branch. The hosted profile-role issue remains under #790/#789, with no migration applied here.
