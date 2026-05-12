from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from session_store import HOOK_EVENTS


DEFAULT_SOCKET_PATH = Path.home() / ".cardputer-daemon" / "control.sock"


class SocketInUseError(RuntimeError):
    pass


class CardputerSocketServer:
    def __init__(
        self,
        event_queue: asyncio.Queue[dict[str, Any]],
        socket_path: Path | str = DEFAULT_SOCKET_PATH,
        connect_timeout: float = 0.2,
        status_timeout: float = 0.2,
    ) -> None:
        self.event_queue = event_queue
        self.socket_path = Path(socket_path)
        self.connect_timeout = connect_timeout
        self.status_timeout = status_timeout
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._prepare_socket_parent()
        if await socket_accepts_connection(self.socket_path, self.connect_timeout):
            raise SocketInUseError(f"socket already accepts connections: {self.socket_path}")
        if self.socket_path.exists():
            self.socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path),
        )
        os.chmod(self.socket_path, 0o600)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self.socket_path.exists():
            self.socket_path.unlink()

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        await self._server.serve_forever()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw = await reader.readline()
            if not raw:
                return
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return

            if not isinstance(message, dict):
                return

            message_type = message.get("type")
            if message_type == "hook":
                await self._handle_hook_message(message)
            elif message_type == "status":
                await self._handle_status_message(writer)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_hook_message(self, message: dict[str, Any]) -> None:
        if message.get("hook_event_name") not in HOOK_EVENTS:
            return
        await self.event_queue.put(message)

    async def _handle_status_message(self, writer: asyncio.StreamWriter) -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        await self.event_queue.put({"type": "status", "future": future})
        try:
            reply = await asyncio.wait_for(future, timeout=self.status_timeout)
        except asyncio.TimeoutError:
            reply = {
                "type": "status_reply",
                "schema_version": 1,
                "error": "status_timeout",
            }
        writer.write(json.dumps(reply, separators=(",", ":")).encode("utf-8") + b"\n")
        await writer.drain()

    def _prepare_socket_parent(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.socket_path.parent, 0o700)


async def socket_accepts_connection(path: Path | str, timeout: float = 0.2) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(str(path)),
            timeout=timeout,
        )
    except (FileNotFoundError, ConnectionRefusedError, OSError, asyncio.TimeoutError):
        return False

    writer.close()
    await writer.wait_closed()
    reader.feed_eof()
    return True
