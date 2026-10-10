"""Record versions without reading credentials or importing the web application."""
from importlib.metadata import version
import platform
import sys

print("executable=" + sys.executable)
print("python=" + platform.python_version())
print("platform=" + platform.platform())
for package in ("SQLAlchemy", "psycopg2-binary", "pytest", "alembic", "schedule", "requests", "pdfplumber"):
    print(package + "=" + version(package))
