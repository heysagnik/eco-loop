import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent.mcp_server import build_mcp_server
from api import db
from api.control_service import ControlLoopService

service = ControlLoopService()
mcp_server = build_mcp_server(service.tool_layer)
mcp_app = mcp_server.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    service.set_event_loop(asyncio.get_running_loop())
    service.start()
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="Eco-Loop API", lifespan=lifespan)
app.mount("/mcp", mcp_app)


@app.get("/state/updates")
async def state_updates(since: int = 0) -> dict:
    version = await service.wait_for_change(since)
    return {
        "version": version,
        "mode": service.mode,
        "summary": db.fetch_summary(service.db_conn, service.run_id),
        "history": list(reversed(db.fetch_recent(service.db_conn, service.run_id, 100))),
        "live_turn": service.get_live_turn(),
    }


@app.get("/state/history")
def state_history(limit: int = 100) -> list[dict]:
    return db.fetch_recent(service.db_conn, service.run_id, limit)


@app.get("/state/summary")
def state_summary() -> dict:
    return db.fetch_summary(service.db_conn, service.run_id)


@app.get("/control/mode")
def control_mode() -> dict:
    return {"mode": service.mode}


@app.post("/control/revert-to-baseline")
def revert_to_baseline() -> dict:
    service.revert_to_baseline()
    return {"mode": service.mode}


@app.post("/control/resume-ai")
def resume_ai() -> dict:
    service.resume_ai()
    return {"mode": service.mode}


@app.post("/benchmark/start")
def benchmark_start() -> dict:
    started = service.begin_run()
    return {"status": "started" if started else "already_running", "run_id": service.run_id}


@app.post("/benchmark/reset")
def benchmark_reset() -> dict:
    service.reset_run()
    return {"status": "reset", "run_id": service.run_id}
