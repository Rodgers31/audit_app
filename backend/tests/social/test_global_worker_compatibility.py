"""Replay existing target-level contracts under an explicit global owner.

Uses a separate strictly assigned fixture because historical port62124 can be
leased to another engineering lane. Original assertions/cases remain unchanged.
"""
import pytest
from sqlalchemy import text
from worker_ownership_support import role_database
from test_queue_postgres import (
    test_ambiguous_result_reconciles_without_blind_resend_while_paused,
    test_crash_after_permit_recovers_into_unknown_without_second_send,
    test_exhausted_read_budget_defers_checkpoint_then_recovers_after_window,
    test_direct_read_permit_cannot_bypass_exhausted_budget,
    test_expired_dispatched_claim_holds_account_and_fences_late_receipt,
    test_completion_database_failure_survives_restart_as_reconciliation,
    test_charged_status_read_is_blocked_without_budget_reservation,
    test_repository_direct_public_permit_cannot_bypass_mutation_gate,
    test_duplicate_unresolved_public_permit_on_same_claim_is_rejected,
    test_repository_reconciliation_retry_cannot_use_generic_truthy_evidence,
    test_verified_complete_original_mutation_absence_proof_allows_bounded_retry,
    test_other_selected_account_failure_does_not_block_independent_valid_permit,
    test_content_capability_and_media_gates_fail_closed,
    test_claim_audit_does_not_deadlock_against_account_then_target_lock_order,
    test_actual_process_kill_after_fake_remote_acceptance_retains_global_owner_without_republish,
    test_mutation_transaction_acquires_documented_lock_order,
    test_empty_queue_minimal_query_and_idle_heartbeat,
)
from test_connections_support import config
from test_native_worker_postgres import (
    test_native_pipeline_survives_restart_at_every_checkpoint,
    test_native_accepted_send_without_saved_id_is_never_resent,
)
from test_paused_queue_postgres import (
    test_paused_normal_targets_are_not_claimed_or_rewritten,
    test_paused_recovery_states_remain_claimable_for_read_intents,
    test_paused_queue_does_not_hide_or_wake_before_recovery_work,
    test_platform_pause_leaves_other_platform_claims_and_wakeups_eligible,
    test_resume_reconsiders_unchanged_queued_authorization,
    test_pause_after_claim_still_refuses_mutation,
    test_missing_controls_are_not_misreported_as_paused_empty_queue,
    test_only_explicit_boolean_platform_pause_suppresses_claims,
)


@pytest.fixture
def engine(role_database):
    owner, _, _, _ = role_database
    with owner.begin() as conn: conn.execute(text('DELETE FROM social_controls'))
    return owner
