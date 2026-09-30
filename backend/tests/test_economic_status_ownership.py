"""Public web status must describe economic ingestion's actual owner."""

import importlib


def test_web_seeder_status_names_dedicated_economic_owner(client):
    response = client.get("/api/v1/system/seeder-status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "economic_indicators" in body["auto_seeder"]["external_job_owner"]["domains"]
    assert "economic_indicators" in body["note"]
    assert "dedicated seeding runner" in body["note"]
    assert "All data is fetched from live sources" not in body["note"]


def test_pipeline_health_reports_retired_web_path_without_import_success(client):
    response = client.get("/api/v1/system/pipeline-health")
    assert response.status_code == 200
    body = response.json()
    assert body["economic_ingestion"] == {
        "owner": "dedicated seeding runner",
        "domain": "economic_indicators",
        "web_refresh": "retired",
        "job_health": "not_checked_here",
    }
    assert "etl.knbs_parser" not in body["modules"]
    assert "extractors.government.knbs_extractor" not in body["modules"]
    assert not any("fall back to cached data" in a["message"] for a in body["alerts"])
    assert any(
        a["source"] == "economic" and "dedicated economic_indicators" in a["message"]
        for a in body["alerts"]
    )


def test_pipeline_health_keeps_ownership_when_web_status_unavailable(client, monkeypatch):
    seeder_module = importlib.import_module("services.auto_seeder")

    def fail_status():
        raise RuntimeError("synthetic web status failure")

    monkeypatch.setattr(seeder_module, "get_seeder_status", fail_status)
    response = client.get("/api/v1/system/pipeline-health")
    assert response.status_code == 200
    body = response.json()
    assert body["economic_ingestion"]["job_health"] == "not_checked_here"
    assert body["economic_ingestion"]["owner"] == "dedicated seeding runner"
    assert any(a["source"] == "auto_seeder" for a in body["alerts"])


def test_missing_web_etl_module_reports_unavailable_without_cached_fallback(
    client, monkeypatch
):
    real_import = importlib.import_module

    def without_web_etl(name, *args, **kwargs):
        if name == "etl.kenya_pipeline":
            raise ModuleNotFoundError("synthetic missing web ETL module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", without_web_etl)
    response = client.get("/api/v1/system/pipeline-health")
    assert response.status_code == 200
    body = response.json()
    assert body["modules"]["etl.kenya_pipeline"]["available"] is False
    messages = [alert["message"] for alert in body["alerts"]]
    assert any("Web ETL discovery is unavailable" in message for message in messages)
    assert not any("fall back to cached data" in message for message in messages)
    assert body["economic_ingestion"]["job_health"] == "not_checked_here"
