FROM public.ecr.aws/docker/library/python:3.12.15-slim-trixie@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe

# Use the same dependency constraints as the backend. The census exercise
# mounts its source at runtime and needs neither app startup nor a database.
COPY requirements.txt requirements-dev.txt security-constraints.txt /tmp/requirements/
RUN cd /tmp/requirements \
    && sed -n -E '/^(fastapi|uvicorn|gunicorn|redis|httpx)(\[|[<=>])/p' requirements.txt > census.txt \
    && sed -n '/^pytest==/p' requirements-dev.txt >> census.txt \
    && python -m pip install --no-cache-dir -c security-constraints.txt -r census.txt
