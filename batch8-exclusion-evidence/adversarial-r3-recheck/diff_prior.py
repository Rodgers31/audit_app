"""Compare r3 (prior) vs r3b (recheck) results by check name: pass flips, actual-value changes, added/removed."""
import json, re
from pathlib import Path
HERE = Path(__file__).resolve().parent; PRIOR = HERE.parent / "adversarial-r3"
# Names with run-varying content (uuids/iteration ids) are compared on pass flag + uuid-masked actual.
U = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
def load(p):
    return {r["name"]: r for r in map(json.loads, p.read_text().splitlines())}
out = []
for label in ("pg", "pg-extra", "sqlite", "sigalrm"):
    a, b = load(PRIOR / f"results-{label}.jsonl"), load(HERE / f"results-{label}.jsonl")
    for n in sorted(set(a) | set(b)):
        ra, rb = a.get(n), b.get(n)
        if ra is None or rb is None:
            out.append({"run": label, "name": n, "change": "only_in_" + ("recheck" if ra is None else "prior"),
                        "prior": ra and [ra["passed"], ra["actual"]], "recheck": rb and [rb["passed"], rb["actual"]]})
            continue
        ma, mb = U.sub("<uuid>", json.dumps(ra["actual"])), U.sub("<uuid>", json.dumps(rb["actual"]))
        ea, eb = U.sub("<uuid>", json.dumps(ra["expected"])), U.sub("<uuid>", json.dumps(rb["expected"]))
        if ra["passed"] != rb["passed"] or ma != mb or ea != eb:
            out.append({"run": label, "name": n, "change": f"passed {ra['passed']}->{rb['passed']}" + ("" if ma == mb else "; actual changed"),
                        "prior_actual": ra["actual"], "recheck_actual": rb["actual"], "expected": rb["expected"]})
    print(label, "prior", len(a), "recheck", len(b))
for o in out:
    print(json.dumps(o, default=str))
(HERE / "diff-vs-prior.jsonl").write_text("".join(json.dumps(o, default=str) + "\n" for o in out))
