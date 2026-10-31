# Explicit maintenance fixture only. Production Dockerfiles remain unchanged.
# Context is repository root; use a clean, tracked public build snapshot locally.
ARG BASE_IMAGE=public.ecr.aws/docker/library/python:3.12.15-slim-trixie@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe
FROM ${BASE_IMAGE} AS bundle
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 ffmpeg postgresql-17 postgresql-contrib-17 libnss-wrapper \
    && rm -rf /var/lib/apt/lists/*
COPY tools/worker_host_fixture/requirements.txt /input/requirements.lock
COPY tools/worker_host_fixture/install_locked.py /input/install_locked.py
RUN python -I -B /input/install_locked.py /input/requirements.lock
COPY backend /input/backend
COPY tools/worker_rehearsal /input/rehearsal
COPY tools/worker_host_fixture /input/host
RUN python -I -B /input/host/build_root.py

FROM ${BASE_IMAGE}
USER root
COPY --from=bundle /fixture-root/ /
USER 10001:10001
RUN python -I -B -S -c "import ctypes,ssl,zlib;print('PUBLIC_STDLIB_LOADS')" \
    && /usr/lib/postgresql/17/bin/postgres --version \
    && /usr/bin/ffprobe -version >/dev/null
WORKDIR /
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8000
ENTRYPOINT ["python", "-I", "-B", "-S", "/host/entry.py"]
