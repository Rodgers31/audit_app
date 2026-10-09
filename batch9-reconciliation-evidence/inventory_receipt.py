"""Read-only repository writer census; host/deployed coverage is unverified."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"register_domain\(|SessionLocal|\b(?:db|session|conn|connection|db_session)\.(?:add|delete|commit|execute|bulk_save_objects|query)\(|INSERT INTO|UPDATE |DELETE FROM|backfill|threading\.Thread|subprocess|initialize_reference_data")
FOLDERS = ("backend", "etl", "scripts", ".github/workflows")


def main():
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\x00")
    tracked = {name for name in tracked if name}
    files = set()
    for name in tracked:
        path = ROOT / name
        relative = Path(name)
        selected = (any(name.startswith(folder + "/") for folder in FOLDERS)
                    and path.suffix in (".py", ".yml", ".yaml")
                    and "tests" not in relative.parts and "__pycache__" not in relative.parts)
        if selected or (relative.parent == Path(".") and relative.match("docker-compose*.yml")):
            files.add(path)
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
               "scope": "Tracked Python/YAML in backend, etl, scripts and .github/workflows, excluding tests and __pycache__, plus root docker-compose*.yml; other files and deployed configuration not scanned",
               "whole_repository_writer_coverage": False,
               "selected_folders": FOLDERS, "selected_suffixes": [".py", ".yml", ".yaml"],
               "tracked_file_count": len(tracked),
               "omitted_tracked_files": sorted(tracked - {str(p.relative_to(ROOT)) for p in files}),
               "omitted_scope_requirement": "Before policy provisioning, independent operators must inventory every omitted repository scope/file for writers and launch configuration, including admin, infra, frontend, Dockerfiles and shell/config files; reconcile that source review with complete deployed host/scheduler discovery. This candidate scan alone cannot authorize quiescence.",
               "source_sha256": source_hashes, "registered_domains": domains, "matches": matches}
    path = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).with_name("writer-census.json")
    assert not path.exists()
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    check = json.loads(path.read_text())
    assert check["generator_sha256"] == receipt["generator_sha256"] and check["matches"] == matches
    print(f"{len(files)} source files; {len(domains)} domains; {len(matches)} candidate anchors. Host coverage unverified.")


if __name__ == "__main__":
    main()
