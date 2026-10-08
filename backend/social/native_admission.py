"""Immutable native admission fields and one persisted/current comparison."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr, field_validator

from .contracts import CapabilitySet, FeatureState, PostFormat, StrictModel


class NativeCapabilityAdmission(StrictModel):
    eligible: StrictBool
    adapter_available: StrictBool
    provider_api_version: StrictStr
    rules_version: StrictStr
    supported_formats: tuple[PostFormat, ...]
    required_scopes: tuple[StrictStr, ...]
    granted_scopes: tuple[StrictStr, ...]
    limits: tuple[tuple[StrictStr, Annotated[int, Field(strict=True, ge=0)] | None], ...]
    publishing_state: FeatureState
    price_class: Literal["free", "paid", "unverified"]

    @field_validator("limits")
    @classmethod
    def ordered_unique_limits(cls, value):
        names = [name for name, _ in value]
        if names != sorted(set(names)):
            raise ValueError("Native admission limits must have unique ordered names")
        return value

    @classmethod
    def from_snapshot(cls, snapshot):
        if isinstance(snapshot, cls):
            return cls.model_validate(snapshot.model_dump())
        # Revalidate instances too: CapabilitySet contains shallow mutable maps.
        if isinstance(snapshot, CapabilitySet):
            snapshot = snapshot.model_dump()
        required = {"eligible", "adapter_available", "provider_api_version", "rules_version",
            "supported_formats", "required_scopes", "granted_scopes", "limits", "feature_states", "price_class"}
        if (not isinstance(snapshot, dict) or not required <= snapshot.keys()
                or not isinstance(snapshot["feature_states"], dict) or "publishing" not in snapshot["feature_states"]):
            raise ValueError("Native admission requires explicit persisted fields")
        caps = CapabilitySet.model_validate(snapshot)
        return cls(eligible=caps.eligible, adapter_available=caps.adapter_available,
            provider_api_version=caps.provider_api_version, rules_version=caps.rules_version,
            supported_formats=caps.supported_formats, required_scopes=caps.required_scopes,
            granted_scopes=caps.granted_scopes, limits=tuple(sorted(caps.limits.items())),
            publishing_state=caps.feature_states.get("publishing", "unverified"), price_class=caps.price_class)


def native_capability_matches(stored, current) -> bool:
    """Missing/malformed state or any changed admission field blocks mutation."""
    try:
        prior = NativeCapabilityAdmission.from_snapshot(stored)
        expected = NativeCapabilityAdmission.from_snapshot(current)
    except (ValueError, TypeError):
        return False
    return (prior.eligible and prior.adapter_available and prior.publishing_state == "supported"
            and prior.price_class == "free" and prior == expected)
