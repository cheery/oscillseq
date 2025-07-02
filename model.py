from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
import itertools
import measure
import music
import json
import random
import string

def random_name():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

Args = Dict[str, Any]
Brush = Any

@dataclass(eq=False)
class Entity:
    shift : int
    brush : Brush

    def to_json(self):
        return {"shift": self.shift, "brush": self.brush.label}

    @classmethod
    def from_json(cls, brushes, obj):
        return cls(
            shift = obj["shift"],
            brush = brushes[obj["brush"]])

def value_to_json(value):
    if isinstance(value, music.Pitch):
        return [value.position, value.accidental]
    assert isinstance(value, (int, float))
    return value

def json_to_value(value):
    if isinstance(value, (tuple, list)):
        return music.Pitch(*value)
    assert isinstance(value, (int, float))
    return value

def json_to_brush(label, obj):
    return {
        "clip": Clip,
        "clap": Tracker,
        "tracker": Tracker,
        "controlpoint": ControlPoint,
        "key": Key,
        "cell": Cell,
        "trackerview": TrackerView,
    }[obj["type"]].from_json(label, obj)

@dataclass(eq=False)
class ControlPoint:
    label : str
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

    def to_json(self):
        return {
            "type": "controlpoint",
            "tag": self.tag,
            "transition": self.transition,
            "value": value_to_json(self.value)
        }
        
    @classmethod
    def from_json(cls, label, obj):
        return cls(label,
            tag = obj["tag"],
            transition = obj["transition"],
            value = json_to_value(obj["value"])
        )

@dataclass(eq=False)
class Key:
    label : str
    lanes : int
    index : int

    def construct(self, sequencer, offset, key):
        return

    def annotate(self, graph_key_map, offset):
        for graph in graph_key_map:
            if self.lanes & (1 << graph.lane):
                graph_key_map[graph].append((offset, self.index))

    @property
    def duration(self):
        return 0

    def to_json(self):
        return {
            "type": "key",
            "lanes": self.lanes,
            "index": self.index,
        }
        
    @classmethod
    def from_json(cls, label, obj):
        return cls(label,
            lanes = obj["lanes"],
            index = obj["index"],
        )

@dataclass(eq=False)
class Clip:
    label : str
    duration : int
    brushes : List[Entity]

    def construct(self, sequencer, offset, key):
        for i, e in enumerate(self.brushes):
            kv = key + (i,)
            e.brush.construct(sequencer, offset + e.shift, kv)

    def annotate(self, graph_key_map, offset):
        for i, e in enumerate(self.brushes):
            e.brush.annotate(graph_key_map, offset + e.shift)

    def to_json(self):
        return {
            "type": "clip",
            "duration": self.duration,
            "brushes": [b.to_json() for b in self.brushes]
        }
        
    @classmethod
    def from_json(cls, label, obj):
        return cls(label,
            duration = obj['duration'],
            brushes = obj['brushes']
        )

def json_to_gen(obj):
    return {
        "note": NoteGen,
        "control": NoteGen,
        "quadratic": NoteGen,
    }[obj["type"]].from_json(obj)

def args_to_json(args):
    if args is not None:
        return {name: value_to_json(a) for name, a in args.items()}

def json_to_args(obj):
    if obj is not None:
        return {name: json_to_value(o) for name, o in obj.items()}

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
                
    def to_json(self):
        return {
            "type": self.flavor,
            "tag": self.tag,
            "track": [args_to_json(args) for args in self.track],
            "loop": self.loop,
        }
        
    @classmethod
    def from_json(cls, obj):
        return cls(
            tag = obj["tag"],
            track = [json_to_args(args) for args in obj["track"]],
            loop = obj["loop"],
            flavor = obj["type"]
        )

def legacy_to_notegens(generators):
    if isinstance(generators, list):
        return generators
    for tag, obj in generators.items():
        if obj['type'] == "const":
            for args in obj['argslist']:
                args = json_to_args(args)
                yield NoteGen(tag, [args], loop=True)
        if obj['type'] == "poly":
            tracks = [[] for _ in range(max(len(argl) for argl in obj['argslists']))]
            for argl in obj['argslists']:
                for i, args in enumerate(argl):
                    args = json_to_args(args)
                    tracks[i].append(args)
                for i in range(i+1, len(tracks)):
                    tracks[i].append(None)
            for track in tracks:
                yield NoteGen(tag, track, loop=False)

@dataclass(eq=False)
class Tracker:
    label : str
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

    def to_json(self):
        return {
            "type": "tracker",
            "duration": self.duration,
            "rhythm": str(self.rhythm),
            "generators": [gen.to_json() for gen in self.generators],
            "view": self.view.label if self.view is not None else None,
        }
        
    @classmethod
    def from_json(cls, label, obj):
        if 'tree' in obj:
            rhythm = measure.Tree.from_string(obj["tree"])
        else:
            rhythm = measure.from_string(obj["rhythm"])
        return cls(label,
            duration = obj["duration"],
            rhythm = rhythm,
            generators = list(legacy_to_notegens(obj["generators"])),
            view = obj.get("view", None),
        )

@dataclass(eq=False)
class Cell:
    label : str
    multi : bool
    synth : str
    pos : Tuple[int, int]
    params : Dict[str, Union[int, float, music.Pitch]]
    type_param : Optional[str] = None

    def to_json(self):
        return {
            'type': "cell",
            'multi': self.multi,
            'synth': self.synth,
            'pos': tuple(self.pos),
            'params': {name: value_to_json(a) for name,a in self.params.items()},
            'type_param': self.type_param
        }

    @classmethod
    def from_json(cls, label, obj):
        return cls(
            label = label,
            multi = obj['multi'],
            synth = obj['synth'],
            pos = tuple(obj['pos']),
            params = {name: json_to_value(o) for name, o in obj['params'].items()},
            type_param = obj.get('type_param', None))

def json_to_view_lane(obj):
    return {
        "staves": Staves,
        "pianoroll": PianoRoll,
        "grid": Grid,
    }[obj["type"]].from_json(obj)

@dataclass(eq=False)
class PianoRoll:
    bot : int
    top : int
    edit : List[Tuple[str, str]]

    def to_json(self):
        return {
            "type": "pianoroll",
            "bot": self.bot,
            "top": self.top,
            "edit": self.edit
        }
        
    @classmethod
    def from_json(cls, obj):
        return cls(
            bot = obj["bot"],
            top = obj["top"],
            edit = [tuple(o) for o in obj["edit"]],
        )

@dataclass(eq=False)
class Staves:
    count : int
    above : int
    below : int
    edit : List[Tuple[str, str]]

    def to_json(self):
        return {
            "type": "staves",
            "above": self.above,
            "below": self.below,
            "edit": self.edit
        }
        
    @classmethod
    def from_json(cls, obj):
        return cls(
            above = obj["above"],
            below = obj["below"],
            edit = [tuple(o) for o in obj["edit"]],
        )

@dataclass(eq=False)
class Grid:
    kind : str
    edit : List[Tuple[str, str]]

    def to_json(self):
        return {
            "type": "grid",
            "kind": self.kind,
            "edit": self.edit
        }
        
    @classmethod
    def from_json(cls, obj):
        return cls(
            kind = obj["kind"],
            edit = [tuple(o) for o in obj["edit"]],
        )

@dataclass(eq=False)
class View:
    label : str

@dataclass(eq=False)
class TrackerView(View):
    lanes : List[Any]

    def to_json(self):
        return {
            'type': "trackerview",
            'lanes': [lane.to_json() for lane in self.lanes],
        }

    @classmethod
    def from_json(cls, label, obj):
        return cls(
            label = obj['label'],
            lanes = [json_to_view_lane(o) for o in obj['lanes']])

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
        for view in self.views:
            visit(view)
        self.labels = labels

    def construct(self, sequencer, offset, key):
        for i, e in enumerate(self.brushes):
            kv = key + (i,)
            e.brush.construct(sequencer, offset + e.shift, kv)

    def annotate(self, graph_key_map, offset):
        for i, e in enumerate(self.brushes):
            e.brush.annotate(graph_key_map, offset + e.shift)

    def to_json(self):
        brushes = {}
        def visit(brush):
            if brush.label not in brushes:
                brushes[brush.label] = brush.to_json()
                if isinstance(brush, Clip):
                   for e in brush.brushes:
                       visit(e.brush)
        for e in self.brushes:
            visit(e.brush)
        brushes[''] = {
            'type': 'clip',
            'duration': self.duration,
            'brushes': [e.to_json() for e in self.brushes]
        }
        for cell in self.cells:
            brushes[cell.label] = cell.to_json()
        for view in self.views:
            brushes[cell.label] = view.to_json()
        return {
            "brushes": brushes,
            "connections": list(self.connections),
        }

    @classmethod
    def from_json(cls, obj):
        brushes = {label: json_to_brush(label,o) for label, o in obj["brushes"].items()}
        cells = []
        views = {}
        for brush in brushes.values():
            if isinstance(brush, Clip):
                brush.brushes = [Entity.from_json(brushes, e) for e in brush.brushes]
            if isinstance(brush, Tracker):
                brush.view = brushes.get(brush.view, None)
            if isinstance(brush, Cell):
                cells.append(brush)
            if isinstance(brush, View):
                views[brush.label] = brush
        root = brushes.pop("")
        return cls(
            brushes = root.brushes,
            duration = root.duration,
            labels = brushes,
            cells = cells,
            views = views,
            connections = set(tuple(o) for o in obj.get("connections", [])),
        )

    def to_json_str(self):
        return json.dumps(self.to_json())

    @classmethod
    def from_json_str(cls, s):
        return cls.from_json(json.loads(s))

    def to_json_fd(self, fd):
        json.dump(self.to_json(), fd, indent=4)

    @classmethod
    def from_json_fd(cls, fd):
        return cls.from_json(json.load(fd))

    def to_json_file(self, filename):
        with open(filename, "w") as fd:
            self.to_json_fd(fd)

    @classmethod
    def from_json_file(cls, filename):
        with open(filename, "r") as fd:
            return cls.from_json_fd(fd)
