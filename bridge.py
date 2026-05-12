#!/usr/bin/env python3
"""Cardputer BLE bridge — send heartbeats to Claude Buddy on the M5 Cardputer Adv.

Acts as a BLE central that pretends to be Claude Desktop:
  1. Scans for "Claude_XXXXXX" (Nordic UART Service 6e400001-...)
  2. Connects, finds NUS RX characteristic
  3. Sends one JSON heartbeat line (UTF-8 + \\n terminator)
  4. Disconnects

The Cardputer's buddy_ui_cp.py renders the heartbeat fields on its 240x135 LCD:
  - msg     -> status line (y=74)
  - total / running / waiting -> queue line "Q: Nrun Nwait Ntot"
  - tokens_today -> tokens line

Usage:
  python3 bridge.py --msg "Task done"
  python3 bridge.py --msg "Building..." --running 1 --total 3
"""

import argparse
import asyncio
import json
import sys

from bleak import BleakScanner, BleakClient

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

DEFAULT_NAME_PREFIX = "Claude_"
SCAN_TIMEOUT_S = 10.0


async def find_device(name_prefix: str, timeout: float):
    print(f"scanning for BLE device starting with '{name_prefix}'...", file=sys.stderr)
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for dev, adv in devices.values():
        name = dev.name or adv.local_name or ""
        if name.startswith(name_prefix):
            print(f"found: {name} @ {dev.address}  rssi={adv.rssi}", file=sys.stderr)
            return dev
    return None


async def send_heartbeat(payload: dict, name_prefix: str = DEFAULT_NAME_PREFIX,
                         timeout: float = SCAN_TIMEOUT_S, listen_s: float = 0.0):
    dev = await find_device(name_prefix, timeout)
    if dev is None:
        print(f"ERROR: no '{name_prefix}*' device found within {timeout}s", file=sys.stderr)
        return 1

    line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")

    async with BleakClient(dev) as client:
        print(f"connected to {dev.address}", file=sys.stderr)

        if listen_s > 0:
            def _on_tx(_handle, data: bytearray):
                try:
                    text = bytes(data).decode("utf-8", errors="replace")
                except Exception:
                    text = repr(data)
                sys.stderr.write(f"  ← {text}")
                sys.stderr.flush()

            try:
                await client.start_notify(NUS_TX_UUID, _on_tx)
            except Exception as e:
                print(f"warn: start_notify failed: {e}", file=sys.stderr)

        await client.write_gatt_char(NUS_RX_UUID, line, response=False)
        print(f"sent: {line.decode().rstrip()}", file=sys.stderr)

        if listen_s > 0:
            await asyncio.sleep(listen_s)

    return 0


def main():
    ap = argparse.ArgumentParser(description="Send a heartbeat to Claude Buddy on Cardputer")
    ap.add_argument("--msg", default="hello from mac mini", help="status line shown at y=74")
    ap.add_argument("--total", type=int, default=0, help="queue total")
    ap.add_argument("--running", type=int, default=0, help="queue running")
    ap.add_argument("--waiting", type=int, default=0, help="queue waiting")
    ap.add_argument("--tokens", type=int, default=0, help="tokens consumed")
    ap.add_argument("--tokens-today", type=int, default=0, help="tokens today")
    ap.add_argument("--entries", type=int, default=0, help="entries count")
    ap.add_argument("--name-prefix", default=DEFAULT_NAME_PREFIX,
                    help="BLE name prefix to scan for")
    ap.add_argument("--timeout", type=float, default=SCAN_TIMEOUT_S, help="scan timeout (s)")
    ap.add_argument("--listen", type=float, default=0.0,
                    help="after sending, listen for device replies for N seconds")
    args = ap.parse_args()

    payload = {
        "msg": args.msg,
        "total": args.total,
        "running": args.running,
        "waiting": args.waiting,
        "tokens": args.tokens,
        "tokens_today": args.tokens_today,
        "entries": args.entries,
    }

    rc = asyncio.run(send_heartbeat(
        payload,
        name_prefix=args.name_prefix,
        timeout=args.timeout,
        listen_s=args.listen,
    ))
    sys.exit(rc)


if __name__ == "__main__":
    main()
