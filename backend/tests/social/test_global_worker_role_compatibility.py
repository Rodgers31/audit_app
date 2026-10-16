"""Existing restricted-role adversaries on the worker lane's isolated schema."""
from test_worker_role_postgres import (
    test_install_is_atomic_idempotent_and_verifies_actual_login,
    test_complete_native_pipeline_and_forbidden_mutations,
    test_authority_drift_refuses_readiness,
    test_restrictive_lock_fence_survives_new_public_permissive_policy,
    test_install_refuses_prior_authority_without_partial_grants,
    test_missing_controls_refuses_and_rolls_back_installation,
    test_install_refuses_prior_maintain_or_login_default_without_partial_grants,
    test_authority_outside_table_grants_refuses_install_verify_and_native_cli,
    test_benign_login_defaults_still_qualify,
    test_extension_default_is_refused_even_where_its_library_is_loaded,
    test_temporary_table_cannot_hide_catalog_rows_from_the_checks,
    test_unpinned_engine_keeps_the_login_search_path,
    test_direct_guards_fail_with_fixed_private_diagnostic,
    test_operator_entrypoint_executes_install_and_actual_login_verification,
    test_own_temporary_objects_in_both_pooled_sessions_still_qualify,
    test_ownership_held_in_another_database_refuses,
    test_loaded_module_default_with_non_user_context_is_refused,
    test_mixed_case_user_setting_default_is_judged_case_insensitively,
)
from test_worker_role_review import (
    test_schema_database_delegation_refuses,
    test_explicit_function_default_grant_refuses,
    test_interrupt_precedence_in_cleanup_is_private,
    test_native_interrupt_drains_owned_cleanup_before_exit130,
    test_remaining_object_delegation_refuses,
)
from test_connections_support import config
from worker_ownership_support import role_database
