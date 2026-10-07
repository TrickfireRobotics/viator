"""
This module contains classes and functions related to coloring text in consoles that support ANSI.
"""

from enum import Enum

# "Borrowed" from here:
# https://stackoverflow.com/questions/287871/how-do-i-print-colored-text-to-the-terminal


# The str mixin type on Enums is subpar as it has some serialization issues, but will work more than
# well enough for our purposes
class ColorCodes(str, Enum):
    """
    An enum whose values represent color tags when printed to a console that supports ANSI
    """

    PINK = "\033[95m"
    BLUE_OK = "\033[94m"
    CYAN_OK = "\033[96m"
    GREEN_OK = "\033[92m"
    WARNING_YELLOW = "\033[93m"
    FAIL_RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def colorStr(text: str, color: ColorCodes) -> str:
    """
    Colors the given string with the given color when printed to console

    Parameters
    ------
    text: str
        The string to color
    color: Color
        The color to color the string with

    Returns
    ------
        A string that will be colored when printed
    """
    return color + text + ColorCodes.ENDC
