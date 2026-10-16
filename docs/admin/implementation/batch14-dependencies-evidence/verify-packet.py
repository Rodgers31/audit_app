"""Verify the complete current packet inventory, independently of historical hashes."""
import hashlib
import json
from pathlib import Path
import sys


def verify(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('packet root must be a real directory')
    manifest_path = root / 'SHA256SUMS.json'
    if manifest_path.is_symlink():
        raise ValueError('linked manifest refused')
    manifest = json.loads(manifest_path.read_text())
    if type(manifest) is not dict or not manifest:
        raise ValueError('nonempty object manifest required')
    actual = {}
    for p in root.rglob('*'):
        if p.is_symlink() or (not p.is_dir() and not p.is_file()):
            raise ValueError('non-regular packet input: ' + str(p))
        if p.is_file() and p != manifest_path:
            actual[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    if actual != manifest:
        raise ValueError('packet inventory or checksum mismatch')
    return len(actual)


if __name__ == '__main__':
    try:
        print(json.dumps({'verified_files': verify(Path(__file__).resolve().parent)}))
    except (OSError, ValueError) as error:
        sys.exit('packet refused: ' + str(error))
