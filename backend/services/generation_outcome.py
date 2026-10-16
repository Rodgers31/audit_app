"""Small safe operational projection; no raw hook diagnostics enter the browser."""
COUNTERS = ("processed", "drafts_created", "baselines", "unchanged", "refused")
STATES = ("disabled", "completed", "unavailable", "failed")


def safe_generation_outcome(raw):
    unknown = {"state": "unavailable", "execution_unverified": True, **dict.fromkeys(COUNTERS, None)}
    if type(raw) is not dict or raw.get("state") not in STATES:
        return unknown
    if "execution_unverified" in raw and type(raw["execution_unverified"]) is not bool:
        return unknown
    if raw.get("execution_unverified") is True:
        if raw["state"] != "failed" or any(raw.get(k) is not None for k in COUNTERS):
            return unknown
        return {**unknown, "state": "failed"}
    if any(type(raw.get(k)) is not int or not 0 <= raw[k] <= 1000 for k in COUNTERS):
        return unknown
    if sum(raw[k] for k in COUNTERS[1:]) != raw["processed"] or raw["state"] == "completed" and raw["refused"]:
        return unknown
    return {"state": raw["state"], "execution_unverified": False, **{k: raw[k] for k in COUNTERS}}
