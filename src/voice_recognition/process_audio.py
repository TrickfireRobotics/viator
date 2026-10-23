import argparse
import json
import queue
import sys
from enum import Enum
from io import BufferedWriter
from typing import Any

import sounddevice as sd

# import the actual voice commands from voice_commands.py
import voice_commands
from vosk import KaldiRecognizer, Model

q: queue.Queue = queue.Queue()


# Defines the valid commands. Use format COMMAND_NAME = "command_name"
class Commands(Enum):
    FOLLOW = "follow"
    COME = "come"
    STAY = "stay"
    FETCH = "fetch"
    GIVE = "give"


# Model Configuration
VOSK_MODEL_SMALL = "vosk-model-small-en-us-0.15"  # Small Vosk model, seems to be best case
VOSK_MODEL_REGULAR = "vosk-model-en-us-0.22"  # Larger model, seems less effective

USE_MODEL = VOSK_MODEL_SMALL  # Select one of the above models


def int_or_str(text: Any) -> int | str:
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


def callback(indata: Any, frames: Any, time: Any, status: Any) -> None:
    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))


# Parse command line arguments
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    "-l", "--list-devices", action="store_true", help="show list of audio devices and exit"
)
args, remaining = parser.parse_known_args()
if args.list_devices:
    print("Available Input Devices (Microphones):")
    print("-" * 45)
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"[{i}] {d['name']}")
    print("-" * 45)
    parser.exit(0)


# NOTE: we could probably hardcode these once we get it on the rover, but this allows flexibility
parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[parser]
)
parser.add_argument(
    "-f", "--filename", type=str, metavar="FILENAME", help="audio file to store recording to"
)
parser.add_argument(
    "-d", "--device", type=int_or_str, help="set input device (numeric ID or substring)"
)
args = parser.parse_args(remaining)

# Main logic
try:
    device_info = sd.query_devices(args.device, "input")
    samplerate = int(device_info["default_samplerate"])

    # Set the model
    model = Model(USE_MODEL)
    dump_fn: BufferedWriter | None = None
    if args.filename:
        dump_fn = open(args.filename, "wb")
    else:
        dump_fn = None

    full_transcript = []  # Store all finalized results

    with sd.RawInputStream(
        samplerate=samplerate,
        blocksize=6000,
        device=args.device,
        dtype="int16",
        channels=1,
        callback=callback,
    ):
        print("#" * 80)
        print("VOSK: Press Ctrl+C to stop the recording")
        print("#" * 80)
        print("Valid Commands:")
        for command in Commands:
            print(command.name)
        print("#" * 80)
        rec = KaldiRecognizer(model, samplerate)

        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "")
                print(text, end=" ", flush=True)
                full_transcript.append(text)  # Store finalized text

                # Print any command that comes through the text
                for command in Commands:
                    if command.value in text:
                        print("\nRunning " + command.value + "();\n")
                        try:
                            cmd = getattr(
                                voice_commands, command.value
                            )  # get the command from the voice_commands.py file
                            if callable(cmd):
                                cmd()
                            else:
                                print("#" * 80)
                                print(
                                    "Couldn't call "
                                    + command.value
                                    + "(); please implement it in voice_commands.py using the "
                                    + "following format:"
                                )
                                print("def " + command.value + "() -> <type>:")
                                print("    # Your code here")
                                print("#" * 80)
                        except AttributeError:
                            print("#" * 80)
                            print(
                                "Failed to run "
                                + command.value
                                + "(); please implement it in voice_commands.py using the "
                                + "following format:"
                            )
                            print("\ndef " + command.value + "() -> <type>:")
                            print("    # Your code here")  # validate the command and call it
                            print("#" * 80)

            if dump_fn is not None:
                dump_fn.write(data)


except KeyboardInterrupt:
    print("\n\nFinal Complete Transcript:")
    print(" ".join(full_transcript))
    parser.exit(0)
except Exception as e:
    parser.error(type(e).__name__ + ": " + str(e))
    parser.exit(0)
