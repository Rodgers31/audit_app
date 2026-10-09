"""Read-only repository writer census; host/deployed coverage is unverified."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"register_domain\(|SessionLocal|\b(?:db|session|conn|connection|db_session)\.(?:add|delete|commit|execute|bulk_save_objects|query)\(|INSERT INTO|UPDATE |DELETE FROM|backfill|threading\.Thread|subprocess|initialize_reference_data")


def main():
    files = set()
    for folder in ("backend", "etl", "scripts", ".github/workflows"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix in (".py", ".yml", ".yaml") and "tests" not in path.parts and "__pycache__" not in path.parts:
                files.add(path)
    files.update(ROOT.glob("docker-compose*.yml"))
    matches, source_hashes, domains = [], {}, {}
    for path in sorted(files):
        raw = path.read_bytes()
        source_hashes[str(path.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
        for line, value in enumerate(raw.decode().splitlines(), 1):
            if PATTERN.search(value):
                matches.append({"path": str(path.relative_to(ROOT)), "line": line, "source": value.strip()})
            match = re.search(r'@register_domain\("([^\"]+)"\)', value)
            if match:
                domains[match[1]] = {"path": str(path.relative_to(ROOT)), "line": line}
    receipt = {"generated_by": str(Path(__file__).relative_to(ROOT)),
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "scope": "repository source candidates; runtime host inventory/deployed configuration unverified",
               "source_sha256": source_hashes, "registered_domains": domains, "matches": matches}
    path = Path(__file__).with_name("writer-census.json")
    assert not path.exists()
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    check = json.loads(path.read_text())
    assert check["generator_sha256"] == receipt["generator_sha256"] and check["matches"] == matches
    print(f"{len(files)} source files; {len(domains)} domains; {len(matches)} candidate anchors. Host coverage unverified.")


if __name__ == "__main__":
    main()
