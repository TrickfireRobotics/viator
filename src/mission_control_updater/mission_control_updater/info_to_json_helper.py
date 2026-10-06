import json

from lib.motor_state.moteus_motor_state import MoteusMotorState


class InfoToJSONHelper:
    def __init__(self) -> None:
        self.moteus_entries: list[MoteusMotorState] = []

    def addMoteusEntry(self, entry: MoteusMotorState) -> None:
        self.moteus_entries.append(entry)

    def buildJSONString(self) -> str:
        moteus_dict_array = []

        for moteus_entry in self.moteus_entries:
            moteus_dict_array.append(moteus_entry.toDict())

        python_dict = {
            "moteusMotorLength": len(moteus_dict_array),
            "moteusMotors": moteus_dict_array,
        }

        return json.dumps(python_dict)
