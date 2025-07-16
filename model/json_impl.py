from .schema import to_json
from .schema import *
import rhythm
import music
import json

@to_json.register
def Entity_to_json(self : Entity):
    return {"shift": self.shift, "brush": self.brush.label}

def Entity_from_json(brushes, obj):
    return Entity(
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
        "clip": Clip_from_json,
        "clap": Tracker_from_json,
        "tracker": Tracker_from_json,
        "controlpoint": ControlPoint_from_json,
        "key": Key_from_json,
        "cell": Cell_from_json,
        "trackerview": View_from_json,
    }[obj["type"]](label, obj)

@to_json.register
def ControlPoint_to_json(self : ControlPoint):
    return {
        "type": "controlpoint",
        "tag": self.tag,
        "transition": self.transition,
        "value": value_to_json(self.value)
    }
        
def ControlPoint_from_json(label, obj):
    return ControlPoint(label,
        tag = obj["tag"],
        transition = obj["transition"],
        value = json_to_value(obj["value"])
    )

@to_json.register
def Key_to_json(self : Key):
    return {
        "type": "key",
        "index": self.index,
    }
        
def Key_from_json(label, obj):
    return Key(label, index = obj["index"])

@to_json.register
def Clip_to_json(self : Clip):
    return {
        "type": "clip",
        "duration": self.duration,
        "brushes": [b.to_json() for b in self.brushes]
    }
        
def Clip_from_json(label, obj):
    return Clip(label,
        duration = obj['duration'],
        brushes = obj['brushes']
    )

def json_to_gen(obj):
    return {
        "note": NoteGen_from_json,
        "control": NoteGen_from_json,
        "quadratic": NoteGen_from_json,
    }[obj["type"]](obj)

def args_to_json(args):
    if args is not None:
        return {name: value_to_json(a) for name, a in args.items()}

def json_to_args(obj):
    if obj is not None:
        return {name: json_to_value(o) for name, o in obj.items()}

@to_json.register
def NoteGen_to_json(self : NoteGen):
    return {
        "type": self.flavor,
        "tag": self.tag,
        "track": [args_to_json(args) for args in self.track],
        "loop": self.loop,
    }
        
def NoteGen_from_json(obj):
    return NoteGen(
        tag = obj["tag"],
        track = [json_to_args(args) for args in obj["track"]],
        loop = obj["loop"],
        flavor = obj["type"]
    )

def legacy_to_notegens(generators):
    if isinstance(generators, list):
        for generator in generators:
            yield json_to_gen(generator)
    else:
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

@to_json.register
def Tracker_to_json(self : Tracker):
    return {
        "type": "tracker",
        "duration": self.duration,
        "rhythm": str(self.rhythm),
        "generators": [gen.to_json() for gen in self.generators],
        "view": self.view.label if self.view is not None else None,
    }
        
def Tracker_from_json(label, obj):
    if 'tree' in obj:
        _rhythm = rhythm.from_string(obj["tree"])
    else:
        _rhythm = rhythm.from_string(obj["rhythm"])
    return Tracker(label,
        duration = obj["duration"],
        rhythm = _rhythm,
        generators = list(legacy_to_notegens(obj["generators"])),
        view = obj.get("view", None)
    )

@to_json.register
def Cell_to_json(self : Cell):
    return {
        'type': "cell",
        'multi': self.multi,
        'synth': self.synth,
        'pos': tuple(self.pos),
        'params': {name: value_to_json(a) for name,a in self.params.items()},
        'type_param': self.type_param
    }

def Cell_from_json(label, obj):
    return Cell(
        label = label,
        multi = obj['multi'],
        synth = obj['synth'],
        pos = tuple(obj['pos']),
        params = {name: json_to_value(o) for name, o in obj['params'].items()},
        type_param = obj.get('type_param', None)
    )

def json_to_view_lane(obj):
    return {
        "staves": Staves_from_json,
        "pianoroll": PianoRoll_from_json,
        "grid": Grid_from_json,
    }[obj["type"]](obj)

@to_json.register
def PianoRoll_to_json(self : PianoRoll):
    return {
        "type": "pianoroll",
        "bot": self.bot,
        "top": self.top,
        "edit": self.edit
    }
        
def PianoRoll_from_json(obj):
    return PianoRoll(
        bot = obj["bot"],
        top = obj["top"],
        edit = [tuple(o) for o in obj["edit"]],
    )

@to_json.register
def Staves_to_json(self : Staves):
    return {
        "type": "staves",
        "count": self.count,
        "above": self.above,
        "below": self.below,
        "edit": self.edit
    }
        
def Staves_from_json(obj):
    return Staves(
        count = obj["count"],
        above = obj["above"],
        below = obj["below"],
        edit = [tuple(o) for o in obj["edit"]],
    )

@to_json.register
def Grid_to_json(self : Grid):
    return {
        "type": "grid",
        "kind": self.kind,
        "edit": self.edit
    }
        
def Grid_from_json(obj):
    return Grid(
        kind = obj["kind"],
        edit = [tuple(o) for o in obj["edit"]],
    )

@to_json.register
def View_to_json(self : View):
    return {
        'type': "trackerview",
        'lanes': [lane.to_json() for lane in self.lanes],
    }

def View_from_json(label, obj):
    return View(
        label = label,
        lanes = [json_to_view_lane(o) for o in obj['lanes']])

@to_json.register
def Document_to_json(self : Document):
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
    for view in self.views.values():
        brushes[view.label] = view.to_json()
    return {
        "brushes": brushes,
        "connections": list(self.connections),
    }

def Document_from_json(obj):
    brushes = {label: json_to_brush(label,o) for label, o in obj["brushes"].items()}
    cells = []
    views = {}
    for brush in brushes.values():
        if isinstance(brush, Clip):
            brush.brushes = [Entity_from_json(brushes, e) for e in brush.brushes]
        if isinstance(brush, Tracker):
            brush.view = brushes.get(brush.view, None)
        if isinstance(brush, Cell):
            cells.append(brush)
        if isinstance(brush, View):
            views[brush.label] = brush
    root = brushes.pop("")
    return Document(
        brushes = root.brushes,
        duration = root.duration,
        labels = brushes,
        cells = cells,
        views = views,
        connections = set(tuple(o) for o in obj.get("connections", [])),
    )

def to_json_str(self):
    return json.dumps(self.to_json())

def from_json_str(s):
    return Document_from_json(json.loads(s))

def to_json_fd(doc, fd):
    json.dump(to_json(doc), fd, indent=4)

def from_json_fd(fd):
    return Document_from_json(json.load(fd))

def to_file(doc, filename):
    with open(filename, "w") as fd:
        to_json_fd(doc, fd)

def from_file(filename):
    with open(filename, "r") as fd:
        return from_json_fd(fd)
