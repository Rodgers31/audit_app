# Held-runtime observations

`probe.py` observes the current Linux cgroup/process inventory and projects three
configured database references into endpoint/login hashes. It opens no database
or network connection, constructs no application runtime and starts no worker.
Missing measurements stay unavailable; `capacity_accepted` is always false.

Run only through an independently reviewed, bounded command packet on the
intended host. Supply its exact serving commit using `--expected-source`. The
tool requires every inventoried operational flag to be absent or exactly
`false`, before and after observation. A literal `<unset>` environment value is
refused; that string appears only in the output projection of absent variables.

Optional `--images --fixture-packet PATH` exercises the actual unchanged image
inspector with exactly two tiny PNG/JPEG fixtures. The packet has only
`fixtures` and `product_sha256` fields. Each fixture has `mime`, `width`,
`height`, `base64`, `sha256`; the source inventory pins `config.py`,
`inspection.py` and `inspection_child.py` under `--media-root` (default
`/app/social/media`). JSON must be bounded, unique-keyed and finite. Fixture
hashes, bytes and dimensions must agree with the product result. Wrong MIME,
length and malformed bytes must all refuse. Private temporary files are removed
on normal completion; an interrupted process cannot emit a completion receipt.

The 96 MiB free-memory check is a conservative execution guard for these tiny
fixtures. It is not an accepted worker reserve. No product inspection limit is
weakened. The image capability inventory can advertise MP4, but this tool does
not decode video; a separate source-bound observation is needed for that claim.

`worker_started:false` and `provider_calls:0` describe this tool's actions.
Its coarse process roles do not certify the absence of other background work.
Bind results to separate before/after controls, background-process and protected
ledger witnesses. Configured endpoint hashes do not validate credentials, pooler
clients, role equivalence, observed occupancy or safe connection reserve.

Offline controls (use an existing Python environment with Pillow):

```sh
python scripts/verification/launch_runtime/test_probe.py
python -O scripts/verification/launch_runtime/test_probe.py
```

The tests execute the product child; a missing codec/dependency is a failure.
These are verifier tests, not application upload, retention, restore, worker-load
or publishing acceptance. See the dated [verification scope](../../../docs/releases/media-runtime-storage-20261103/VERIFICATION.md).
