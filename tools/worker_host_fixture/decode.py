"""Strict off-host reconstruction of the bounded inert log exports.

Callers supply the expected run, immutable manifest and exporter hashes from the
reviewed build. Neither a complete backup nor capacity export proves host stop;
the authentic launcher and Render deployment records must be checked separately.
"""
import base64
import hashlib
import re
import zlib


def decode(rows, *, name, run_id, manifest_sha256, generator_sha256):
    if (type(name) is not str or not re.fullmatch('[a-z][a-z0-9_-]{0,40}', name)
            or type(run_id) is not str or not re.fullmatch('[0-9a-f]{12}', run_id)
            or any(type(s) is not str or not re.fullmatch('[0-9a-f]{64}', s)
                   for s in (manifest_sha256, generator_sha256))):
        raise ValueError('Expected external identity required')
    if type(rows) is not list or not 1 <= len(rows) <= 171:
        raise ValueError('Complete nonempty chunk set required')
    expected = {'version', 'name', 'run_id', 'manifest_sha256', 'generator_sha256',
                'index', 'count', 'sha256', 'size', 'data'}
    pieces, binding = {}, None
    for row in rows:
        if (type(row) is not dict or set(row) != expected
                or type(row['version']) is not int or row['version'] != 1
                or row['name'] != name or row['run_id'] != run_id
                or row['manifest_sha256'] != manifest_sha256 or row['generator_sha256'] != generator_sha256
                or type(row['index']) is not int or type(row['count']) is not int
                or not 1 <= row['count'] <= 171 or not 0 <= row['index'] < row['count']
                or type(row['size']) is not int or not 0 < row['size'] <= 4 * 1024 ** 2
                or type(row['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', row['sha256'])
                or type(row['data']) is not str or not 0 < len(row['data']) <= 1536
                or row['index'] in pieces):
            raise ValueError('Chunk shape/identity invalid')
        current = (row['count'], row['sha256'], row['size'])
        if binding is not None and current != binding:
            raise ValueError('Artifact binding changed')
        binding = current
        pieces[row['index']] = row['data']
    count, sha, size = binding
    if set(pieces) != set(range(count)):
        raise ValueError('Artifact incomplete')
    encoded = ''.join(pieces[i] for i in range(count))
    if len(encoded) > 256 * 1024:
        raise ValueError('Encoded bound')
    compressed = base64.b64decode(encoded, validate=True)
    obj = zlib.decompressobj()
    content = obj.decompress(compressed, 4 * 1024 ** 2 + 1)
    if (len(content) != size or len(content) > 4 * 1024 ** 2 or not obj.eof
            or obj.unused_data or obj.unconsumed_tail or hashlib.sha256(content).hexdigest() != sha):
        raise ValueError('Artifact length/hash/compression differs')
    return content
