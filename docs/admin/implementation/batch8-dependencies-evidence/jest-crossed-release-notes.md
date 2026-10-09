# Jest publisher release-note review

Primary publisher: [Jest CHANGELOG](https://github.com/jestjs/jest/blob/main/CHANGELOG.md) and [Jest30 migration guide](https://jestjs.io/docs/upgrading-to-jest30).

The full captured publisher notes remain in the owned raw evidence, `jest-crossed-release-notes.md` and `jest-publisher-CHANGELOG.md`. The crossed-release extract SHA256 is `d407e9f396cb9afcbf23a8ee5fed93cc6cedd5045c5aae9e65b72a45cdfc7aa3`.

Crossed release headers, as captured: 30.5.2, 30.5.1, 30.5.0, 30.4.2, 30.4.1, 30.4.0, 30.3.0, 30.2.0, Features, 30.1.3, 30.1.2, 30.1.1, 30.1.0, Features, 30.0.5, 30.0.4, 30.0.3, 30.0.2, 30.0.1, 30.0.0.

Review focused on supported engine requirements, the newly expanded default discovery extensions, resolver replacement, Parcel native watching, coverage instrumentation, formatting and public CLI behavior. The candidate preserves the previous application patterns explicitly, executes the same 147 suites, exercises real JS/JSX/TS/TSX imports/transforms and coverage, and demonstrates actual file-change reruns on both tested native watcher bindings. No publisher compatibility claim substitutes for those executed receipts. The new graph removes braces/micromatch while retaining the unresolved NYC/js-yaml/sprintf chain.

Only Node 22 macOS arm64 and emulated Linux amd64 are verified. Full release text and its original failures/observations are retained locally; this compact note summarizes the review decision.
