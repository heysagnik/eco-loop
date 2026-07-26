
from __future__ import annotations

import asyncio
import json
import random
import threading
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

CONNECT_RETRY_INTERVAL_SECONDS = 1.0
CONNECT_MAX_WAIT_SECONDS = 30.0
CONNECT_RETRY_BACKOFF_CAP_SECONDS = 5.0
CALL_TIMEOUT_SECONDS = 30.0


class MCPToolExecutor:
    

    def __init__(self, mcp_url: str) -> None:
        self._mcp_url = mcp_url
        self._loop = asyncio.new_event_loop()
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    async def _connect_with_retry(self) -> None:
        waited = 0.0
        delay = CONNECT_RETRY_INTERVAL_SECONDS
        while True:
            try:
                await self._connect()
                return
            except Exception:
                if waited >= CONNECT_MAX_WAIT_SECONDS:
                    raise
                sleep_for = delay + random.uniform(0, delay * 0.25)
                await asyncio.sleep(sleep_for)
                waited += sleep_for
                delay = min(delay * 2, CONNECT_RETRY_BACKOFF_CAP_SECONDS)

    async def _connect(self) -> None:
        stack = AsyncExitStack()
        try:
            read, write, _ = await stack.enter_async_context(streamablehttp_client(self._mcp_url))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        self._session = session

    async def _ensure_connected(self) -> None:
        if self._session is None:
            await self._connect_with_retry()

    def __call__(self, name: str, arguments: dict) -> dict:
        try:
            return asyncio.run_coroutine_threadsafe(self._call(name, arguments), self._loop).result(
                timeout=CALL_TIMEOUT_SECONDS
            )
        except FuturesTimeoutError:
            return {"error": f"MCP call to '{name}' timed out after {CALL_TIMEOUT_SECONDS}s"}

    async def _call(self, name: str, arguments: dict) -> dict:
        await self._ensure_connected()
        assert self._session is not None
        result = await self._session.call_tool(name, arguments)
        if result.isError:
            text = "; ".join(getattr(c, "text", str(c)) for c in result.content)
            return {"error": text}

        if getattr(result, "structuredContent", None) is not None:
            return result.structuredContent

        for item in result.content or []:
            text_val = getattr(item, "text", None)
            if text_val:
                try:
                    parsed = json.loads(text_val)
                    if isinstance(parsed, dict):
                        return parsed
                    return {"result": parsed}
                except (json.JSONDecodeError, TypeError):
                    return {"result": text_val}

        return {"error": f"tool '{name}' returned no structured content or text output"}

    def close(self) -> None:
        if self._stack is not None:
            asyncio.run_coroutine_threadsafe(self._stack.aclose(), self._loop).result()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
