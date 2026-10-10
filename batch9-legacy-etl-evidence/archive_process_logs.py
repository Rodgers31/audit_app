"""Preserve raw owned subprocess logs and verify every archived byte."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
destination = root / "batch9-legacy-etl-evidence/process-logs"
destination.mkdir(exist_ok=True)
records = []
for name, directory in (("original-red", "red4"), ("final-red", "final-red"),
                        ("final-minimum", "final-minimum"), ("final-current", "final-current")):
    source = Path("/tmp/batch9-legacy-etl-" + directory)
    files = sorted([*source.rglob("*.txt"), *source.rglob("*.jsonl")])
    assert files, source
    path = destination / (name + ".tar.gz")
    hashes = {str(file.relative_to(source)): hashlib.sha256(file.read_bytes()).hexdigest() for file in files}
    with tarfile.open(path, "w:gz") as archive:
        for file in files:
            archive.add(file, arcname=str(file.relative_to(source)), recursive=False)
    with tarfile.open(path, "r:gz") as archive:
        for member, expected in hashes.items():
            assert hashlib.sha256(archive.extractfile(member).read()).hexdigest() == expected
    records.append({"original_directory": str(source.resolve()), "archive": str(path.relative_to(root)),
                    "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "files": hashes})
output = {"generated_by": str(Path(__file__).relative_to(root)),
          "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "records": records}
manifest = destination / "manifest.json"
manifest.write_text(json.dumps(output, indent=2) + "\n")
assert json.loads(manifest.read_text()) == output
print(json.dumps({record["archive"]: len(record["files"]) for record in records}))
