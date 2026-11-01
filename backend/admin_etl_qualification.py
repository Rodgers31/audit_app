"""One operator-admitted generation; never an automatic retry or a writer lane."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import UUID


POLICY_ENV = "ADMIN_ETL_QUALIFICATION_POLICY"
WORKER_SECONDS = 120
HANDLER_SECONDS = 45
ADMISSION_SECONDS = 3600
DISABLED_FLAGS = (
    "SOCIAL_MEDIA_ENABLED", "SOCIAL_NATIVE_ENABLED", "SOCIAL_WORKER_SUPERVISOR_ENABLED",
    "SOCIAL_ANALYTICS_ENABLED", "SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED",
    "SOCIAL_POLICY_AUTOMATION_ENABLED", "SOCIAL_REPORT_GENERATION_ENABLED", "SOCIAL_STUDIO_ENABLED",
    "SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED",
    "SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED",
    "SOCIAL_WORKER_MEDIA_READS_ENABLED", "SOCIAL_MEDIA_RETAINED_WRITES_ENABLED",
    "SOCIAL_MEDIA_FENCED_RETIREMENT_ENABLED", "SOCIAL_MEDIA_OWNED_QUIESCENCE_ENABLED",
)


class QualificationRefused(ValueError):
    pass


@dataclass(frozen=True)
class Qualification:
    generation: UUID
    issued_at: datetime
    expires_at: datetime

    def permits(self, source, dry_run, generation, now):
        return (type(now) is datetime and now.utcoffset() == timedelta(0)
                and isinstance(generation, UUID) and source == "opendata" and dry_run is True
                and generation == self.generation
                and self.issued_at <= now < self.expires_at)


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise QualificationRefused("Duplicate qualification field")
        value[key] = item
    return value


def qualification(now=None):
    """Absent means the existing lane; present but invalid never falls back."""
    raw = os.environ.get(POLICY_ENV)
    if raw is None:
        return None
    try:
        if not 0 < len(raw) <= 512:
            raise ValueError()
        value = json.loads(raw, object_pairs_hook=_pairs)
        if (type(value) is not dict or set(value) != {
                "version", "generation", "issued_at", "expires_at"}
                or type(value["version"]) is not int or value["version"] != 1):
            raise ValueError()
        identity = UUID(value["generation"])
        if str(identity) != value["generation"] or identity.version != 4:
            raise ValueError()
        dates = []
        for name in ("issued_at", "expires_at"):
            text = value[name]
            if type(text) is not str or len(text) > 32 or not text.endswith("Z"):
                raise ValueError()
            dates.append(datetime.fromisoformat(text[:-1] + "+00:00"))
        issued, expires = dates
        current = now if now is not None else datetime.now(timezone.utc)
        if (expires - issued != timedelta(seconds=ADMISSION_SECONDS)
                or not issued <= current < expires
                or os.environ.get("ADMIN_ETL_DISPATCH_SOURCES") != "opendata"
                or os.environ.get("SEED_OPENDATA_INGESTION_ENABLED") != "true"
                or os.environ.get("AUTO_SEEDER_ENABLED") != "false"
                or any(os.environ.get(key, "false") != "false" for key in DISABLED_FLAGS)
                or os.environ.get("SEED_KNBS_RELEASE_DISCOVERY_ENABLED", "false") != "false"
                or os.environ.get("SOCIAL_GENERATION_HOOK_ENABLED", "false") != "false"):
            raise ValueError()
        return Qualification(identity, issued, expires)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise QualificationRefused("Qualification policy unavailable") from None
