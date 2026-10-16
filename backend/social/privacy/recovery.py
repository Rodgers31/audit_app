"""Explicit in-memory restoration proof for supplied stored subject digests.

No secret-store, environment, database or provider access. Operators must obtain
the restored keys independently and reconcile coverage against an approved
snapshot. A successful probe is not a custody or whole-database attestation.
"""
from dataclasses import dataclass, field
import hmac
import re
from types import MappingProxyType
from uuid import UUID

from .subjects import SubjectDigester

MAX_RECOVERY_PROBES = 100
MAX_RECOVERY_KEYS = 16


class SubjectRecoveryError(ValueError):
    def __init__(self):
        super().__init__('SUBJECT_RECOVERY_REFUSED')


@dataclass(frozen=True, repr=False)
class SubjectRecoveryProbe:
    record_id: UUID
    app_id: str
    subject: str = field(repr=False)
    digest_version: str
    stored_digest: str = field(repr=False)


def _snapshot_probes(probes):
    frozen, records = [], set()
    for probe in tuple(probes):
        if type(probe) is not SubjectRecoveryProbe or type(probe.record_id) is not UUID:
            raise SubjectRecoveryError()
        record = probe.record_id.int
        app, subject, version, digest = probe.app_id, probe.subject, probe.digest_version, probe.stored_digest
        if (type(record) is not int or not 0 < record < 2**128 or record in records
                or type(app) is not str or type(subject) is not str or type(version) is not str
                or type(digest) is not str or re.fullmatch(r'[a-f0-9]{64}', digest) is None):
            raise SubjectRecoveryError()
        records.add(record)
        frozen.append((app, subject, version, digest))
    if not 1 <= len(frozen) <= MAX_RECOVERY_PROBES:
        raise SubjectRecoveryError()
    return tuple(frozen)


def _copy_digester(active, material):
    # MappingProxyType may wrap a caller-supplied Mapping. Bound actual iteration,
    # not its advertised length, and reconstruct only validated primitive values.
    keys = {}
    for label in material:
        if len(keys) >= MAX_RECOVERY_KEYS or type(label) is not str or label in keys:
            raise SubjectRecoveryError()
        value = material[label]
        if type(value) is not bytes or len(value) != 32:
            raise SubjectRecoveryError()
        keys[label] = value
    return SubjectDigester(active, keys)


def verify_subject_restoration(original: SubjectDigester, restored: SubjectDigester,
                               probes: list[SubjectRecoveryProbe]) -> dict:
    """Reproduce each stored lookup with two separately reconstructed keysets.

    Every row ID must be unique. Multiple ownership rows can share a subject.
    Both computations must match the supplied stored digest, so two identically
    wrong keysets cannot certify each other. Active-version drift is a separate
    rotation decision. No input keysets or probes are modified or returned.
    """
    try:
        if (type(original) is not SubjectDigester or type(restored) is not SubjectDigester
                or original is restored or original.keys is restored.keys
                or type(original.keys) is not MappingProxyType
                or type(restored.keys) is not MappingProxyType
                or type(original.active_version) is not str
                or type(restored.active_version) is not str
                or original.active_version != restored.active_version
                or type(probes) is not list or not 1 <= len(probes) <= MAX_RECOVERY_PROBES):
            raise SubjectRecoveryError()
        # Freeze primitive proof values before invoking any supplied key mapping.
        frozen = _snapshot_probes(probes)
        active = original.active_version
        first_material, second_material = original.keys, restored.keys
        first = _copy_digester(active, first_material)
        second = _copy_digester(active, second_material)
        versions = set()
        for app, subject, version, stored in frozen:
            expected = first.digest(app, subject, version)
            actual = second.digest(app, subject, version)
            if not hmac.compare_digest(expected, stored) or not hmac.compare_digest(actual, stored):
                raise SubjectRecoveryError()
            versions.add(version)
        return {'status': 'VERIFIED_BY_EXECUTION', 'scope': 'supplied_privacy_subject_digests',
                'records_verified': len(frozen), 'versions_verified': sorted(versions),
                'database_coverage_verified': False, 'backup_custody_verified': False,
                'production_authorized': False}
    except Exception:
        # Mapping callbacks can raise arbitrary ordinary errors. Preserve only a
        # fixed refusal; KeyboardInterrupt/SystemExit still propagate normally.
        pass
    raise SubjectRecoveryError()
