"""Explicit worker configuration; importing this module never loads a .env."""
from __future__ import annotations

from dataclasses import dataclass
import math

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url


@dataclass(frozen=True)
class WorkerConfig:
    database_url: str
    deployment_version: str = "batch-1"
    external_slots: int = 2
    active_scan_seconds: float = 5
    idle_scan_seconds: float = 30
    active_heartbeat_seconds: float = 15
    idle_heartbeat_seconds: float = 60
    lease_seconds: int = 120
    renewal_seconds: float = 20
    max_submissions: int = 5
    retry_lifetime_seconds: int = 86400
    maintenance_batch_size: int = 20

    def __post_init__(self):
        for name in ("external_slots", "lease_seconds", "max_submissions", "retry_lifetime_seconds", "maintenance_batch_size"):
            if type(getattr(self, name)) is not int:
                raise ValueError("Worker integer settings reject booleans and non-integers")
        for name in ("active_scan_seconds", "idle_scan_seconds", "active_heartbeat_seconds", "idle_heartbeat_seconds", "renewal_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 3600:
                raise ValueError("Worker timing settings must be finite positive seconds")
        if not self.database_url:
            raise ValueError("An explicit PostgreSQL database URL is required")
        url = make_url(self.database_url)
        if url.get_backend_name() != "postgresql":
            raise ValueError("The durable worker requires PostgreSQL")
        if self.external_slots not in (1, 2):
            raise ValueError("Worker permits at most two external operations")
        if not 0 < self.renewal_seconds < self.lease_seconds:
            raise ValueError("Lease renewal must precede lease expiry")
        if not 1 <= self.max_submissions <= 5:
            raise ValueError("At most five public submissions are permitted")
        if not 0 < self.retry_lifetime_seconds <= 86400:
            raise ValueError("Retry lifetime must be bounded to 24 hours")
        if not 1 <= self.maintenance_batch_size <= 100:
            raise ValueError("Maintenance batch must be bounded")


def create_worker_engine(config: WorkerConfig) -> Engine:
    """Two pooled connections; no backend.database import or implicit credentials."""
    url = make_url(config.database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg2")
    return create_engine(
        url,
        pool_size=2,
        max_overflow=0,
        pool_timeout=10,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
    )
