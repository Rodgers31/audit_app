from datetime import datetime, timedelta, timezone
import math
from uuid import uuid4

import pytest

from social.contracts import OperationPlan, OperationResult
from social.worker.policy import bounded_json, retry_decision, validate_plan


def policy(result, **kwargs):
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)
    return retry_decision(result, now=now, submit_count=1, first_started_at=now,
                          retry_deadline=now+timedelta(hours=24), content_valid_until=None,
                          random_fraction=0.5, **kwargs)


def test_retry_classification_requires_definite_acceptance_evidence():
    assert policy(OperationResult(outcome="ambiguous", retry_safe=True,error_code="RATE_LIMITED")).action == "reconcile"
    assert policy(OperationResult(outcome="definite_failure",retry_safe=False,error_code="RATE_LIMITED")).action == "reconcile"
    assert policy(OperationResult(outcome="definite_failure",retry_safe=False,error_code="INVALID_MEDIA")).action == "fail"
    assert policy(OperationResult(outcome="definite_failure",error_code="TOKEN_REVOKED")).action == "block"
    assert policy(OperationResult(outcome="definite_failure",retry_safe=True,error_code="NOT_SENT")).action == "retry"


def test_retry_after_is_not_capped_below_provider_delay():
    future = datetime(2026,10,3,18,tzinfo=timezone.utc)
    decision = policy(OperationResult(outcome="definite_failure",retry_safe=True,error_code="RATE_LIMITED",next_action_at=future))
    assert decision.next_action_at == future
    assert policy(OperationResult(outcome="definite_failure",retry_safe=True,error_code="RATE_LIMITED",
                                 next_action_at=future+timedelta(hours=7))).action == "block"


@pytest.mark.parametrize("value", [[], {"bad": float("nan")}, {"huge":"x"*65536}, {"bad":object()}])
def test_checkpoint_rejects_non_json_malformed_and_unbounded_values(value):
    with pytest.raises((ValueError,TypeError)):
        bounded_json(value)


def test_operation_boundary_contract_cannot_hide_public_send():
    for operation, public, replay in (("publish",False,"safe"),("poll",True,"read_only"),
                                      ("reconcile",False,"safe"),("upload",False,"read_only")):
        with pytest.raises(ValueError):
            validate_plan(OperationPlan(operation_id=uuid4(),operation=operation,publication_capable=public,
                                        safe_replay_class=replay), {})
    with pytest.raises(ValueError):
        validate_plan(OperationPlan(operation_id=uuid4(),operation="publish",publication_capable=True,
                                    safe_replay_class="requires_reconciliation",checkpoint={"different":1}), {})


@pytest.mark.parametrize("count",[True,-1,float("nan")])
def test_direct_retry_policy_rejects_hostile_submission_count(count):
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        retry_decision(OperationResult(outcome="definite_failure",error_code="NOT_SENT",retry_safe=True),
            now=now,submit_count=count,first_started_at=now,retry_deadline=now+timedelta(hours=24),content_valid_until=None)


def test_whitespace_metadata_is_not_positive_confirmation():
    from social.worker.runner import SocialWorker
    assert not SocialWorker._confirmed(OperationResult(outcome="confirmed_success",primary_remote_id=" ",
        visibility_state="public",confirmation_kind=" "))


@pytest.mark.parametrize("ceiling",[True,0,-1,float("nan"),float("inf"),65537])
def test_json_ceiling_direct_call_cannot_override_global_bound(ceiling):
    with pytest.raises(ValueError):
        bounded_json({"large":"x"*100000},max_bytes=ceiling)
