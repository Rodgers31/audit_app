"""Domain registry utilities for seeding orchestration."""

from __future__ import annotations

import importlib
from typing import Callable, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from .config import SeedingSettings
from .types import DomainRunContext, DomainRunResult

DomainHandler = Callable[
    [Session, SeedingSettings, DomainRunContext], Optional[DomainRunResult]
]


class DomainRegistry:
    """Central registry mapping domain names to seeding callables."""

    def __init__(self) -> None:
        self._handlers: Dict[str, DomainHandler] = {}

    def register(self, domain: str, handler: DomainHandler) -> None:
        if domain in self._handlers:
            raise ValueError(f"Domain '{domain}' already registered")
        self._handlers[domain] = handler

    def decorator(self, domain: str) -> Callable[[DomainHandler], DomainHandler]:
        """Decorator for domain modules to register their runner."""

        def _inner(handler: DomainHandler) -> DomainHandler:
            self.register(domain, handler)
            return handler

        return _inner

    def get(self, domain: str) -> Optional[DomainHandler]:
        return self._handlers.get(domain)

    def has(self, domain: str) -> bool:
        return domain in self._handlers

    def domains(self) -> List[str]:
        return sorted(self._handlers.keys())

    def __iter__(self) -> Iterable[str]:  # pragma: no cover - simple proxy
        return iter(self.domains())


REGISTRY = DomainRegistry()


def register_domain(domain: str) -> Callable[[DomainHandler], DomainHandler]:
    """Public decorator shortcut for registering domain runners."""

    return REGISTRY.decorator(domain)


_BUILTIN_DOMAIN_PACKAGES = [
    "seeding.domains.counties_budget",
    "seeding.domains.audits",
    "seeding.domains.economic_indicators",
    "seeding.domains.population",
    "seeding.domains.national_debt",
    "seeding.domains.national_budget",
    "seeding.domains.pending_bills",
    "seeding.domains.debt_timeline",
    "seeding.domains.fiscal_summary",
    "seeding.domains.revenue_by_source",
    "seeding.domains.learning_hub",
    "seeding.domains.stalled_projects",
    "seeding.domains.national_gdp",
]


def load_builtin_domains() -> None:
    """Attempt to import built-in domain packages so they can self-register."""

    for module_name in _BUILTIN_DOMAIN_PACKAGES:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue


__all__ = [
    "DomainHandler",
    "DomainRegistry",
    "REGISTRY",
    "register_domain",
    "load_builtin_domains",
]
