"""Partial downloads the nightly paid for must survive to the next night.

The nightly seed job streams 0.6-50MB source PDFs under a wall-clock cap and
keeps a resumable ``<sha256(url)>.part`` when the cap bites, so a document too
slow to fetch in one night finishes across several. That only works if the
partial is still there the next night, which means the ``actions/cache`` save
has to happen.

It did not. From 2026-09-14 to 2026-09-18 (runs 34799406076, 34921218282,
35048000013, 35174426953, 35299414702) the log reads:

    Sep 14  Cache saved with key: seed-pdf-cache-2026-w38-c72cd0b7025eea9d
    Sep 15  Failed to save: Unable to reserve cache with key
              seed-pdf-cache-2026-w38-c72cd0b7025eea9d
    Sep 16  Failed to save: ...   (same key)
    Sep 17  Failed to save: ...   (same key)
    Sep 18  Failed to save: ...   (same key)

    Sep 15, 16, 17, 18:  "PDF cache miss; streaming download
                          (cap 300s, resuming from 27751154 bytes)"

Byte-identical on four consecutive nights. The save key was a hash of the
COMPLETED ``*.pdf`` filenames, so a night whose only progress was 7MB more of
a ``.part`` recomputed the key it already had, collided, and stored nothing.
Every night re-did the same 27MB and threw it away.

What these tests exercise
-------------------------
The real ``Fingerprint the PDF cache`` step, pulled out of
``.github/workflows/seed.yml`` and RUN, over a real directory — not the YAML
text, and not a re-implementation of the step. ``test_a_week_of_nights``
drives it through a week against a model of ``actions/cache``, and the model's
two rules are the two behaviours the logs show:

  * a save whose key already exists stores nothing
    ("Unable to reserve cache with key ..., another job may be creating this
    cache" — and the run carries on),
  * a restore that misses its exact key falls back to the NEWEST entry under
    the prefix ("Cache hit for restore-key: seed-pdf-cache-2026-w38-...").

Everything else — the key templates, the restore prefixes, the fingerprint
command — is read out of the workflow, so these tests track the workflow
instead of drifting from it.

Seen to fail: against the pre-fix step the week ends resuming from the same
offset it started at, exactly as the five runs above did.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "seed.yml"
CACHE_PATH = "backend/data/seeding/cache/pdfs"

#: The 48MB COB county BIRR document, and the offset its ``.part`` was stuck
#: at on 2026-09-15, -16, -17 and -18. Not a round number on purpose: it is
#: the number in the logs.
COB_PART = "c0b" + "0" * 61 + ".part"
STUCK_AT = 27_751_154
COB_TOTAL = 49_758_224  # "PDF downloaded and cached (49758224 bytes)", Sep 15

#: Five OAG documents that are in the cache the whole time, so the completed
#: ``*.pdf`` filename set never changes and the old key never moves.
OAG_PDFS = [
    "3b64a7d8aee22d5ec660d5fd75c6bfcc748edf213850739625dffe726fefe57a.pdf",
    "53c9d1f712f1e3e315070a08388b71b36e849a3e20a0a45ed44501a678e88345.pdf",
    "02abe7a1e0cd4884368b2e4cef1e5277967d1291e47b1a2f11556b59d24a7de1.pdf",
    "d41b489757dce4b8e4ff2cd5adb9efd8cc99e57ec13800f26665b8b703a26e4d.pdf",
    "b70d698a0173638ba89547029f226c5fb6b1dfa3502875c2f3754211c219e808.pdf",
]


# ── reading the real workflow ──────────────────────────────────────────

def _seed_steps() -> list[dict]:
    doc = yaml.safe_load(SEED_WORKFLOW.read_text(encoding="utf-8"))
    return doc["jobs"]["seed"]["steps"]


def _step_by(pred) -> dict:
    for step in _seed_steps():
        if pred(step):
            return step
    raise AssertionError("no such step in the seed job")


def _fingerprint_script() -> str:
    """The `run:` of the step that computes the cache fingerprint."""
    step = _step_by(lambda s: s.get("id") == "pdf_cache_state")
    script = step.get("run")
    assert script, "the fingerprint step has no run: block to execute"
    return script


def _save_key_template() -> str:
    step = _step_by(lambda s: str(s.get("uses", "")).startswith("actions/cache/save"))
    return step["with"]["key"]


def _restore_prefixes() -> list[str]:
    step = _step_by(lambda s: str(s.get("uses", "")).startswith("actions/cache/restore"))
    return [p for p in str(step["with"]["restore-keys"]).split("\n") if p.strip()]


def _render(template: str, period: str, fingerprint: str, run_id: str) -> str:
    """Resolve the ``${{ ... }}`` in a key template.

    Only the three expressions these keys actually use are handled; anything
    else left over is an error rather than a silently half-rendered key.
    """
    out = template
    out = re.sub(r"\$\{\{\s*steps\.pdf_cache_period\.outputs\.period\s*\}\}", period, out)
    out = re.sub(
        r"\$\{\{\s*steps\.pdf_cache_state\.outputs\.fingerprint\s*\}\}", fingerprint, out
    )
    out = re.sub(r"\$\{\{\s*github\.run_id\s*\}\}", run_id, out)
    assert "${{" not in out, f"unresolved expression in key template: {out!r}"
    return out.strip()


# ── running the real step ──────────────────────────────────────────────

def _step_outputs(workspace: Path, period: str = "2026-w38") -> dict[str, str]:
    """Execute the workflow's fingerprint step and return what it wrote.

    Runs the actual `run:` text in bash with ``$GITHUB_OUTPUT`` set, the way
    the runner does, and parses the ``name=value`` lines it appends there.
    ``${{ }}`` inside the run: block is resolved first, as the runner resolves
    it before the shell ever sees the script.
    """
    github_output = workspace / "_github_output"
    github_output.write_text("", encoding="utf-8")
    step = _step_by(lambda s: s.get("id") == "pdf_cache_state")

    # The step's own `env:`, with the one expression it uses resolved --
    # the runner resolves these before the shell starts.
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GITHUB_OUTPUT": str(github_output),
        "HOME": str(workspace),
    }
    for name, value in (step.get("env") or {}).items():
        env[name] = re.sub(
            r"\$\{\{\s*steps\.pdf_cache_period\.outputs\.period\s*\}\}",
            period,
            str(value),
        )

    # A `${{ }}` left in the run: block is pasted in as text by the runner,
    # so do the same here rather than leaving it for bash to mangle.
    script = re.sub(
        r"\$\{\{\s*steps\.pdf_cache_period\.outputs\.period\s*\}\}",
        period,
        _fingerprint_script(),
    )
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
    )
    written = github_output.read_text(encoding="utf-8")
    outputs: dict[str, str] = {}
    for line in written.splitlines():
        if "=" in line:
            name, _, value = line.partition("=")
            outputs[name.strip()] = value.strip()
    return outputs


def _run_fingerprint(workspace: Path) -> str:
    """The fingerprint the step produced, or '' if it produced none.

    A step that cannot produce a fingerprint cannot key a cache; '' is what
    the runner would interpolate into the key, so that is what is returned
    rather than raising. The point of the test is what the KEY does.
    """
    return _step_outputs(workspace).get("fingerprint", "")


class FakeActionsCache:
    """The two ``actions/cache`` behaviours the run logs demonstrate."""

    def __init__(self) -> None:
        self._entries: list[tuple[str, dict[str, bytes]]] = []
        self.save_log: list[tuple[str, bool]] = []

    def save(self, key: str, directory: Path) -> bool:
        """Store ``directory`` under ``key``. A key that exists is a no-op."""
        if any(k == key for k, _ in self._entries):
            self.save_log.append((key, False))
            return False
        snapshot = {p.name: p.read_bytes() for p in sorted(directory.iterdir()) if p.is_file()}
        self._entries.append((key, snapshot))
        self.save_log.append((key, True))
        return True

    def restore(self, key: str, prefixes: list[str], directory: Path) -> str | None:
        """Exact key, else the newest entry under the first matching prefix."""
        for stored_key, snapshot in reversed(self._entries):
            if stored_key == key:
                self._write(snapshot, directory)
                return stored_key
        for prefix in prefixes:
            for stored_key, snapshot in reversed(self._entries):
                if stored_key.startswith(prefix.strip()):
                    self._write(snapshot, directory)
                    return stored_key
        return None

    @staticmethod
    def _write(snapshot: dict[str, bytes], directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for name, blob in snapshot.items():
            (directory / name).write_bytes(blob)


def _workspace(tmp_path: Path, night: int) -> Path:
    """A fresh runner checkout: the repo's scripts, an empty cache dir."""
    ws = tmp_path / f"night{night}"
    (ws / CACHE_PATH).mkdir(parents=True)
    scripts = REPO_ROOT / ".github" / "scripts"
    if scripts.is_dir():
        shutil.copytree(scripts, ws / ".github" / "scripts")
    return ws


# ── the tests ──────────────────────────────────────────────────────────

def test_the_fingerprint_step_is_runnable_at_all():
    """A step whose command cannot run keys every cache the same.

    ``find -printf`` is a GNU extension; on BSD/macOS it exits non-zero with
    "unknown primary or operator". The pre-fix step sent that to /dev/null and
    keyed the cache on the hash of an empty list.
    """
    ws_root = Path(__file__).resolve().parent / "_fp_probe"
    shutil.rmtree(ws_root, ignore_errors=True)
    (ws_root / CACHE_PATH).mkdir(parents=True)
    scripts = REPO_ROOT / ".github" / "scripts"
    if scripts.is_dir():
        shutil.copytree(scripts, ws_root / ".github" / "scripts")
    try:
        (ws_root / CACHE_PATH / OAG_PDFS[0]).write_bytes(b"%PDF-1.4\n%%EOF\n")
        first = _run_fingerprint(ws_root)
        assert first, (
            "the fingerprint step produced no fingerprint= output on this "
            "platform, so every cache save would use the same key"
        )
    finally:
        shutil.rmtree(ws_root, ignore_errors=True)


def test_a_grown_partial_moves_the_key(tmp_path):
    """7MB more of a ``.part`` is progress, and must change the save key."""
    ws = _workspace(tmp_path, 0)
    cache = ws / CACHE_PATH
    for name in OAG_PDFS:
        (cache / name).write_bytes(b"%PDF-1.4\n%%EOF\n")
    (cache / COB_PART).write_bytes(b"x" * 1024)
    before = _run_fingerprint(ws)

    with (cache / COB_PART).open("ab") as handle:
        handle.write(b"y" * 4096)
    after = _run_fingerprint(ws)

    assert before != after, (
        "the cache key did not change when a partial download grew, so the "
        "save collides with the existing entry and the progress is discarded"
    )


def test_a_refreshed_ttl_sidecar_moves_the_key(tmp_path):
    """The five OAG documents have a 24h TTL (``cache_ttl_seconds``).

    Their freshness lives in the ``.json`` sidecar's ``created_at``. If a
    refreshed sidecar does not move the key it is never stored, so the
    restored sidecar ages without bound and the documents miss the cache
    forever after. That is what the run logs show from Sep 16 onward.
    """
    ws = _workspace(tmp_path, 1)
    cache = ws / CACHE_PATH
    for name in OAG_PDFS:
        (cache / name).write_bytes(b"%PDF-1.4\n%%EOF\n")
        (cache / name.replace(".pdf", ".json")).write_text(
            '{"url": "x", "created_at": 1000.0, "bytes": 15}', encoding="utf-8"
        )
    before = _run_fingerprint(ws)

    stale = cache / OAG_PDFS[0].replace(".pdf", ".json")
    stale.write_text('{"url": "x", "created_at": 9999.0, "bytes": 15}', encoding="utf-8")
    after = _run_fingerprint(ws)

    assert before != after, (
        "a refreshed TTL sidecar did not change the cache key, so the "
        "refreshed timestamp is never banked and the document re-downloads "
        "every night"
    )


def test_an_empty_cache_is_never_saved_over_a_good_one(tmp_path):
    """A run that dies before its first download must not publish emptiness.

    The save step is ``if: always()``. ``actions/cache`` hands back the NEWEST
    entry matching the prefix, so storing an empty directory would become that
    newest entry and wipe out every banked partial the next night. Now that
    the key tracks content, such a save would SUCCEED rather than collide, so
    the guard has to be there.
    """
    ws = _workspace(tmp_path, 2)
    outputs = _step_outputs(ws)
    assert outputs.get("files") == "0", (
        "the fingerprint step does not report a file count for an empty "
        "cache directory, so the save step cannot refuse to store it: "
        f"{outputs!r}"
    )

    save_step = _step_by(
        lambda s: str(s.get("uses", "")).startswith("actions/cache/save")
    )
    condition = " ".join(str(save_step.get("if", "")).split())
    assert "files != '0'" in condition, (
        "the cache save is not guarded on a non-empty cache directory; "
        f"its condition is {condition!r}"
    )


def test_a_week_of_nights(tmp_path):
    """The headline. Five nights, the real step, a model of actions/cache.

    Each night the COB document advances by the ~7MB the CDN manages inside
    the 300s cap and is cut off, exactly as observed. By night five the
    document should be complete, or at the very least further along than it
    was on night one.

    Against the pre-fix step every night restores the same snapshot, resumes
    from the same offset and saves nothing — which is the defect, reproduced.
    """
    cache_service = FakeActionsCache()
    period = "2026-w38"
    prefixes = [
        _render(p, period, "unused", "unused") for p in _restore_prefixes()
    ]

    #: What the CDN manages inside the 300s cap on a slow night.
    NIGHTLY_BYTES = 7_248_846

    resumed_at: list[int] = []
    for night in range(5):
        ws = _workspace(tmp_path, night)
        cache = ws / CACHE_PATH
        run_id = f"3500000000{night}"

        restore_key = _render(
            "seed-pdf-cache-${{ steps.pdf_cache_period.outputs.period }}-"
            "${{ github.run_id }}",
            period, "unused", run_id,
        )
        cache_service.restore(restore_key, prefixes, cache)

        # Night one seeds the five completed OAG documents; they never change
        # again, which is precisely why the old filename-only key never moved.
        for name in OAG_PDFS:
            target = cache / name
            if not target.exists():
                target.write_bytes(b"%PDF-1.4\n%%EOF\n")

        part = cache / COB_PART
        start = part.stat().st_size if part.exists() else 0
        resumed_at.append(start)
        with part.open("ab") as handle:
            handle.write(b"z" * min(NIGHTLY_BYTES, COB_TOTAL - start))

        outputs = _step_outputs(ws, period)
        # The step may hand the whole key over (so the workflow does not have
        # to rebuild it in an expression); otherwise render the save step's
        # own template with the fingerprint it did produce.
        save_key = outputs.get("key") or _render(
            _save_key_template(), period, outputs.get("fingerprint", ""), run_id
        )
        cache_service.save(save_key, cache)

    assert resumed_at[-1] > resumed_at[1], (
        "five nights of downloading and the last night resumed from "
        f"{resumed_at[-1]} bytes, no further than night two's "
        f"{resumed_at[1]}. Offsets by night: {resumed_at}. Partial progress "
        "is not being banked — this is runs 34921218282 / 35048000013 / "
        "35174426953 / 35299414702 all resuming from 27751154."
    )
    assert resumed_at == sorted(resumed_at), (
        f"progress went backwards across the week: {resumed_at}"
    )
    assert resumed_at[-1] >= NIGHTLY_BYTES * 3, (
        "by the fifth night the download should have accumulated several "
        f"nights of progress; it had only {resumed_at[-1]} bytes"
    )
