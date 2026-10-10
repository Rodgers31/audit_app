"""Execute configuration, ownership and export refusal boundaries without a DB."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "prepare_reconciliation_test_fixture.py"
SPEC = importlib.util.spec_from_file_location("reconciliation_fixture", SCRIPT)
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


class FixtureControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="batch9-review-592-controls-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.state = self.directory / "state.json"
        self.export = self.directory / "env"
        self.value = {"version": 1, "nonce": "a" * 32, "container_name": subject.PREFIX + "a" * 32 + "-db",
                      "network_name": subject.PREFIX + "a" * 32 + "-net", "database": subject.PREFIX + "a" * 32,
                      "port": 55496, "image": subject.IMAGE, "container_id": "b" * 64, "network_id": "c" * 64,
                      "ready": True, "cleaned": False}
        self.labels = {"audit.review": "592", "audit.fixture.nonce": "a" * 32}
        self.container = {"Id": "b" * 64, "Name": "/" + self.value["container_name"],
                          "Config": {"Labels": self.labels, "Image": subject.IMAGE},
                          "HostConfig": {"PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55496"}]}},
                          "NetworkSettings": {"Networks": {self.value["network_name"]: {}}}}
        self.network = {"Id": "c" * 64, "Name": self.value["network_name"], "Labels": self.labels, "Containers": {"b" * 64: {}}}

    def test_actual_immutable_pin_matches_approved_fixture(self):
        self.assertEqual(subject.IMAGE, "public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675")

    def test_migrated_revision_matches_the_actual_migration_head(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        backend = SCRIPT.parents[2] / "backend"
        config = Config(str(backend / "alembic.ini"))
        config.set_main_option("script_location", str(backend / "alembic"))
        self.assertEqual(subject.REVISION, ScriptDirectory.from_config(config).get_current_head())

    def prepare_with_proof(self, proof_change):
        def inspect(kind, target, deadline):
            if kind == "image":
                return {"Os": "linux", "Architecture": "arm64", "Id": "sha256:" + "a" * 64,
                        "RepoDigests": [subject.IMAGE]}
            value = json.loads(self.state.read_text())
            labels = {"audit.review": "592", "audit.fixture.nonce": value["nonce"]}
            if kind == "container":
                return {"Id": value["container_id"], "Name": "/" + value["container_name"],
                        "Config": {"Labels": labels, "Image": subject.IMAGE},
                        "HostConfig": {"PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(value["port"])}]}},
                        "NetworkSettings": {"Networks": {value["network_name"]: {}}}}
            if kind == "network":
                return {"Id": value["network_id"], "Name": value["network_name"], "Labels": labels,
                        "Containers": {value["container_id"]: {}}}
            raise AssertionError("Unexpected resource inspection")

        def run(command, deadline, **kwargs):
            if command[:2] == ["docker", "version"]:
                return json.dumps({"Os": "linux", "Arch": "arm64"})
            if command[:3] == ["docker", "network", "create"]:
                return "c" * 64
            if command[:2] == ["docker", "run"]:
                return "b" * 64
            if "pg_isready" in command:
                return ""
            if "alembic" in command:
                self.assertEqual(command[-2:], ["upgrade", "head"])
                return ""
            if "psql" in command:
                value = json.loads(self.state.read_text())
                proof = {"database": value["database"], "autovacuum": "off", "revision": subject.REVISION,
                         "claim": True, "jobs": True, "audit": True, "rls": True, "active_index": True}
                return json.dumps(proof_change(proof))
            raise AssertionError("Unexpected fixture command")

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with patch.dict(os.environ, {}, clear=True), patch.object(subject, "inspect", side_effect=inspect), patch.object(subject, "run", side_effect=run):
            return subject.prepare(self.state, port, self.export, time.monotonic() + 30)

    def test_valid_migration_proof_exports_owned_database(self):
        result = self.prepare_with_proof(lambda proof: proof)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(self.export.is_file())
        self.assertTrue(subject.state_read(self.state)["ready"])

    def test_numeric_capabilities_refuse_before_database_export(self):
        for capability in ("claim", "jobs", "audit", "rls", "active_index"):
            with self.subTest(capability=capability):
                if self.state.exists():
                    self.state.unlink()
                with self.assertRaisesRegex(subject.Refused, "migrated_template_readback_mismatch"):
                    self.prepare_with_proof(lambda proof: {**proof, capability: 1})
                self.assertFalse(self.export.exists())
                self.assertFalse(subject.state_read(self.state)["ready"])

    def test_every_ambient_libpq_input_refuses_before_mutation(self):
        for name in subject.LIBPQ:
            with self.subTest(name=name), patch.dict(os.environ, {name: "synthetic-private-input"}, clear=True), patch.object(subject, "run") as run:
                with self.assertRaisesRegex(subject.Refused, "ambient_libpq"):
                    subject.prepare(self.state, 55496, self.export, time.monotonic()+30)
                run.assert_not_called()
                self.assertFalse(self.export.exists())

    def test_invalid_ports_refuse_direct_api(self):
        for port in (True, False, None, "55496", 0, -1, 1023, 65536, float("nan"), float("inf")):
            with self.subTest(port=port), self.assertRaises(subject.Refused):
                subject.validate_port(port)

    def test_existing_state_refuses_before_docker_or_environment_export(self):
        self.state.write_text("do not replace")
        with patch.dict(os.environ, {}, clear=True), patch.object(subject, "run") as run:
            with self.assertRaisesRegex(subject.Refused, "existing_state"):
                subject.prepare(self.state, 55496, self.export, time.monotonic()+30)
            run.assert_not_called()
        self.assertEqual(self.state.read_text(), "do not replace")
        self.assertFalse(self.export.exists())

    def test_busy_loopback_port_refuses_without_export(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            port = occupied.getsockname()[1]
            with patch.dict(os.environ, {}, clear=True), patch.object(subject, "run") as run:
                with self.assertRaisesRegex(subject.Refused, "port_unavailable"):
                    subject.prepare(self.state, port, self.export, time.monotonic()+30)
                run.assert_not_called()
                self.assertFalse(self.export.exists())

    def test_state_shape_identity_and_permissions_are_required(self):
        subject.state_write(self.state, self.value)
        self.assertEqual(subject.state_read(self.state), self.value)
        self.state.chmod(0o644)
        with self.assertRaisesRegex(subject.Refused, "permissions"):
            subject.state_read(self.state)
        self.state.chmod(0o600)
        for field, wrong in (("version", True), ("nonce", ""), ("image", "postgres:17"),
                             ("container_id", "foreign"), ("port", True), ("container_name", "production"),
                             ("network_name", "shared-network"), ("database", "postgres"), ("ready", 1)):
            with self.subTest(field=field):
                subject.state_write(self.state, {**self.value, field: wrong})
                with self.assertRaises(subject.Refused):
                    subject.state_read(self.state)

    def test_cleanup_refuses_foreign_container_without_any_delete(self):
        subject.state_write(self.state, self.value)
        variants = [ {**self.container, "Name": "/production"},
                     {**self.container, "Config": {"Labels": {}, "Image": subject.IMAGE}},
                     {**self.container, "HostConfig": {"PortBindings": {}}},
                     {**self.container, "NetworkSettings": {"Networks": {"shared": {}}}}]
        for container in variants:
            with self.subTest(container=container), patch.dict(os.environ, {}, clear=True), patch.object(subject, "inspect", return_value=container), patch.object(subject, "run") as run:
                with self.assertRaisesRegex(subject.Refused, "container_ownership"):
                    subject.cleanup(self.state, time.monotonic()+30)
                run.assert_not_called()
                self.assertFalse(subject.state_read(self.state)["cleaned"])

    def test_cleanup_refuses_foreign_network_member_without_any_delete(self):
        subject.state_write(self.state, self.value)
        with patch.dict(os.environ, {}, clear=True), patch.object(subject, "inspect", side_effect=[self.container, {**self.network, "Containers": {"f"*64:{}}}]), patch.object(subject, "run") as run:
            with self.assertRaisesRegex(subject.Refused, "network_ownership"):
                subject.cleanup(self.state, time.monotonic()+30)
            run.assert_not_called()

    def test_valid_cleanup_deletes_only_bound_ids_and_reads_final_state(self):
        subject.state_write(self.state, self.value)
        with patch.dict(os.environ, {}, clear=True), patch.object(subject, "inspect", side_effect=[self.container, self.network]), patch.object(subject, "run", return_value="") as run:
            result = subject.cleanup(self.state, time.monotonic()+30)
            self.assertEqual(result["status"], "cleaned")
            self.assertEqual([c.args[0] for c in run.call_args_list], [["docker", "rm", "-f", "--volumes", "b"*64], ["docker", "network", "rm", "c"*64]])
        self.assertTrue(subject.state_read(self.state)["cleaned"])
        self.assertFalse(subject.state_read(self.state)["ready"])

    def test_symlinks_refuse_both_state_and_export(self):
        target = self.directory / "owned"
        target.write_text("keep")
        self.state.symlink_to(target)
        with self.assertRaises(subject.Refused):
            subject.state_read(self.state)
        self.export.symlink_to(target)
        with self.assertRaises(subject.Refused):
            subject.private_path(self.export)
        self.assertEqual(target.read_text(), "keep")

    def test_mutable_wrong_architecture_and_mixed_digest_images_refuse(self):
        base = {"Os": "linux", "Architecture": "arm64", "Id": "sha256:"+"a"*64, "RepoDigests": [subject.IMAGE]}
        for changes in ({"Architecture":"amd64"}, {"Id":"postgres:17"}, {"RepoDigests":[subject.IMAGE, None]}, {"RepoDigests":[]}):
            with self.subTest(changes=changes), patch.dict(os.environ, {}, clear=True), patch.object(subject, "inspect", return_value={**base, **changes}), patch.object(subject,"run", return_value=json.dumps({"Os":"linux","Arch":"arm64"})) as run:
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 0))
                    port=probe.getsockname()[1]
                with self.assertRaisesRegex(subject.Refused,"image_unverified"):
                    subject.prepare(self.state,port,self.export,time.monotonic()+30)
                self.assertFalse(self.state.exists())
                self.assertFalse(self.export.exists())
                self.assertEqual(len(run.call_args_list),1)


if __name__ == "__main__":
    unittest.main()
