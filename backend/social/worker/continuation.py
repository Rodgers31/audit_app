"""Pure binding checks for nonpublic provider-session recovery receipts."""
from ..contracts import NonPublicContinuationProof, canonical_hash


def nonpublic_continuation_matches(proof, original, *, account_id, payload_hash, checkpoint, outcome):
    try:
        proof = NonPublicContinuationProof.model_validate(proof)
        intent = original['receipt']['intent']
        return (outcome == 'confirmed_success' and original['operation'] in {'upload','create_container','finalize'}
            and original['dispatch_started_at'] is None and intent['publication_capable'] is False
            and intent['mutating'] is True and intent['safe_replay_class'] == 'requires_reconciliation'
            and str(proof.account_id) == str(account_id) and str(proof.operation_id) == str(original['operation_id'])
            and proof.content_hash == payload_hash and proof.request_fingerprint == original['request_fingerprint']
            and proof.checkpoint_hash == canonical_hash(checkpoint))
    except (ValueError,TypeError,KeyError):
        return False
