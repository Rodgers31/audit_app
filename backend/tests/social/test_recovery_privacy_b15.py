"""Observed regression: a backup writer must read its persisted bytes back."""
import builtins
from pathlib import Path
import pytest
from social.connections.recovery import RecoveryKeyring, RecoveryError, write_keyring_backup
from cryptography.fernet import Fernet


def test_backup_write_refuses_disk_corruption_before_acknowledging(tmp_path, monkeypatch):
    import social.connections.recovery as recovery
    original = recovery.os.fsync
    destination = tmp_path / 'backup.json'
    def corrupt_after_sync(fd):
        original(fd)
        # Simulate corrupt persisted bytes after the directory synchronization.
        if destination.exists():
            destination.write_bytes(b'{}')
    monkeypatch.setattr(recovery.os, 'fsync', corrupt_after_sync)
    with pytest.raises(RecoveryError):
        write_keyring_backup(destination, RecoveryKeyring('v1', {'v1': Fernet.generate_key().decode()}))
