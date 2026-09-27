"""Alembic history must stay one line: exactly one head, every revision reachable.

Two pull requests that each add a migration revising the same parent both pass
CI on their own, and together fork the history. ``alembic upgrade head`` then
refuses to run ("Multiple head revisions are present"), and it is what
``ci.yml``'s run-migrations job runs against production on every push to main
and what the nightly seed's migrate job runs before anything is seeded. So one
unnoticed fork stops every nightly until someone rechains it by hand.

This happened in the 2026-09-25 round: #244 (drop five unwritten tables) and
#262 (refile the nine-month CBIRR) both revised ``a2f7c1b48d90``. Neither PR's
CI could see the other.

CI tests a pull request merged into the current main, so once the first of two
such PRs has merged, this fails on the second before it can merge.

Reads the migration scripts only; no database.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]


def _script() -> ScriptDirectory:
    cfg = Config(str(BACKEND / "alembic.ini"))
    # alembic.ini's script_location is relative ("alembic"); pin it so the test
    # reads this tree's migrations whatever directory pytest runs from.
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_the_guard_reads_the_real_migrations():
    # Without this, a script_location that resolved to an empty directory
    # would give zero heads and zero revisions, and the checks below would
    # have nothing to disagree with.
    revisions = list(_script().walk_revisions("base", "heads"))
    assert len(revisions) >= 5, (
        f"only {len(revisions)} alembic revisions found under {BACKEND / 'alembic'}"
    )


def test_alembic_has_exactly_one_head():
    heads = _script().get_heads()
    assert len(heads) == 1, (
        f"alembic has {len(heads)} heads {sorted(heads)}: two migrations revise "
        "the same parent. Rechain the later one's down_revision onto the other; "
        "until then `alembic upgrade head` refuses to run in ci.yml's "
        "run-migrations job and in the nightly's migrate job."
    )


def test_every_revision_walks_back_to_base():
    # A down_revision naming a revision that does not exist (a rechain typo)
    # breaks the walk here rather than in production's migrate job.
    script = _script()
    head = script.get_current_head()
    walked = [rev.revision for rev in script.iterate_revisions(head, "base")]
    assert walked and walked[0] == head
    assert len(walked) == len(list(script.walk_revisions("base", "heads")))
