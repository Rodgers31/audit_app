"""Explicit runtime injection; importing or configuring OAuth mounts no ingress."""
from dataclasses import dataclass, field
from .api import STATUS_PATH, create_privacy_router
from .ownership import OwnershipRecorder
from .service import PrivacyConfig, PrivacyService
from .subjects import SubjectDigester
from ..connections.crypto import CredentialCipher
from ..service import SocialError


@dataclass(frozen=True)
class PrivacyRegistration:
    config: PrivacyConfig
    digester: SubjectDigester = field(repr=False)
    cipher: CredentialCipher = field(repr=False)
    session_factory: object = field(repr=False)

    def validate(self):
        if (type(self.config) is not PrivacyConfig or not isinstance(self.digester, SubjectDigester)
                or not isinstance(self.cipher, CredentialCipher) or not callable(self.session_factory)):
            raise SocialError('PRIVACY_CONFIGURATION_INVALID', 'Explicit privacy dependencies are required.', 503)
        self.config.validate()
        from urllib.parse import urlsplit
        if urlsplit(self.config.status_url_base).path != STATUS_PATH:
            raise SocialError('PRIVACY_CONFIGURATION_INVALID', 'The exact installed status path is required.', 503)

    def service_dependency(self):
        with self.session_factory() as db:
            yield PrivacyService(db, self.config, digester=self.digester, cipher=self.cipher)


def install_privacy(app, registration):
    if type(registration) is not PrivacyRegistration or hasattr(app.state, 'social_privacy_registration'):
        raise SocialError('PRIVACY_CONFIGURATION_INVALID', 'One explicit privacy registration is required.', 503)
    registration.validate()
    if registration.config.enabled:
        app.include_router(create_privacy_router(registration.service_dependency))
    app.state.social_privacy_registration = registration


def registered_ownership(request):
    registration = getattr(request.app.state, 'social_privacy_registration', None)
    if registration is None:
        return None  # Legacy/index-incomplete; never upgraded by declarations.
    if type(registration) is not PrivacyRegistration:
        raise SocialError('PRIVACY_CONFIGURATION_INVALID', 'The privacy registration is unavailable.', 503)
    registration.validate()
    return OwnershipRecorder(registration.config.app_id, registration.digester)
