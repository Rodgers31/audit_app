"""Finite private JSON wire format. No application, credential or SQL imports."""
import json
import math

OPERATION_SECONDS = 20.0
CLEANUP_SECONDS = 1.0
MAX_INPUT = 131072
MAX_OUTPUT = 65536


def encode(value):
    return json.dumps(value, allow_nan=False, separators=(',', ':')).encode('utf-8')


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate protocol field')
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError('Nonfinite protocol value')

    def finite_float(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError('Nonfinite protocol value')
        return value

    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
        parse_constant=nonfinite, parse_float=finite_float)
