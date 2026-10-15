"""Owned epoch PostgreSQL prerequisite and workflow boundary regressions."""
from pathlib import Path
from copy import deepcopy
import importlib.util
import json
import os
import subprocess
import tempfile
import time
from unittest.mock import patch
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[3]

class AuditEpochWorkflowTests(unittest.TestCase):
    def test_unchanged_epoch_cohort_has_required_prerequisite_and_cleanup(self):
        for name in ("ci.yml", "verification.yml"):
            with self.subTest(workflow=name):
                job = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())["jobs"]["test-backend"]
                steps = job["steps"]
                names = [step.get("name") for step in steps]
                self.assertIn("Prepare owned audit epoch test fixture", names)
                self.assertIn("Remove owned audit epoch test fixture", names)
                prepare = steps[names.index("Prepare owned audit epoch test fixture")]
                cleanup = steps[names.index("Remove owned audit epoch test fixture")]
                test_index = next(i for i, step in enumerate(steps) if step.get("id") == "backend_tests")
                self.assertLess(names.index("Prepare owned reconciliation test fixture"), steps.index(prepare))
                self.assertLess(steps.index(prepare), test_index)
                self.assertGreater(steps.index(cleanup), test_index)
                self.assertEqual(job["timeout-minutes"], 60)
                self.assertEqual(prepare["timeout-minutes"], 5)
                self.assertEqual(cleanup["timeout-minutes"], 5)
                self.assertEqual(cleanup["if"], "always()")
                self.assertNotIn("continue-on-error", prepare)
                self.assertNotIn("continue-on-error", cleanup)
                state = '\"$RUNNER_TEMP/audit-epoch-fixture-state.json\"'
                self.assertEqual(prepare["run"], f"python .github/scripts/prepare_audit_epoch_test_fixture.py prepare --state {state} --port 55534")
                self.assertIn(f"python .github/scripts/prepare_audit_epoch_test_fixture.py cleanup --state {state}", cleanup["run"])
                self.assertEqual(steps[test_index]["run"], "python .github/scripts/run_backend_tests.py")
                self.assertEqual(steps[test_index]["env"]["DATABASE_URL"], "postgresql://postgres:postgres@localhost:5432/audit_app_test")


SPEC = importlib.util.spec_from_file_location("audit_epoch_helper_test", ROOT / ".github/scripts/prepare_audit_epoch_test_fixture.py")
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)

class AuditEpochFixtureBoundaryTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"PATH": os.defpath}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.state_path = self.directory / "epoch-state.json"
        self.export_path = self.directory / "github-env"
        self.deadline = time.monotonic() + 60
        self.state = {"version": 1, "reset_id": None, "reset_removed": False, "ready": False, "cleaned": False}
        nonce = "a" * 32
        self.value = {"version": 1, "nonce": nonce, "container_name": helper.base.PREFIX + nonce + "-db",
                      "network_name": helper.base.PREFIX + nonce + "-net", "database": helper.base.PREFIX + nonce,
                      "port": 55534, "image": helper.base.IMAGE, "container_id": "b" * 64,
                      "network_id": "c" * 64, "ready": True, "cleaned": False}
        self.mount = {"Type": "volume", "Name": "d" * 64, "Source": "/owned-volume",
                      "Destination": helper.PGDATA, "Driver": "local", "RW": True}
        self.container = {"State": {"Running": False, "Status": "exited", "ExitCode": 0, "Error": ""},
                          "Mounts": [self.mount], "Config": {"Env": ["PGDATA=" + helper.PGDATA]},
                          "HostConfig": {"Binds": None, "VolumesFrom": None}}
        self.utility = {"Id": "e" * 64, "Name": "/" + helper.reset_name(self.value),
            "Config": {"Image": helper.base.IMAGE, "User": "postgres", "Entrypoint": ["/bin/sh"], "Cmd": ["-ceu", helper.RESET],
                       "Labels": {"audit.review": "592", "audit.fixture.nonce": nonce, "audit.fixture.purpose": "epoch-reset"},
                       "Env": ["PGDATA=" + helper.PGDATA]},
            "HostConfig": {"NetworkMode": "none", "Binds": None, "PortBindings": None, "Privileged": False,
                           "ReadonlyRootfs": True, "VolumesFrom": [self.value["container_id"] + ":rw"]}, "Mounts": [self.mount]}

    def refused_before_prepare(self, callback, reason):
        with patch.object(helper.base, "prepare") as prepare:
            with self.assertRaisesRegex(helper.Refused, reason):
                callback()
            prepare.assert_not_called()

    def test_invalid_prototype_ports_refuse_before_resource_creation(self):
        for value in (True, "55534", 55496, 55548, 0, None):
            with self.subTest(port=value):
                self.refused_before_prepare(lambda: helper.prepare(self.state_path, value, self.export_path, self.deadline), "explicit_issue611_owned_port_required")
        for value in (55534, 55545):
            helper.validate_port(value)

    def test_ambient_configuration_refuses_before_resources(self):
        for key in (*helper.base.LIBPQ, *helper.KEYS):
            with self.subTest(key=key), patch.dict(os.environ, {key: "inert"}, clear=True):
                self.refused_before_prepare(lambda: helper.prepare(self.state_path, 55534, self.export_path, self.deadline), "ambient_")
        self.assertFalse(self.state_path.exists())

    def test_existing_or_aliased_state_and_export_refuse(self):
        for occupied in (self.state_path, *helper.paths(self.state_path)):
            occupied.write_text("owned marker")
            self.refused_before_prepare(lambda: helper.prepare(self.state_path, 55534, self.export_path, self.deadline), "existing_state_or_private_export_refused")
            self.assertEqual(occupied.read_text(), "owned marker")
            occupied.unlink()
        self.refused_before_prepare(lambda: helper.prepare(self.state_path, 55534, self.state_path, self.deadline), "aliased_fixture_state_or_export")

    def test_destination_symlinks_and_parent_traversal_refuse_before_io(self):
        outside = self.directory / "outside"; outside.mkdir()
        link = self.directory / "link"; link.symlink_to(outside, target_is_directory=True)
        for value in (link / "state", self.directory / "missing" / ".." / "state", ROOT / "state"):
            with self.subTest(path=str(value)):
                self.refused_before_prepare(lambda: helper.prepare(value, 55534, self.export_path, self.deadline), "owned_path_required|symlink")
        self.assertEqual(list(outside.iterdir()), [])
        dangling = self.directory / "dangling"; dangling.symlink_to(outside / "new")
        self.refused_before_prepare(lambda: helper.prepare(self.state_path, 55534, dangling, self.deadline), "symlink")

    def test_state_exact_types_and_permissions_are_required(self):
        helper.state_write(self.state_path, self.state)
        self.assertEqual(helper.state_read(self.state_path), self.state)
        for delta in ({"version": True}, {"reset_id": "bad"}, {"reset_removed": 1}, {"ready": True}, {"unknown": "field"}):
            bad = {**self.state, **delta}; helper.base.state_write(self.state_path, bad)
            with self.assertRaisesRegex(helper.Refused, "epoch_state_identity"):
                helper.state_read(self.state_path)
        helper.base.state_write(self.state_path, self.state); self.state_path.chmod(0o644)
        with self.assertRaisesRegex(helper.Refused, "state_permissions"):
            helper.state_read(self.state_path)

    def test_export_preserves_original_reconciliation_url_byte_for_byte(self):
        original = b"BATCH9_RECONCILIATION_DATABASE_URL=postgresql+psycopg2://postgres@127.0.0.1:55548/owned\nOTHER=inert\n"
        self.export_path.write_bytes(original)
        self.assertEqual(helper.environment_bytes(self.export_path), original)
        helper.export(self.export_path, 55534, original)
        self.assertEqual(self.export_path.read_bytes(), original + b"ISSUE611_OWNED_POSTGRES=1\nISSUE611_PG_PORT=55534\n")
        with self.assertRaisesRegex(helper.Refused, "existing_epoch_environment_export_refused"):
            helper.environment_bytes(self.export_path)
        for bad in (b"ISSUE611_OWNED_POSTGRES=0\n", b"ISSUE611_PG_PORT=55545\n", b"unterminated"):
            self.export_path.write_bytes(bad)
            with self.assertRaisesRegex(helper.Refused, "existing_epoch_environment_export_refused|incomplete_line"):
                helper.environment_bytes(self.export_path)
            self.assertEqual(self.export_path.read_bytes(), bad)
        self.export_path.write_bytes(b"changed\n")
        with self.assertRaisesRegex(helper.Refused, "environment_export_changed"):
            helper.export(self.export_path, 55534, original)

    def test_stopped_server_and_fresh_anonymous_volume_are_required(self):
        with patch.object(helper.base, "verify_resources"), patch.object(helper.base, "inspect", return_value=self.container):
            self.assertEqual(helper.container(self.value, self.deadline, running=False), self.mount)
        for mutate in (lambda v: v["State"].update(Running=True), lambda v: v["State"].update(ExitCode=1),
                       lambda v: v["State"].update(ExitCode=False), lambda v: v["Mounts"][0].update(Type="bind"),
                       lambda v: v["Mounts"][0].update(Name="foreign"), lambda v: v["Mounts"][0].update(RW=False),
                       lambda v: v["HostConfig"].update(VolumesFrom=["foreign:rw"]), lambda v: v["Config"].update(Env=[]),
                       lambda v: v["Config"].update(Env="PGDATA=" + helper.PGDATA),
                       lambda v: v["Config"].update(Env=["PGDATA=" + helper.PGDATA, 1]),
                       lambda v: v["Mounts"][0].update(Source=None), lambda v: v["Mounts"][0].update(Source="")):

            bad = deepcopy(self.container); mutate(bad)
            with patch.object(helper.base, "verify_resources"), patch.object(helper.base, "inspect", return_value=bad):
                with self.assertRaises(helper.Refused):
                    helper.container(self.value, self.deadline, running=False)

    def test_utility_is_exact_pinned_owned_offline_command(self):
        with patch.object(helper.base, "inspect", return_value=self.utility):
            helper.verify_reset(self.value, "e" * 64, self.mount, self.deadline)
        for mutate in (lambda v: v.update(Id="f" * 64), lambda v: v["Config"].update(Image="postgres:latest"),
                       lambda v: v["Config"]["Labels"].update({"audit.fixture.nonce": "foreign"}),
                       lambda v: v["Config"].update(Cmd=["-ceu", "pg_resetwal -f"]),
                       lambda v: v["HostConfig"].update(NetworkMode="default"),
                       lambda v: v["HostConfig"].update(VolumesFrom=["foreign:rw"]),
                       lambda v: v["HostConfig"].update(Privileged=True), lambda v: v["Mounts"][0].update(Name="f" * 64),
                       lambda v: v.update(Mounts=[None]), lambda v: v["Config"].update(Env="PGDATA=" + helper.PGDATA),
                       lambda v: v["Mounts"][0].update(RW=1), lambda v: v["Mounts"][0].update(Source=None)):

            bad = deepcopy(self.utility); mutate(bad)
            with patch.object(helper.base, "inspect", return_value=bad):
                with self.assertRaisesRegex(helper.Refused, "epoch_utility_ownership_mismatch"):
                    helper.verify_reset(self.value, "e" * 64, self.mount, self.deadline)
        self.assertNotIn("-f", helper.RESET)
        self.assertIn('test ! -e "$PGDATA/postmaster.pid"', helper.RESET)

    def test_epoch_readback_rejects_epoch_zero_wrong_owner_and_boolean_counts(self):
        valid = {"database": "issue611", "user": "inert", "owner": "inert", "root": str(2**32 + 1001), "autovacuum": "off", "tables": 0, "roles": 0}
        with patch.object(helper, "psql", return_value=json.dumps(valid)):
            self.assertEqual(helper.proof(self.value, self.deadline), valid)
        for delta in ({"root": "1001"}, {"root": 2**32 + 1001}, {"owner": "postgres"}, {"tables": False}, {"roles": 1}, {"extra": 0}):
            with self.subTest(delta=delta), patch.object(helper, "psql", return_value=json.dumps({**valid, **delta})):
                with self.assertRaisesRegex(helper.Refused, "epoch_database_readback_mismatch"):
                    helper.proof(self.value, self.deadline)

    def test_absence_requires_exact_not_found_not_daemon_error(self):
        identity = "e" * 64
        for kind, error in (("container", "Error response from daemon: No such container: " + identity), ("network", "Error response from daemon: network " + identity + " not found")):
            result = subprocess.CompletedProcess([], 1, "[]\n", error + "\n")
            with patch.object(helper.subprocess, "run", return_value=result):
                helper.absence(kind, identity, self.deadline)
            for bad in (subprocess.CompletedProcess([], 1, "[]", "Cannot connect to the Docker daemon"),
                        subprocess.CompletedProcess([], 1, "[]", error + "x"), subprocess.CompletedProcess([], 0, "[]", error),
                        subprocess.CompletedProcess([], 1, "", error), subprocess.CompletedProcess([], 1, "[]", "permission denied")):
                with patch.object(helper.subprocess, "run", return_value=bad):
                    with self.assertRaisesRegex(helper.Refused, "resource_absence_unverified"):
                        helper.absence(kind, identity, self.deadline)

    def test_cleanup_checks_all_ownership_before_deletion(self):
        self.state.update(reset_id="e" * 64)
        helper.state_write(self.state_path, self.state)
        helper.base.state_write(helper.paths(self.state_path)[0], self.value)
        with patch.object(helper.base, "verify_resources", side_effect=helper.Refused("container_ownership_mismatch")), patch.object(helper.base, "run") as run:
            with self.assertRaisesRegex(helper.Refused, "container_ownership_mismatch"):
                helper.cleanup(self.state_path, self.deadline)
            run.assert_not_called()
        with patch.object(helper.base, "verify_resources"), patch.object(helper.base, "inspect", return_value=self.container), patch.object(helper, "verify_reset", side_effect=helper.Refused("epoch_utility_ownership_mismatch")), patch.object(helper.base, "run") as run:
            with self.assertRaisesRegex(helper.Refused, "epoch_utility_ownership_mismatch"):
                helper.cleanup(self.state_path, self.deadline)
            run.assert_not_called()

    def test_cleanup_proves_absence_even_for_previously_cleaned_state(self):
        self.state.update(reset_id="e" * 64, reset_removed=True, cleaned=True)
        helper.state_write(self.state_path, self.state)
        self.value.update(ready=False, cleaned=True)
        helper.base.state_write(helper.paths(self.state_path)[0], self.value)
        with patch.object(helper, "absence") as absence, patch.object(helper.base, "cleanup") as cleanup:
            self.assertTrue(helper.cleanup(self.state_path, self.deadline)["physical_resource_absence_verified"])
            cleanup.assert_not_called()
            self.assertEqual([call.args[:2] for call in absence.call_args_list], [("container", "b" * 64), ("network", "c" * 64), ("container", "e" * 64)])
        with patch.object(helper, "absence", side_effect=helper.Refused("resource_absence_unverified")):
            with self.assertRaisesRegex(helper.Refused, "resource_absence_unverified"):
                helper.cleanup(self.state_path, self.deadline)

    def test_partial_before_resource_creation_is_cleanup_safe(self):
        helper.state_write(self.state_path, self.state)
        with patch.object(helper.base, "run") as run:
            self.assertEqual(helper.cleanup(self.state_path, self.deadline)["status"], "cleaned_before_creation")
            run.assert_not_called()
        self.assertTrue(helper.state_read(self.state_path)["cleaned"])
        self.state.update(reset_id="e" * 64)
        helper.state_write(self.state_path, self.state)
        with self.assertRaisesRegex(helper.Refused, "missing_secondary_fixture_state"):
            helper.cleanup(self.state_path, self.deadline)

if __name__ == "__main__":
    unittest.main()
