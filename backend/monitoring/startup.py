"""Server opt-in for the shared Sentry privacy policy; no feature enablement."""
import os

from sentry_sdk.utils import Dsn

from .instrumentation import setup_sentry


class MonitoringConfigurationError(RuntimeError):
    """Configuration failures expose no server material or SDK exception text."""


def install_sentry(app, settings):
    """Install before requests only when the server explicitly opts in.

    A dormant DSN is intentionally ignored, including secret-manager lookup.
    SDK shutdown/flush uses its standard process lifecycle integration.
    """
    enabled = os.getenv('SENTRY_ENABLED', 'false')
    if enabled == 'false':
        return
    try:
        if enabled != 'true':
            raise ValueError()
        dsn = settings.SENTRY_DSN
        if type(dsn) is not str or not dsn or len(dsn) > 2048:
            raise ValueError()
        Dsn(dsn)
        setup_sentry(app, dsn=dsn)
    except Exception:
        raise MonitoringConfigurationError('Sentry startup configuration is invalid.') from None
