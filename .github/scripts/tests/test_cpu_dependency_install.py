"""Keep CPU-only CI installs on the packaged ONNX runtime with scripts enabled."""

from copy import deepcopy
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
CPU_JOBS = ("test-frontend", "test-browser", "test-browser-legacy")
INSTALL_FLAG = "ONNXRUNTIME_NODE_INSTALL"


def validate_cpu_installs(workflow):
    if INSTALL_FLAG in workflow.get("env", {}):
        raise ValueError("The optional ONNX downloader flag must be install-step scoped")
    for name, job in workflow["jobs"].items():
        if INSTALL_FLAG in job.get("env", {}):
            raise ValueError("The optional ONNX downloader flag must be install-step scoped")
        installs = [step for step in job["steps"]
                    if "npm ci" in step.get("run", "")]
        if name in CPU_JOBS and len(installs) != 1:
            raise ValueError("Each CPU test job requires its locked npm install")
        for step in job["steps"]:
            flag = step.get("env", {}).get(INSTALL_FLAG)
            if step in installs and name in CPU_JOBS:
                if flag != "skip":
                    raise ValueError("CPU installs must skip only optional ONNX binaries")
                if "npm ci" not in [line.strip() for line in step["run"].splitlines()]:
                    raise ValueError("The locked install must retain its lifecycle scripts")
                if "ignore-scripts" in step["run"] or step.get("env", {}).get("npm_config_ignore_scripts"):
                    raise ValueError("Dependency lifecycle scripts must remain enabled")
                if step.get("continue-on-error"):
                    raise ValueError("Dependency installation remains a required gate")
            elif flag is not None:
                raise ValueError("The optional ONNX downloader flag escaped CPU installs")


class CpuDependencyInstallTests(unittest.TestCase):
    def workflows(self):
        return [(name, yaml.safe_load((ROOT / ".github/workflows" / name).read_text()))
                for name in ("ci.yml", "verification.yml")]

    def test_canonical_and_manual_cpu_installs_keep_lifecycle_scripts(self):
        for filename, workflow in self.workflows():
            with self.subTest(workflow=filename):
                validate_cpu_installs(workflow)

    def test_every_install_requires_the_optional_download_flag(self):
        for filename, workflow in self.workflows():
            for name in CPU_JOBS:
                changed = deepcopy(workflow)
                install = next(step for step in changed["jobs"][name]["steps"]
                               if "npm ci" in step.get("run", ""))
                install.get("env", {}).pop(INSTALL_FLAG, None)
                with self.subTest(workflow=filename, job=name):
                    with self.assertRaisesRegex(ValueError, "skip only optional ONNX"):
                        validate_cpu_installs(changed)

    def test_global_flags_script_skips_and_optional_install_gates_are_rejected(self):
        for filename, workflow in self.workflows():
            for mutation in ("global", "job", "ignore-scripts", "ignore-scripts-env", "optional", "next-step"):
                changed = deepcopy(workflow)
                job = changed["jobs"]["test-frontend"]
                install = next(step for step in job["steps"] if "npm ci" in step.get("run", ""))
                if mutation == "global":
                    changed.setdefault("env", {})[INSTALL_FLAG] = "skip"
                elif mutation == "job":
                    job.setdefault("env", {})[INSTALL_FLAG] = "skip"
                elif mutation == "ignore-scripts":
                    install["run"] = install["run"].replace("npm ci", "npm ci --ignore-scripts")
                elif mutation == "ignore-scripts-env":
                    install.setdefault("env", {})["npm_config_ignore_scripts"] = "true"
                elif mutation == "optional":
                    install["continue-on-error"] = True
                else:
                    job["steps"][job["steps"].index(install) + 1].setdefault("env", {})[INSTALL_FLAG] = "skip"
                with self.subTest(workflow=filename, mutation=mutation):
                    with self.assertRaises(ValueError):
                        validate_cpu_installs(changed)


if __name__ == "__main__":
    unittest.main()
