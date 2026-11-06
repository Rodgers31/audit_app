"""Prevent omission of the original affected families from lane qualification."""
import json
from pathlib import Path


def test_lane_selector_keeps_original_runtime_and_new_boundaries_explicit():
    root=Path(__file__).resolve().parents[3]
    manifest=json.loads(Path(__file__).with_name('selectors.json').read_text())
    required={'backend/tests/test_nightly_runtime_profile.py','backend/tests/test_seeding_cli_budget.py',
              'backend/tests/social/test_connections_provider.py','backend/tests/social/test_meta_verification_budget.py',
              'backend/tests/test_refresh_eligibility.py','backend/tests/test_health_selected_plan.py',
              'backend/tests/test_workflow_refresh_adversarial.py','backend/tests/test_workflow_refresh_signed.py'}
    selected=manifest['always']
    assert selected and len(selected)==len(set(selected)) and required <= set(selected)
    assert all((root/name).is_file() for name in selected)
    assert set(manifest['acceptance_owned_held']).isdisjoint(selected)
    assert 'backend/tests/test_refresh_current_run_postgres.py' in manifest['acceptance_owned_held']
