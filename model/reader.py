from .schema import *
import re

_FLOAT_EXPR = r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?"
_FLOAT = re.compile("^" + _FLOAT_EXPR + "$")

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
    params = {name: False if paramfn is None else None for name, paramfn in parameter_spec.items()}
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

