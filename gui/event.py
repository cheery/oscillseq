from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from .base import process_event

class uievent:
    def __init__(self, action):
        self.action = action

    def __repr__(self):
        return f"UIEvent:{self.name}"

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return uievent(self.action.__get__(instance, owner))

    def __call__(self, *args):
        return eventlope(self, args)

    def invoke(self):
        return self.action()

@dataclass(eq=True, frozen=True)
class eventlope:
    event : uievent
    args  : Tuple[Any]
    def __call__(self, *args):
        return eventlope(self.event, self.args + args)

    def invoke(self):
        return self.event.action(*self.args)

def invoke_at_event(ui, root, ev, rect):
    for ue in process_event(ui, root, ev, rect):
        ue.invoke()
