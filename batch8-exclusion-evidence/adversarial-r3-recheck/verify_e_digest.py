"""Post-hoc: for every E_shared_scope record, the DB entry_id must equal entry_digest(the scope's raw nonce)."""
import json, sys
from uuid import UUID
from seeding.exclusion import entry_digest
ok = []
for f in ("results-pg-run01.jsonl", "results-pg.jsonl"):
    for r in map(json.loads, open(f)):
        if r["name"].startswith("E_shared_scope_4_threads_one_entry_"):
            ok.append([f, r["name"], str(entry_digest(UUID(r["expected"][2]))) == r["actual"][2], r["actual"][:2] == [1, True]])
for o in ok: print(o)
print("all_digest_match", all(o[2] and o[3] for o in ok), len(ok))
sys.exit(0 if ok and all(o[2] and o[3] for o in ok) else 1)
