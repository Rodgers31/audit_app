"""Shared data structures for seeding workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class DomainRunContext:
    """Context object supplied to domain runners."""

    since: Optional[datetime]
    dry_run: bool
    job_id: Optional[int] = None
    # Explicit execution input; never sourced from scheduled environment defaults.
    audits_source_manifest: Optional[bytes] = None
    audits_source_receipt: Optional[Dict[str, Any]] = None
    audits_observe_listing: bool = False


class DomainRunResult(BaseModel):
    """Standardized result payload for a domain execution."""

    domain: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    items_processed: int = 0
    items_created: int = 0
    items_updated: int = 0
    dry_run: bool = False
    errors: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @classmethod
    def empty(
        cls,
        domain: str,
        dry_run: bool,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> "DomainRunResult":
        """Return an empty result stub for a domain."""

        return cls(
            domain=domain,
            dry_run=dry_run,
            started_at=started_at or datetime.now(timezone.utc),
            finished_at=finished_at or datetime.now(timezone.utc),
        )

    def with_error(self, message: str) -> "DomainRunResult":
        """Return a copy of the result with an appended error message."""

        payload = self.model_copy(deep=True)
        payload.errors.append(message)
        return payload

    def mark_finished(self) -> "DomainRunResult":
        """Return a copy of the result with updated finish timestamp."""

        payload = self.model_copy()
        payload.finished_at = datetime.now(timezone.utc)
        return payload


__all__ = ["DomainRunContext", "DomainRunResult"]
