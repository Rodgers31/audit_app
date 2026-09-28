"""Execute the ACTUAL seed.yml refresh steps against loopback test servers."""

import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse
import yaml

ROOT = Path(__file__).resolve().parents[2]
for key in ("API_BASE_URL", "REVALIDATE_URL"):
    if urlparse(os.environ[key]).hostname != "127.0.0.1":
        raise SystemExit("Browser refresh harness refuses non-loopback destinations")
doc = yaml.safe_load((ROOT / ".github/workflows/seed.yml").read_text())
for step in doc["jobs"]["revalidate"]["steps"]:
    if "run" not in step:
        continue
    script = step["run"].replace("${{ github.run_id }}", "browser-acceptance")
    if "${{" in script:
        raise SystemExit("Unexpected workflow expression in refresh step")
    print(step["name"], flush=True)
    subprocess.run(["bash", "-eo", "pipefail", "-c", script], cwd=ROOT, check=True)
