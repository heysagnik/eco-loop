from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agent.tools import ComfortBounds, CurrentState, HistoryEntry, ProposeSetpointChange, ProposalResult, ToolLayer


def build_mcp_server(tool_layer: ToolLayer) -> FastMCP:
    mcp = FastMCP("eco-mcp", stateless_http=True, streamable_http_path="/")

    @mcp.tool()
    def get_current_state() -> CurrentState:
        
        return tool_layer.get_current_state()

    @mcp.tool()
    def get_comfort_bounds(zone: str) -> ComfortBounds:
        
        return tool_layer.get_comfort_bounds(zone)

    @mcp.tool()
    def get_recent_history(n: int) -> list[HistoryEntry]:
        
        return tool_layer.get_recent_history_entries(n)

    @mcp.tool()
    def propose_setpoint_change(zone: str, heating_setpoint_c: float, cooling_setpoint_c: float) -> ProposalResult:
        
        return tool_layer.propose_setpoint_change(ProposeSetpointChange(
            zone=zone, heating_setpoint_c=heating_setpoint_c, cooling_setpoint_c=cooling_setpoint_c,
        ))

    return mcp
