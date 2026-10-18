from ..contracts import canonical_hash
from ..models import SocialPostRevision
from ..service import SocialError
from .contracts import Composition


def bound_composition(db, row):
    """Revalidate durable bytes, not merely their ORM insertion-time history."""
    composition = Composition.model_validate(row.composition)
    revision = db.get(SocialPostRevision, row.revision_id, populate_existing=True)
    if revision is None or composition.revision_id != row.revision_id:
        raise SocialError('RENDER_INTEGRITY', 'The derivative source identity is invalid.')
    revision_hash = canonical_hash({'document': revision.document, 'evidence_snapshot': revision.evidence_snapshot})
    expected = canonical_hash({'composition': composition.model_dump(mode='json'), 'revision_hash': revision_hash})
    if revision_hash != revision.content_hash or expected != row.input_hash:
        raise SocialError('RENDER_INTEGRITY', 'The durable render input differs from its source-bound checksum.')
    return composition
