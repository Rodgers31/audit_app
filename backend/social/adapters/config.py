"""Explicit construction settings, never environment-driven enablement."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetaAdapterConfig:
    graph_version: str
    enabled: bool = False
    operational_gates_verified: bool = False
    app_secret: str = field(default="", repr=False)

    def __post_init__(self):
        if self.graph_version != "v26.0":
            raise ValueError("Native Meta adapter evidence is pinned to v26.0")
        if type(self.enabled) is not bool or type(self.operational_gates_verified) is not bool:
            raise ValueError("Adapter gates must be explicit booleans")
        if not isinstance(self.app_secret, str) or len(self.app_secret) > 16384 or any(ord(c) < 32 or ord(c) == 127 for c in self.app_secret):
            raise ValueError("Invalid server application material")

    @property
    def ready(self):
        return self.enabled and self.operational_gates_verified
