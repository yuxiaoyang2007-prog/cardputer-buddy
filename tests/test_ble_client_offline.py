from __future__ import annotations

import asyncio

from ble_client import CardputerBleClient, NUS_RX_UUID


class FakeBleakClient:
    def __init__(self) -> None:
        self.is_connected = True
        self.writes: list[tuple[str, bytes, bool]] = []
        self.disconnects = 0

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
        self.writes.append((uuid, data, response))

    async def disconnect(self) -> None:
        self.disconnects += 1
        self.is_connected = False


def test_backoff_sequence_caps_at_sixty_seconds() -> None:
    assert [CardputerBleClient.backoff_delay(i) for i in range(8)] == [
        2,
        4,
        8,
        16,
        32,
        60,
        60,
        60,
    ]


def test_send_line_when_disconnected_only_buffers_latest_heartbeat() -> None:
    asyncio.run(_test_send_line_when_disconnected_only_buffers_latest_heartbeat())


async def _test_send_line_when_disconnected_only_buffers_latest_heartbeat() -> None:
    client = CardputerBleClient()

    sent = await client.send_line({"msg": "first", "total": 1})

    assert sent is False
    assert client.dirty is True
    assert client.last_heartbeat == {"msg": "first", "total": 1}
    assert client.is_connected() is False


def test_reconnect_flushes_only_latest_buffered_heartbeat() -> None:
    asyncio.run(_test_reconnect_flushes_only_latest_buffered_heartbeat())


async def _test_reconnect_flushes_only_latest_buffered_heartbeat() -> None:
    client = CardputerBleClient()
    await client.send_line({"msg": "one", "total": 1})
    await client.send_line({"msg": "two", "total": 2})
    await client.send_line({"msg": "three", "total": 3})

    fake = FakeBleakClient()
    await client.on_connected(fake)

    assert client.dirty is False
    assert len(fake.writes) == 1
    uuid, data, response = fake.writes[0]
    assert uuid == NUS_RX_UUID
    assert response is False
    assert b'"msg":"three"' in data
    assert b'"total":3' in data
