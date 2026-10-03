"""Two separate interpreters adopt one marker without restarting either."""

import hashlib
import hmac
import json
import multiprocessing
import os
import time

from test_cache_generation_status import SECRET


def worker(pipe, marker, value_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pathlib import Path
    from cache import invalidation
    from routers.cache_invalidation import router

    os.environ["CACHE_GENERATION_FILE"] = marker
    os.environ["REVALIDATE_SECRET"] = SECRET
    os.environ["RENDER_GIT_COMMIT"] = "a" * 40
    invalidation._local_caches = {}
    invalidation._redis_instances = lambda: []
    invalidation._seen = None
    invalidation._seen_initialised = False
    cached = {}
    def clear():
        count = len(cached)
        cached.clear()
        return count
    invalidation.register_local_cache("fixture", clear)
    app = FastAPI()
    app.include_router(router)
    @app.middleware("http")
    async def sync(request, call_next):
        invalidation.sync_generation()
        return await call_next(request)
    @app.get("/fixture")
    def fixture():
        if "value" not in cached:
            cached["value"] = Path(value_path).read_text()
        return {"value": cached["value"], "pid": os.getpid()}
    with TestClient(app) as client:
        pipe.send(os.getpid())
        while True:
            path = pipe.recv()
            if path == "stop":
                return
            if path == "/fixture":
                response = client.get(path)
            else:
                raw = json.dumps({"ts": time.time()}).encode()
                response = client.post(path, content=raw, headers={
                    "x-revalidate-signature": hmac.new(
                        SECRET.encode(), raw, hashlib.sha256
                    ).hexdigest()
                })
            pipe.send((response.status_code, response.json()))


def test_real_processes_acknowledge_and_clear_shared_generation(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    value = tmp_path / "value"
    value.write_text("100")
    children, pipes, pids = [], [], []
    def request(index, path):
        pipes[index].send(path)
        assert pipes[index].poll(10), "worker did not answer"
        status, body = pipes[index].recv()
        assert status == 200, body
        return body
    try:
        for _ in range(2):
            parent, child = ctx.Pipe()
            process = ctx.Process(target=worker, args=(child, str(tmp_path / "generation"), str(value)))
            process.start()
            children.append(process)
            pipes.append(parent)
            assert parent.poll(10), "worker did not start"
            pids.append(parent.recv())
        assert len(set(pids)) == 2
        for index in range(2):
            assert request(index, "/fixture")["value"] == "100"
        value.write_text("125")
        for index in range(2):
            assert request(index, "/fixture")["value"] == "100", "baseline cache must be warm"
        ack = request(0, "/api/v1/system/cache/invalidate")
        for index in range(2):
            status = request(index, "/api/v1/system/cache/status")
            assert status["pid"] == pids[index]
            assert status["synchronised"] is True
            assert status["observed_identity"] == status["adopted_identity"] == ack["marker_identity"]
            assert request(index, "/fixture") == {"value": "125", "pid": pids[index]}
    finally:
        for pipe, process in zip(pipes, children):
            if process.is_alive():
                pipe.send("stop")
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join(5)
            pipe.close()
        assert all(not process.is_alive() for process in children)
