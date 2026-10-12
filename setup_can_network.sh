#!/bin/bash

# Commands
START_CMD="8800000000000000"
CLEAR_CMD="9B00000000000000"
SPEED_CMD="A200000000000000"

# Ensure driver dependencies are loaded
sudo modprobe can
sudo modprobe can_raw
sudo modprobe mttcan

# Set up the CAN interface
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
echo "CAN interface can0 set up successfully."

# Motor CAN IDs (hexadecimal)
MOTOR_IDS=("155" "156" "157" "158" "159" "15A")

# Enable motors in speed mode
for CAN_ID in "${MOTOR_IDS[@]}"; do
  echo "Sending clear command to CAN ID 0x$CAN_ID: $CLEAR_CMD"
  sudo cansend can0 "$CAN_ID#$CLEAR_CMD"
  sleep 0.1

  echo "Sending start command to CAN ID 0x$CAN_ID: $START_CMD"
  sudo cansend can0 "$CAN_ID#$START_CMD"
  sleep 0.1

  echo "Sending speed mode command to CAN ID 0x$CAN_ID: $SPEED_CMD"
  sudo cansend can0 "$CAN_ID#$SPEED_CMD"
  sleep 0.1
done

echo "Speed setup commands sent to CAN IDs 21-26 (hex 0x15-0x1A)."
