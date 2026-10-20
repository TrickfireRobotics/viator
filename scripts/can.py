#!/usr/bin/env python3
"""make can-setup: bring the CAN bus up and put the drivebase controllers into speed mode."""

from __future__ import annotations

import re
import subprocess
import sys
import time

import _lib as lib

CLEAR_CMD = "9B00000000000000"
START_CMD = "8800000000000000"
SPEED_CMD = "A200000000000000"
BITRATE = 1_000_000
MOTOR_IDS = ["155", "156", "157", "158", "159", "15A"]


def _can_state() -> str:
    result = subprocess.run(
        ["ip", "-details", "link", "show", lib.CAN_IFACE], capture_output=True, text=True
    )
    match = re.search(r"state (\S+) \(berr-counter", result.stdout)
    return match.group(1) if match else ""


def _tx_packets() -> int:
    result = subprocess.run(
        ["ip", "-s", "link", "show", lib.CAN_IFACE], capture_output=True, text=True
    )
    lines = result.stdout.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("TX:") and i + 1 < len(lines):
            fields = lines[i + 1].split()
            if len(fields) > 1:
                return int(fields[1])
    return 0


def main(argv: list[str]) -> None:
    lib.require_orin()
    lib.section(lib.CAN_IFACE)

    for module in ("can", "can_raw", "mttcan"):
        lib.run_checked(["sudo", "modprobe", module])

    if not lib.can_exists():
        lib.note("the transceiver likely isn't powered, check 'ip link show' and dmesg")
        lib.die(f"{lib.CAN_IFACE} cannot be found")

    subprocess.run(["sudo", "ip", "link", "set", lib.CAN_IFACE, "down"])
    lib.run_checked(
        ["sudo", "ip", "link", "set", lib.CAN_IFACE, "type", "can", "bitrate", str(BITRATE)]
    )
    lib.run_checked(["sudo", "ip", "link", "set", lib.CAN_IFACE, "up"])
    lib.info(f"up at {BITRATE} bit/s")

    tx_before = _tx_packets()

    for motor_id in MOTOR_IDS:
        for cmd in (CLEAR_CMD, START_CMD, SPEED_CMD):
            lib.run_checked(["sudo", "cansend", lib.CAN_IFACE, f"{motor_id}#{cmd}"])
            time.sleep(0.1)
        lib.note(f"0x{motor_id} cleared, started, speed mode")

    tx_sent = _tx_packets() - tx_before
    state = _can_state()

    if state == "BUS-OFF" or tx_sent == 0:
        lib.die(
            f"transmitted {tx_sent} frames in state {state or 'UNKNOWN'}, "
            "nothing reached the bus :("
        )

    lib.info(f"{len(MOTOR_IDS)} controllers set up", f"from 0x{MOTOR_IDS[0]} to 0x{MOTOR_IDS[-1]}")
    lib.info(f"{tx_sent} frames confirmed transmitted", f"in state {state}")


if __name__ == "__main__":
    main(sys.argv[1:])
