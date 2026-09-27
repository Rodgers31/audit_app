"""Exercise legacy discovery using a production-shaped import boundary.

The backend Docker build copies backend/, whose etl package has no pipeline.
These tests execute the real handlers with that package copied into an isolated
import directory; they do not infer availability from source-text assertions.
The available control supplies a tiny real module instead of reaching publishers.
"""

import importlib
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def image_imports(monkeypatch, tmp_path):
    import main

    backend = Path(main.__file__).resolve().parent
    image = tmp_path / "image"
    image.mkdir()
    shutil.copytree(backend / "etl", image / "etl")
    # Retain standard library/site-packages but prevent the checkout's root ETL
    # package (or an already imported copy) from supplying files absent in Docker.
    excluded = {backend, backend.parent}
    monkeypatch.setattr(
        sys,
        "path",
        [str(image)]
        + [p for p in sys.path if p and Path(p).resolve() not in excluded],
    )
    for name in list(sys.modules):
        if name == "etl" or name.startswith("etl."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(main, "__file__", str(image / "main.py"))
    monkeypatch.setenv("PARLIAMENT_PIPELINE_ENABLED", "0")
    importlib.invalidate_caches()
    yield main, image
    # Imports performed by the test are not tracked by monkeypatch; remove them
    # so the fixture's restored original modules/path cannot be shadowed later.
    for name in list(sys.modules):
        if name == "etl" or name.startswith("etl."):
            del sys.modules[name]


def _available_pipeline(image):
    (image / "etl" / "kenya_pipeline.py").write_text(
        "class KenyaDataPipeline:\n"
        "    def discover_budget_documents(self, source):\n"
        "        return [{'title': source + ' report', "
        "'url': 'https://example.invalid/report.pdf'}]\n"
    )
    importlib.invalidate_caches()


def _scheduler(monkeypatch, main):
    scheduler = Mock()
    original = main.importlib.import_module

    def import_module(name, *args, **kwargs):
        if name == "apscheduler.schedulers.asyncio":
            return SimpleNamespace(AsyncIOScheduler=lambda: scheduler)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(main.importlib, "import_module", import_module)
    return scheduler


@pytest.mark.asyncio
async def test_backend_image_skips_unavailable_discovery_but_keeps_digest(
    image_imports, monkeypatch
):
    main, _ = image_imports
    scheduler = _scheduler(monkeypatch, main)
    await main._setup_etl_scheduler()
    ids = {call.kwargs["id"] for call in scheduler.add_job.call_args_list}
    assert "etl_weekly_digest" in ids
    assert not ids.intersection(
        {"etl_oag_light", "etl_cob_light", "etl_treasury_light"}
    )


@pytest.mark.asyncio
async def test_backend_image_direct_discovery_reports_unavailable(image_imports):
    main, _ = image_imports
    with pytest.raises(RuntimeError, match="(?i)discovery.*unavailable"):
        await main._discover("oag")


@pytest.mark.asyncio
async def test_backend_image_job_refuses_before_creating_artifacts(
    image_imports, monkeypatch
):
    main, _ = image_imports
    artifacts = Mock(side_effect=AssertionError("unavailable job created artifacts"))
    monkeypatch.setattr(main, "_artifact_dir", artifacts)
    with pytest.raises(RuntimeError, match="(?i)discovery.*unavailable"):
        await main._run_job("oag", "light")
    artifacts.assert_not_called()


@pytest.mark.asyncio
async def test_backend_image_admin_rejects_unavailable_without_enqueuing(
    image_imports, monkeypatch
):
    from fastapi import HTTPException

    main, _ = image_imports
    before = dict(main._etl_jobs)
    scheduled = []

    def capture_task(coroutine):
        scheduled.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(main.asyncio, "create_task", capture_task)
    try:
        with pytest.raises(HTTPException) as exc:
            await main.run_etl_job(source="oag", job="light", _actor=object())
        assert exc.value.status_code == 503
        assert "unavailable" in str(exc.value.detail).lower()
        assert main._etl_jobs == before
        assert scheduled == []
    finally:
        main._etl_jobs.clear()
        main._etl_jobs.update(before)


@pytest.mark.asyncio
async def test_packaged_pipeline_keeps_all_light_schedules(image_imports, monkeypatch):
    main, image = image_imports
    _available_pipeline(image)
    scheduler = _scheduler(monkeypatch, main)
    await main._setup_etl_scheduler()
    args = [call.kwargs.get("args") for call in scheduler.add_job.call_args_list]
    assert all([source, "light"] in args for source in ("oag", "cob", "treasury"))
    assert not any(arg and arg[-1] == "deep" for arg in args)


@pytest.mark.asyncio
async def test_packaged_discovery_executes_and_admin_job_completes(
    image_imports, monkeypatch, tmp_path
):
    main, image = image_imports
    _available_pipeline(image)
    assert await main._discover("oag") == [
        {"title": "oag report", "url": "https://example.invalid/report.pdf"}
    ]
    artifacts = tmp_path / "artifacts"
    known = tmp_path / "known"
    artifacts.mkdir()
    known.mkdir()
    monkeypatch.setattr(main, "_artifact_dir", lambda: str(artifacts))
    monkeypatch.setattr(main, "_known_dir", lambda: str(known))
    monkeypatch.setattr(main, "_artifact_root", lambda: str(tmp_path))
    email = Mock()
    monkeypatch.setattr(main, "send_email", email)
    scheduled = []
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: scheduled.append(coro))
    before = dict(main._etl_jobs)
    try:
        response = await main.run_etl_job(source="oag", job="light", _actor=object())
        assert response["status"] == "started"
        assert len(scheduled) == 1
        await scheduled.pop()
        job = main._etl_jobs[response["job_id"]]
        assert job["status"] == "completed"
        assert job["result"]["discovered"] == 1
        assert job["result"]["new"] == 1
        assert job["result"]["processed"] == 0
        assert (artifacts / "oag_light_summary.json").is_file()
        email.assert_called_once()
    finally:
        for coroutine in scheduled:
            coroutine.close()
        main._etl_jobs.clear()
        main._etl_jobs.update(before)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [
        "# KenyaDataPipeline is absent\n",
        "KenyaDataPipeline = None\n",
        "class KenyaDataPipeline:\n    pass\n",
        "class KenyaDataPipeline:\n    discover_budget_documents = []\n",
        "import unavailable_discovery_dependency_for_test\n",
        "raise ImportError('transitive dependency has no required symbol')\n",
    ],
    ids=[
        "missing-class", "noncallable-class", "missing-method",
        "noncallable-method", "missing-transitive-module", "transitive-import-error",
    ],
)
async def test_malformed_pipeline_cannot_schedule_or_report_started(
    image_imports, monkeypatch, source
):
    from fastapi import HTTPException

    main, image = image_imports
    (image / "etl" / "kenya_pipeline.py").write_text(source)
    importlib.invalidate_caches()
    scheduler = _scheduler(monkeypatch, main)
    before = dict(main._etl_jobs)
    artifacts = Mock(side_effect=AssertionError("unavailable job created artifacts"))
    monkeypatch.setattr(main, "_artifact_dir", artifacts)

    with pytest.raises(RuntimeError, match="(?i)discovery.*unavailable"):
        await main._discover("oag")
    with pytest.raises(RuntimeError, match="(?i)discovery.*unavailable"):
        await main._run_job("oag", "light")
    with pytest.raises(HTTPException) as exc:
        await main.run_etl_job(source="oag", job="light", _actor=object())
    assert exc.value.status_code == 503
    assert main._etl_jobs == before
    artifacts.assert_not_called()

    await main._setup_etl_scheduler()
    ids = {call.kwargs["id"] for call in scheduler.add_job.call_args_list}
    assert ids == {"etl_weekly_digest"}


@pytest.mark.asyncio
async def test_available_capability_preserves_existing_import_path(image_imports):
    main, image = image_imports
    _available_pipeline(image)
    original_path = list(sys.path)
    assert main._discovery_pipeline_class().__module__ == "etl.kenya_pipeline"
    assert len(await main._discover("treasury")) == 1
    assert sys.path == original_path
