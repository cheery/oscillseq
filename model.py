from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
import itertools
import music
import rhythm
import json
import random
import string
import re

_FLOAT_EXPR = r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?"
_FLOAT = re.compile("^" + _FLOAT_EXPR + "$")
_WORD = re.compile(r"^\w+$")
_STRING = re.compile(r'^"[^"]*"?$')

_TOKEN = re.compile("|".join([
    r'#.*$',
    r'(?:\w|\.)+',
    _FLOAT_EXPR,
    r'"[^"]*"?',
    r' +',
    r'.'
]))

class TokenStream:
    def __init__(self, stream):
        self.lineno, self.token = next(stream, (1, None))
        self.stream = stream

    def shift(self):
        token, (self.lineno, self.token) = self.token, next(self.stream, (self.lineno, None))
        return token

    def shift_id(self):
        if self.token == None or self.token == "" or self.token.isspace():
            self.expected("identifier")
        return self.shift()

    def advance(self, token):
        if self.token != token:
            self.expected(token)
        self.shift()

    def expected(self, token):
        got = repr(self.token) if self.token is not None else "end of line"
        this = "new line" if token.isspace() else token
        raise ValueError(f"{self.lineno}: Expected {this}, got {got}")

    def perhaps(self, token):
        if self.token == token:
            self.shift()
            return True
        else:
            return False

    def advance_int(self):
        if (result := self.perhaps_int()) is not None:
            return result
        self.expected("integer")

    def perhaps_int(self):
        try:
            result = int(self.token)
            self.shift()
            return result
        except ValueError:
            return None

    def advance_float(self):
        if (result := self.perhaps_float()) is not None:
            return result
        self.expected("float")

    def perhaps_float(self):
        try:
            result = float(self.token)
            self.shift()
            return result
        except ValueError:
            return None

    def advance_regex(self, regex, sanitized_name):
        if (result := self.perhaps_regex(regex)) is not None:
            return result
        self.expected(sanitized_name)

    def match_regex(self, regex):
        if self.token is not None and (m := regex.match(self.token)) is not None:
            return m.group(0)

    def perhaps_regex(self, regex):
        if self.token is not None and (m := regex.match(self.token)) is not None:
            self.shift()
            return m.group(0)

    def perhaps_match(self, regex):
        if self.token is not None and (m := regex.match(self.token)) is not None:
            self.shift()
            return m

    def on_indent(self, n):
        if self.token is None:
            return False
        elif self.token == "" and n == 0:
            self.shift()
            return True
        elif self.token.isspace() and len(self.token) > n:
            raise ValueError(f"{self.lineno}: Expected lower indent")
        elif self.token.isspace() and len(self.token) == n:
            self.shift()
            return True
        elif self.token.isspace() and len(self.token) < n:
            return False
        elif self.not_indent():
            raise ValueError(f"{self.lineno}: Expected next line at {repr(self.token)}")
        return False

    def not_indent(self):
        if self.token is None:
            return False
        elif self.token == "":
            return False
        elif self.token.isspace():
            return False
        return True

def tokenize_file(filename):
    with open(filename, "r") as fd:
        for lineno, line in enumerate(fd.readlines(), 1):
            yield from tokenize(line, lineno)

def tokenize(s, lineno):
    first = True
    indent = 0
    for token in _TOKEN.findall(s.strip('\r\n')):
        if first:
            first = False
            if token.isspace():
                if len(token) in [4,8]:
                    indent = len(token)
                else:
                    indent = None
        if token.isspace():
            continue
        if indent is not None:
            yield lineno, ' '*indent
            indent = None
        if token.startswith('"'):
            if token.endswith('"'):
                token = token[1:-1]
            else:
                raise ValueError(f'{lineno}: Unterminated string, file corrupted?')
        yield lineno, token

def from_file(filename):
    stream = TokenStream(tokenize_file(filename))
    stream.advance("")
    stream.advance("oscillseq")
    stream.advance("file")
    stream.advance("version")
    if not stream.perhaps("0"):
        raise ValueError(f"version mismatch, there's a new version of oscillseq file format?")

    brushes = {}
    labels  = {}
    cells   = []
    views   = {}
    connections = set()
    def checked_tag():
        if stream.token in labels:
            raise ValueError(f"{stream.lineno}: tag {repr(stream.token)} already declared")
        return stream.shift_id()

    while stream.on_indent(0):
        if stream.perhaps("tracker"):
            tag = checked_tag()
            if stream.token in labels:
                raise ValueError(f"{stream.lineno}: tag already declared")
            duration = stream.advance_int()
            rh = rhythm.from_stream(stream)
            generators, view = generators_from_stream(stream)
            brushes[tag] = labels[tag] = Tracker(tag, duration, rh, generators, view)
        elif stream.perhaps("clip"):
            tag = checked_tag()
            duration = stream.advance_int()
            entities = entities_from_stream(stream)
            brushes[tag] = labels[tag] = Clip(tag, duration, entities)
        elif stream.perhaps("controlpoint"):
            tag = checked_tag()
            target = stream.shift_id()
            transition = stream.perhaps("~")
            value = value_from_stream(stream)
            brushes[tag] = labels[tag] = ControlPoint(tag, target, transition, value)
        elif stream.perhaps("key"):
            tag = checked_tag()
            index = stream.advance_int()
            brushes[tag] = labels[tag] = Key(tag, index)
        elif "" not in labels and stream.perhaps("document"):
            duration = stream.advance_int()
            entities = entities_from_stream(stream)
            brushes[""] = Clip("", duration, entities)
        elif stream.perhaps("cell"):
            tag = checked_tag()
            synth = synth_name_from_stream(stream)
            x = stream.advance_int()
            y = stream.advance_int()
            extra = inline_parameters_from_stream(stream, {"multi":None, "type_param":stream.shift_id})
            params = parameters_list_from_stream(stream)
            cell = Cell(tag, extra["multi"], synth, (x, y), params, extra["type_param"])
            cells.append(cell)
            labels[tag] = cell
        elif stream.perhaps("view"):
            tag = checked_tag()
            lanes = lanes_from_stream(stream)
            views[tag] = labels[tag] = TrackerView(tag, lanes)
        elif stream.perhaps("connections"):
            connections.update(connections_from_stream(stream))
        else:
            raise ValueError(f"{stream.lineno}: Unknown or duplicate/misplaced symbol")

    for brush in brushes.values():
        if isinstance(brush, Clip):
            brush.brushes = [Entity(e.shift, labels[e.brush]) for e in brush.brushes]
        if isinstance(brush, Tracker):
            brush.view = views.get(brush.view, None)
    root = brushes.pop("")
    return Document(
        brushes = root.brushes,
        duration = root.duration,
        labels = labels,
        cells = cells,
        views = views,
        connections = connections)


_LANE_CLASS = re.compile(r"^staves|pianoroll|grid$")

def lanes_from_stream(stream):
    lanes = []
    pos = lambda: int(stream.advance_regex(_POSITIVE, "positive"))
    while stream.on_indent(4):
        flavor = stream.advance_regex(_LANE_CLASS, "staves|pianoroll|grid")
        if flavor == "staves":
            extra = inline_parameters_from_stream(stream, {"count": pos, "above": pos, "below": pos})
            lane = Staves(extra['count'] or 0, extra['above'] or 0, extra['below'] or 0, [])
        elif flavor == "pianoroll":
            extra = inline_parameters_from_stream(stream, {"bot": pos, "top": pos})
            lane = PianoRoll(extra['bot'] or 0, extra['top'] or 0, [])
        elif flavor == "grid":
            kind = stream.shift_id()
            lane = Grid(kind, [])
        while stream.on_indent(8):
            name = stream.shift_id()
            stream.advance(":")
            parameter = stream.shift_id()
            lane.edit.append((name, parameter))
        lanes.append(lane)
    return lanes

def connections_from_stream(stream):
    while stream.on_indent(4):
        src = stream.shift_id()
        while stream.perhaps(":"):
            src += ":" + stream.shift_id()
        dst = stream.shift_id()
        while stream.perhaps(":"):
            dst += ":" + stream.shift_id()
        yield (src, dst)

def synth_name_from_stream(stream):
    name = stream.shift_id()
    while stream.perhaps("/"):
        name += "/" + stream.shift_id()
    return name

def inline_parameters_from_stream(stream, parameter_spec):
    params = {name: None if paramfn is None else False for name, paramfn in parameter_spec.items()}
    encountered = set()
    while stream.token in parameter_spec and stream.token not in encountered:
        name = stream.shift_id()
        if parameter_spec[name]:
            stream.advance(":")
            params[name] = parameter_spec[name]()
        else:
            params[name] = True
        encountered.add(name)
    return params

def parameters_list_from_stream(stream):
    params = {}
    while stream.on_indent(4):
        name = stream.shift_id()
        stream.advance(":")
        params[name] = value_from_stream(stream)
    return params
_TRACK_CLASS = re.compile(r"^note|control|quadratic$")
_NONZERO    = re.compile(r"^[1-9][0-9]*$")
_POSITIVE    = re.compile(r"^[0-9]+$")

def generators_from_stream(stream):
    generators = []
    view = None
    while stream.on_indent(4):
        if flavor := stream.perhaps_regex(_TRACK_CLASS):
            tag  = stream.shift_id()
            loop = stream.perhaps("loop")
            track = track_from_stream(stream)
            generators.append(NoteGen(tag, track, loop, flavor))
        elif stream.perhaps("view"):
            view = stream.shift_id()
        else:
            stream.expected("note|control|quadratic" + "|view"*(view is None))
    return generators, view

def track_from_stream(stream):
    params = defaultdict(list)
    not_present = set()
    while stream.on_indent(8):
        name = stream.shift_id()
        values = params[name]
        stream.advance(":")
        while stream.not_indent():
            np = False
            if stream.perhaps("_"):
                value = None
                np = True
            elif stream.perhaps("x") or stream.perhaps("X"):
                value = None
            elif name != "+":
                value = value_from_stream(stream)
            else:
                self.expected("_ or x")
            if stream.perhaps("*"):
                num = int(stream.advance_regex(_NONZERO, "nonzero number"))
            else:
                num = 1
            for _ in range(num):
                if np:
                    not_present.add(len(values))
                values.append(value)
    track = []
    for i in range(max(map(len, params.values()))):
        args = {}
        for name, values in params.items():
            if values[i % len(values)] is not None:
                args[name] = values[i % len(values)]
        if (i not in not_present) or len(args) > 0:
            args.pop("+", None)
            track.append(args)
        else:
            track.append(None)
    if not track:
        raise ValueError(f"{stream.lineno}: track data missing")
    return track

def entities_from_stream(stream):
    entities = []
    while stream.on_indent(4):
        shift = stream.advance_int()
        while stream.not_indent():
            tag = stream.shift_id()
            entities.append(Entity(shift, tag))
    return entities

_NOTE = re.compile(r"^([A-Ga-g])(s|ss|b|bb|n)?(\d+)$")
_ACCIDENTALS = {"bb": -2, "b": -1, "n": 0, None: 0, "s": 1, "ss": 2}

def value_from_stream(stream):
    if (num := stream.perhaps_int()) is not None:
        return num
    elif (num := stream.perhaps_float()) is not None:
        return num
    elif (m := stream.perhaps_match(_NOTE)):
        pclass = "CDEFGAB".index(m.group(1))
        acc    = _ACCIDENTALS[m.group(2)]
        octave = int(m.group(3))
        return music.Pitch(pclass + octave*7, acc)
    else:
        stream.expected("value")

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

    def copy(self):
        return Entity(self.shift, self.brush)

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

    def copy(self):
        return ControlPoint("", self.tag, self.transition, self.value)

    def __str__(self):
        tr = " ~" if self.transition else ""
        return f"controlpoint {str_tag(self.label)} {str_tag(self.tag)}{tr} {str_value(self.value)}"

@dataclass(eq=False)
class Key:
    label : str
    index : int

    def construct(self, sequencer, offset, key):
        return

    def annotate(self, graph_key_map, offset):
        graph_key_map.append((offset, self.index))

    @property
    def duration(self):
        return 0

    def to_json(self):
        return {
            "type": "key",
            "index": self.index,
        }
        
    @classmethod
    def from_json(cls, label, obj):
        return cls(label,
            index = obj["index"],
        )

    def copy(self):
        return Key("", self.lanes, self.index)

    def __str__(self):
        return f"key {str_tag(self.label)} {self.index}"

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

    def copy(self):
        return Clip("", self.duration, [e.copy() for e in self.brushes])

    def __str__(self):
        return f"clip {str_tag(self.label)} {self.duration}" + "".join(str_entities(self.brushes))

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

    def copy(self):
        return NoteGen(self.tag, [copy_args(a) for a in self.track], self.loop, self.flavor)

    def __str__(self):
        extra = " loop" if self.loop else ""
        return f"{self.flavor} {str_tag(self.tag)}{extra}" + str_track(self.track)

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
            _rhythm = rhythm.from_string(obj["tree"])
        else:
            _rhythm = rhythm.from_string(obj["rhythm"])
        return cls(label,
            duration = obj["duration"],
            rhythm = _rhythm,
            generators = list(legacy_to_notegens(obj["generators"])),
            view = obj.get("view", None),
        )

    def copy(self):
        return Tracker("",
            self.duration,
            rhythm.from_string(str(self.rhythm)),
            [g.copy() for g in self.generators],
            self.view)

    def __str__(self):
        s_view = ""
        if self.view:
            s_view = "\n    view " + str_tag(self.view.label)
        return f"tracker {str_tag(self.label)} {self.duration} {str(self.rhythm)}" + str_generators(self.generators) + s_view

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

    def copy(self):
        return Cell("", self.multi, self.synth, tuple(self.pos), self.params.copy(), self.type_param)

    def __str__(self):
        extra = ""
        if self.multi:
            extra += " multi"
        if self.type_param:
            extra += " type_param:" + str_tag(self.type_param)
        return f"cell {str_tag(self.label)} {str_tag(self.synth)} {int(self.pos[0])} {int(self.pos[1])}{extra}" + str_params(self.params)

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

    def __str__(self):
        extra = ""
        if self.bot:
            extra += " bot:" + str(self.bot)
        if self.top:
            extra += " top:" + str(self.top)
        return f"pianoroll{extra}" + str_edit(self.edit)

@dataclass(eq=False)
class Staves:
    count : int
    above : int
    below : int
    edit : List[Tuple[str, str]]

    def to_json(self):
        return {
            "type": "staves",
            "count": self.count,
            "above": self.above,
            "below": self.below,
            "edit": self.edit
        }
        
    @classmethod
    def from_json(cls, obj):
        return cls(
            count = obj["count"],
            above = obj["above"],
            below = obj["below"],
            edit = [tuple(o) for o in obj["edit"]],
        )

    def __str__(self):
        extra = ""
        if self.count:
            extra += " count:" + str(self.count)
        if self.above:
            extra += " above:" + str(self.above)
        if self.below:
            extra += " below:" + str(self.below)
        return f"staves{extra}" + str_edit(self.edit)

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

    def __str__(self):
        return f"grid {str_tag(self.kind)}" + str_edit(self.edit)

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
            label = label,
            lanes = [json_to_view_lane(o) for o in obj['lanes']])

    def str_lines(self):
        yield f"view {str_tag(self.label)}"
        for lane in self.lanes:
            yield str(lane)

    def __str__(self):
        return "\n    ".join(self.str_lines())

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
        for view in self.views.values():
            brushes[view.label] = view.to_json()
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

    def str_lines(self):
        yield "oscillseq file version 0"
        yield f"document {self.duration}" + "".join(str_entities(self.brushes))
        for brush in self.labels.values():
            yield str(brush)
        yield "\n    ".join(str_connections(self.connections))

    def __str__(self):
        return "\n\n".join(self.str_lines())

def str_connections(connections):
    yield "connections"
    for src, dst in connections:
        src = ":".join(map(str_tag, src.split(":")))
        dst = ":".join(map(str_tag, dst.split(":")))
        yield f"{src} {dst}"

def str_edit(edit):
    def _impl_():
        for src, dst in edit:
            yield "\n        " + str_tag(src) + ":" + str_tag(dst)
    return "".join(_impl_())

def str_entities(entities):
    bins = defaultdict(list)
    for entity in entities:
        bins[entity.shift].append(str_tag(entity.brush.label))
    for shift in sorted(list(bins.keys())):
        yield f"\n    {shift} " + " ".join(bins[shift])

def str_generators(generators):
    def _impl_():
        for gen in generators:
            yield "\n    " + str(gen)
    return "".join(_impl_())

def str_track(track):
    def _impl_():
        rows = set()
        for args in track:
            if args:
                rows.update(args)
        for tag in rows:
            values = ["_"]
            repeats = [0]
            def push(s):
                if values[-1] == s:
                    repeats[-1] += 1
                else:
                    values.append(s)
                    repeats.append(1)
            for args in track:
                if args is None:
                    push("_")
                elif tag in args:
                    push(str_value(args[tag]))
                else:
                    push("x")
            values = [(f"{v}*{r}" if r != 1 else v) for v,r in zip(values, repeats) if r > 0]
            yield f"\n        {str_tag(tag)}:" + " ".join(values)
        return iter(())
    return "".join(_impl_())

def str_tag(label):
    if _WORD.match(label):
        return label
    else:
        s_label = '"' + label + '"'
        if _STRING.match(s_label):
            return s_label
        else:
            raise ValueError("label {repr(label)} contains disallowed characters")

def str_params(params):
    def _impl_():
        for key, value in params.items():
            yield "\n    " + str_tag(key) + ": " + str_value(value)
    return "".join(_impl_())

def str_value(value):
    if isinstance(value, music.Pitch):
        cls = "CDEFGAB"[value.position%7]
        octave = value.position//7
        if value.accidental < 0:
            t = "b" * -value.accidental
        else:
            t = "s" * value.accidental
        return f"{cls}{t}{octave}"
    elif isinstance(value, float):
        return repr(value)
    else:
        return str(value)
