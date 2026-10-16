"""Default-off runtime assembly using explicit existing privacy key registration."""
import base64
import json
import os
from pathlib import Path
from uuid import UUID
from ..service import SocialError
from .deletion_ledger import FileDeletionLedger, _pairs
from .workflow_api import router
from .workflow_contracts import PrivacyWorkflowConfig


def configure_privacy_workflow(app, environ=None):
    values = os.environ if environ is None else environ
    try:
        enabled = values.get('SOCIAL_PRIVACY_WORKFLOW_ENABLED', 'false')
        execution = values.get('SOCIAL_PRIVACY_EXECUTION_ENABLED', 'false')
        if enabled not in ('true', 'false') or execution not in ('true', 'false'):
            raise ValueError()
        policies, approvers, ledger = (), (), None
        if enabled == 'true':
            if getattr(app.state, 'social_privacy_registration', None) is None:
                raise ValueError()
            raw = values.get('SOCIAL_PRIVACY_POLICIES', '')
            actors = values.get('SOCIAL_PRIVACY_APPROVERS', '')
            if type(raw) is not str or len(raw) > 8192 or type(actors) is not str or len(actors) > 8192:
                raise ValueError()
            policy = json.loads(raw, object_pairs_hook=_pairs)
            actors = json.loads(actors)
            if type(policy) is not dict or type(actors) is not list:
                raise ValueError()
            policies = tuple(policy.items())
            approvers = tuple(UUID(a) for a in actors)
        config = PrivacyWorkflowConfig(enabled == 'true', execution == 'true', policies, approvers)
        config.validate()
        if config.execution_enabled:
            path, key = values.get('SOCIAL_PRIVACY_LEDGER_DIRECTORY'), values.get('SOCIAL_PRIVACY_LEDGER_SIGNING_KEY')
            if type(path) is not str or not Path(path).is_absolute() or type(key) is not str or len(key) != 44:
                raise ValueError()
            decoded = base64.b64decode(key, altchars=b'-_', validate=True)
            if base64.urlsafe_b64encode(decoded).decode() != key:
                raise ValueError()
            ledger = FileDeletionLedger(Path(path), decoded)
    except Exception:
        pass
    else:
        app.state.social_privacy_workflow_config = config
        app.state.social_privacy_deletion_ledger = ledger
        app.include_router(router)
        return config
    raise SocialError('PRIVACY_WORKFLOW_CONFIGURATION_INVALID', 'Explicit privacy policy, approvers and custody configuration are required.', 503)
