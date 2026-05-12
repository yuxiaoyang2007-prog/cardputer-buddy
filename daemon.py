from __future__ import annotations

import asyncio
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sys
import time
from typing import Any

from ble_client import CardputerBleClient
from session_store import SessionStore
from socket_server import CardputerSocketServer, SocketInUseError, socket_accepts_connection


VERSION = "v0.1"
RUNTIME_DIR = Path.home() / ".cardputer-daemon"
SOCKET_PATH = RUNTIME_DIR / "control.sock"
LOCK_PATH = RUNTIME_DIR / "daemon.lock"
LOG_PATH = RUNTIME_DIR / "daemon.log"
MUTE_PATH = Path.home() / ".cardputer-mute"
TTL_SECONDS = 60


class SingleInstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        self._file = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another cardputer daemon instance is already running") from exc

    def close(self) -> None:
        if self._file is not None:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file = None


async def event_consumer(
    queue: asyncio.Queue[dict[str, Any]],
    store: SessionStore,
    ble_client: CardputerBleClient,
    started_at: float,
) -> None:
    while True:
        event = await queue.get()
        event_type = event.get("type")
        if event_type == "hook":
            applied = store.apply_event(event)
            if applied:
                heartbeat = store.compute_heartbeat()
                if not MUTE_PATH.exists():
                    await ble_client.send_line(heartbeat)
                logging.info("hook applied: %s %s", event.get("hook_event_name"), event.get("session_id"))
            else:
                logging.warning("ignored hook event: %s", event)
        elif event_type == "prune_tick":
            pruned = store.prune_inactive()
            heartbeat = store.compute_heartbeat()
            if not MUTE_PATH.exists():
                await ble_client.send_line(heartbeat)
            if pruned:
                logging.info("pruned inactive sessions: %s", pruned)
        elif event_type == "status":
            future = event.get("future")
            if future is not None and not future.done():
                future.set_result(build_status_snapshot(store, ble_client, started_at))
        else:
            logging.warning("ignored unknown event type: %s", event_type)


async def ttl_ticker(queue: asyncio.Queue[dict[str, Any]]) -> None:
    while True:
        await asyncio.sleep(TTL_SECONDS)
        await queue.put({"type": "prune_tick"})


def build_status_snapshot(
    store: SessionStore,
    ble_client: CardputerBleClient,
    started_at: float,
) -> dict[str, Any]:
    return {
        "type": "status_reply",
        "schema_version": 1,
        "version": VERSION,
        "uptime_s": int(time.monotonic() - started_at),
        "ble_state": ble_client.state,
        "ble_last_send_error": ble_client.last_send_error,
        "sessions": store.snapshot_sessions(),
        "tokens_today": store.tokens_today,
        "entries_today": store.entries_today,
        "last_heartbeat": ble_client.last_heartbeat,
    }


async def run_daemon() -> int:
    setup_logging()
    lock = SingleInstanceLock(LOCK_PATH)
    server: CardputerSocketServer | None = None
    tasks: list[asyncio.Task] = []
    shutdown_event = asyncio.Event()

    try:
        lock.acquire()
        if await socket_accepts_connection(SOCKET_PATH, timeout=0.2):
            raise SocketInUseError(f"socket already accepts connections: {SOCKET_PATH}")

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        store = SessionStore()
        ble_client = CardputerBleClient(state_callback=lambda state: logging.info("ble state: %s", state))
        started_at = time.monotonic()

        server = CardputerSocketServer(queue, SOCKET_PATH)
        await server.start()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_event.set)

        tasks = [
            asyncio.create_task(event_consumer(queue, store, ble_client, started_at)),
            asyncio.create_task(ttl_ticker(queue)),
            asyncio.create_task(ble_client.run_forever()),
        ]
        logging.info("cardputer daemon started")
        await shutdown_event.wait()
        logging.info("cardputer daemon shutting down")
        await ble_client.stop()
        return 0
    except Exception:
        logging.exception("cardputer daemon failed")
        return 1
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if server is not None:
            await server.stop()
        lock.close()


def setup_logging() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(RUNTIME_DIR, 0o700)
    level = logging.DEBUG if os.environ.get("CARDPUTER_DAEMON_DEBUG") == "1" else logging.INFO
    handlers: list[logging.Handler] = [
        RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3),
    ]
    if os.environ.get("CARDPUTER_DAEMON_STDERR") == "1":
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def main() -> None:
    raise SystemExit(asyncio.run(run_daemon()))


if __name__ == "__main__":
    main()
