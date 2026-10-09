"""Fixed inert database port selection for the owned CI browser launcher."""
import os


def browser_database_port(default):
    enabled = os.environ.get("BATCH9_CI_BROWSER", "false")
    supplied = os.environ.get("BROWSER_FIXTURE_POSTGRES_PORT")
    if enabled == "false" and supplied is None:
        return default
    if enabled == "true" and supplied == "55494":
        return 55494
    raise RuntimeError("Browser CI requires its explicit owned loopback database port")
