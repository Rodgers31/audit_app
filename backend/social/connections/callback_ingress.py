"""Admission for exact callbacks whose earliest collectors were separately qualified.

This attestation does not redact logs. Existing Vercel callbacks are unqualified
(#767); their URLs must not be added merely to make the connection UI available.
"""
import json

from ..service import SocialError

BLOCKER = 'CALLBACK_INGRESS_UNVERIFIED'
MESSAGE = 'New connections are paused until callback privacy is verified. Existing account maintenance remains available.'


def verified_callbacks(raw):
    """Malformed or absent operator attestations always leave OAuth paused."""
    try:
        values = json.loads(raw)
    except (ValueError, TypeError):
        return ()
    if (type(values) is not list or not 1 <= len(values) <= 16
            or any(type(v) is not str or not 1 <= len(v) <= 2048 for v in values)
            or len(values) != len(set(values))):
        return ()
    return tuple(values)


def ingress_qualified(registered, verified, valid):
    # An old approval cannot silently admit a new alias, path or deployment.
    return (type(registered) is tuple and type(verified) is tuple and bool(registered)
            and len(registered) <= 16
            and all(type(v) is str and valid(v) for v in registered)
            and len(registered) == len(set(registered))
            and all(type(v) is str and valid(v) for v in verified)
            and len(verified) == len(set(verified)) and set(registered) == set(verified))


def require_ingress(registered, verified, valid):
    if not ingress_qualified(registered, verified, valid):
        raise SocialError(BLOCKER, MESSAGE, 503)
