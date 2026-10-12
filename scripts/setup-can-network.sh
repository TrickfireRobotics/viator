#!/bin/bash
set -e

IFACE="${CAN_IFACE:-can0}"
BITRATE=1000000

# Commands
START_CMD="8800000000000000"
CLEAR_CMD="9B00000000000000"
SPEED_CMD="A200000000000000"

can_state() {
    ip -details link show "$IFACE" | awk '/berr-counter/ {for (i = 1; i <= NF; i++) if ($i == "state") print $(i + 1)}'
}

tx_packets() {
    ip -s link show "$IFACE" | awk '/^ *TX:/ {getline; print $2}'
}

# Ensure driver dependencies are loaded
sudo modprobe can
sudo modprobe can_raw
sudo modprobe mttcan

# Set up the CAN interface
sudo ip link set "$IFACE" down
sudo ip link set "$IFACE" type can bitrate "$BITRATE"
sudo ip link set "$IFACE" up
echo "CAN interface $IFACE set up successfully."

TX_BEFORE=$(tx_packets)
TX_BEFORE=${TX_BEFORE:-0}

# Motor CAN IDs (hexadecimal)
MOTOR_IDS=("155" "156" "157" "158" "159" "15A")

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

TX_AFTER=$(tx_packets)
TX_AFTER=${TX_AFTER:-0}
TX_SENT=$((TX_AFTER - TX_BEFORE))
STATE=$(can_state)

if [ "$STATE" = "BUS-OFF" ] || [ "$TX_SENT" -eq 0 ]; then
    echo "ERROR: $IFACE transmitted $TX_SENT frames and is in state ${STATE:-UNKNOWN}." >&2
    echo "Nothing reached the bus, so candump will show nothing." >&2
    echo "Check transceiver power and its standby pin, 120 ohm termination, CANH/CANL" >&2
    echo "orientation, and that the motors are powered and set to $BITRATE bit/s." >&2
    echo "Details: ip -details -statistics link show $IFACE" >&2
    exit 1
fi

echo "Speed setup commands sent to CAN IDs 21-26 (hex 0x15-0x1A)."
echo "$TX_SENT frames confirmed transmitted on $IFACE (state: $STATE)."
