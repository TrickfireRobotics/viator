#!/usr/bin/env bash
# Brings the CAN bus up and puts the drivebase controllers into speed mode.
#
# Safe to run more than once: it reconfigures the interface from scratch each time rather
# than assuming what state it was left in. Configures the interface and enables the
# controllers only; it does not command any motion.
#
# Called by `make can-setup`, by `make launch` when the bus isn't up yet, and by
# viator-can.service at boot on a deployed rover.

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# mttcan is the Tegra SoC's built-in CAN controller driver - it doesn't exist for any
# other hardware, so this would otherwise fail confusingly at modprobe on a laptop.
requireOrin "can1 or the mttcan driver"

# Commands
START_CMD="8800000000000000"
CLEAR_CMD="9B00000000000000"
SPEED_CMD="A200000000000000"

IFACE="${CAN_IFACE:-can1}"
BITRATE=1000000

# Motor CAN IDs (hexadecimal)
MOTOR_IDS=("155" "156" "157" "158" "159" "15A")

# Ensure driver dependencies are loaded
sudo modprobe can
sudo modprobe can_raw
sudo modprobe mttcan

if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "error: ${IFACE} does not exist even though this is the Orin." >&2
    echo "The CAN transceiver likely isn't powered. Check 'ip link show' and dmesg." >&2
    exit 1
fi

# Down first so the bitrate can be set: a CAN interface that is up refuses reconfiguration.
# Tolerant of it already being down, which is the normal case on a fresh boot.
sudo ip link set "$IFACE" down || true
sudo ip link set "$IFACE" type can bitrate "$BITRATE"
sudo ip link set "$IFACE" up
echo "CAN interface ${IFACE} up at ${BITRATE} bit/s."

# Enable motors in speed mode
for CAN_ID in "${MOTOR_IDS[@]}"; do
    echo "Sending clear command to CAN ID 0x$CAN_ID: $CLEAR_CMD"
    sudo cansend "$IFACE" "$CAN_ID#$CLEAR_CMD"
    sleep 0.1

    echo "Sending start command to CAN ID 0x$CAN_ID: $START_CMD"
    sudo cansend "$IFACE" "$CAN_ID#$START_CMD"
    sleep 0.1

    echo "Sending speed mode command to CAN ID 0x$CAN_ID: $SPEED_CMD"
    sudo cansend "$IFACE" "$CAN_ID#$SPEED_CMD"
    sleep 0.1
done

echo "Speed setup commands sent to CAN IDs 0x${MOTOR_IDS[0]}-0x${MOTOR_IDS[-1]}."
