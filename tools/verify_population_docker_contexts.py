"""Exercise Docker's own ignore semantics with disposable, secret-free contexts.

Runs two FROM scratch COPY builds; never sends the actual workspace to Docker.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAMES = (
    ".env",
    ".env.production",
    "private.pem",
    "signing.key",
    "identity.p12",
    "identity.pfx",
    "secrets.local.json",
    "secrets.sops.yaml",
    "service-account-prod.json",
)


def verify_context(name, ignore_text):
    with tempfile.TemporaryDirectory(prefix="audit-context-") as tmp:
        base = Path(tmp)
        context, output = base / "context", base / "export"
        context.mkdir()
        (context / ".dockerignore").write_text(ignore_text)
        (context / "Dockerfile").write_text("FROM scratch\nCOPY . /context/\n")
        decoys = []
        for parent in ("", "nested", "nested/deeper"):
            for filename in SECRET_NAMES:
                path = Path(parent) / filename
                (context / path).parent.mkdir(parents=True, exist_ok=True)
                (context / path).write_text("PUBLIC TEST DECOY; NOT A CREDENTIAL")
                decoys.append(path)
        code = "config/secrets.py" if name == "backend" else "backend/config/secrets.py"
        positives = ["main.py", "nested/.env.example", code]
        for path in positives:
            (context / path).parent.mkdir(parents=True, exist_ok=True)
            (context / path).write_text("# public runtime/test sentinel")
        if name == "root":
            bundle = Path("config/certs/knbs_trust_store.pem")
            (context / bundle).parent.mkdir(parents=True)
            shutil.copyfile(ROOT / bundle, context / bundle)
            positives.append(str(bundle))
        result = subprocess.run(
            [
                "docker",
                "build",
                "--quiet",
                "--output",
                f"type=local,dest={output}",
                str(context),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)
        shipped = output / "context"
        leaked = [str(p) for p in decoys if (shipped / p).exists()]
        missing = [p for p in positives if not (shipped / p).is_file()]
        if leaked or missing:
            raise RuntimeError(
                json.dumps(
                    {
                        "context": name,
                        "leaked_decoys": leaked,
                        "missing_public_files": missing,
                    }
                )
            )
        return {
            "context": name,
            "excluded_decoys": len(decoys),
            "retained_public_files": positives,
        }


if __name__ == "__main__":
    print(
        json.dumps(
            [
                verify_context(name, (ROOT / path).read_text())
                for name, path in [
                    ("backend", "backend/.dockerignore"),
                    ("root", ".dockerignore"),
                ]
            ],
            indent=2,
        )
    )
