"""Verify a fresh final replay against the actual published checkout/corpus."""
import argparse
from datetime import datetime
import importlib.util
import json
from pathlib import Path


def verify(root, receipt):
    spec = importlib.util.spec_from_file_location(
        "readiness_recorder", Path(__file__).with_name("record.py")
    )
    record = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(record)
    data = json.loads(receipt.read_text())
    command = data["command"]
    runtime = data["runtime"]
    environment = data["environment"]
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(value, str) or not value.strip() for value in command)
        or not isinstance(runtime, dict)
        or any(
            not isinstance(runtime.get(key), str) or not runtime[key].strip()
            for key in ("executable", "python", "platform")
        )
        or not isinstance(environment, dict)
        or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in environment.items()
        )
        or environment.get("PYTHON_DOTENV_DISABLED") != "1"
    ):
        raise RuntimeError("Missing or malformed execution provenance")
    started, ended = (
        datetime.fromisoformat(data[key]) for key in ("started_at", "ended_at")
    )
    if started.tzinfo is None or ended.tzinfo is None or ended < started:
        raise RuntimeError("Invalid execution timestamps")
    if (
        data["verdict"] != "PASS"
        or type(data["child_exit"]) is not int
        or data["child_exit"] != 0
        or data["timed_out"] is not False
        or data["negative_diagnostic"] is not None
    ):
        raise RuntimeError("Receipt is not a successful positive execution")
    if data["source_stable"] is not True or data["before"] != data["after"]:
        raise RuntimeError("Recorded source was unstable")
    if not data["before"]["sources"]:
        raise RuntimeError("Empty source inventory")
    generator = root / data["generated_by"]
    if (
        generator.resolve() != Path(__file__).with_name("record.py").resolve()
        or record.digest(generator) != data["generator_sha256"]
    ):
        raise RuntimeError("Generator bytes differ")
    if record.digest(receipt.with_suffix(".txt")) != data["log_sha256"]:
        raise RuntimeError("Output bytes differ")
    current = record.identity(root)
    if current != data["after"]:
        raise RuntimeError("Published source/corpus differs from replay")
    return dict(
        verdict="PASS",
        head=current["head"],
        tree=current["tree"],
        sources=len(current["sources"]),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve(), args.receipt.resolve())))
