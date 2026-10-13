#!/usr/bin/env bash
# Brings the CAN bus up and puts the drivebase controllers into speed mode.
#
# Safe to run more than once: it reconfigures the interface from scratch each time rather
# than assuming what state it was left in. Configures the interface and enables the
# controllers only; it does not command any motion.
#
# Fails loudly if nothing actually made it onto the wire, which is what a dead transceiver
# or miswired bus looks like - the ip commands all succeed and candump just stays empty.
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

# The controller's own state, e.g. ERROR-ACTIVE or BUS-OFF. Anchored on berr-counter so it
# picks the controller state and not the link's "state UP" earlier in the same output.
canState() {
    ip -details link show "$IFACE" 2>/dev/null |
        grep -oP 'state \K[A-Z-]+(?= \(berr-counter)' || true
}

# Cumulative frames the interface has put on the wire since it came up.
txPackets() {
    ip -s link show "$IFACE" 2>/dev/null | awk '/^ *TX:/ {getline; print $2}'
}

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

TX_BEFORE="$(txPackets)"
TX_BEFORE="${TX_BEFORE:-0}"

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

TX_AFTER="$(txPackets)"
TX_SENT=$((${TX_AFTER:-0} - TX_BEFORE))
STATE="$(canState)"

# cansend exits 0 as soon as the frame is queued, so a bus with nothing on the other end
# looks identical to a working one until you check what the controller actually shifted.
if [ "$STATE" = "BUS-OFF" ] || [ "$TX_SENT" -eq 0 ]; then
    echo "error: ${IFACE} transmitted ${TX_SENT} frames and is in state ${STATE:-UNKNOWN}." >&2
    echo "Nothing reached the bus, so candump will show nothing." >&2
    echo "Check transceiver power and its standby pin, 120 ohm termination, CANH/CANL" >&2
    echo "orientation, and that the motors are powered and set to ${BITRATE} bit/s." >&2
    echo "Details: ip -details -statistics link show ${IFACE}" >&2
    exit 1
fi

echo "Speed setup commands sent to CAN IDs 0x${MOTOR_IDS[0]}-0x${MOTOR_IDS[-1]}."
echo "${TX_SENT} frames confirmed transmitted on ${IFACE} (state: ${STATE})."
