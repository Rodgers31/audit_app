# Current replay tools for the retained investigations

Use these entry points for new executions. The original dependency `run.py` and
`preview.cjs`, and scroll `reviews/review-spec/review_runner.py` and
`direct_controls.mjs`, are **archival-only producers**. Their exact bytes remain
bound to the original receipts. They inherited ambient environment inputs or
depended on author-specific paths. Do not launch them against application
fixtures, pass credentials to them, or use their old output destinations for a
new review. The old packet READMEs describe the original execution procedure;
this document supersedes their recorder/preview instructions for future use.

This additive tooling does not fix #494, #601, or the distinct pagination failure
#607. The historical browser's Linux Node 22.23.3, emulated Chromium 145 and
Playwright 1.58.2 identities remain unchanged. New archive validation on another
runtime certifies archive integrity only, not browser or migration acceptance.

From any clean clone, Python 3.9+ and Node 22+ can run the offline scroll archive
review without dependency installs, browsers, GitHub credentials or network:

```sh
mkdir /absolute/owned/new-scroll-review
python3 docs/admin/implementation/batch10-investigation-replay/scroll_review_v2.py /absolute/owned/new-scroll-review /absolute/path/to/node
```

The output must be an existing empty external directory. The runner derives the
checkout from its own location and passes absolute script paths with the checkout
as its working directory. The direct-control entry point explicitly selects
`frontend` before importing the unchanged parser, which resolves source existence
from its import-time working directory. It executes the current archive verifier, all 32
archive controls and the independent parser/partition controls. It omits the old
runner's live GitHub queries; an offline replay cannot establish live issue state.
Each actual child is captured by the new recorder, with source identities,
generator and environment-policy hashes, real exits, streams and exclusive
readback. `execution-v2.json` explicitly reports
`current_checkout_acceptance: false`.

For a new dependency candidate command, use:

```sh
mkdir /absolute/owned/new-command-output
BATCH10_DEPENDENCIES_OUTPUT=/absolute/owned/new-command-output python3 docs/admin/implementation/batch10-investigation-replay/run_v2.py unique-name /absolute/owned/candidate /absolute/path/to/executable argument
```

The recorder requires an independent Git repository at its own checkout root;
it refuses ancestor discovery. A separate candidate working directory need not
be a Git repository: its actual before/after input bytes are captured separately.
Output paths must be external and fresh. The child receives an explicit minimal
environment, a fresh home/temp/cache, inert loopback API/Supabase targets and no
ambient database/service-role/cloud credentials, provider endpoints, proxies,
loader inputs or npm configuration. The executable path is explicit; runtime
PATH is assembled from its directory, the Python runtime and OS defaults. Dotenv
runtime files at the checkout root, frontend or child working directory are refused;
unloaded `.env*.example`, `.env*.sample` and `.env*.template` documentation is allowed.
This controls inherited configuration; it is not a filesystem or network sandbox
for arbitrary commands. Choose inert fixture commands and owned resources.

For an already prepared owned Next build, use the new preview entry point:

```sh
node docs/admin/implementation/batch10-investigation-replay/preview_v2.cjs /absolute/owned/candidate/frontend 13014 /absolute/owned/new-preview-scratch /absolute/path/to/npm browser
```

It uses the same inert environment boundary for both the server and optional
browser child, rejects dotenv input and inherited runtime output, binds only
loopback, fetches CSS only from that origin without redirects and verifies owned
process cleanup. This command requires real installed application/browser
prerequisites. The regression fixture uses a real owned loopback server and toy
npm commands to test environment isolation and cleanup; it does not establish a
fresh Next/browser acceptance run.

Run the current replay controls with an explicit Node runtime:

```sh
BATCH10_REPLAY_TEST_NODE=/absolute/path/to/node python3 docs/admin/implementation/batch10-investigation-replay/test_replay.py
BATCH10_REPLAY_TEST_NODE=/absolute/path/to/node python3 -O docs/admin/implementation/batch10-investigation-replay/test_replay.py
```

The seven controls execute both actual child environments, a non-Git candidate
mutation, ancestor-Git refusal, in-source output refusal, dotenv refusal and
inherited-output refusal, plus the unloaded dotenv-template positive. The original eight recorder and fourteen bundle
controls remain separate historical compatibility checks. Their candidate test
already initializes the recorder's Git root; initializing the independent
candidate would not address the reported premise. The original scroll runner
also already supplied absolute package commands, so changing only its working
directory would not repair its actual hardcoded-root problem.
