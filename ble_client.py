from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any


NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
DEFAULT_BLE_NAME = "Claude_984552"
DEFAULT_BLE_PREFIX = "Claude_"
BACKOFF_CAP_SECONDS = 60


StateCallback = Callable[[str], None]
SleepFn = Callable[[float], Awaitable[None]]


class CardputerBleClient:
    def __init__(
        self,
        target_name: str | None = None,
        state_callback: StateCallback | None = None,
        sleep_fn: SleepFn = asyncio.sleep,
    ) -> None:
        self.target_name = target_name or os.environ.get("CARDPUTER_BLE_NAME", DEFAULT_BLE_NAME)
        self.state_callback = state_callback
        self.sleep_fn = sleep_fn
        self.state = "disconnected"
        self.last_heartbeat: dict[str, Any] | None = None
        self.dirty = False
        self.last_send_error: str | None = None
        self.failed_send_count = 0
        self._client: Any | None = None
        self._stop_event = asyncio.Event()

    @staticmethod
    def backoff_delay(attempt: int) -> int:
        return min(2 * (2**attempt), BACKOFF_CAP_SECONDS)

    def is_connected(self) -> bool:
        return bool(self._client is not None and getattr(self._client, "is_connected", False))

    async def send_line(self, payload: dict[str, Any]) -> bool:
        self.last_heartbeat = dict(payload)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

        if not self.is_connected():
            self.dirty = True
            return False

        try:
            await self._client.write_gatt_char(NUS_RX_UUID, line.encode("utf-8"), response=False)
        except Exception as exc:  # BLE stack errors vary by bleak backend.
            self.last_send_error = f"{type(exc).__name__}: {exc}"
            self.failed_send_count += 1
            self.dirty = True
            if self.failed_send_count >= 3:
                await self._disconnect_after_send_errors()
            return False

        self.last_send_error = None
        self.failed_send_count = 0
        self.dirty = False
        return True

    async def flush_dirty(self) -> bool:
        if not self.dirty or self.last_heartbeat is None:
            return False
        return await self.send_line(self.last_heartbeat)

    async def on_connected(self, client: Any) -> None:
        self._client = client
        self._set_state("connected")
        await self.flush_dirty()

    async def on_disconnected(self, _client: Any | None = None) -> None:
        self._client = None
        self._set_state("disconnected")

    async def stop(self) -> None:
        self._stop_event.set()
        await self._disconnect_after_send_errors()

    async def run_forever(self) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            try:
                self._set_state("scanning")
                device = await self._find_device()
                if device is None:
                    self._set_state("backoff")
                    await self.sleep_fn(self.backoff_delay(attempt))
                    attempt += 1
                    continue

                self._set_state("connecting")
                client = await self._connect_device(device)
                await self.on_connected(client)
                attempt = 0
                while self.is_connected() and not self._stop_event.is_set():
                    await self.sleep_fn(1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_send_error = f"{type(exc).__name__}: {exc}"
                self._set_state("backoff")
                await self.sleep_fn(self.backoff_delay(attempt))
                attempt += 1
            finally:
                if self.state in ("connected",):
                    await self.on_disconnected(None)

    async def _find_device(self) -> Any | None:
        scanner, _client_cls = _load_bleak()
        devices = await scanner.discover(service_uuids=[NUS_SERVICE_UUID])
        for device in devices:
            if self._matches_device(getattr(device, "name", None)):
                return device
        return None

    async def _connect_device(self, device: Any) -> Any:
        _scanner, client_cls = _load_bleak()
        client = client_cls(device, disconnected_callback=self._on_bleak_disconnected)
        await client.connect()
        return client

    def _on_bleak_disconnected(self, client: Any) -> None:
        self._client = None
        self._set_state("disconnected")

    def _matches_device(self, name: str | None) -> bool:
        if not name:
            return False
        if os.environ.get("CARDPUTER_BLE_NAME"):
            return name == self.target_name
        return name == self.target_name or name.startswith(DEFAULT_BLE_PREFIX)

    async def _disconnect_after_send_errors(self) -> None:
        client = self._client
        self._client = None
        if client is not None and getattr(client, "is_connected", False):
            disconnect = getattr(client, "disconnect", None)
            if disconnect is not None:
                result = disconnect()
                if isinstance(result, Awaitable):
                    await result
        self._set_state("disconnected")

    def _set_state(self, state: str) -> None:
        self.state = state
        if self.state_callback is not None:
            self.state_callback(state)


def _load_bleak() -> tuple[Any, Any]:
    from bleak import BleakClient, BleakScanner

    return BleakScanner, BleakClient
