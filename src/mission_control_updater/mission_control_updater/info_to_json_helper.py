import json
from typing import Any

from lib.motor_state.can_motor_state import CANMotorState


class InfoToJSONHelper:
    def __init__(self) -> None:
        self.moteus_entries: list[CANMotorState[Any]] = []

    def add_moteus_entry(self, entry: CANMotorState[Any]) -> None:
        self.moteus_entries.append(entry)

    def build_json_string(self) -> str:
        moteus_dict_array = []

        for moteus_entry in self.moteus_entries:
            moteus_dict_array.append(moteus_entry.to_dict())

        python_dict = {
            "moteusMotorLength": len(moteus_dict_array),
            "moteusMotors": moteus_dict_array,
        }

        return json.dumps(python_dict)
