"""Owned filesystem and Docker-command controls; no real registry credentials."""
import base64
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "prepare_browser_registry_auth.py"


class RegistryAuthenticationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("owned_registry_auth", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory(prefix="browser-registry-control-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.state = self.base / self.module.STATE_NAME
        command_dir = self.base / "_runner_file_commands"
        command_dir.mkdir(mode=0o700)
        self.env_file = command_dir / "set_env_01234567-89ab-cdef-0123-456789abcdef"
        self.env_file.write_text("")
        self.token = "INERT_READ_TOKEN"
        self.username = "inert_reader"
        self.mode = "valid"
        self.calls = []
        self.environment = patch.dict(os.environ, {
            "RUNNER_TEMP": str(self.base), "GITHUB_ENV": str(self.env_file),
            "DOCKERHUB_USERNAME": self.username, "DOCKERHUB_TOKEN": self.token,
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.process = patch.object(self.module.subprocess, "run", side_effect=self.fake_docker)
        self.process.start()
        self.addCleanup(self.process.stop)

    def fake_docker(self, argv, *, input, capture_output, timeout, env):
        self.calls.append(argv)
        self.assertEqual(argv[:2], ["docker", "--config"])
        self.assertNotIn(self.token, argv)
        self.assertTrue(capture_output)
        self.assertEqual(timeout, 60)
        self.assertFalse(self.module.SECRET_NAMES & set(env))
        config = Path(argv[2])
        self.assertEqual(env["DOCKER_CONFIG"], str(config))
        if argv[3] == "login":
            self.assertEqual(argv[4:], ["--username", self.username, "--password-stdin", "docker.io"])
            self.assertEqual(input, (self.token + "\n").encode())
            initial = config / "config.json"
            self.assertEqual(json.loads(initial.read_text()), {
                "auths": {"https://index.docker.io/v1/": {"auth": ""}}
            })
            self.assertEqual(initial.stat().st_mode & 0o077, 0)
            if self.mode == "login-timeout":
                raise subprocess.TimeoutExpired(argv, timeout, output=self.token.encode())
            if self.mode in ("login-error-empty", "login-error-secret"):
                return subprocess.CompletedProcess(argv, 1, b"", b"" if self.mode.endswith("empty") else self.token.encode())
            path = config / "config.json"
            if self.mode == "absent-config":
                path.unlink()
            if self.mode != "absent-config":
                auth = base64.b64encode((self.username + ":" + self.token).encode()).decode()
                if self.mode == "wrong-config":
                    auth = base64.b64encode(b"other:other").decode()
                data = {"auths": {"https://index.docker.io/v1/": {"auth": auth}}}
                if self.mode == "credential-helper":
                    data["credsStore"] = "unowned-helper"
                path.write_text("not JSON" if self.mode == "malformed-config" else json.dumps(data))
                path.chmod(0o644 if self.mode == "public-config" else 0o600)
            return subprocess.CompletedProcess(argv, 0, b"Login Succeeded", b"")
        self.assertEqual(argv[3:], ["logout", "docker.io"])
        self.assertIsNone(input)
        if self.mode == "logout-timeout":
            raise subprocess.TimeoutExpired(argv, timeout, output=self.token.encode())
        return subprocess.CompletedProcess(argv, 1 if self.mode == "logout-error" else 0, b"", b"")

    def prepare(self):
        with redirect_stdout(io.StringIO()) as output:
            self.module.prepare(self.state)
        self.assertNotIn(self.token, output.getvalue())
        data = json.loads(self.state.read_text())
        self.assertNotIn(self.token, self.state.read_text())
        return Path(data["config"])

    def cleanup(self):
        with redirect_stdout(io.StringIO()) as output:
            self.module.cleanup(self.state)
        self.assertNotIn(self.token, output.getvalue())

    def test_actual_owned_config_is_exported_then_physically_removed(self):
        config = self.prepare()
        self.assertEqual(self.env_file.read_text(), "DOCKER_CONFIG=" + str(config) + "\n")
        self.assertEqual(json.loads(self.state.read_text())["status"], "AUTHENTICATED_CONFIG_VERIFIED")
        self.cleanup()
        self.assertFalse(config.exists())
        data = json.loads(self.state.read_text())
        self.assertEqual(data["status"], "OWNED_CONFIG_REMOVED")
        self.assertIs(data["physical_config_removed"], True)
        self.assertEqual(data["logout_exit_code"], 0)

    def test_missing_or_hostile_credentials_refuse_before_any_allocation(self):
        for name in ("DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN"):
            for value in ("", " whitespace", "line\nbreak"):
                with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}):
                    with self.assertRaises(RuntimeError):
                        self.module.prepare(self.state)
                    self.assertFalse(self.state.exists())
                    self.assertEqual(list(self.base.glob("browser-registry-*")), [])
        self.assertEqual(self.calls, [])
        with patch.object(self.module.os, "environ", {**dict(os.environ), "DOCKERHUB_TOKEN": "nul\0byte"}):
            with self.assertRaises(RuntimeError):
                self.module.prepare(self.state)
        self.assertEqual(self.calls, [])

    def test_nonzero_login_with_empty_stderr_is_refused(self):
        self.mode = "login-error-empty"
        with self.assertRaisesRegex(RuntimeError, "nonzero exit"):
            self.module.prepare(self.state)
        self.assertEqual(self.env_file.read_text(), "")
        self.assertEqual(json.loads(self.state.read_text())["login_exit_code"], 1)
        self.cleanup()

    def test_missing_malformed_wrong_nonprivate_or_helper_config_is_refused(self):
        for mode in ("absent-config", "malformed-config", "wrong-config", "public-config", "credential-helper"):
            with self.subTest(mode=mode):
                self.mode = mode
                with self.assertRaises((RuntimeError, FileNotFoundError, ValueError)):
                    self.module.prepare(self.state)
                self.assertEqual(self.env_file.read_text(), "")
                self.assertEqual(json.loads(self.state.read_text())["status"], "PREPARATION_FAILED")
                self.mode = "valid"
                self.cleanup()
                self.state.unlink()

    def test_login_timeout_preserves_failure_and_cleanup_removes_owned_config(self):
        self.mode = "login-timeout"
        with self.assertRaises(subprocess.TimeoutExpired):
            self.module.prepare(self.state)
        self.assertEqual(json.loads(self.state.read_text())["status"], "PREPARATION_FAILED")
        self.mode = "valid"
        self.cleanup()

    def test_logout_nonzero_and_timeout_are_not_green_but_credentials_are_removed(self):
        for mode in ("logout-error", "logout-timeout"):
            with self.subTest(mode=mode):
                self.mode = "valid"
                config = self.prepare()
                self.mode = mode
                with self.assertRaisesRegex(RuntimeError, "logout did not succeed"):
                    self.cleanup()
                self.assertFalse(config.exists())
                data = json.loads(self.state.read_text())
                self.assertEqual(data["status"], "REMOVED_WITH_LOGOUT_ERROR")
                self.assertIs(data["physical_config_removed"], True)
                self.state.unlink()
                self.env_file.write_text("")

    def test_peer_marker_or_unowned_state_path_refuses_cleanup(self):
        config = self.prepare()
        marker = config / "owner.json"
        original = marker.read_bytes()
        marker.write_text('{"nonce":"peer"}')
        with self.assertRaises(RuntimeError):
            self.cleanup()
        self.assertTrue(config.exists())
        marker.write_bytes(original)
        with self.assertRaises(RuntimeError):
            self.module.cleanup(self.base / "peer-state.json")
        self.cleanup()

    def test_credential_file_symlink_cannot_delete_peer_file(self):
        config = self.prepare()
        peer = self.base / "peer-credentials.json"
        peer.write_text("PEER_SENTINEL")
        credential = config / "config.json"
        original = credential.read_bytes()
        credential.unlink()
        credential.symlink_to(peer)
        with self.assertRaises((RuntimeError, OSError)):
            self.cleanup()
        self.assertEqual(peer.read_text(), "PEER_SENTINEL")
        credential.unlink()
        credential.write_bytes(original)
        credential.chmod(0o600)
        self.cleanup()

    def test_bool_owner_and_altered_source_binding_refuse(self):
        config = self.prepare()
        raw = self.state.read_bytes()
        for key, value in (("uid", True), ("generator_sha256", "0" * 64), ("config", str(self.base))):
            data = json.loads(raw)
            data[key] = value
            self.state.write_text(json.dumps(data))
            with self.assertRaises(RuntimeError):
                self.cleanup()
            self.assertTrue(config.exists())
        self.state.write_bytes(raw)
        self.cleanup()

    def test_cli_failure_prints_no_docker_output_or_token(self):
        self.mode = "login-error-secret"
        with patch.object(sys, "argv", [str(SCRIPT), "prepare", "--state", str(self.state)]), redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as refused:
                self.module.main()
        self.assertEqual(refused.exception.code, 1)
        self.assertNotIn(self.token, output.getvalue())
        self.assertNotIn(base64.b64encode((self.username + ":" + self.token).encode()).decode(), output.getvalue())
        self.mode = "valid"
        self.cleanup()

    def test_actual_cli_refuses_fifo_state_and_export_without_waiting(self):
        for mode in ("prepare", "cleanup"):
            with self.subTest(mode=mode):
                target = self.env_file if mode == "prepare" else self.state
                if target.exists():
                    target.unlink()
                os.mkfifo(target)
                command = [sys.executable, "-B", *(["-O"] if sys.flags.optimize else []),
                           str(SCRIPT), mode, "--state", str(self.state)]
                process = subprocess.Popen(command, env=dict(os.environ),
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    stdout, stderr = process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    self.fail("Nonregular registry control file caused a blocking open")
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=2)
                    target.unlink()
                self.assertEqual(process.returncode, 1, stderr.decode())
                self.assertNotIn(self.token.encode(), stdout + stderr)
                self.assertEqual(self.calls, [])
                self.env_file.write_text("")


if __name__ == "__main__":
    unittest.main()
