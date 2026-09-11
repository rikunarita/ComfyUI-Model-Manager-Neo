"""Minimal `server` stub for the verification harness.

Provides `PromptServer.instance` with:
  - routes: an aiohttp RouteTableDef the extension registers its routes on
  - user_manager.settings: an in-memory settings store (get/save)
  - send_json(): records websocket pushes so the probe can assert them
"""

import json

from aiohttp import web


class _Settings:
    def __init__(self) -> None:
        self._data: dict = {}

    def get_settings(self, request) -> dict:
        return dict(self._data)

    def save_settings(self, request, settings) -> None:
        self._data = dict(settings)


class _UserManager:
    def __init__(self) -> None:
        self.settings = _Settings()


class PromptServer:
    instance: "PromptServer"

    def __init__(self) -> None:
        self.routes = web.RouteTableDef()
        self.user_manager = _UserManager()
        self.sent: list[tuple[str, object]] = []
        self.sockets: set = set()

    async def send_json(self, event: str, data, sid=None) -> None:
        self.sent.append((event, data))
        payload = json.dumps({"type": event, "data": data})
        for ws in list(self.sockets):
            try:
                await ws.send_str(payload)
            except Exception:
                self.sockets.discard(ws)


PromptServer.instance = PromptServer()
