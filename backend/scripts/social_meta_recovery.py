"""Run an inert local key recovery drill; no supplied secrets or live writes."""
from __future__ import annotations

import argparse
import base64
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import UUID

from social.connections.crypto import CredentialCipher
from social.connections.recovery import (PURPOSES, RecoveryError, RecoveryKeyring, RecoveryProbe,
                                         read_keyring_backup, verify_restoration, write_keyring_backup)
from social.service import SocialError


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RecoveryError()


def fixture_drill():
    keys = {name: base64.urlsafe_b64encode(bytes(range(start, start + 32))).decode('ascii')
            for name, start in (('fixture-v1', 0), ('fixture-v2', 32))}
    original = RecoveryKeyring('fixture-v1', keys)
    cipher = original.cipher()
    owner = UUID('11111111-1111-4111-8111-111111111111')
    probes = []
    for purpose in sorted(PURPOSES):
        version, data = cipher.encrypt(owner, purpose, {'access_token': 'INERT-RECOVERY-MARKER', 'kind': purpose})
        probes.append(RecoveryProbe(owner, purpose, version, data))
    with TemporaryDirectory(prefix='social-meta-fixture-') as directory:
        backup = Path(directory) / 'backup.json'
        write_keyring_backup(backup, original)
        restored = read_keyring_backup(backup)
        result = verify_restoration(original, restored, probes)
        rotated = RecoveryKeyring('fixture-v2', dict(restored.keys))
        rotated_backup = Path(directory) / 'rotated.json'
        write_keyring_backup(rotated_backup, rotated)
        restarted = read_keyring_backup(rotated_backup).cipher()
        for probe in probes:
            expected = cipher.decrypt(owner, probe.purpose, probe.key_version, probe.ciphertext)
            if restarted.decrypt(owner, probe.purpose, probe.key_version, probe.ciphertext) != expected:
                raise RecoveryError()
            version, data = restarted.rotate(owner, probe.purpose, probe.key_version, probe.ciphertext)
            fresh = CredentialCipher('fixture-v2', {'fixture-v2': keys['fixture-v2']})
            if version != 'fixture-v2' or fresh.decrypt(owner, probe.purpose, version, data) != expected:
                raise RecoveryError()
            new_version, new_data = restarted.encrypt(owner, probe.purpose, {'fresh': True})
            if fresh.decrypt(owner, probe.purpose, new_version, new_data) != {'fresh': True}:
                raise RecoveryError()
        negative_checks = 0
        for bad in (replace(probes[0], owner=UUID('22222222-2222-4222-8222-222222222222')),
                    replace(probes[0], purpose='oauth_pending'),
                    replace(probes[0], key_version='missing'),
                    replace(probes[0], ciphertext=b'corrupt')):
            try:
                verify_restoration(original, restored, [bad])
            except RecoveryError:
                negative_checks += 1
        if negative_checks != 4:
            raise RecoveryError()
    result.update(scope='inert_fixture_only', purposes_verified=len(probes),
                  active_rotation_verified=True, new_material_verified=True,
                  negative_controls_rejected=negative_checks)
    return result


def main(argv=None):
    parser = _Arguments(prog='social_meta_recovery', description='Execute fixture-only local backup/restore/rotation. No environment defaults, key input or provider calls.')
    parser.add_argument('--fixture-drill', action='store_true')
    try:
        argv = sys.argv[1:] if argv is None else argv
        if (type(argv) is not list or len(argv) > 2
                or any(type(v) is not str or len(v) > 64 or any(ord(c) < 32 or ord(c) == 127 for c in v) for v in argv)):
            raise RecoveryError()
        args = parser.parse_args(argv)
        if args.fixture_drill:
            result = fixture_drill()
        else:
            result = {'status': 'MISSING', 'scope': 'inert_fixture_only', 'reason': 'EXPLICIT_FIXTURE_DRILL_REQUIRED', 'production_authorized': False}
    except (RecoveryError, SocialError, OSError):
        result = {'status': 'BLOCKED', 'reason': 'CREDENTIAL_RECOVERY_REFUSED', 'production_authorized': False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'VERIFIED_BY_EXECUTION' else 2


if __name__ == '__main__':
    raise SystemExit(main())
