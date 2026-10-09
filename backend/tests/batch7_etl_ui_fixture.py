"""UI-only frozen-contract fixture. No product backend, DB or worker certification."""
import base64
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3162"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])
SOURCES = ("treasury", "cob", "oag", "knbs", "opendata", "cra")
GENERATION = "11111111-1111-4111-8111-111111111111"
ADMIN = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
state = {}

def stamp(value=None):
    return (value or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")

def command(i, status="completed", dry_run=True):
    created = datetime.now(timezone.utc) - timedelta(minutes=i + 1)
    return dict(id=str(UUID(int=i + 1)), source="oag", dry_run=dry_run,
                status=status, version=3 if status != "queued" else 1,
                created_at=stamp(created), updated_at=stamp(created + timedelta(seconds=2)),
                started_at=None if status == "queued" else stamp(created + timedelta(seconds=1)),
                finished_at=None if status in ("queued", "running") else stamp(created + timedelta(seconds=2)),
                job_id=i + 1 if status == "completed" else None,
                outcome={"completed": "completed", "failed": "failed", "interrupted": "execution_unverified"}.get(status))

def reset():
    state.clear()
    state.update(mode="ready", deny=0, role="admin", entries=[command(i) for i in range(45)],
                 intents={}, requests=[], next_status="queued")
reset()

def actor(request):
    try:
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not token.endswith(".inert-signature"):
            raise ValueError()
        uid = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "==="))["sub"]
        if uid not in (ADMIN, OTHER):
            raise ValueError()
        return uid
    except Exception:
        raise HTTPException(401, "Fixture authorization unavailable") from None

@app.middleware("http")
async def privacy(request, call_next):
    if request.url.path.startswith("/api/v1/admin/"):
        if state["deny"]:
            return JSONResponse({"detail": "Administrator access unavailable."}, state["deny"],
                                headers={"Cache-Control": "private, no-store", "Vary": "Authorization"})
        try:
            actor(request)
        except HTTPException:
            return JSONResponse({"detail": "Administrator access unavailable."}, 401)
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"
    return response

@app.post("/fixture/reset")
def fixture_reset():
    reset()
    return {"fixture": True}

@app.post("/fixture/config")
async def config(request: Request):
    values = await request.json()
    for key in ("mode", "deny", "role", "next_status"):
        if key in values:
            state[key] = values[key]
    return {"fixture": True}

@app.get("/fixture/requests")
def requests():
    return state["requests"]

@app.post("/fixture/command/{command_id}/{status}")
def change_command(command_id: str, status: str):
    row = next(row for row in state["entries"] if row["id"] == command_id)
    row.update(status=status, version=row["version"] + 1, updated_at=stamp(),
               started_at=row["started_at"] or stamp(),
               finished_at=stamp() if status in ("completed", "failed", "interrupted") else None,
               outcome={"completed": "completed", "failed": "failed", "interrupted": "execution_unverified"}.get(status),
               job_id=100 if status == "completed" else None)
    return {"fixture": True}

@app.get("/auth/v1/user")
def auth_user(request: Request):
    return {"id": actor(request), "aud": "authenticated", "role": "authenticated",
            "email": "etl-ui@example.invalid", "app_metadata": {}, "user_metadata": {},
            "created_at": "2026-01-01T00:00:00Z"}

@app.get("/rest/v1/profiles")
def profile(request: Request):
    data = dict(id=actor(request), email="etl-ui@example.invalid",
                display_name="Inert ETL UI Admin", roles=[state["role"]])
    return data if "object+json" in request.headers.get("accept", "") else [data]

@app.get("/api/v1/admin/etl/dispatch")
def dispatch():
    now = datetime.now(timezone.utc)
    available = state["mode"] not in ("unavailable",)
    result = dict(timestamp=stamp(now), evidence="worker_dispatch", available=available,
                  reason="Dedicated fixture worker ready." if available else "Dedicated worker dispatch is unavailable.",
                  generation=GENERATION if available else None,
                  worker=dict(status="ready" if available else "unavailable",
                              last_seen_at=stamp(now - timedelta(seconds=1)) if available else None,
                              expires_at=stamp(now + timedelta(seconds=30)) if available else None),
                  sources={s: dict(available=available and s == "oag", reason="Supported fixture audit runner." if s == "oag" and available else "No approved dispatch mapping.") for s in SOURCES})
    if state["mode"] == "stale":
        result["timestamp"] = stamp(now - timedelta(minutes=2))
        result["worker"]["last_seen_at"] = stamp(now - timedelta(minutes=2, seconds=1))
        result["worker"]["expires_at"] = stamp(now - timedelta(minutes=1))
    if state["mode"] == "malformed":
        result["available"] = "true"
    return result

@app.get("/api/v1/admin/etl/schedule")
def schedule():
    manual = dict(available=False, reason="Calendar execution remains unverified. No calendar job was accepted.")
    return dict(timestamp=stamp(), evidence="calendar_plan", manual_trigger=manual,
                summary=dict(sources_running_today=1, sources_skipping_today=5, total_sources=6,
                             skip_percentage=83.3, efficiency_vs_fixed_schedule="Calendar only",
                             sources_to_run=[dict(source="oag", reason="Calendar fixture")],
                             sources_not_running=[s for s in SOURCES if s != "oag"]),
                sources={s: dict(should_run=s == "oag", reason="Calendar fixture" if s == "oag" else "Deferred",
                                 next_run=None, next_reason="", current_period="default") for s in SOURCES})

@app.get("/api/v1/admin/etl/health")
def health():
    return dict(timestamp=stamp(), scheduler_status="unverified", worker_status="unverified",
                data_freshness="unverified", plan_status="available",
                manual_trigger=dict(available=False, reason="Calendar execution remains unverified. No calendar job was accepted."))

@app.post("/api/v1/admin/etl/trigger/{source}")
async def trigger(source: str, request: Request):
    uid = actor(request)
    body = await request.json()
    key = request.headers.get("idempotency-key", "")
    state["requests"].append(dict(actor=uid, key=key, source=source, body=body))
    if source not in SOURCES:
        raise HTTPException(404, "Unknown source.")
    if set(body) != {"dry_run", "dispatch_generation"} or type(body["dry_run"]) is not bool:
        raise HTTPException(422, "Invalid intent.")
    try:
        if str(UUID(key)) != key:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "Invalid intent key.") from None
    previous = state["intents"].get((uid, key))
    if previous:
        if previous["source"] != source or previous["dry_run"] != body["dry_run"]:
            raise HTTPException(409, "Changed intent.")
        return JSONResponse(dict(ok=True, accepted=True, replayed=True, audit_recorded=True, command=previous), 202)
    if state["mode"] != "ready":
        raise HTTPException(503, "Dedicated worker dispatch is unavailable.")
    if body["dispatch_generation"] != GENERATION:
        raise HTTPException(409, "Worker generation changed.")
    if source != "oag":
        raise HTTPException(503, "Unsupported source mapping.")
    row = command(100 + len(state["intents"]), state["next_status"], body["dry_run"])
    now = stamp()
    row.update(id=str(uuid4()), created_at=now, updated_at=now,
               started_at=None if row["status"] == "queued" else now,
               finished_at=now if row["status"] in ("completed", "failed", "interrupted") else None)
    state["entries"].insert(0, row)
    state["intents"][(uid, key)] = row
    return JSONResponse(dict(ok=True, accepted=True, replayed=False, audit_recorded=True, command=row), 202)

@app.get("/api/v1/admin/etl/commands")
def commands(page: int = 1, page_size: int = 20, source: str = "", status: str = ""):
    if not 1 <= page <= 10000 or not 1 <= page_size <= 50 or source and source not in SOURCES or status and status not in ("queued", "running", "completed", "failed", "interrupted"):
        raise HTTPException(422, "Invalid command query.")
    rows = sorted((r for r in state["entries"] if (not source or r["source"] == source) and (not status or r["status"] == status)), key=lambda r: (r["created_at"], r["id"]), reverse=True)
    return dict(entries=rows[(page - 1) * page_size:page * page_size], page=page, page_size=page_size,
                total=len(rows), has_more=page * page_size < len(rows))

@app.get("/api/v1/admin/etl/commands/{command_id}")
def detail(command_id: str):
    row = next((r for r in state["entries"] if r["id"] == command_id), None)
    if not row:
        raise HTTPException(404, "Command unavailable.")
    return row

if __name__ == "__main__":
    import uvicorn
    print("UI-only in-memory frozen contract fixture; no product worker/DB; loopback 8162", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8162)
