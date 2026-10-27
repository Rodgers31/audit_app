# Ingestion time and frontend Node runtime

IngestionJob's existing timestamp-without-time-zone columns record UTC. The read API normalizes started_at, finished_at and created_at to explicit UTC timestamps. Already-aware values preserve their instant. Unknown timestamps remain null; no history or schema is rewritten. Duration is elapsed time between normalized instants, with pending or invalid intervals unknown.

The ingestion browser parser accepts the same explicit offsets and interprets only these legacy ingestion fields without an offset as UTC. It rejects impossible dates. Relative ages use elapsed instants; detail times use the viewer's browser timezone and show its timezone abbreviation. Missing or invalid display values show an em dash. This rule does not change other ETL calendar or metadata dates.

The frontend requires Node >=24.22.1 <25. Vercel selects the 24.x major and manages security patch rollout; the package engine is a supported-version constraint, not an installed binary. A nested dependency engine such as >=20.0.0 likewise states compatibility. @types/node is TypeScript declarations, not a Node installation.

The actual binary is checked through process.versions.node before dev, build, lint, test and start, with a version receipt in the build output. Node22, Node20, Node24 patches below24.22.1, other majors and prereleases are refused. Both Dockerfiles and setup-node workflow entries select Node24; .nvmrc selects the minimum qualified patch. Docker's mutable24 tag and Vercel's major selection can deliver newer24 security patches. The guard remains required even when a platform accepts a broad engine range.

Run npm run test:node-runtime and the admin operations tests on a supported binary. CI workflow state is an account/release control: updating setup-node entries does not enable any disabled workflow or admit a new nightly source. No provider connection, publishing, uploads or worker activation is part of this repair.

References: [Vercel Node versions](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions), [Node October2026 security releases](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases).
