"""Freshness gates — "is this data actually still arriving?"

WHY THIS EXISTS
---------------
The nightly validation asserted row-count FLOORS:

    [OK] Audit Records: 27 rows (expected >= 20)

``27 >= 20`` passes forever. It passed every night for months while
``audits`` had not gained a row since 2026-07-19 and ``budget_lines`` since
2026-06-11, because a floor cannot distinguish "up to date" from "frozen".
A gate that cannot fail is not a gate.

Two independent questions are asked here, and both must be, because either
alone can be fooled:

1. :func:`check_ingestion_freshness` — *is the pipeline still reaching the
   publisher?* Read from ``ingestion_jobs.metadata.source_mode``, which
   ``seeding/freshness.py`` records. Catches "we fell back to a git-tracked
   fixture every night", which is invisible in row counts because a fixture
   re-seeds identical values.

2. :func:`check_table_freshness` — *has the data itself moved inside its
   publication cadence?* Catches a source that is reachable and parsing but
   silently yielding nothing.

Cadences come from the Layer-1 source registry, so the tolerances track the
publisher's real schedule (OAG annual with a 6-9 month lag; COB quarterly at
+45 days) instead of an arbitrary number. Being inside a known publication
lull is NOT staleness — a gate that fires every summer would be muted by
February, which is how gates die.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional

from .source_registry import PUBLICATION_SCHEDULE

logger = logging.getLogger("seeding.staleness")

# Severity levels, mirroring the nightly's existing vocabulary.
FAIL = "FAIL"
WARN = "WARN"

#: Fallback reasons a domain sets to say "there is no live source for this
#: yet", as opposed to "the live source failed". Only these downgrade an
#: all-fixture domain from FAIL to WARN. Emitted today by learning_hub
#: (editorial glossary copy) and stalled_projects (OAG audit records with no
#: machine-readable publisher). Adding a reason here is a decision that the
#: gap is known and accepted — not a way to quiet a broken fetch.
DECLARED_NO_SOURCE_REASONS = frozenset({"no_live_source"})

#: Reasons meaning "this fixture is still READ, but nothing in it can reach a
#: reader" — the live domain took over and the file is vestigial. Kept apart
#: from DECLARED_NO_SOURCE_REASONS because it is the opposite statement: not
#: "no extractor exists" but "the extractor exists and it delivered".
#:
#: Without this the gate could not express the healthiest state the design
#: produces. ``bootstrap_provenance`` always reports ``source_mode="fixture"``
#: — bootstrap reads git-tracked files by definition and has no publisher of
#: its own — so a fully superseded bootstrap landed in the all-fixture branch
#: and was reported CRITICAL. The WEAKER claim (no_live_source: nobody ever
#: built an extractor) warned, while the STRONGER one (verified this run
#: against the database: every fixture vestigial) failed the nightly. A domain
#: in the best state it can reach was indistinguishable from a broken one.
#:
#: This is NOT a general-purpose exemption. bootstrap only emits it from
#: ``_supersession()``, which demands per-file evidence from the DATABASE and
#: returns False on any doubt — no session, an unregistered check, a raising
#: check. And it stays WARN, never OK: a git-tracked file is still being read.
SUPERSEDED_REASONS = frozenset({"fixture_superseded"})
OK = "OK"


@dataclass(frozen=True)
class Finding:
    level: str
    label: str
    message: str

    def __str__(self) -> str:  # matches the nightly's "[LEVEL] label: msg"
        return f"[{self.level}] {self.label}: {self.message}"


@dataclass(frozen=True)
class TableRule:
    """How stale a fact table is allowed to get before it is a defect."""

    label: str
    model_name: str
    column: str
    max_age_days: int
    dataset_id: Optional[str] = None
    level: str = FAIL
    note: str = ""


# Tolerances = publication cadence + lag + a grace margin, so a gate only
# fires when the data is later than the publisher's own schedule allows.
TABLE_RULES: List[TableRule] = [
    TableRule(
        label="Audit findings",
        model_name="Audit",
        column="created_at",
        # OAG is annual with a 6-9 month lag, so ~15 months is the honest
        # ceiling for "a new report should have appeared by now".
        max_age_days=460,
        dataset_id="oag_national_audits",
        note="OAG annual, 6-9 month lag",
    ),
    TableRule(
        label="Budget lines",
        model_name="BudgetLine",
        column="created_at",
        # COB reports quarterly at ~45 days, so rows should arrive roughly
        # every 90 days. 150d means one whole quarter was missed — tight
        # enough to fire, loose enough to survive a late publication.
        max_age_days=150,
        dataset_id="cob_qbirr",
        note="COB quarterly, +45 day lag",
    ),
    TableRule(
        label="Source documents",
        model_name="SourceDocument",
        column="fetch_date",
        # Something should be fetched at least monthly across all sources.
        max_age_days=45,
        note="any publisher, any dataset",
    ),
    TableRule(
        label="Economic indicators",
        model_name="EconomicIndicator",
        column="created_at",
        max_age_days=120,
        level=WARN,
        note="KNBS/World Bank, monthly-to-annual",
    ),
]

# A domain must have reached its publisher at least this recently. Generous
# because a slow CDN legitimately costs a few nights of resumed downloading.
MAX_DAYS_SINCE_LIVE = 14


# ─────────────────────────────────────────────────────────────────────────
# Row-count regression — the third question, and the one the FLOORS in
# seed.yml were pretending to answer.
# ─────────────────────────────────────────────────────────────────────────
#
# The nightly asserts ~20 absolute floors. Measured against the 2026-09-07
# run (the counts are that run's own output, not an estimate):
#
#     [OK] Budget Lines: 2136 rows (expected >= 400)
#     [OK] Audit Records: 2338 rows (expected >= 20)
#     [OK] Extractions (provenance middle link): 2325 rows (expected >= 1)
#
# Delete four fifths of the database and fourteen of those twenty floors
# still print ``[OK]`` — including every large fact table. A floor set at
# 20%, or at 0.04%, of live volume is a DISASTER detector wearing a
# regression gate's clothes: it answers "is the table empty?", never "did
# this table just lose most of its rows?".
#
# Raising the constants does not fix it. A hand-tuned higher number is
# stale the next time the data grows, and it converts every legitimate
# reduction into a red night. The floor has to be RELATIVE to what this
# same pipeline saw recently, so it tracks growth by itself.
#
# The baseline is the MAXIMUM observed in a trailing window, not the last
# observation. Comparing only against last night is a ratchet: -5% a night
# clears every individual comparison and compounds to -79% in a month,
# which is the same "cannot fail" defect one layer up. A window maximum
# fires on the cliff AND on the slow bleed, and stays red while the rows
# are still missing rather than absolving itself the following night.
#
# The cost of that choice, stated plainly: a DELIBERATE reduction (the 512
# fabricated county audit rows purged on 2026-07-07 was one) fails the gate
# until the window rolls past it. That is why the window is a week rather
# than MAX_DAYS_SINCE_LIVE's fortnight. No mute is provided, on purpose —
# building an escape hatch before observing any real noise is how a gate
# ends up permanently muted.

#: ``ingestion_jobs.domain`` under which each validate run parks the counts
#: it observed. Reuses a table that already exists and that the freshness
#: gates already read; no migration, no new schema to go dead (P6).
ROW_CENSUS_DOMAIN = "__row_census__"

#: How far back to look for a baseline. Short enough that a deliberate
#: reduction clears on its own within a week; long enough that a single
#: failed night cannot erase the high-water mark.
ROW_CENSUS_WINDOW_DAYS = 7

#: Fraction of the baseline a table may lose before it is a regression.
#: 10% is wider than the churn actually seen between nightly runs (the
#: pending-bills domain rewrites 48 of the 110 loan rows each night, so a
#: short BROP table moves single digits) and far tighter than the 81-99.96%
#: headroom the absolute floors leave.
ROW_DROP_TOLERANCE = 0.10

#: …and it must be a real drop, not tiny-table arithmetic. On a 7-row table
#: one row is 14%. Below this many rows lost, the percentage is noise.
ROW_DROP_MIN_ABSOLUTE = 2


def _age_days(ts: Optional[datetime], now: datetime) -> Optional[float]:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() / 86400.0


def in_publication_lull(dataset_id: Optional[str], today: date) -> bool:
    """True when the publisher is not expected to have published recently.

    Prevents the annual-report gate from screaming through the eight months
    of every year when OAG legitimately has nothing new out.
    """
    if not dataset_id:
        return False
    sched = PUBLICATION_SCHEDULE.get(dataset_id)
    if not sched:
        return False
    return sched.get("frequency") == "annual"


def check_table_freshness(session, now: Optional[datetime] = None) -> List[Finding]:
    """Has each fact table changed inside its publisher's cadence?"""
    from sqlalchemy import func

    import models

    now = now or datetime.now(timezone.utc)
    findings: List[Finding] = []

    for rule in TABLE_RULES:
        model = getattr(models, rule.model_name, None)
        if model is None:  # pragma: no cover - defensive
            findings.append(
                Finding(FAIL, rule.label, f"model {rule.model_name} not found")
            )
            continue
        column = getattr(model, rule.column, None)
        if column is None:  # pragma: no cover - defensive
            findings.append(
                Finding(
                    FAIL, rule.label, f"column {rule.column} not on {rule.model_name}"
                )
            )
            continue

        newest = session.query(func.max(column)).scalar()
        age = _age_days(newest, now)
        if age is None:
            findings.append(
                Finding(rule.level, rule.label, "table is EMPTY — nothing ingested")
            )
            continue
        if age > rule.max_age_days:
            findings.append(
                Finding(
                    rule.level,
                    rule.label,
                    f"newest row is {age:.0f} days old (limit "
                    f"{rule.max_age_days}d for {rule.note}); newest={newest}",
                )
            )
        else:
            findings.append(
                Finding(
                    OK,
                    rule.label,
                    f"newest row {age:.0f}d old (limit {rule.max_age_days}d)",
                )
            )
    return findings


def _prior_census(session, now: datetime) -> tuple:
    """Every row census recorded inside the window, oldest first.

    Returns ``(observations, error)``. ``error`` is a string when the census
    could NOT be read — the caller must surface that rather than treat an
    unreadable history as "no drop detected", which is the fail-open shape
    this whole module exists to remove.
    """
    from models import IngestionJob

    cutoff = now - timedelta(days=ROW_CENSUS_WINDOW_DAYS)
    try:
        rows = (
            session.query(IngestionJob)
            .filter(
                IngestionJob.domain == ROW_CENSUS_DOMAIN,
                IngestionJob.started_at >= cutoff.replace(tzinfo=None),
            )
            .all()
        )
    except Exception as exc:  # pragma: no cover - defensive
        return [], f"could not read the row census: {exc}"

    observations = []
    for job in sorted(rows, key=_run_order):
        # ``meta`` is JSONB: it can legitimately come back as a list, a
        # string or null. Calling .get on those raises, and a raise inside
        # the read loop would take out the whole validate step — so the
        # shape is checked rather than assumed.
        meta = job.meta if isinstance(job.meta, dict) else {}
        counts = meta.get("row_counts")
        if isinstance(counts, dict) and counts:
            observations.append((getattr(job, "started_at", None), counts))
    return observations, None


def check_row_count_drop(
    session, counts: dict, now: Optional[datetime] = None
) -> List[Finding]:
    """Has any counted table lost rows against what this pipeline last saw?

    ``counts`` is ``{label: row_count}`` for the current run — the same
    labels the nightly's absolute floors already print, so the two gates
    describe the same tables and a reader can line them up.

    Reads only observations recorded by EARLIER runs. It never sees the
    current run's own census, because a baseline that includes today is a
    baseline the current run can never fall below — see
    :func:`check_and_record_row_census`, which is the only supported way to
    call this.
    """
    now = now or datetime.now(timezone.utc)
    findings: List[Finding] = []

    observations, error = _prior_census(session, now)
    if error:
        return [Finding(FAIL, "Row census", error)]

    if not observations:
        # First run after this gate ships, or the census stopped being
        # written. Either way nothing is known — and "nothing is known" is
        # reported as such, never as OK.
        return [
            Finding(
                WARN,
                "Row census",
                f"no baseline in the last {ROW_CENSUS_WINDOW_DAYS} days — "
                f"{len(counts)} count(s) recorded now; drop detection starts "
                f"on the next run",
            )
        ]

    baselines: dict = {}
    for started_at, observed in observations:
        for label, value in observed.items():
            if not isinstance(value, int) or isinstance(value, bool):
                continue
            best = baselines.get(label)
            if best is None or value > best[0]:
                baselines[label] = (value, started_at)

    for label in sorted(counts):
        count = counts[label]
        entry = baselines.get(label)
        if entry is None:
            findings.append(
                Finding(
                    WARN,
                    label,
                    f"{count} rows — no baseline in the last "
                    f"{ROW_CENSUS_WINDOW_DAYS} days for this count; it is "
                    f"new, or it was renamed",
                )
            )
            continue

        baseline, seen_at = entry
        lost = baseline - count
        limit = baseline * (1 - ROW_DROP_TOLERANCE)
        when = seen_at.date().isoformat() if seen_at else "an earlier run"
        if count < limit and lost >= ROW_DROP_MIN_ABSOLUTE:
            findings.append(
                Finding(
                    FAIL,
                    label,
                    f"{count} rows — DOWN {lost} ({lost / baseline:.0%}) from "
                    f"{baseline} seen on {when}. Tolerance is "
                    f"{ROW_DROP_TOLERANCE:.0%}. Rows that were published "
                    f"yesterday are not being published today; find what "
                    f"stopped writing them before the next deploy.",
                )
            )
        elif lost > 0:
            findings.append(
                Finding(
                    OK,
                    label,
                    f"{count} rows — down {lost} from {baseline} ({when}), "
                    f"inside the {ROW_DROP_TOLERANCE:.0%} tolerance",
                )
            )
        else:
            findings.append(
                Finding(
                    OK,
                    label,
                    f"{count} rows — {'+' if count > baseline else '='}"
                    f"{count - baseline} vs {baseline} ({when})",
                )
            )

    # A count that was watched a week ago and is not watched now means a
    # check left seed.yml. Silently narrowing the watch list is the defect
    # in miniature, so it is reported.
    dropped = sorted(set(baselines) - set(counts))
    if dropped:
        findings.append(
            Finding(
                WARN,
                "Row census",
                f"{len(dropped)} count(s) were recorded within the last "
                f"{ROW_CENSUS_WINDOW_DAYS} days and are no longer being "
                f"checked: {', '.join(dropped)}",
            )
        )

    return findings


def record_row_census(
    session, counts: dict, now: Optional[datetime] = None
) -> List[Finding]:
    """Park this run's counts so the next run has something to compare to.

    Returns a FAIL finding if it could not be recorded. A census that stops
    being written freezes the baseline, and a frozen baseline degrades this
    gate back into the floors it replaced — quietly. So it is reported.
    """
    from models import IngestionJob, IngestionStatus

    now = now or datetime.now(timezone.utc)
    try:
        session.add(
            IngestionJob(
                domain=ROW_CENSUS_DOMAIN,
                status=IngestionStatus.COMPLETED,
                started_at=now.replace(tzinfo=None),
                finished_at=now.replace(tzinfo=None),
                items_processed=len(counts),
                meta={"row_counts": dict(counts)},
            )
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        return [
            Finding(
                FAIL,
                "Row census",
                f"counts could NOT be recorded ({exc}) — the next run will "
                f"compare against an older baseline, or none at all",
            )
        ]
    return []


def check_and_record_row_census(
    session, counts: dict, now: Optional[datetime] = None
) -> List[Finding]:
    """Check for a drop, THEN record — in that order, always.

    The order is the whole point, which is why it is not left to callers.
    Recording first puts the current run into its own baseline window, the
    maximum then includes today, and the comparison can never fail. That is
    precisely the shape this gate replaces.
    """
    now = now or datetime.now(timezone.utc)
    findings = check_row_count_drop(session, counts, now=now)
    return findings + record_row_census(session, counts, now=now)


def _all_registered_domains(seen: dict) -> List[str]:
    """Every domain that SHOULD run, not just those that did.

    Reported by review on PR #136. The default used to be ``sorted(seen)`` —
    the domains with a recent job — which made the ``if not jobs`` branch
    below unreachable on exactly the path the nightly uses (``run_all`` passes
    no domain list). A domain that stopped running entirely did not report an
    outage; it silently left the report. A gate that cannot fire is not a gate.

    Falls back to the observed set only if the registry cannot be imported, so
    a packaging problem degrades to the old behaviour rather than crashing the
    nightly — and says so, because a silently reduced watch list is the defect
    being fixed.
    """
    try:
        from .registries import REGISTRY, load_builtin_domains

        load_builtin_domains()
        registered = set(REGISTRY.domains())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Could not read the domain registry (%s); watching only the %d "
            "domain(s) that reported a run. A domain that never ran will NOT "
            "be flagged this cycle.",
            exc,
            len(seen),
        )
        return sorted(seen)
    return sorted(registered | set(seen))


def _run_order(job) -> tuple:
    """Sort key for job recency that never compares ``None`` to ``None``.

    ``started_at`` is non-null in practice, but two rows missing it made the
    plain ``(is not None, started_at)`` key raise on the tuple's second
    element. Ordering by recency must not be able to crash the gate.
    """
    started = getattr(job, "started_at", None)
    return (started is not None, started or datetime.min)


def _latest_run_reasons(jobs) -> set:
    """The fallback reason(s) recorded by the most recent run that recorded one.

    Rows tied on ``started_at`` are kept together: concurrent writers are
    describing the same moment, and a moment its own writers disagree about is
    not a moment we can call healthy.
    """
    reasoned = [j for j in jobs if (j.meta or {}).get("source_fallback_reason")]
    if not reasoned:
        return set()
    newest = max(_run_order(j) for j in reasoned)
    return {
        (j.meta or {}).get("source_fallback_reason")
        for j in reasoned
        if _run_order(j) == newest
    }


def _latest_run_modes(jobs) -> set:
    """The ``source_mode``(s) recorded by the most recent run.

    Rows tied on ``started_at`` are kept together, for the same reason
    :func:`_latest_run_reasons` keeps them: concurrent writers are describing
    one moment, and a moment its own writers disagree about is not one we can
    call healthy.
    """
    if not jobs:
        return set()
    newest = max(_run_order(j) for j in jobs)
    return {
        (j.meta or {}).get("source_mode")
        for j in jobs
        if _run_order(j) == newest
    }


def check_ingestion_freshness(
    session, now: Optional[datetime] = None, domains: Optional[List[str]] = None
) -> List[Finding]:
    """Has each domain actually reached its publisher recently?

    Reads ``ingestion_jobs.metadata.source_mode``. A domain whose every
    recent run says ``fixture`` is serving a file from the repo — the exact
    condition that hid three frozen domains behind a green nightly.
    """
    from models import IngestionJob

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAX_DAYS_SINCE_LIVE)
    findings: List[Finding] = []

    rows = (
        session.query(IngestionJob)
        .filter(IngestionJob.started_at >= cutoff.replace(tzinfo=None))
        .all()
    )
    seen: dict[str, list] = {}
    for job in rows:
        # The row census parks its counts in this same table but is not a
        # seeding domain: it has no publisher and records no source_mode, so
        # letting it through would post a permanent "provenance unknown" WARN
        # about the gate's own bookkeeping. A gate that generates its own
        # noise gets muted along with everything beside it.
        if job.domain == ROW_CENSUS_DOMAIN:
            continue
        seen.setdefault(job.domain, []).append(job)

    watched = domains if domains is not None else _all_registered_domains(seen)
    for domain in watched:
        jobs = seen.get(domain, [])
        if not jobs:
            findings.append(
                Finding(
                    WARN,
                    f"{domain} ingestion",
                    f"no run recorded in the last {MAX_DAYS_SINCE_LIVE} days",
                )
            )
            continue
        modes = [(j.meta or {}).get("source_mode") for j in jobs]
        if "refused" in _latest_run_modes(jobs):
            # The domain reached a verdict of "do not publish" and wrote
            # nothing (freshness.REFUSED). Two things this must not say:
            #
            #   "served from a FIXTURE ... (reasons: unrecorded)"
            #       — which is what a refusal used to print, because raising
            #         before any mark_* left the mode at "unknown" and dropped
            #         it into the all-fixture branch below. Right severity,
            #         false prose: nothing was served from a fixture, nothing
            #         was served at all, and the reason was known.
            #
            #   "reached the publisher in 8/22 recent run(s)"  [OK]
            #       — which is what the `"live" in modes` branch would print
            #         for the first fortnight of nightly refusals, because the
            #         window is 14 days wide and production's window held 8
            #         live runs the day the refuse path went in. That is a
            #         false GREEN, and worse than the false prose.
            #
            # Hence: judged on the LATEST run, not on the union of the window.
            # A refusal is a claim about NOW — about what a reader is being
            # served today — the same reason supersession is judged that way
            # (see _latest_run_reasons). Older live runs do not un-refuse
            # tonight, and a later live run clears it immediately.
            refusals = [m for m in modes if m == "refused"]
            span = (
                f"all {len(modes)} recent run(s)"
                if len(refusals) == len(modes)
                # Never "all N" when it was not all N: writing a different
                # false sentence is not a fix for a false sentence.
                else f"{len(refusals)} of {len(modes)} recent run(s)"
            )
            reasons = {
                (j.meta or {}).get("source_fallback_reason")
                for j in jobs
                if (j.meta or {}).get("source_mode") == "refused"
                and (j.meta or {}).get("source_fallback_reason")
            }
            # WHICH gate refused, not merely that one did. ``source_detail``
            # is the key seeding/cli.py writes from freshness's ``detail``;
            # take the newest refusing run's, since the others describe runs
            # already superseded by it.
            detail = next(
                (
                    d
                    for d in (
                        (j.meta or {}).get("source_detail")
                        for j in sorted(jobs, key=_run_order, reverse=True)
                        if (j.meta or {}).get("source_mode") == "refused"
                    )
                    if d
                ),
                None,
            )
            findings.append(
                Finding(
                    FAIL,
                    f"{domain} ingestion",
                    f"refused to publish in {span}: "
                    f"{', '.join(sorted(reasons)) or 'reason unrecorded'}"
                    f"{f' — {detail}' if detail else ''}. Nothing was written; "
                    f"the site is serving the previous seed's data.",
                )
            )
        elif "live" not in modes and "partial" in modes:
            # Reached the publisher for a secondary series only. Not OK: the
            # figure this domain publishes did not move. See freshness.PARTIAL.
            reasons = {
                (j.meta or {}).get("source_fallback_reason")
                for j in jobs
                if (j.meta or {}).get("source_fallback_reason")
            }
            findings.append(
                Finding(
                    WARN,
                    f"{domain} ingestion",
                    f"only a SECONDARY series refreshed in all "
                    f"{len(modes)} recent run(s); the published figure is "
                    f"still a fixture "
                    f"(reasons: {', '.join(sorted(reasons)) or 'unrecorded'})",
                )
            )
        elif "live" in modes:
            findings.append(
                Finding(
                    OK,
                    f"{domain} ingestion",
                    f"reached the publisher in {modes.count('live')}/"
                    f"{len(modes)} recent run(s)",
                )
            )
        elif all(m is None for m in modes):
            # Pre-dates provenance recording; cannot judge, and saying "OK"
            # would be exactly the false green this module exists to kill.
            findings.append(
                Finding(
                    WARN,
                    f"{domain} ingestion",
                    "no source_mode recorded on any recent run — provenance "
                    "unknown, not confirmed healthy",
                )
            )
        else:
            reasons = {
                (j.meta or {}).get("source_fallback_reason")
                for j in jobs
                if (j.meta or {}).get("source_fallback_reason")
            }
            declared = bool(reasons) and reasons <= DECLARED_NO_SOURCE_REASONS
            # Supersession is a claim about NOW, so it is judged on the newest
            # run alone rather than on the union above.
            #
            # Every bootstrap run writes ONE job row whose reason is already
            # aggregated across all three fixtures (``bootstrap_provenance``
            # -> ``initialize_reference_data``), so that row is a complete,
            # current answer. The union asks a different question — "was this
            # domain ever unhealthy in the last MAX_DAYS_SINCE_LIVE days" — to
            # which, after any one bad night, the answer is permanently yes.
            # That is why #173 did not turn the nightly green: production's
            # window held 27 pre-fix `fixture_stale` rows and one
            # `bootstrap_failed`, so the newest run's verified
            # `fixture_superseded` could not be heard for another fortnight,
            # and any single failure re-armed the veto for a fortnight more.
            # The message already came from the newest row, so the gate
            # printed "all 3 fixture(s) superseded by live data" and failed
            # the run in the same line.
            #
            # ``declared`` deliberately keeps the union: "no extractor was
            # ever built for this domain" is a stable property of the
            # codebase, so a run that disagrees is suspicious, not superseded
            # (see test_staleness_declared_no_source.py). "Every fixture is
            # vestigial" is a property of the live DATABASE, which this
            # pipeline is supposed to flip from false to true.
            latest_reasons = _latest_run_reasons(jobs)
            superseded = bool(latest_reasons) and latest_reasons <= SUPERSEDED_REASONS
            # WHICH file, not just "a fixture". bootstrap already records the
            # offending filename and its age in `source_fallback_detail`; the
            # gate dropped it, so "reasons: fixture_stale" named none of the
            # three files it reads and the message could not be acted on. Take
            # the newest run's detail — the others describe runs already
            # superseded by it.
            detail = next(
                (
                    d
                    for d in (
                        (j.meta or {}).get("source_fallback_detail")
                        for j in sorted(jobs, key=_run_order, reverse=True)
                    )
                    if d
                ),
                None,
            )
            suffix = f" — {detail}" if detail else ""
            if superseded:
                findings.append(
                    Finding(
                        # Never OK: a git-tracked file is still being read, and
                        # a reader of this line should still see that.
                        WARN,
                        f"{domain} ingestion",
                        f"served from a FIXTURE in all {len(modes)} recent "
                        f"run(s), but every file is SUPERSEDED — verified "
                        f"against the database this run, nothing in them "
                        f"reaches a reader{suffix}",
                    )
                )
                continue
            findings.append(
                Finding(
                    # A domain that has never HAD a live source is undelivered,
                    # not broken, and failing the run for it every night is how
                    # a real breakage hides in a permanently red gate. It stays
                    # visible as a WARN — never OK — so the gap is still
                    # reported, it just does not masquerade as a regression.
                    #
                    # Only reasons the domain DECLARED qualify. An unrecorded
                    # reason is still a FAIL: "we don't know why this fell back"
                    # is exactly the state this module exists to catch.
                    WARN if declared else FAIL,
                    f"{domain} ingestion",
                    (
                        f"served from a FIXTURE in all {len(modes)} recent "
                        f"run(s) BY DESIGN — no extractor has been built for "
                        f"it yet (reasons: {', '.join(sorted(reasons))})"
                    )
                    if declared
                    else (
                        f"served from a FIXTURE in all {len(modes)} recent "
                        f"run(s) — the publisher was never successfully read "
                        f"(reasons: {', '.join(sorted(reasons)) or 'unrecorded'})"
                        f"{suffix}"
                    ),
                )
            )
    return findings


def run_all(
    session, now: Optional[datetime] = None, counts: Optional[dict] = None
) -> List[Finding]:
    """Every gate. ``counts`` enables the row-count regression check.

    Omitting ``counts`` runs the two original gates only. It is optional
    because ``run_all`` has callers that have no count to offer, NOT because
    the third gate is — the nightly passes the counts it already computed for
    its own floors.
    """
    findings = check_table_freshness(session, now) + check_ingestion_freshness(
        session, now
    )
    if counts is not None:
        findings += check_and_record_row_census(session, counts, now=now)
    return findings


__all__ = [
    "FAIL",
    "Finding",
    "OK",
    "ROW_CENSUS_DOMAIN",
    "ROW_CENSUS_WINDOW_DAYS",
    "ROW_DROP_MIN_ABSOLUTE",
    "ROW_DROP_TOLERANCE",
    "TABLE_RULES",
    "TableRule",
    "WARN",
    "check_and_record_row_census",
    "check_ingestion_freshness",
    "check_row_count_drop",
    "check_table_freshness",
    "in_publication_lull",
    "record_row_census",
    "run_all",
]
