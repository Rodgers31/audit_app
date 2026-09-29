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

import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, List, Optional

from .source_registry import PUBLICATION_SCHEDULE

logger = logging.getLogger("seeding.staleness")

# Severity levels, mirroring the nightly's existing vocabulary.
FAIL = "FAIL"
WARN = "WARN"

#: Fallback reasons a domain sets to say "there is no live source for this
#: yet", as opposed to "the live source failed". Only these downgrade an
#: all-fixture domain from FAIL to WARN. Emitted today by learning_hub
#: (editorial glossary copy). stalled_projects emitted it until #230 gave it
#: a live source (COB's CBIRR) and removed its invented fixture. Adding a reason here is a decision that the
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

@dataclass(frozen=True)
class SeriesRule:
    """How old the newest OBSERVATION of one national series may get.

    ``TableRule("Economic indicators")`` asks when any row was last
    *created*, across every series in the table. That cannot see a single
    series freezing: the World Bank pull creates rows every January, so a
    monthly inflation series could stop for a year behind a green table.
    This asks the reader's question instead — how old is the figure the page
    would show — by the observation's own ``indicator_date``.
    """

    label: str
    indicator_type: str
    max_age_days: int
    level: str = WARN
    note: str = ""


SERIES_RULES: List[SeriesRule] = [
    SeriesRule(
        label="Monthly inflation (CBK 12-month CPI)",
        indicator_type="inflation_rate_12m",
        # KNBS publishes month M on the last day of M, and rows are dated at
        # month end — so the newest row is 0-31 days old in steady state.
        # 60d means a whole monthly release was missed.
        max_age_days=60,
        note="KNBS monthly CPI, published at month end",
    ),
]


def check_series_freshness(session, now: Optional[datetime] = None) -> List[Finding]:
    """Is the newest observation of each national series inside its cadence?"""
    from sqlalchemy import func

    from models import EconomicIndicator

    now = now or datetime.now(timezone.utc)
    findings: List[Finding] = []
    for rule in SERIES_RULES:
        newest = (
            session.query(func.max(EconomicIndicator.indicator_date))
            .filter(
                EconomicIndicator.indicator_type == rule.indicator_type,
                EconomicIndicator.entity_id.is_(None),
            )
            .scalar()
        )
        age = _age_days(newest, now)
        if age is None:
            findings.append(
                Finding(
                    rule.level,
                    rule.label,
                    f"no national {rule.indicator_type} rows at all",
                )
            )
        elif age > rule.max_age_days:
            findings.append(
                Finding(
                    rule.level,
                    rule.label,
                    f"newest observation is {age:.0f} days old (limit "
                    f"{rule.max_age_days}d for {rule.note}); newest={newest}",
                )
            )
        else:
            findings.append(
                Finding(
                    OK,
                    rule.label,
                    f"newest observation {age:.0f}d old (limit {rule.max_age_days}d)",
                )
            )
    return findings


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
# until the window rolls past it. Inflation has a narrow row-identity receipt
# check for the writer's validated off-cycle supersession; other decreases
# still fail. The window is a week rather than MAX_DAYS_SINCE_LIVE's fortnight.

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
            observations.append((
                getattr(job, "started_at", None),
                counts,
                meta.get("inflation_rows"),
            ))
    return observations, None


def _inflation_rows(session) -> list[dict]:
    """Small identity census for the annual inflation series only."""
    from models import EconomicIndicator

    rows = (
        session.query(
            EconomicIndicator.id,
            EconomicIndicator.indicator_date,
            EconomicIndicator.entity_id,
            EconomicIndicator.value,
            EconomicIndicator.source_document_id,
        )
        .filter(EconomicIndicator.indicator_type == "inflation_rate")
        .order_by(EconomicIndicator.id)
        .all()
    )
    return [
        {
            "id": row.id,
            "date": row.indicator_date.date().isoformat(),
            "entity_id": row.entity_id,
            "stored_value": str(row.value),
            "source_document_id": row.source_document_id,
        }
        for row in rows
    ]


def _canonical_day(value) -> Optional[date]:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _annual_coverage_dates(value) -> Optional[set[str]]:
    if not isinstance(value, list) or not value:
        return None
    dates = set()
    for day in value:
        parsed = _canonical_day(day)
        if parsed is None or (parsed.month, parsed.day) != (12, 31):
            return None
        dates.add(day)
    return dates


def _valid_optional_id(value) -> bool:
    return value is None or (type(value) is int and value > 0)


def _valid_removal_receipt(receipt) -> bool:
    return (
        isinstance(receipt, dict)
        and isinstance(receipt.get("indicator_type"), str)
        and bool(receipt["indicator_type"])
        and type(receipt.get("id")) is int
        and receipt["id"] > 0
        and _canonical_day(receipt.get("date")) is not None
        and isinstance(receipt.get("stored_value"), str)
        and "entity_id" in receipt
        and "source_document_id" in receipt
        and _valid_optional_id(receipt.get("entity_id"))
        and _valid_optional_id(receipt.get("source_document_id"))
    )


def _valid_supersession_coverage(coverage) -> bool:
    from .domains.economic_indicators import cbk_inflation, fetcher

    if not isinstance(coverage, dict) or not coverage:
        return False
    annual_types = {item["indicator_type"] for item in fetcher._WB_INDICATORS.values()}
    for kind, days in coverage.items():
        if not isinstance(kind, str) or not isinstance(days, list) or not days:
            return False
        if kind in annual_types:
            if _annual_coverage_dates(days) is None:
                return False
        elif kind == cbk_inflation.INDICATOR_TYPE:
            for day in days:
                parsed = _canonical_day(day)
                if parsed is None or parsed.day != calendar.monthrange(
                    parsed.year, parsed.month
                )[1]:
                    return False
        else:
            return False
    return True


def _explained_inflation_drop(session, prior_rows, baseline, seen_at, count, now):
    """Require every vanished row to match a successful writer receipt."""
    from models import IngestionJob, IngestionStatus

    if not isinstance(prior_rows, list) or len(prior_rows) != baseline:
        return False, "the older census has no complete row identities"
    if not all(
        isinstance(row, dict)
        and type(row.get("id")) is int
        and row["id"] > 0
        and _canonical_day(row.get("date")) is not None
        and isinstance(row.get("stored_value"), str)
        and "entity_id" in row
        and "source_document_id" in row
        and _valid_optional_id(row["entity_id"])
        and _valid_optional_id(row["source_document_id"])
        for row in prior_rows
    ):
        return False, "the older census has malformed row identities"
    prior_by_id = {row["id"]: row for row in prior_rows}
    if len(prior_by_id) != baseline:
        return False, "the older census has duplicate row identities"
    try:
        current_rows = _inflation_rows(session)
        jobs = (
            session.query(IngestionJob)
            .filter(
                IngestionJob.domain == "economic_indicators",
                IngestionJob.started_at > seen_at,
                IngestionJob.started_at <= now.replace(tzinfo=None),
            )
            .order_by(IngestionJob.started_at)
            .all()
        )
    except Exception as exc:
        return False, f"could not read row identities or writer receipts: {exc}"
    if len(current_rows) != count:
        return False, "the current count does not match the row identities"
    vanished = set(prior_by_id) - {row["id"] for row in current_rows}
    if not vanished:
        return False, "no vanished row identities explain the count drop"

    witnessed = set()
    for job in jobs:
        if job.status != IngestionStatus.COMPLETED or job.dry_run or job.errors:
            continue
        meta = job.meta if isinstance(job.meta, dict) else {}
        receipts = meta.get("superseded_rows_removed")
        coverage = meta.get("supersession_coverage")
        if not isinstance(receipts, list) or not _valid_supersession_coverage(coverage):
            continue
        if not all(_valid_removal_receipt(receipt) for receipt in receipts):
            continue
        dates = _annual_coverage_dates(coverage.get("inflation_rate"))
        if dates is None:
            continue
        inflation_receipts = [
            receipt for receipt in receipts
            if isinstance(receipt, dict) and receipt.get("indicator_type") == "inflation_rate"
        ]
        if len(inflation_receipts) > 12:
            continue
        for receipt in inflation_receipts:
            row_id = receipt.get("id")
            prior = prior_by_id.get(row_id)
            if not prior or prior.get("entity_id") is not None:
                continue
            day = prior["date"]
            parsed_day = _canonical_day(day)
            if (
                receipt.get("date") == day
                and receipt.get("stored_value") == prior["stored_value"]
                and receipt.get("entity_id") is None
                and receipt.get("source_document_id") == prior["source_document_id"]
                and day not in dates
                and min(dates) <= day <= max(dates)
                and parsed_day is not None
                and (parsed_day.month, parsed_day.day) != (12, 31)
            ):
                witnessed.add(row_id)

    if vanished <= witnessed:
        return True, f"all {len(vanished)} vanished row identities have successful off-cycle supersession receipts"
    return False, f"{len(vanished - witnessed)} vanished row identity/identities lack a matching supersession receipt"


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
    for started_at, observed, inflation_rows in observations:
        for label, value in observed.items():
            if not isinstance(value, int) or isinstance(value, bool):
                continue
            best = baselines.get(label)
            if best is None or value > best[0]:
                baselines[label] = (value, started_at, inflation_rows)

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

        baseline, seen_at, prior_inflation_rows = entry
        lost = baseline - count
        limit = baseline * (1 - ROW_DROP_TOLERANCE)
        when = seen_at.date().isoformat() if seen_at else "an earlier run"
        if count < limit and lost >= ROW_DROP_MIN_ABSOLUTE:
            if label == "Inflation Rate records" and seen_at is not None:
                explained, detail = _explained_inflation_drop(
                    session, prior_inflation_rows, baseline, seen_at, count, now
                )
                if explained:
                    findings.append(Finding(
                        OK, label,
                        f"{count} rows — down {lost} from {baseline} ({when}); {detail}",
                    ))
                    continue
            else:
                detail = "no row-level supersession receipt applies"
            message = (
                f"{count} rows — DOWN {lost} ({lost / baseline:.0%}) from "
                f"{baseline} seen on {when}. Tolerance is "
                f"{ROW_DROP_TOLERANCE:.0%}. "
            )
            if label == "Inflation Rate records":
                message += f"The missing identities are not fully reconciled: {detail}."
            else:
                message += (
                    "Rows that were published yesterday are not being published "
                    "today; find what stopped writing them before the next deploy."
                )
            findings.append(
                Finding(
                    FAIL,
                    label,
                    message,
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
        meta = {"row_counts": dict(counts)}
        if "Inflation Rate records" in counts:
            inflation_rows = _inflation_rows(session)
            if len(inflation_rows) != counts["Inflation Rate records"]:
                raise ValueError("inflation count does not match the row identity census")
            meta["inflation_rows"] = inflation_rows
        session.add(
            IngestionJob(
                domain=ROW_CENSUS_DOMAIN,
                status=IngestionStatus.COMPLETED,
                started_at=now.replace(tzinfo=None),
                finished_at=now.replace(tzinfo=None),
                items_processed=len(counts),
                meta=meta,
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


def _job_text(job, key):
    """JSON job metadata is untrusted, including scalar values inside a dict."""
    value = _as_dict(getattr(job, "meta", None)).get(key)
    return value if isinstance(value, str) and value else None


def _malformed_job_metadata(job):
    meta = getattr(job, "meta", None)
    if not isinstance(meta, dict):
        return True
    mode = meta.get("source_mode")
    if mode is not None and mode not in (
        "live", "fixture", "partial", "refused", "unknown"
    ):
        return True
    return any(key in meta and meta[key] is not None and not isinstance(meta[key], str)
               for key in ("source_fallback_reason", "source_detail", "source_fallback_detail"))


def _latest_run_reasons(jobs) -> set:
    """The fallback reason(s) recorded by the most recent run that recorded one.

    Rows tied on ``started_at`` are kept together: concurrent writers are
    describing the same moment, and a moment its own writers disagree about is
    not a moment we can call healthy.
    """
    reasoned = [j for j in jobs if _job_text(j, "source_fallback_reason")]
    if not reasoned:
        return set()
    newest = max(_run_order(j) for j in reasoned)
    return {
        _job_text(j, "source_fallback_reason")
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
        _job_text(j, "source_mode")
        for j in jobs
        if _run_order(j) == newest
    }


def _national_discovery_state(job) -> str:
    """A stored discovery receipt must prove an actual completed search."""
    report = _as_dict(getattr(job, "meta", None)).get("oag_national_discovery")
    if not isinstance(report, dict):
        return "unrecorded"
    status = report.get("status")
    if status != "completed":
        return status if status in ("failed", "partial", "deferred") else "unknown"
    attempted = report.get("attempted_queries")
    successful = report.get("successful_queries")
    candidates = report.get("candidate_count")
    if (
        type(attempted) is not int or attempted <= 0
        or type(successful) is not int or successful != attempted
        or type(candidates) is not int or candidates < 0
        or report.get("failures") != []
        or any(
            isinstance(error, str) and error.startswith("OAG national discovery:")
            for error in (getattr(job, "errors", None) or [])
        )
    ):
        return "inconsistent"
    return "completed"


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
        newest = max(_run_order(j) for j in jobs)
        if any(_malformed_job_metadata(j) for j in jobs if _run_order(j) == newest):
            refused = "refused" in _latest_run_modes(jobs)
            findings.append(Finding(
                FAIL if refused else WARN, f"{domain} ingestion",
                "newest run refused to publish; refusal details malformed"
                if refused else "newest run has malformed source metadata; provenance unknown",
            ))
            continue
        modes = [_job_text(j, "source_mode") for j in jobs]
        latest_modes = _latest_run_modes(jobs)
        latest_jobs = [j for j in jobs if _run_order(j) == newest]
        national_discovery_states = set()
        if domain == "audits":
            for job in latest_jobs:
                national_discovery_states.add(_national_discovery_state(job))
        if (None in latest_modes or "unknown" in latest_modes) and "live" in modes and "refused" not in latest_modes:
            findings.append(Finding(
                WARN, f"{domain} ingestion",
                "newest run has unconfirmed source_mode; older live runs cannot confirm current provenance",
            ))
            continue
        if "refused" in latest_modes:
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
                _job_text(j, "source_fallback_reason")
                for j in jobs
                if _job_text(j, "source_mode") == "refused"
                and _job_text(j, "source_fallback_reason")
            }
            # WHICH gate refused, not merely that one did. ``source_detail``
            # is the key seeding/cli.py writes from freshness's ``detail``;
            # take the newest refusing run's, since the others describe runs
            # already superseded by it.
            detail = next(
                (
                    d
                    for d in (
                        _job_text(j, "source_detail")
                        for j in sorted(jobs, key=_run_order, reverse=True)
                        if _job_text(j, "source_mode") == "refused"
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
                _job_text(j, "source_fallback_reason")
                for j in jobs
                if _job_text(j, "source_fallback_reason")
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
        elif "live" in modes and national_discovery_states - {"completed"}:
            findings.append(Finding(
                WARN,
                f"{domain} ingestion",
                "national discovery "
                f"{', '.join(sorted(national_discovery_states - {'completed'}))} "
                "on the newest run; known audit documents may still have "
                "refreshed, but new national coverage was not fully checked",
            ))
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
                _job_text(j, "source_fallback_reason")
                for j in jobs
                if _job_text(j, "source_fallback_reason")
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
                        _job_text(j, "source_fallback_detail")
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


#: ``ingestion_jobs.domain`` for bootstrap's reference-data load. Bootstrap
#: reads git-tracked files by definition and has no publisher of its own, so
#: it always records ``source_mode="fixture"`` and its fixture vocabulary
#: (``fixture_current``, ``fixture_stale``, ``fixture_missing``,
#: ``fixture_superseded``, ``bootstrap_failed``) is judged by
#: :func:`check_ingestion_freshness`, not by the per-run verdict below.
#:
#: Spelled out here rather than imported: ``bootstrap.py`` is a 2,000-line
#: module that pulls in the whole model layer, and this file is imported by
#: a workflow step. ``tests/test_hollow_run_gate.py`` asserts the two strings
#: are equal, so the copy cannot drift in silence.
BOOTSTRAP_DOMAIN = "bootstrap_reference_data"

#: Rows in ``ingestion_jobs`` that are not a seeding domain reaching a
#: publisher, and so cannot be judged as one.
NON_PUBLISHER_DOMAINS = frozenset({ROW_CENSUS_DOMAIN, BOOTSTRAP_DOMAIN})

#: Fixture reasons that do NOT make a run hollow. Same two sets the window
#: gate already uses, deliberately reused rather than re-typed: a reason is
#: either "there is no publisher to reach" or "the publisher's data already
#: landed and the file is vestigial". Anything else means the domain HAS a
#: publisher and did not reach it tonight.
EXEMPT_FIXTURE_REASONS = DECLARED_NO_SOURCE_REASONS | SUPERSEDED_REASONS


def latest_job_per_domain(jobs: Iterable) -> List:
    """One row per domain — the most recent — from a window of jobs.

    The nightly reads ``ingestion_jobs`` over the last 30 minutes, which can
    hold two rows for a domain if a run was re-dispatched. A verdict about
    THIS run must be about the newest row, not whichever the query happened
    to yield first.

    On a ``started_at`` tie the higher ``id`` wins. ``_run_order`` alone is
    stable, so the survivor was whichever the CALLER's ordering put last —
    and the nightly queries ``ORDER BY id DESC``, which made the tie-break
    select the OLDEST row and contradict this docstring.
    """
    newest: dict = {}
    for job in sorted(jobs, key=lambda j: (_run_order(j), getattr(j, "id", 0) or 0)):
        newest[getattr(job, "domain", None)] = job
    return list(newest.values())


def hollow_run_findings(jobs: Iterable) -> List[Finding]:
    """Domains that published nothing from their publisher on THIS run.

    WHY THIS IS SEPARATE FROM :func:`check_ingestion_freshness`
    -----------------------------------------------------------
    That gate asks "has this domain reached its publisher recently?" over a
    14-day window, and answers with the UNION of the window. It is the right
    question for "has a source gone away", and it is structurally blind to
    the failure this one catches.

    On 2026-09-19 (run 35415601792) the nightly served fixtures for
    ``audits`` (``processed=0`` — all five OAG URLs returned HTML, not PDFs),
    ``counties_budget`` (COB 403) and ``national_budget``, printed::

        [STALE] audits: completed_with_errors | created=0 updated=0 processed=0
        [STALE] counties_budget: completed_with_errors | ...
        ...
        All domains completed successfully.

    and exited 0. The window gate, in the same workflow minutes later, said::

        [OK] audits ingestion: reached the publisher in 13/22 recent run(s)

    Both were working as written. Neither could say "tonight, nothing
    arrived", because the run-level check only counted ``status == 'failed'``
    and the window-level check was answering about a fortnight.

    A run that refreshes nothing is the failure this project cares most
    about — it reads as success, so nobody looks, and the site goes on
    publishing figures it describes as current.

    WHAT IS EXEMPT, AND WHY IT IS NOT A LOOPHOLE
    --------------------------------------------
    Only two reasons: ``no_live_source`` (learning_hub's editorial copy,
    which has no machine-readable publisher; stalled_projects used it until
    #230) and ``fixture_superseded`` (the file is still read but every
    figure in it has been replaced from the database). Both are the same
    slugs the window gate already exempts. Adding a slug here is a decision
    that a gap is known and accepted, not a way to quiet a broken fetch — a
    domain that starts returning ``no_live_source`` because someone deleted
    its fetcher would be exempting itself, which is why the slugs are listed
    in one place and reviewed as a set.

    EVERY MODE IS JUDGED, AND THE SEVERITIES ARE NOT NEW
    ----------------------------------------------------
    ``freshness.py`` declares five modes: live, fixture, partial, refused,
    unknown. The first version of this function branched on ``fixture`` and
    ``unknown`` and let the other two fall through to no finding at all —
    so a domain that recorded PARTIAL or REFUSED passed the gate silently,
    printed ``[OK]``, and exited 0. That is the same shape as the defect the
    function exists to catch, one mode over, and it was live: the KRA
    overlay leaves ``revenue_by_source`` PARTIAL and the census leaves
    ``population`` PARTIAL.

    So the mapping is exhaustive, and its severities are taken from
    :func:`check_ingestion_freshness` rather than invented here:

    * ``live`` — OK, nothing reported.
    * ``fixture`` — FAIL, unless the reason is declared exempt.
    * ``refused`` — FAIL. The domain reached a verdict of "do not publish"
      and wrote nothing; the reader is on the previous seed's rows.
    * ``partial`` — WARN, not FAIL. A secondary series DID refresh. The
      window gate says WARN for the same state, and it must stay WARN here:
      ``revenue_by_source`` has been partial for ~20 consecutive runs, so
      failing on it would make the nightly red every single night, and a
      gate that fires every night gets muted along with everything beside
      it. WARN still prints, which is the part that was missing.
    * anything else — FAIL. ``unknown``, ``None``, a mode this function has
      not been taught, a non-string, a value with stray whitespace or odd
      casing. "We did not record where this came from", and "we recorded
      something nobody here understands", are both the absence of evidence
      that the publisher was reached. Matching a known set and failing on
      the remainder is what keeps a sixth mode from arriving green.

    An unrecorded mode is therefore a FAIL, not a pass — the whole freshness
    module exists because an absent signal was being read as a good one.
    """
    findings: List[Finding] = []
    for job in latest_job_per_domain(jobs):
        domain = getattr(job, "domain", None)
        if domain in NON_PUBLISHER_DOMAINS:
            continue
        meta = job.meta if isinstance(getattr(job, "meta", None), dict) else {}
        mode = meta.get("source_mode")
        reason = _job_text(job, "source_fallback_reason")
        label = f"{domain} this run"

        if mode == "live":
            continue

        if mode == "fixture":
            if reason in EXEMPT_FIXTURE_REASONS:
                continue
            findings.append(
                Finding(
                    FAIL,
                    label,
                    "served a FIXTURE, not the publisher "
                    f"(reason={reason or 'unrecorded'}). This run published "
                    "nothing new for this domain; its created/updated counts "
                    "describe a git-tracked file.",
                )
            )
        elif mode == "refused":
            findings.append(
                Finding(
                    FAIL,
                    label,
                    f"REFUSED to publish (reason={reason or 'unrecorded'}). "
                    "Nothing was written — not a fixture, not a partial "
                    "register. The reader is on the previous seed's rows.",
                )
            )
        elif mode == "partial":
            findings.append(
                Finding(
                    WARN,
                    label,
                    f"only a SECONDARY series refreshed (reason="
                    f"{reason or 'unrecorded'}); the figure this domain "
                    "publishes is still a fixture.",
                )
            )
        else:
            status = getattr(getattr(job, "status", None), "value", None)
            if status == "failed":
                # Already a failure by its own status; saying it twice
                # would inflate the count the operator reads.
                continue
            described = "no source_mode" if mode in (None, "") else repr(mode)
            findings.append(
                Finding(
                    FAIL,
                    label,
                    f"recorded {described}, so there is no evidence it "
                    "reached its publisher. Unrecorded, and unrecognised, "
                    "are not the same as fine.",
                )
            )
    return findings


# ─────────────────────────────────────────────────────────────────────────
# County audit coverage — the fourth question: has OAG published a year of
# county audits that we do not carry?
# ─────────────────────────────────────────────────────────────────────────
#
# Every gate above passed on 2026-09-24 while every county finding on the
# site was FY2020/21 and OAG had published FY2021/22 through FY2024/25. The
# audits table WAS moving (the national Blue Book loads nightly), the domain
# DID reach its publisher, and no table lost rows. None of them asks "is
# there a year the publisher has out that we hold nothing for?", so none
# could see a four-year gap.
#
# The listing is read by the audits domain, not here: the validate job makes
# no network calls, and OAG challenges GitHub runners intermittently. The
# domain records what OAG's county listing named in
# ``ingestion_jobs.metadata.oag_county_discovery.listing_fiscal_years``, and
# this compares that against the county findings actually published.
#
# FAIL, not WARN, when a listed year has no county finding. The nightly
# discovers and processes the newest year first in the same run that
# validates, so a year OAG has just published is red for at most the nights
# the backlog takes. A red that clears itself is what a gate is for.

COUNTY_AUDIT_LABEL = "County audit coverage"
#: Every county is audited every year: 47 executives and 47 assemblies.
COUNTY_COUNT = 47


def check_county_audit_coverage(session, now: Optional[datetime] = None) -> List[Finding]:
    """Compare OAG's listing with attributed county/period/institution evidence."""
    from .county_audit_coverage import county_audit_coverage_receipt, coverage_verdict

    level, message = coverage_verdict(county_audit_coverage_receipt(session))
    return [Finding(level, COUNTY_AUDIT_LABEL, message)]


STALLED_PROJECTS_DOMAIN = "stalled_projects"


def _whole(value) -> Optional[int]:
    """A count or id as an int, or None. Strict: bools, NaN and prose are not
    numbers, but "16482" and 168.0 are (JSON round-trips produce both)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == value and value not in (float("inf"), float("-inf")):
        return int(value) if value.is_integer() else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def check_stalled_projects_edition(session) -> List[Finding]:
    """Is the site publishing COB's newest CBIRR, and did it read its tables?

    Two ways this domain can go quiet that no other gate sees:

    * COB lists a newer county BIRR than the one ingested — or the same link
      now serves a re-issued file. The download is ~50MB at as little as
      43 KB/s and resumes across nights, so a domain that keeps refusing
      ``download_incomplete`` still has a live-looking history while the page
      shows last quarter's tables.
    * The newest edition HAS "County Stalled Projects as of" captions and the
      run parsed none of them — a layout change the parser did not survive.

    Judges the newest NON-dry-run job that recorded an edition verdict
    (``cbirr_published`` present). A dry run, a crash, a timeout or a
    budget-dropped run stores no verdict; before this rule one of those
    became "the latest run" and turned a real FAIL into WARN (found by an
    adversarial pass). OK is only ever said when every fact it rests on was
    recorded: an unrecorded fingerprint or count is WARN, never OK.
    """
    from models import IngestionJob

    label = "stalled_projects edition"
    jobs = (
        session.query(IngestionJob)
        .filter(IngestionJob.domain == STALLED_PROJECTS_DOMAIN)
        .order_by(IngestionJob.started_at.desc(), IngestionJob.id.desc())
        .limit(60)
        .all()
    )
    job = next(
        (
            j
            for j in jobs
            if not getattr(j, "dry_run", False)
            and "cbirr_published" in _as_dict(j.meta)
        ),
        None,
    )
    if job is None:
        return [Finding(WARN, label, "no stalled_projects run has recorded an edition verdict")]
    preamble: List[Finding] = []
    if jobs and jobs[0] is not job:
        preamble.append(
            Finding(
                WARN,
                label,
                "the latest stalled_projects run recorded no verdict (dry run, "
                "crash or timeout); judging the run before it",
            )
        )
    findings: List[Finding] = []
    meta = _as_dict(job.meta)
    newest = _as_dict(meta.get("cbirr_listing_newest"))
    published = _as_dict(meta.get("cbirr_published"))
    reason = _job_text(job, "source_fallback_reason")
    captions = _whole(meta.get("captions_found"))
    parsed = _whole(meta.get("rows_parsed"))
    written = _whole(meta.get("rows_written"))
    newest_id, published_id = _whole(newest.get("wpdmdl")), _whole(published.get("wpdmdl"))
    refused = _as_dict(meta.get("refused_edition"))

    if captions and not parsed:
        findings.append(
            Finding(
                FAIL,
                label,
                f"the newest edition has {captions} stalled-projects caption(s) "
                f"and the last run parsed {meta.get('rows_parsed')!r} rows from them",
            )
        )
    if parsed and (written is None or written != parsed):
        findings.append(
            Finding(
                FAIL,
                label,
                f"{parsed} row(s) parsed but {meta.get('rows_written')!r} written — "
                f"county entities not matched: {meta.get('unmatched_counties')}",
            )
        )

    if newest_id is None:
        findings.append(
            Finding(
                WARN,
                label,
                "COB's listing was not read on the last run; cannot say whether "
                f"a newer edition exists ({reason or 'reason unrecorded'})",
            )
        )
    elif published_id is None:
        findings.append(
            Finding(
                FAIL,
                label,
                f"COB lists wpdmdl={newest_id} ({newest.get('slug')}) and no CBIRR "
                "edition with a wpdmdl is published",
            )
        )
    elif newest_id != published_id:
        if reason == "edition_has_no_stalled_tables" and _whole(refused.get("wpdmdl")) == newest_id:
            # Checked, and COB's newest edition simply has no such tables.
            # Red every night until the next edition would mute the gate.
            findings.append(
                Finding(
                    WARN,
                    label,
                    f"COB's newest edition (wpdmdl={newest_id}) has no stalled-"
                    f"projects tables; still publishing wpdmdl={published_id}",
                )
            )
        else:
            findings.append(
                Finding(
                    FAIL,
                    label,
                    f"COB lists a newer edition, wpdmdl={newest_id} "
                    f"({newest.get('slug')}), than the one published: "
                    f"wpdmdl={published_id} "
                    f"({published.get('fiscal_year')} {published.get('period')}, "
                    f"as of {published.get('as_of')}). Last run: "
                    f"{reason or meta.get('source_mode') or 'unrecorded'}",
                )
            )
    else:
        now_fp, pub_fp = newest.get("server_fingerprint"), published.get("server_fingerprint")
        if now_fp and pub_fp and now_fp != pub_fp:
            # Same link, different file: COB re-issued the edition (its
            # filenames run "... Final 5.pdf") and the new one is not in yet.
            findings.append(
                Finding(
                    FAIL,
                    label,
                    f"COB re-issued wpdmdl={newest_id}: it now serves {now_fp!r}, "
                    f"the site publishes {pub_fp!r}",
                )
            )
        elif not (now_fp and pub_fp):
            findings.append(
                Finding(
                    WARN,
                    label,
                    f"wpdmdl={newest_id} is current, but whether COB re-issued it "
                    "cannot be checked: the server's file name was not recorded "
                    f"({'listing' if not now_fp else 'published edition'})",
                )
            )

    if not any(f.level in (FAIL, WARN) for f in findings):
        findings.append(
            Finding(
                OK,
                label,
                f"publishing COB's newest edition, wpdmdl={published_id} "
                f"({published.get('fiscal_year')} {published.get('period')}, as of "
                f"{published.get('as_of')}): {parsed} row(s)",
            )
        )
    return preamble + findings


#: The basis a fiscal year's split must declare to count as "has a split".
#: Spelled here, not imported, so this module stays importable without the
#: fiscal_summary domain; ``test_fiscal_split_gate.py`` pins the two equal.
FISCAL_SPLIT_BASIS = "treasury_fiscal_framework"
FISCAL_SPLIT_LABEL = "Fiscal split vs Treasury Budget Summary"


def _fy_key(label: Optional[str]) -> tuple:
    """``'FY 2026/27'`` -> ``(2026,)``; anything unparseable sorts first."""
    import re

    m = re.search(r"(\d{4})", label or "")
    return (int(m.group(1)),) if m else (-1,)


def check_fiscal_split_freshness(
    session, now: Optional[datetime] = None
) -> List[Finding]:
    """Is there a Budget Summary on Treasury's listing newer than the newest
    fiscal year this site can split?

    Every July an enacted budget lands and the site should start showing its
    borrowing, recurrent / development / county split and tax versus non-tax.
    If the new edition cannot be read (a layout change, a dead link, a
    renamed table), nothing fails: the fixture is served, the old year stays
    "current" on the split, and the page quietly draws last year's shape. A
    row-count floor cannot see that and neither can ``source_mode``, which
    stays ``live`` because older editions still parse.

    Judged on the NEWEST run that recorded the listing, never on a window.
    "The listing carries a year we cannot split" is a statement about now:
    a union over past runs would stay green for a fortnight after a new
    edition broke, which is exactly the hole this gate closes. An unreadable
    listing is WARN, never OK: absence of evidence is not health.
    """
    from models import FiscalSummary, IngestionJob

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAX_DAYS_SINCE_LIVE)
    jobs = [
        j
        for j in session.query(IngestionJob)
        .filter(IngestionJob.domain == "fiscal_summary")
        .filter(IngestionJob.started_at >= cutoff.replace(tzinfo=None))
        .all()
        if "budget_summary_listing_newest_fy" in _as_dict(j.meta)
    ]
    if not jobs:
        return [
            Finding(
                WARN,
                FISCAL_SPLIT_LABEL,
                f"no fiscal_summary run in the last {MAX_DAYS_SINCE_LIVE} days "
                "recorded what Treasury's Budget Summary listing carries, so "
                "whether a newer budget is waiting cannot be judged",
            )
        ]
    latest = max(jobs, key=_run_order)
    meta = latest.meta or {}
    listed = meta.get("budget_summary_listing_newest_fy")
    editions = meta.get("budget_summary_editions") or {}
    findings: List[Finding] = []

    if meta.get("budget_summary_undated_links"):
        findings.append(
            Finding(
                WARN,
                FISCAL_SPLIT_LABEL,
                f"{len(meta['budget_summary_undated_links'])} Budget Summary "
                "link(s) name no fiscal year on the link or on a readable "
                f"cover, so a newer edition could be among them: "
                f"{meta['budget_summary_undated_links']}",
            )
        )
    if not listed:
        findings.append(
            Finding(
                WARN,
                FISCAL_SPLIT_LABEL,
                "the newest run could not establish any Budget Summary year on "
                f"the listing (listing: {meta.get('budget_summary_listing_status')})",
            )
        )
        return findings

    if _fy_key(listed) == (-1,):
        findings.append(
            Finding(
                WARN,
                FISCAL_SPLIT_LABEL,
                f"the listing's newest Budget Summary year {listed!r} is not a "
                "fiscal year, so it cannot be compared with what is published",
            )
        )
        return findings

    from services.publication_gate import publishable_fiscal_summaries

    # A split is the object with its total, not just the label: an empty or
    # total-less object has nothing a page can draw.
    split_years = [
        r.fiscal_year
        for r in publishable_fiscal_summaries(session.query(FiscalSummary).all())
        if (r.meta or {}).get("split_basis") == FISCAL_SPLIT_BASIS
        and ((r.meta or {}).get("fiscal_framework") or {}).get("total_expenditure_billion")
    ]
    newest_split = max(split_years, key=_fy_key) if split_years else None

    if newest_split is not None and _fy_key(listed) < _fy_key(newest_split):
        findings.append(
            Finding(
                WARN,
                FISCAL_SPLIT_LABEL,
                f"the split is published through {newest_split} but the listing's "
                f"newest Budget Summary is now {listed}: the edition behind the "
                "newest split has gone from Treasury's listing",
            )
        )
    elif newest_split is None or _fy_key(listed) > _fy_key(newest_split):
        status = "; ".join(
            f"{e.get('status')}" + (f" ({e.get('detail')})" if e.get("detail") else "")
            for u, e in editions.items()
            if e.get("fiscal_year") == listed
        )
        findings.append(
            Finding(
                FAIL,
                FISCAL_SPLIT_LABEL,
                f"Treasury has published the Budget Summary for {listed}, but "
                f"the newest fiscal year with a split is {newest_split or 'none'}. "
                f"The site is drawing borrowing, the spending split and tax vs "
                f"non-tax for an older budget. Edition status: {status or 'unrecorded'}",
            )
        )
    else:
        findings.append(
            Finding(
                OK,
                FISCAL_SPLIT_LABEL,
                f"newest Budget Summary on the listing is {listed}; split "
                f"published through {newest_split}",
            )
        )
    return findings


def run_all(
    session, now: Optional[datetime] = None, counts: Optional[dict] = None
) -> List[Finding]:
    """Every gate. ``counts`` enables the row-count regression check.

    Omitting ``counts`` skips the row-count regression check (the table,
    series, ingestion and publisher-edition gates always run). It is optional
    because ``run_all`` has callers that have no count to offer, NOT because
    that check is — the nightly passes the counts it already computed for
    its own floors.
    """
    findings = (
        check_table_freshness(session, now)
        + check_series_freshness(session, now)
        + check_ingestion_freshness(session, now)
        + check_county_audit_coverage(session, now)
        + check_stalled_projects_edition(session)
        + check_fiscal_split_freshness(session, now)
    )
    if counts is not None:
        findings += check_and_record_row_census(session, counts, now=now)
    # Is the publisher AHEAD of what we publish? (#241, #243)
    from .edition_gates import check_publisher_editions

    findings += check_publisher_editions(session)
    return findings


__all__ = [
    "BOOTSTRAP_DOMAIN",
    "COUNTY_AUDIT_LABEL",
    "check_county_audit_coverage",
    "EXEMPT_FIXTURE_REASONS",
    "FAIL",
    "Finding",
    "NON_PUBLISHER_DOMAINS",
    "OK",
    "ROW_CENSUS_DOMAIN",
    "ROW_CENSUS_WINDOW_DAYS",
    "ROW_DROP_MIN_ABSOLUTE",
    "ROW_DROP_TOLERANCE",
    "SERIES_RULES",
    "SeriesRule",
    "TABLE_RULES",
    "TableRule",
    "WARN",
    "check_and_record_row_census",
    "check_ingestion_freshness",
    "check_fiscal_split_freshness",
    "check_row_count_drop",
    "check_series_freshness",
    "check_stalled_projects_edition",
    "check_table_freshness",
    "hollow_run_findings",
    "in_publication_lull",
    "latest_job_per_domain",
    "record_row_census",
    "run_all",
]
