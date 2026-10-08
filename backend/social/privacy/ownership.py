"""Record only the inspected provider port, inside the connection transaction."""
from uuid import UUID, uuid4
from sqlalchemy import func, select
from ..models import SocialAccount
from ..connections.provider import InspectedDiscovery
from ..connections.models import SocialCredential
from ..service import SocialError
from .models import SocialPrivacyOwnership, SocialPrivacyReceipt
from .subjects import SubjectDigester


def unavailable():
    return SocialError('PRIVACY_OWNERSHIP_UNRESOLVED', 'Inspected ownership is unavailable or conflicts with retained history.', 409)


class OwnershipRecorder:
    def __init__(self, app_id, digester):
        if not isinstance(digester, SubjectDigester):
            raise unavailable()
        digester.digest(app_id, '1')
        self.app_id, self.digester = app_id, digester

    def _add(self, db, *, digest_version, subject_digest, reference_key, flow, credential=None, account=None, page_id=None, generation_at=None):
        values = dict(app_id=self.app_id, digest_version=digest_version, subject_digest=subject_digest,
                      reference_key=reference_key, flow_id=flow.id,
                      credential_id=credential.id if credential else None,
                      credential_version=credential.version if credential else None,
                      account_id=account.id if account else None, page_id=page_id,
                      generation_at=generation_at if generation_at is not None else credential.created_at if credential else flow.created_at)
        old = db.scalar(select(SocialPrivacyOwnership).where(SocialPrivacyOwnership.reference_key == reference_key))
        if old:
            if any(getattr(old, k) != v for k, v in values.items()):
                raise unavailable()
            return old
        row = SocialPrivacyOwnership(id=uuid4(), **values)
        db.add(row)
        db.flush()
        return row

    def record_discovery(self, db, flow, inspected):
        if (type(inspected) is not InspectedDiscovery or inspected.app_id != self.app_id
                or type(inspected.page_ids) is not tuple or len(inspected.page_ids) > 100
                or len(set(inspected.page_ids)) != len(inspected.page_ids)):
            raise unavailable()
        subject = self.digester.digest(self.app_id, inspected.subject)
        # Validate provider-port bindings independently of the encrypted bundle.
        grant = inspected.grant
        if (type(grant) is not dict or type(grant.get('metadata')) is not dict
                or grant['metadata'].get('external_user_id') != inspected.subject
                or type(grant.get('choices')) is not list
                or tuple(p.get('page_id') for p in grant['choices'] if type(p) is dict) != inspected.page_ids
                or any(type(p) is not dict or type(p.get('metadata')) is not dict
                       or p['metadata'].get('external_user_id') != inspected.subject for p in grant['choices'])):
            raise unavailable()
        # A callback may arrive while provider HTTP is in progress, before its
        # subject is indexable. A fresh save must honor that durable request.
        from sqlalchemy import or_
        candidates = self.digester.candidates(self.app_id, inspected.subject)
        versions = set(db.scalars(select(SocialPrivacyReceipt.digest_version).where(SocialPrivacyReceipt.app_id == self.app_id).distinct().limit(17)))
        if not versions <= set(self.digester.keys):
            raise unavailable()
        pending = db.scalar(select(SocialPrivacyReceipt.id).where(
            SocialPrivacyReceipt.app_id == self.app_id,
            SocialPrivacyReceipt.received_at >= flow.created_at,
            or_(*((SocialPrivacyReceipt.digest_version == v) & (SocialPrivacyReceipt.subject_digest == d) for v, d in candidates))).limit(1))
        if pending is not None:
            raise unavailable()
        self._add(db, digest_version=self.digester.active_version, subject_digest=subject,
                  reference_key='flow:' + str(flow.id), flow=flow, generation_at=db.scalar(select(func.current_timestamp())))

    def record_selection(self, db, flow, grant, parent, credential, accounts, page_id):
        owner = db.scalar(select(SocialPrivacyOwnership).where(SocialPrivacyOwnership.reference_key == 'flow:' + str(flow.id)))
        if owner is None or owner.app_id != self.app_id:
            raise unavailable()
        subject = self.digester.digest(self.app_id, grant['metadata']['external_user_id'], owner.digest_version)
        if owner.subject_digest != subject:
            raise unavailable()
        self._add(db, digest_version=owner.digest_version, subject_digest=subject,
                  reference_key='credential:' + str(parent.id) + ':' + str(parent.version), flow=flow, credential=parent)
        for account in accounts:
            if account.credential_id != credential.id or type(account.id) is not UUID:
                raise unavailable()
            self._add(db, digest_version=owner.digest_version, subject_digest=subject,
                      reference_key='credential:' + str(credential.id) + ':' + str(credential.version) + ':' + str(account.id),
                      flow=flow, credential=credential, account=account, page_id=page_id)

    def record_rotation(self, db, credential, old_version):
        owners = list(db.scalars(select(SocialPrivacyOwnership).where(
            SocialPrivacyOwnership.credential_id == credential.id, SocialPrivacyOwnership.credential_version == old_version)))
        if any(old.app_id != self.app_id for old in owners):
            raise unavailable()
        for old in owners:
            from ..connections.models import SocialOAuthFlow
            flow = db.get(SocialOAuthFlow, old.flow_id)
            account = db.get(SocialAccount, old.account_id) if old.account_id else None
            self._add(db, digest_version=old.digest_version, subject_digest=old.subject_digest,
                      reference_key='credential:' + str(credential.id) + ':' + str(credential.version) + (':' + str(account.id) if account else ''),
                      flow=flow, credential=credential, account=account, page_id=old.page_id)
