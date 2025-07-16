from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from functools import singledispatch
import itertools
import music
import rhythm
import random
import string

__all__ = [
    'Brush',
    'ControlPoint',
    'Entity',
    'Key',
    'Clip',
    'Tracker',
    'NoteGen',
    'Document',
    'Cell',
    'PianoRoll',
    'Staves',
    'Grid',
    'View', 'TrackerView',
]

def random_name():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

Args = Dict[str, Any]

@singledispatch
def stringify(self):
    raise ValueError(f"stringify: no method for {type(self)}")

@singledispatch
def to_json(self):
    raise ValueError(f"to_json: no method for {type(self)}")

@dataclass(eq=False)
class Brush:
    label : str
    __str__ = stringify
    to_json = to_json

@dataclass(eq=False)
class Entity:
    shift : int
    brush : Brush

    def copy(self):
        return Entity(self.shift, self.brush)

@dataclass(eq=False)
class ControlPoint(Brush):
    tag : str
    transition : bool
    value : Any

    def construct(self, sequencer, offset, key):
        if self.tag == "tempo" and self.value <= 0:
            return
        sequencer.quadratic(offset, self.tag, self.transition, self.value)

    def annotate(self, graph_key_map, offset):
        pass

    @property
    def duration(self):
        return 0

    def copy(self):
        return ControlPoint("", self.tag, self.transition, self.value)

@dataclass(eq=False)
class Key(Brush):
    index : int

    def construct(self, sequencer, offset, key):
        return

    def annotate(self, graph_key_map, offset):
        graph_key_map.append((offset, self.index))

    @property
    def duration(self):
        return 0

    def copy(self):
        return Key("", self.lanes, self.index)

@dataclass(eq=False)
class Clip(Brush):
    duration : int
    brushes : List[Entity]

    def construct(self, sequencer, offset, key):
        for i, e in enumerate(self.brushes):
            kv = key + (i,)
            e.brush.construct(sequencer, offset + e.shift, kv)

    def annotate(self, graph_key_map, offset):
        for i, e in enumerate(self.brushes):
            e.brush.annotate(graph_key_map, offset + e.shift)

    def copy(self):
        return Clip("", self.duration, [e.copy() for e in self.brushes])

def copy_args(args):
    if args is not None:
        return args.copy()

@dataclass(eq=False)
class NoteGen:
    tag : str
    track : List[Optional[Args]]
    loop : bool
    flavor : str = "note"

    def generate(self, sequencer, rhythm, key):
        for i, (start, duration), args in zip(itertools.count(), rhythm, itertools.cycle(self.track)):
            if args is not None:
                if self.flavor == 'note':
                    sequencer.note(self.tag, start, duration, key + (i,), args)
                elif self.flavor == 'control':
                    sequencer.control(start, self.tag, args)
                elif self.flavor == 'quadratic':
                    sequencer.quadratic(start, tag, args["~"], args["*"])

    def loop_group(self):
        return len(self.track) if self.loop else None
                
    def copy(self):
        return NoteGen(self.tag, [copy_args(a) for a in self.track], self.loop, self.flavor)

@dataclass(eq=False)
class Tracker(Brush):
    duration : int
    rhythm : Any
    generators : List[Any]
    view : Any

    def construct(self, sequencer, offset, key):
        rhythm = self.rhythm.to_events(offset, self.duration)
        for i, gen in enumerate(self.generators):
            gen.generate(sequencer, rhythm, key + (i,))

    def annotate(self, graph_key_map, offset):
        pass

    def copy(self):
        return Tracker("",
            self.duration,
            rhythm.from_string(str(self.rhythm)),
            [g.copy() for g in self.generators],
            self.view)

@dataclass(eq=False)
class Cell(Brush):
    multi : bool
    synth : str
    pos : Tuple[int, int]
    params : Dict[str, Union[int, float, music.Pitch]]
    type_param : Optional[str] = None

    def copy(self):
        return Cell("", self.multi, self.synth, tuple(self.pos), self.params.copy(), self.type_param)

@dataclass(eq=False)
class PianoRoll:
    bot : int
    top : int
    edit : List[Tuple[str, str]]

@dataclass(eq=False)
class Staves:
    count : int
    above : int
    below : int
    edit : List[Tuple[str, str]]

@dataclass(eq=False)
class Grid:
    kind : str
    edit : List[Tuple[str, str]]

@dataclass(eq=False)
class View(Brush):
    lanes : List[Any]
TrackerView = View

@dataclass(eq=False)
class Document:
    brushes : List[Entity]
    duration : int
    labels : Dict[str, Brush]
    cells : List[Brush]
    views : Dict[str, Brush]
    connections : Set[Tuple[str, str]]

    def intro(self, brush):
        if brush.label in self.labels and brush == self.labels[brush.label]:
            return brush
        if brush.label == "" or brush.label in self.labels:
            name = random_name()
            while name in self.labels:
                name = random_name()
            brush.label = name
        self.labels[brush.label] = brush
        return brush

    def rebuild_labels(self):
        labels = {}
        def visit(brush):
            labels[brush.label] = brush
            if isinstance(brush, Clip):
                for e in brush.brushes:
                    visit(e.brush)
        for e in self.brushes:
            visit(e.brush)
        for cell in self.cells:
            visit(cell)
        for view in self.views.values():
            visit(view)
        self.labels = labels

    def construct(self, sequencer, offset, key):
        for i, e in enumerate(self.brushes):
            kv = key + (i,)
            e.brush.construct(sequencer, offset + e.shift, kv)

    def annotate(self, graph_key_map, offset):
        for i, e in enumerate(self.brushes):
            e.brush.annotate(graph_key_map, offset + e.shift)

    __str__ = stringify
