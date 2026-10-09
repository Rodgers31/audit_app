# Retained helper boundary decisions

- Supported identity inputs are canonical or compact hexadecimal UUID strings,
  optionally enclosed by balanced braces or prefixed once by `urn:uuid:`.
  Uppercase hex/prefixes are supported. Canonical, uppercase, compact, balanced
  braces and `urn:uuid:` forms are exercised. Malformed brace/tag/hyphen spellings
  accepted by Python's permissive UUID parser are explicitly rejected.
  They are normalized to canonical UUIDs **before** constructing HTTPX query
  parameters. UUID objects and non-string values are not the public str contract.
  Query syntax/delimiters cannot be identities. Invalid inputs raise safe 400
  before configuration or transport. Bulk requires a list; only `[]` bypasses
  transport.
- Duplicate requested identities are queried once in first-request order;
  canonical equivalents deduplicate together. Bulk returns provider order and
  permits missing requested identities. A valid `[]` from the provider means
  missing (`None` single, `[]` bulk).
- A non-array/absent container, non-object row, invalid/missing identity,
  unrequested identity, repeated normalized identity or explicit failure verdict
  invalidates the entire read with 502. Single cannot return multiple rows.
  Empty HTTP bodies/204 are not evidence of a valid missing-row array.
- Matching profile rows retain fields/values unchanged. The generic reader does
  not require a role vocabulary or every optional projected field. Signed auth
  already validates its role array; active Users has separate row validation.
- Shared errors keep public class/import identity, constructor signature and
  status classification. Ordinary `str`, `repr`, `args`, `.body` contain no
  provider payload. Body is discarded, not truncated. Invalid constructor
  status values become 502 without being formatted; genuine HTTP statuses stay.
- HTTPX transport failures become safe 503; rejected JSON (including invalid
  encoding or excessive decoder nesting) becomes safe 502. Original exception
  chains are suppressed in normal formatted tracebacks. No automatic retry is
  added: an unconfirmed mutation can already have occurred upstream.
- Suppressed chaining does not scrub Python's internal `__context__` or traceback
  frame locals. Deliberate exception/frame introspection is outside the ordinary
  diagnostic contract; the independent Standards probe and author replay confirm
  this limit. No new trusted diagnostic access channel is introduced.
- Invalid configured URLs and non-ASCII service keys become safe 500 before
  transport, including consumers importing shared configuration helpers. Invalid
  per-call header construction becomes safe 400; a direct invalid raw-request URL
  becomes safe 500. No original input or exception text is formatted.
- Count retains valid 206/header/filtered positive controls. Redirects now raise
  their safe HTTP status instead of becoming a spurious zero; non-2xx failure
  handling matches the common transport. Count malformed-success-header semantics
  and column/operator validation are unchanged and outside this lane.

These are deliberate fail-closed compatibility choices for #570/#571, not an
active Users/auth policy rewrite. Future review should assess them against the
frozen Batch 8 contract and actual caller inventory.
