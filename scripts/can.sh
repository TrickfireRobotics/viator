#!/usr/bin/env bash
# make can-setup: bring the CAN bus up and put the drivebase controllers into speed mode.

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
requireOrin

readonly CLEAR_CMD="9B00000000000000"
readonly START_CMD="8800000000000000"
readonly SPEED_CMD="A200000000000000"
readonly BITRATE=1000000
readonly MOTOR_IDS=(155 156 157 158 159 15A)

section "$CAN_IFACE"

canState() {
    ip -details link show "$CAN_IFACE" 2>/dev/null |
        grep -oP 'state \K[A-Z-]+(?= \(berr-counter)' || true
}

txPackets() {
    ip -s link show "$CAN_IFACE" 2>/dev/null | awk '/^ *TX:/ {getline; print $2}'
}

sudo modprobe can
sudo modprobe can_raw
sudo modprobe mttcan

if ! canExists; then
    note "the transceiver likely isn't powered, check 'ip link show' and dmesg"
    die "${CAN_IFACE} cannot be found"
fi

sudo ip link set "$CAN_IFACE" down || true
sudo ip link set "$CAN_IFACE" type can bitrate "$BITRATE"
sudo ip link set "$CAN_IFACE" up
info "up at ${BITRATE} bit/s"

tx_before="$(txPackets)"
tx_before="${tx_before:-0}"

for id in "${MOTOR_IDS[@]}"; do
    for cmd in "$CLEAR_CMD" "$START_CMD" "$SPEED_CMD"; do
        sudo cansend "$CAN_IFACE" "${id}#${cmd}"
        sleep 0.1
    done
    note "0x${id} cleared, started, speed mode"
done

tx_sent=$(($(txPackets) - tx_before))
state="$(canState)"

if [ "$state" = "BUS-OFF" ] || [ "$tx_sent" -eq 0 ]; then
    die "transmitted ${tx_sent} frames in state ${state:-UNKNOWN}, nothing reached the bus :("
fi

info "${#MOTOR_IDS[@]} controllers set up" "from 0x${MOTOR_IDS[0]} to 0x${MOTOR_IDS[-1]}"
info "${tx_sent} frames confirmed transmitted" "in state ${state}"
