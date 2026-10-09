"""Execute the preparation CLI against an owned Docker command boundary."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "prepare_postgres_test_images.py"
spec = importlib.util.spec_from_file_location("prepare_images", SCRIPT)
prepare_images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_images)
FIXTURE_REF = "public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675"
SERVICE_REF = "public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3"


class ImagePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="owned_image_preparation_")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.refs = prepare_images.required_images()
        self.image = {"Id": "sha256:" + "a" * 64, "Os": "linux", "Architecture": "amd64"}
        self.cached = {ref: [{**self.image, "RepoDigests": [ref]}] for ref in self.refs}
        # The real script runs subprocesses. This fixture implements only the
        # reviewed Docker commands, and records their exact order and arguments.
        docker = self.directory / "docker"
        docker.write_text(f"#!{sys.executable}\n" + '''import json, pathlib, sys
root=pathlib.Path(__file__).parent
config=json.loads((root/'fixture.json').read_text())
args=sys.argv[1:]
with (root/'calls.jsonl').open('a') as stream: stream.write(json.dumps(args)+'\\n')
phase='docker_server' if args[:1]==['version'] else 'alias_tag' if args[:2]==['image','tag'] else 'pull' if args[:1]==['pull'] else 'inspect_pulled' if (root/('pulled-'+args[-1].split(':')[-1])).exists() else 'inspect_cached'
failure=config.get('failure',{})
if failure.get('phase')==phase and failure.get('image',args[-1])==args[-1]:
 print(failure.get('stderr','owned command failure'),file=sys.stderr)
 sys.exit(failure.get('exit_code',1))
if args==['version','--format','{{json .Server}}']:
 print(json.dumps(config.get('server',{'Os':'linux','Arch':'amd64'})))
elif args[:2]==['image','inspect']:
 ref=args[2]
 pulled=(root/('pulled-'+ref.split(':')[-1])).exists()
 images=config.get('after',config['cached']) if pulled else config['cached']
 if ref=='postgres:17' and (root/'alias.json').exists():
  print(json.dumps(config.get('alias_readback',json.loads((root/'alias.json').read_text()))))
  sys.exit(0)
 if ref not in images:
  print('Error response from daemon: No such image: '+ref,file=sys.stderr)
  sys.exit(1)
 print(json.dumps(images[ref]))
elif args[:1]==['pull']:
 if config.get('pull_failed'): sys.exit(2)
 if len(args)!=4 or args[1]!='--platform': sys.exit(9)
 (root/('pulled-'+args[3].split(':')[-1])).touch()
 print('owned fixture pull completed')
elif args[:2]==['image','tag']:
 records=[records for records in config['cached'].values() if isinstance(records,list) and len(records)==1 and records[0].get('Id')==args[2]]
 if len(args)!=4 or args[3]!='postgres:17' or not records: sys.exit(9)
 (root/'alias.json').write_text(json.dumps(records[0]))
 print('owned fixture alias created')
else: sys.exit(9)
''')
        docker.chmod(0o700)

    def run_cli(self, *, arguments=(), **config):
        (self.directory / "calls.jsonl").write_text("")
        (self.directory / "fixture.json").write_text(json.dumps({"cached": self.cached, **config}))
        result = subprocess.run([sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True,
                                env={"PATH": str(self.directory) + os.pathsep + os.defpath,
                                     "PYTHONDONTWRITEBYTECODE": "1"}, timeout=10)
        calls = [json.loads(line) for line in (self.directory / "calls.jsonl").read_text().splitlines()]
        return result, calls

    def test_owned_fixture_uses_official_ecr_with_unchanged_digest(self):
        self.assertEqual(self.refs[0], FIXTURE_REF)
        self.assertEqual(self.refs[1], "public.ecr.aws/supabase/postgres@sha256:21ab971149317ea9cd12a8126fe4ebb34def08c8972956b0958cba0924409dab")

    def test_unknown_old_registry_and_mutable_fixture_refs_refuse(self):
        root = self.directory / "source"
        (root / "tools").mkdir(parents=True)
        for bad_ref in ("postgres@sha256:" + "a" * 64,
                        "public.ecr.aws/docker/library/postgres:17",
                        "public.ecr.aws/docker/library/postgres-lookalike@sha256:" + "a" * 64,
                        "registry.invalid/postgres@sha256:" + "a" * 64):
            with self.subTest(ref=bad_ref), patch.object(prepare_images, "ROOT", root):
                (root / "tools/bounded_pg_backup.py").write_text(
                    f"IMAGE = {bad_ref!r}\nSUPABASE_IMAGE = {self.refs[1]!r}\n")
                with self.assertRaisesRegex(prepare_images.Refusal, "invalid_fixture_image_pin"):
                    prepare_images.required_images()

    def test_service_alias_binds_verified_native_service_id_without_a_pull(self):
        service = {**self.image, "Id": "sha256:" + "b" * 64, "RepoDigests": [SERVICE_REF]}
        result, calls = self.run_cli(arguments=("--service-postgres-ref", SERVICE_REF),
                                     cached={**self.cached, SERVICE_REF: [service]})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["image", "tag", service["Id"], "postgres:17"], calls)
        alias_tag = calls.index(["image", "tag", service["Id"], "postgres:17"])
        self.assertEqual(calls[alias_tag + 1], ["image", "inspect", "postgres:17"])
        self.assertFalse(any(command[0] == "pull" for command in calls))

    def test_existing_identical_alias_is_verified_without_writing(self):
        service = {**self.image, "RepoDigests": [SERVICE_REF]}
        result, calls = self.run_cli(arguments=("--service-postgres-ref", SERVICE_REF),
                                     cached={**self.cached, SERVICE_REF: [service], "postgres:17": [service]})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["image", "inspect", "postgres:17"], calls)
        self.assertFalse(any(command[:2] == ["image", "tag"] for command in calls))

    def test_existing_mismatched_alias_is_never_overwritten(self):
        service = {**self.image, "RepoDigests": [SERVICE_REF]}
        result, calls = self.run_cli(arguments=("--service-postgres-ref", SERVICE_REF),
            cached={**self.cached, SERVICE_REF: [service], "postgres:17": [{**service, "Id": "sha256:" + "c" * 64}]})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["reason"], "existing_service_alias_mismatch")
        self.assertFalse(any(command[:2] == ["image", "tag"] or command[0] == "pull" for command in calls))

    def test_native_arm_service_alias_retains_native_platform(self):
        cached = {ref: [{**self.image, "Architecture": "arm64", "RepoDigests": [ref]}]
                  for ref in (*self.refs, SERVICE_REF)}
        result, calls = self.run_cli(arguments=("--service-postgres-ref", SERVICE_REF),
                                     cached=cached, server={"Os": "linux", "Arch": "arm64"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["image", "tag", self.image["Id"], "postgres:17"], calls)
        self.assertFalse(any(command[0] == "pull" for command in calls))

    def test_missing_service_cache_refuses_without_download_or_alias_write(self):
        result, calls = self.run_cli(arguments=("--service-postgres-ref", SERVICE_REF))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(command[:2] == ["image", "tag"] or command[0] == "pull" for command in calls))

    def test_wrong_service_identity_platform_or_metadata_refuses_before_alias(self):
        for change in ({"RepoDigests": [FIXTURE_REF]}, {"Architecture": "arm64"},
                       {"Os": "windows"}, {"Id": "tag"}):
            with self.subTest(change=change):
                result, calls = self.run_cli(arguments=("--service-postgres-ref", SERVICE_REF),
                    cached={**self.cached, SERVICE_REF: [{**self.image, "RepoDigests": [SERVICE_REF], **change}]})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(command[0] == "pull" or "postgres:17" in command for command in calls))

    def test_wrong_alias_readback_refuses(self):
        result, _ = self.run_cli(arguments=("--service-postgres-ref", SERVICE_REF),
            cached={**self.cached, SERVICE_REF: [{**self.image, "RepoDigests": [SERVICE_REF]}]},
            alias_readback=[{**self.image, "RepoDigests": [SERVICE_REF], "Id": "sha256:" + "c" * 64}])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["reason"], "service_alias_identity_mismatch")

    def test_mixed_malformed_fixture_repo_digests_cannot_certify_preparation(self):
        for extra in ({"not": "a digest"}, None, "", "postgres:17", "bad@sha256:short", "bad@@sha256:" + "a" * 64):
            with self.subTest(extra=extra):
                result, _ = self.run_cli(cached={self.refs[0]: [{**self.image, "RepoDigests": [self.refs[0], extra]}]})
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Prepared", result.stdout)

    def test_mixed_malformed_service_repo_digests_refuse_before_alias_operations(self):
        result, calls = self.run_cli(arguments=("--service-postgres-ref", SERVICE_REF),
            cached={**self.cached, SERVICE_REF: [{**self.image, "RepoDigests": [SERVICE_REF, {"not": "a digest"}]}]})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(command[0] == "pull" or "postgres:17" in command for command in calls))

    def test_valid_canonical_metadata_aliases_do_not_change_the_explicit_transport(self):
        cached = {ref: [{**self.image, "RepoDigests": [ref, "postgres@" + ref.split("@")[1]]}]
                  for ref in self.refs}
        cached[SERVICE_REF] = [{**self.image, "Id": "sha256:" + "b" * 64,
                               "RepoDigests": [SERVICE_REF, "postgres@" + SERVICE_REF.split("@")[1]]}]
        result, calls = self.run_cli(arguments=("--service-postgres-ref", SERVICE_REF), cached=cached)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(command[0] == "pull" for command in calls))
        self.assertIn(["image", "tag", "sha256:" + "b" * 64, "postgres:17"], calls)

    def test_unsafe_service_argument_is_redacted_before_any_docker_command(self):
        for arguments in (("--service-postgres-ref", "https://user:do-not-print@registry.invalid/postgres"),
                          ("--service-postgres-ref", "postgres:17"),
                          ("--service-postgres-ref", FIXTURE_REF), ("--unknown", "do-not-print")):
            with self.subTest(arguments=arguments):
                result, calls = self.run_cli(arguments=arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [])
                self.assertNotIn("do-not-print", result.stdout + result.stderr)
                self.assertIsNone(json.loads(result.stderr)["image"])

    def test_direct_unsafe_service_argument_refuses_before_subprocess(self):
        for value in ("https://user:do-not-print@registry.invalid/postgres", "", True, False, [], {}, float("nan")):
            with self.subTest(value=value), patch.object(prepare_images.subprocess, "run") as run:
                with self.assertRaises(prepare_images.Refusal) as refusal:
                    prepare_images.prepare(service_postgres_ref=value)
                self.assertIsNone(refusal.exception.receipt["image"])
                self.assertNotIn("do-not-print", json.dumps(refusal.exception.receipt))
                run.assert_not_called()

    def test_cached_exact_native_pins_need_no_pull(self):
        result, calls = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["version", "--format", "{{json .Server}}"],
                                 *[["image", "inspect", ref] for ref in self.refs]])

    def test_cold_cache_pulls_both_exact_pins_and_readbacks_before_success(self):
        result, calls = self.run_cli(cached={}, after=self.cached)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[1:], [command for ref in self.refs for command in
                                    (["image", "inspect", ref], ["pull", "--platform", "linux/amd64", ref],
                                     ["image", "inspect", ref])])

    def test_native_arm_cache_is_supported(self):
        cached = {ref: [{**self.image, "Architecture": "arm64", "RepoDigests": [ref]}] for ref in self.refs}
        result, _ = self.run_cli(cached=cached, server={"Os": "linux", "Arch": "arm64"})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrong_pin_platform_and_malformed_metadata_refuse(self):
        for changed in ([{**self.image, "RepoDigests": ["postgres:17"]}],
                        [{**self.image, "RepoDigests": [self.refs[0]], "Architecture": "arm64"}],
                        [{**self.image, "RepoDigests": [self.refs[0]], "Id": "tag"}],
                        None, [], [self.image, self.image]):
            with self.subTest(changed=changed):
                result, _ = self.run_cli(cached={self.refs[0]: changed})
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Prepared", result.stdout)

    def test_pull_failure_and_unbound_post_pull_image_refuse(self):
        for config in ({"pull_failed": True}, {"after": {}},
                       {"after": {self.refs[0]: [{**self.image, "RepoDigests": []}]}}):
            with self.subTest(config=config):
                result, _ = self.run_cli(cached={}, **config)
                self.assertNotEqual(result.returncode, 0)

    def test_non_linux_or_unknown_platform_refuses_before_image_commands(self):
        result, calls = self.run_cli(server={"Os": "windows", "Arch": "amd64"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)

    def test_malformed_architecture_has_structured_refusal_before_alias_or_pull(self):
        for architecture in ([], {}, None, True, 7):
            with self.subTest(architecture=architecture):
                result, calls = self.run_cli(arguments=("--service-postgres-ref", SERVICE_REF),
                                            server={"Os": "linux", "Arch": architecture})
                self.assertNotEqual(result.returncode, 0)
                receipt = json.loads(result.stderr)
                self.assertEqual(receipt["reason"], "unsupported_native_docker_platform")
                self.assertEqual(receipt["phase"], "docker_server")
                self.assertIsNone(receipt["image"])
                self.assertEqual(calls, [["version", "--format", "{{json .Server}}"]])

    def test_cached_inspect_daemon_failure_is_not_treated_as_missing_image(self):
        secret = 'do-not-print-this-token'
        result, calls = self.run_cli(failure={'phase': 'inspect_cached', 'stderr': 'Cannot connect to the Docker daemon; ' + secret})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(command[0] == 'pull' for command in calls))
        receipt = json.loads(result.stderr)
        self.assertEqual(receipt['phase'], 'inspect_cached')
        self.assertEqual(receipt['image'], self.refs[0])
        self.assertEqual(receipt['platform'], 'linux/amd64')
        self.assertEqual(receipt['exit_code'], 1)
        self.assertEqual(receipt['diagnostic_category'], 'docker_daemon_unavailable')
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_pull_failure_records_second_exact_pin_and_safe_bounded_category(self):
        secret = 'do-not-print-this-token'
        result, calls = self.run_cli(cached={self.refs[0]: self.cached[self.refs[0]]},
            failure={'phase': 'pull', 'image': self.refs[1], 'exit_code': 42,
                     'stderr': 'toomanyrequests: ' + secret + 'x' * 20000})
        self.assertNotEqual(result.returncode, 0)
        receipt = json.loads(result.stderr)
        self.assertEqual(receipt['phase'], 'pull')
        self.assertEqual(receipt['image'], self.refs[1])
        self.assertEqual(receipt['platform'], 'linux/amd64')
        self.assertEqual(receipt['exit_code'], 42)
        self.assertEqual(receipt['diagnostic_category'], 'registry_rate_limited')
        self.assertTrue(receipt['diagnostic_sample_truncated'])
        self.assertLess(len(result.stderr), 1000)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(sum(command[0] == 'pull' for command in calls), 1)

    def test_unknown_failure_text_is_redacted_without_guessing_cause(self):
        result, _ = self.run_cli(failure={'phase': 'docker_server', 'stderr': 'token=arbitrary-secret'})
        receipt = json.loads(result.stderr)
        self.assertEqual(receipt['phase'], 'docker_server')
        self.assertIsNone(receipt['image'])
        self.assertIsNone(receipt['platform'])
        self.assertEqual(receipt['diagnostic_category'], 'unclassified')
        self.assertNotIn('arbitrary-secret', result.stderr)

    def test_timeout_is_bounded_and_not_retried(self):
        with patch.object(prepare_images.subprocess, "run", side_effect=subprocess.TimeoutExpired("docker", 15)) as run:
            with self.assertRaisesRegex(prepare_images.Refusal, "timed_out"):
                prepare_images.prepare()
            self.assertEqual(run.call_count, 1)
            self.assertLessEqual(run.call_args.kwargs["timeout"], 15)
        with patch.object(prepare_images.time, "monotonic", side_effect=[0, 241]), patch.object(prepare_images.subprocess, "run") as run:
            with self.assertRaisesRegex(prepare_images.Refusal, "deadline"):
                prepare_images.prepare()
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
