#!/usr/bin/env python3
"""Hold connection for 30s and stream heartbeats so user can watch the screen."""
import asyncio
import json
import sys
from bleak import BleakScanner, BleakClient

NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


async def main():
    print("scanning...", file=sys.stderr)
    devices = await BleakScanner.discover(timeout=8.0, return_adv=True)
    dev = None
    for d, adv in devices.values():
        name = d.name or adv.local_name or ""
        if name.startswith("Claude_"):
            dev = d
            print(f"found: {name} @ {d.address}", file=sys.stderr)
            break
    if not dev:
        print("ERROR: no Claude_ device", file=sys.stderr)
        return 1

    def on_tx(_h, data):
        sys.stderr.write(f"  ← {bytes(data).decode('utf-8', errors='replace')}")
        sys.stderr.flush()

    async with BleakClient(dev) as client:
        print(f"connected. holding 30s and streaming heartbeats...", file=sys.stderr)
        try:
            await client.start_notify(NUS_TX, on_tx)
        except Exception as e:
            print(f"warn: start_notify: {e}", file=sys.stderr)

        for i in range(15):
            hb = {
                "msg": f"tick {i+1}/15",
                "total": 3, "running": 1, "waiting": 2,
                "tokens": 100 * (i+1),
                "tokens_today": 12345,
                "entries": 7,
            }
            line = (json.dumps(hb, separators=(",", ":")) + "\n").encode()
            await client.write_gatt_char(NUS_RX, line, response=False)
            print(f"sent #{i+1}: {hb['msg']}", file=sys.stderr)
            await asyncio.sleep(2.0)

    print("disconnected", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
