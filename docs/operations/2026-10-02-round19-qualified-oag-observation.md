# Qualified county listing during bounded OAG ingestion

The explicit `--audits-observe-listing` option bridges #234's current publisher
inventory and the five-edition execution scope. It requires the unchanged reviewed
`--audits-source-manifest`, audits alone, and non-dry execution. Omitting either
opt-in preserves the existing behavior. This code grants no production approval;
Actions remains OFF.

From the approved release checkout's `backend` directory, with its verified
interpreter and configuration, the proposed command is:

```sh
python -m seeding.cli seed --domain audits \
  --audits-source-manifest ../docs/operations/2026-10-01-round11-oag-catchup/manifest.json \
  --audits-observe-listing --no-dry-run
```

The observer bypasses the HTTP body cache and reads the official parent listing
and every year page from FY2021/22 onward. Its inventory is qualified **county
combined volumes on publisher year pages**, not all OAG documents. The ordinary
scheduled path retains its sitemap discovery. No unselected source registration,
PDF fetch, extraction, load or publication write is offered.

Before selected registration, each unselected listed volume must match the
hash-pinned eight-edition authority shipped with the backend package. Verification
reads its actual retained PDF bytes; Kenya/publisher/type/status/dataset/edition;
complete parser statistics and latest attempt; extracted MD5 and any individual
artifact binding; every extraction and its exactly-one adopted audit, text/JSON
hash/page/county/period; and all 47 attributed county chapters. Legacy absent
binding stays absent and is labelled as extracted-MD5/complete-parser evidence.
Retained bytes **do not establish an unchanged live publisher PDF**. Missing files,
changed editions or incomplete evidence refuse before selected source writes;
the CLI's already-created job and observational metadata can still be committed.
Do not download/reparse unselected volumes or invent provenance to clear refusal.

Successful metadata distinguishes five processed/current selected outcomes from
three independently verified adopted outcomes. `whole_world_coverage` stays false.
The actual coverage consumer rechecks unselected persisted state, inventory/year
coherence, pinned scope outcomes and observation age (maximum 24 hours; future or
naive timestamps refuse). The existing geographic/institutional/publication gates
still detect missing cells and new listed years. Producer and page hashes bind the
receipt's lineage; they do not authenticate arbitrary database rewrites. A newer
ordinary broad run continues to use its existing outcome contract.

The observation shares normal domain/total budgets and precedes the county start
window's fetch decisions. Three adopted volume reads add bounded DB transfer and
local hashing; no production timing/egress forecast is certified. A timeout may
retain the job/listing receipt and earlier selected commits. Resume the same
command after checking actual state; do not clear caches, reset IDs or broaden
scope. There is no generic catch-up inverse.

The Round19 evidence bank contains the proposed full validation runner copied from
the existing `seed.yml` Python body, with only a verified `READ ONLY REPEATABLE READ`
transaction and rollback added. It does not create an ingestion job. Root must
run that complete validation in the accepted runtime; a county-only OK is not
full pipeline acceptance. The bank's runner is syntax-checked, not production-run.

Before adoption, S1's compatible recovery and exclusive writer window, actual
publisher/code corrections and the three #379 text trims must complete. Recapture
the **actual** resulting baseline; never reuse a pre-code correction plan. Protect
national2392, legacy2395/2396, Homa Bay2391, current2539/2541/2542 and all unselected
sources, entities/countries and audit/extraction columns. The observer fingerprints
current unselected rows; independent release preservation must still verify all
protected cohorts.

Remaining #234 acceptance is actual five-volume adoption, 376 distinct qualified
county/year/institution cells under the unchanged current inventory, complete
source/page and preservation receipts, successful full validation, then S2's
signed backend invalidation followed by exact frontend acknowledgement and changed
API/rendered evidence at fixed deployment SHAs. #230's disputed project identity,
payment/source narrative, human review, cleanup and Projects exposure remain
separate. Neither issue closes from local tests or a publisher HTML capture.
