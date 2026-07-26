import asyncio
import socket
import sys
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from unittest.mock import MagicMock

import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.mcp_server import build_mcp_server
from agent.tools import ToolLayer
from simulation.runner import StateSnapshot, ZoneSnapshot

EXPECTED_TOOLS = {"get_current_state", "get_comfort_bounds", "get_recent_history", "propose_setpoint_change"}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def main() -> None:
    runner = MagicMock()
    tool_layer = ToolLayer(runner)
    tool_layer.ingest_snapshot(StateSnapshot(
        sim_time_hours=9.0,
        outdoor_air_temp_c=-5.0,
        facility_electricity_w=3000.0,
        zones={"Core_ZN": ZoneSnapshot(mean_air_temp_c=19.5, relative_humidity_pct=35.0,
                                        heating_setpoint_c=17.0, cooling_setpoint_c=28.0)},
    ))

    mcp = build_mcp_server(tool_layer)

    tools = list(mcp._tool_manager.list_tools())
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS, f"tool set mismatch: {names}"
    print(f"list_tools OK: {sorted(names)}")

    port = _free_port()
    app = mcp.streamable_http_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    
    server_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)

    try:
        
        
        url = f"http://127.0.0.1:{port}/"
        async with AsyncExitStack() as stack:
            read, write, _ = await stack.enter_async_context(streamablehttp_client(url))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            state = await session.call_tool("get_current_state", {})
            assert not state.isError
            assert state.structuredContent is not None, "expected structuredContent over the wire"
            assert state.structuredContent["sim_time_hours"] == 9.0
            assert state.structuredContent["zones"][0]["zone"] == "Core_ZN"
            print("get_current_state OK (wire):", state.structuredContent)

            history = await session.call_tool("get_recent_history", {"n": 5})
            assert not history.isError
            print("get_recent_history OK (wire):", history.structuredContent)

            proposal = await session.call_tool(
                "propose_setpoint_change",
                {"zone": "Core_ZN", "heating_setpoint_c": 21.0, "cooling_setpoint_c": 24.0},
            )
            assert not proposal.isError
            assert proposal.structuredContent is not None
            assert proposal.structuredContent["accepted"]
            print("propose_setpoint_change OK (wire):", proposal.structuredContent)
            print(f"runner.submit_setpoints called {runner.submit_setpoints.call_count} time(s)")
    finally:
        server.should_exit = True
        await server_task


if __name__ == "__main__":
    asyncio.run(main())
