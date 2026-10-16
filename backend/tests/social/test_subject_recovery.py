"""Independent recovery must reproduce stored app-scoped subject lookups."""
from dataclasses import replace
from collections.abc import Mapping
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from social.privacy.subjects import SubjectDigester
from social.privacy.recovery import SubjectRecoveryError, SubjectRecoveryProbe, verify_subject_restoration

KEYS = {'old': b'a' * 32, 'current': b'b' * 32}
APP, SUBJECT = '100100', '200200'


@pytest.fixture
def recovery():
    original = SubjectDigester('current', dict(KEYS))
    restored = SubjectDigester('current', dict(KEYS))
    probes = [SubjectRecoveryProbe(uuid4(), APP, SUBJECT, version,
                                  original.digest(APP, SUBJECT, version)) for version in KEYS]
    return original, restored, probes


def verify(recovery, probes=None):
    original, restored, default = recovery
    return verify_subject_restoration(original, restored, default if probes is None else probes)


def test_reconstructs_old_and_current_stored_digests_without_certifying_inventory(recovery):
    result = verify(recovery)
    assert result == {'status': 'VERIFIED_BY_EXECUTION', 'scope': 'supplied_privacy_subject_digests',
                      'records_verified': 2, 'versions_verified': ['current', 'old'],
                      'database_coverage_verified': False, 'backup_custody_verified': False,
                      'production_authorized': False}
    assert APP not in repr(result) and SUBJECT not in repr(result)


def test_different_ownership_rows_may_share_subject_and_version(recovery):
    probe = recovery[2][0]
    assert verify(recovery, [probe, replace(probe, record_id=uuid4())])['records_verified'] == 2


@pytest.mark.parametrize('alias', ['instance', 'keys'])
def test_refuses_reused_live_container_as_backup_proof(recovery, alias):
    original, restored, probes = recovery
    if alias == 'instance':
        restored = original
    else:
        restored.keys = original.keys
    with pytest.raises(SubjectRecoveryError):
        verify_subject_restoration(original, restored, probes)


@pytest.mark.parametrize('side', ['original', 'restored', 'both'])
def test_wrong_keys_cannot_pass_even_when_both_instances_agree(recovery, side):
    original, restored, probes = recovery
    wrong = {'old': b'x' * 32, 'current': b'y' * 32}
    if side in ('original', 'both'):
        original = SubjectDigester('current', dict(wrong))
    if side in ('restored', 'both'):
        restored = SubjectDigester('current', dict(wrong))
    with pytest.raises(SubjectRecoveryError):
        verify_subject_restoration(original, restored, probes)


@pytest.mark.parametrize('change', [
    {'record_id': UUID(int=0)}, {'record_id': 'not-a-uuid'}, {'record_id': True},
    {'app_id': '100101'}, {'app_id': ''}, {'app_id': None}, {'app_id': True},
    {'subject': '200201'}, {'subject': '0'}, {'subject': None}, {'subject': True},
    {'digest_version': 'missing'}, {'digest_version': None}, {'digest_version': True},
    {'stored_digest': '0' * 64}, {'stored_digest': 'A' * 64},
    {'stored_digest': ''}, {'stored_digest': None}, {'stored_digest': b'a' * 64},
])
def test_identity_version_and_stored_digest_are_all_bound(recovery, change):
    with pytest.raises(SubjectRecoveryError) as caught:
        verify(recovery, [replace(recovery[2][0], **change)])
    assert str(caught.value) == 'SUBJECT_RECOVERY_REFUSED'
    assert caught.value.__context__ is None


@pytest.mark.parametrize('value', [None, [], (), {}, True, [None], [True]])
def test_refuses_absent_empty_or_malformed_proof(recovery, value):
    with pytest.raises(SubjectRecoveryError):
        verify_subject_restoration(recovery[0], recovery[1], value)


def test_repeated_record_identity_does_not_inflate_coverage(recovery):
    with pytest.raises(SubjectRecoveryError):
        verify(recovery, [recovery[2][0], recovery[2][0]])


def test_bounded_inventory_accepts_100_unique_rows_and_refuses_101(recovery):
    probes = [replace(recovery[2][0], record_id=uuid4()) for _ in range(101)]
    assert verify(recovery, probes[:100])['records_verified'] == 100
    with pytest.raises(SubjectRecoveryError):
        verify(recovery, probes)


def test_missing_historical_key_refuses_recovery(recovery):
    restored = SubjectDigester('current', {'current': KEYS['current']})
    with pytest.raises(SubjectRecoveryError):
        verify_subject_restoration(recovery[0], restored, recovery[2])


def test_missing_explicit_version_cannot_use_active_version_default(recovery):
    current = recovery[2][1]
    with pytest.raises(SubjectRecoveryError):
        verify(recovery, [replace(current, digest_version=None)])


def test_active_version_drift_requires_a_separate_rotation_decision(recovery):
    restored = SubjectDigester('old', dict(KEYS))
    with pytest.raises(SubjectRecoveryError):
        verify_subject_restoration(recovery[0], restored, recovery[2])


@pytest.mark.parametrize('bad', [None, {}, True, object()])
def test_wrong_digester_types_are_refused(recovery, bad):
    with pytest.raises(SubjectRecoveryError):
        verify_subject_restoration(recovery[0], bad, recovery[2])


def test_digester_inputs_are_revalidated_and_instance_method_overrides_ignored(recovery):
    original, restored, probes = recovery
    original.digest = lambda *args: '0' * 64
    restored.digest = lambda *args: '0' * 64
    assert verify(recovery)['records_verified'] == 2
    restored.keys = MappingProxyType({'old': b'a', 'current': b'b'})
    with pytest.raises(SubjectRecoveryError):
        verify(recovery)


def test_probe_and_error_representations_contain_no_subject_or_digest(recovery):
    probe = recovery[2][0]
    for value in (APP, SUBJECT, probe.stored_digest, repr(KEYS['old'])):
        assert value not in repr(probe)
        assert value not in repr(SubjectRecoveryError())


class CallbackKeys(Mapping):
    def __init__(self, callback):
        self.callback = callback

    def __iter__(self):
        self.callback()
        return iter(KEYS)

    def __len__(self):
        return len(KEYS)

    def __getitem__(self, key):
        return KEYS[key]


def test_key_mapping_cannot_erase_invalid_probes_and_certify_empty_success(recovery):
    original, restored, probes = recovery
    probes[0] = replace(probes[0], stored_digest='0' * 64)
    restored.keys = MappingProxyType(CallbackKeys(probes.clear))
    with pytest.raises(SubjectRecoveryError):
        verify_subject_restoration(original, restored, probes)


def test_key_mapping_cannot_expand_proof_batch_past_checked_limit(recovery):
    original, restored, probes = recovery

    def expand():
        probes.extend(replace(probes[0], record_id=uuid4()) for _ in range(100))

    restored.keys = MappingProxyType(CallbackKeys(expand))
    assert verify_subject_restoration(original, restored, probes)['records_verified'] == 2


@pytest.mark.parametrize('error', [KeyError, RuntimeError])
def test_key_mapping_errors_remain_fixed_private_refusals(recovery, error):
    original, restored, probes = recovery

    def fail():
        raise error('PRIVATE_TEST_MARKER')

    restored.keys = MappingProxyType(CallbackKeys(fail))
    with pytest.raises(SubjectRecoveryError) as caught:
        verify_subject_restoration(original, restored, probes)
    assert str(caught.value) == 'SUBJECT_RECOVERY_REFUSED'
    assert caught.value.__context__ is None


def test_key_mapping_cannot_repair_initially_wrong_probe_fields(recovery):
    original, restored, probes = recovery
    correct = probes[0].stored_digest
    probes[0] = replace(probes[0], stored_digest='0' * 64)
    restored.keys = MappingProxyType(CallbackKeys(
        lambda: object.__setattr__(probes[0], 'stored_digest', correct)))
    with pytest.raises(SubjectRecoveryError):
        verify_subject_restoration(original, restored, probes)


@pytest.mark.parametrize('error', [KeyboardInterrupt, SystemExit])
def test_operator_interrupts_are_preserved(recovery, error):
    original, restored, probes = recovery

    def stop():
        raise error()

    restored.keys = MappingProxyType(CallbackKeys(stop))
    with pytest.raises(error):
        verify_subject_restoration(original, restored, probes)


def test_same_key_version_alias_does_not_certify_snapshot_label_provenance():
    keys = {'old': b'a' * 32, 'current': b'a' * 32}
    original = SubjectDigester('current', dict(keys))
    restored = SubjectDigester('current', dict(keys))
    old_digest = original.digest(APP, SUBJECT, 'old')
    probe = SubjectRecoveryProbe(uuid4(), APP, SUBJECT, 'current', old_digest)
    result = verify_subject_restoration(original, restored, [probe])
    assert result['versions_verified'] == ['current']
    assert result['database_coverage_verified'] is False
