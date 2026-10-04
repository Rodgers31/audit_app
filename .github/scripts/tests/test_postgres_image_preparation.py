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
if args==['version','--format','{{json .Server}}']:
 print(json.dumps(config.get('server',{'Os':'linux','Arch':'amd64'})))
elif args[:2]==['image','inspect']:
 ref=args[2]
 pulled=(root/('pulled-'+ref.split(':')[-1])).exists()
 images=config.get('after',config['cached']) if pulled else config['cached']
 if ref not in images: sys.exit(1)
 print(json.dumps(images[ref]))
elif args[:1]==['pull']:
 if config.get('pull_failed'): sys.exit(2)
 if len(args)!=4 or args[1]!='--platform': sys.exit(9)
 (root/('pulled-'+args[3].split(':')[-1])).touch()
 print('owned fixture pull completed')
else: sys.exit(9)
''')
        docker.chmod(0o700)

    def run_cli(self, **config):
        (self.directory / "fixture.json").write_text(json.dumps({"cached": self.cached, **config}))
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                                env={"PATH": str(self.directory) + os.pathsep + os.defpath,
                                     "PYTHONDONTWRITEBYTECODE": "1"}, timeout=10)
        calls = [json.loads(line) for line in (self.directory / "calls.jsonl").read_text().splitlines()]
        return result, calls

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
