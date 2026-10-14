"""
This module contains a JsonMsg base class that should be inherited. This JsonMsg class allows for
easy conversion between String messages containing strings and python dictionaries.

Inheriting this class should look like this:
```
class FooMsg(JsonMsg["FooMsg"]):
    # your code
    pass
```

Optionally you can make the subclass a dataclass too:
```
@dataclass
class FooMsg(JsonMsg["FooMsg"]):
    foo: int
    bar: int
```
"""

import json
from typing import Any, Generic, TypeVar

from std_msgs.msg import String

T = TypeVar("T")


# Yes I had to do some ungodly things to make type checking work. I dont think anyone on the team
# but me knows precisely what this code does... itll be find - kyler
class JsonMsg(Generic[T]):
    """
    A base class that allows subclasses to easily be converted into String message objects
    containing a Json string.

    The generic type `T` should be the inheriting class:
    ```
    class FooMsg(JsonMsg["FooMsg"]):
        # your code
        pass
    ```
    """

    def toMsg(self) -> String:
        """
        Convert the message object into a String message containing a Json string.
        """
        str_msg = String()
        str_msg.data = json.dumps(self.toDict())
        return str_msg

    def toDict(self) -> dict[str, Any]:
        """
        Converts the message object into a dictionary.
        """
        return {
            key: value for key, value in self.__dict__.copy().items() if not key.startswith("_")
        }

    @classmethod
    def fromJsonMsg(cls, msg: String) -> T:
        """
        Creates a JsonMsg object from a string message.
        """
        json_obj = json.loads(msg.data)

        # This code just gets the child class and constructs a new one
        # You can think of it like this: return T(**json_obj)
        # It's just that the above code is not valid
        return cls(**json_obj)  # type: ignore
