from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import stat
import tempfile

from socket_server import CardputerSocketServer


HOOK_NAMES = [
    "SessionStart",
    "UserPromptSubmit",
    "Stop",
    "SubagentStop",
    "SessionEnd",
]


def hook_message(name: str, sid: str = "s1") -> dict:
    return {
        "type": "hook",
        "hook_event_name": name,
        "session_id": sid,
        "cwd": "/tmp/project",
        "transcript_path": "/tmp/transcript.jsonl",
    }


def test_socket_server_queues_five_valid_hook_events(tmp_path) -> None:
    del tmp_path
    with short_temp_dir() as temp_path:
        asyncio.run(_test_socket_server_queues_five_valid_hook_events(temp_path))


async def _test_socket_server_queues_five_valid_hook_events(tmp_path) -> None:
    queue: asyncio.Queue[dict] = asyncio.Queue()
    server = CardputerSocketServer(queue, tmp_path / "control.sock")
    await server.start()
    try:
        for index, name in enumerate(HOOK_NAMES):
            await send_line(server.socket_path, hook_message(name, sid=f"s{index}"))

        received = [await asyncio.wait_for(queue.get(), timeout=0.2) for _ in HOOK_NAMES]
        assert [item["hook_event_name"] for item in received] == HOOK_NAMES
    finally:
        await server.stop()


def test_socket_server_ignores_malformed_json_and_keeps_running(tmp_path) -> None:
    del tmp_path
    with short_temp_dir() as temp_path:
        asyncio.run(_test_socket_server_ignores_malformed_json_and_keeps_running(temp_path))


async def _test_socket_server_ignores_malformed_json_and_keeps_running(tmp_path) -> None:
    queue: asyncio.Queue[dict] = asyncio.Queue()
    server = CardputerSocketServer(queue, tmp_path / "control.sock")
    await server.start()
    try:
        await send_raw(server.socket_path, b"{not-json\n")
        await asyncio.sleep(0)
        assert queue.empty()

        await send_line(server.socket_path, hook_message("Stop"))
        received = await asyncio.wait_for(queue.get(), timeout=0.2)
        assert received["hook_event_name"] == "Stop"
    finally:
        await server.stop()


def test_socket_server_status_request_round_trips_via_queue(tmp_path) -> None:
    del tmp_path
    with short_temp_dir() as temp_path:
        asyncio.run(_test_socket_server_status_request_round_trips_via_queue(temp_path))


async def _test_socket_server_status_request_round_trips_via_queue(tmp_path) -> None:
    queue: asyncio.Queue[dict] = asyncio.Queue()
    server = CardputerSocketServer(queue, tmp_path / "control.sock")
    await server.start()
    try:
        client_task = asyncio.create_task(send_status(server.socket_path))
        status_event = await asyncio.wait_for(queue.get(), timeout=0.2)
        assert status_event["type"] == "status"
        status_event["future"].set_result(
            {
                "type": "status_reply",
                "schema_version": 1,
                "ble_state": "disconnected",
            }
        )

        reply = await asyncio.wait_for(client_task, timeout=0.2)
        assert reply["type"] == "status_reply"
        assert reply["ble_state"] == "disconnected"
    finally:
        await server.stop()


def test_socket_server_prepares_private_parent_and_socket_permissions(tmp_path) -> None:
    del tmp_path
    with short_temp_dir() as temp_path:
        asyncio.run(_test_socket_server_prepares_private_parent_and_socket_permissions(temp_path))


async def _test_socket_server_prepares_private_parent_and_socket_permissions(tmp_path) -> None:
    socket_path = tmp_path / "runtime" / "control.sock"
    socket_path.parent.mkdir()
    socket_path.write_text("stale", encoding="utf-8")

    queue: asyncio.Queue[dict] = asyncio.Queue()
    server = CardputerSocketServer(queue, socket_path)
    await server.start()
    try:
        parent_mode = stat.S_IMODE(os.stat(socket_path.parent).st_mode)
        socket_mode = stat.S_IMODE(os.stat(socket_path).st_mode)
        assert parent_mode == 0o700
        assert socket_mode == 0o600
    finally:
        await server.stop()


async def send_line(path, payload: dict) -> None:
    await send_raw(path, json.dumps(payload).encode("utf-8") + b"\n")


async def send_raw(path, raw: bytes) -> None:
    _reader, writer = await asyncio.open_unix_connection(str(path))
    writer.write(raw)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def send_status(path) -> dict:
    reader, writer = await asyncio.open_unix_connection(str(path))
    writer.write(b'{"type":"status"}\n')
    await writer.drain()
    raw = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return json.loads(raw.decode("utf-8"))


class short_temp_dir:
    def __enter__(self) -> Path:
        self._temp_dir = tempfile.TemporaryDirectory(prefix="cs-", dir="/tmp")
        return Path(self._temp_dir.__enter__())

    def __exit__(self, exc_type, exc, tb) -> None:
        self._temp_dir.__exit__(exc_type, exc, tb)
