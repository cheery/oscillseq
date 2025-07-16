from collections import defaultdict
from .schema import stringify
from .schema import *
import re
import music

_WORD = re.compile(r"^\w+$")
_STRING = re.compile(r'^"[^"]*"?$')

@stringify.register
def ControlPoint_stringify(self : ControlPoint):
    tr = " ~" if self.transition else ""
    return f"controlpoint {stringify(self.label)} {stringify(self.tag)}{tr} {stringify(self.value)}"

@stringify.register
def Key_stringify(self : Key):
    return f"key {stringify(self.label)} {self.index}"

@stringify.register
def Cell_stringify(self : Cell):
    extra = ""
    if self.multi:
        extra += " multi"
    if self.type_param:
        extra += " type_param:" + stringify(self.type_param)
    return f"cell {stringify(self.label)} {stringify(self.synth)} {int(self.pos[0])} {int(self.pos[1])}{extra}" + str_params(self.params)
@stringify.register
def Clip_stringify(self : Clip):
    return f"clip {stringify(self.label)} {self.duration}" + "".join(str_entities(self.brushes))

@stringify.register
def Document_stringify(self : Document):
    def str_lines():
        yield "oscillseq file version 0"
        yield f"document {self.duration}" + "".join(str_entities(self.brushes))
        for brush in self.labels.values():
            yield str(brush)
        yield "\n    ".join(str_connections(self.connections))
    return "\n\n".join(str_lines())

@stringify.register
def Tracker_stringify(self : Tracker):
    s_view = ""
    if self.view:
        s_view = "\n    view " + stringify(self.view.label)
    return f"tracker {stringify(self.label)} {self.duration} {str(self.rhythm)}" + str_generators(self.generators) + s_view

@stringify.register
def NoteGen_stringify(self : NoteGen):
    extra = " loop" if self.loop else ""
    return f"{self.flavor} {stringify(self.tag)}{extra}" + str_track(self.track)

@stringify.register
def TrackerView_stringify(self : TrackerView):
    def str_lines():
        yield f"view {stringify(self.label)}"
        for lane in self.lanes:
            yield stringify(lane)
    return "\n    ".join(str_lines())

@stringify.register
def PianoRoll_stringify(self : PianoRoll):
    extra = ""
    if self.bot:
        extra += " bot:" + str(self.bot)
    if self.top:
        extra += " top:" + str(self.top)
    return f"pianoroll{extra}" + str_edit(self.edit)

@stringify.register
def Staves_stringify(self : Staves):
    extra = ""
    if self.count:
        extra += " count:" + str(self.count)
    if self.above:
        extra += " above:" + str(self.above)
    if self.below:
        extra += " below:" + str(self.below)
    return f"staves{extra}" + str_edit(self.edit)

@stringify.register
def Grid_stringify(self : Grid):
    return f"grid {stringify(self.kind)}" + str_edit(self.edit)


def str_connections(connections):
    yield "connections"
    for src, dst in connections:
        src = ":".join(map(stringify, src.split(":")))
        dst = ":".join(map(stringify, dst.split(":")))
        yield f"{src} {dst}"

def str_edit(edit):
    def _impl_():
        for src, dst in edit:
            yield "\n        " + stringify(src) + ":" + stringify(dst)
    return "".join(_impl_())

def str_entities(entities):
    bins = defaultdict(list)
    for entity in entities:
        bins[entity.shift].append(stringify(entity.brush.label))
    for shift in sorted(list(bins.keys())):
        yield f"\n    {shift} " + " ".join(bins[shift])

def str_generators(generators):
    def _impl_():
        for gen in generators:
            yield "\n    " + stringify(gen)
    return "".join(_impl_())

def str_track(track):
    def _impl_():
        rows = set()
        for args in track:
            if args:
                rows.update(args)
        if not rows and track:
            rows.add('+')
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
                    push(stringify(args[tag]))
                else:
                    push("x")
            values = [(f"{v}*{r}" if r != 1 else v) for v,r in zip(values, repeats) if r > 0]
            yield f"\n        {stringify(tag)}:" + " ".join(values)
    return "".join(_impl_())

def str_params(params):
    def _impl_():
        for key, value in params.items():
            yield "\n    " + stringify(key) + ": " + stringify(value)
    return "".join(_impl_())

@stringify.register
def Str_stringify(self : str):
    if _WORD.match(self):
        return self
    else:
        s_self = '"' + self + '"'
        if _STRING.match(s_self):
            return s_self
        else:
            raise ValueError("{repr(self)} contains disallowed characters")

@stringify.register
def Pitch_stringify(self : music.Pitch):
    cls = "CDEFGAB"[self.position%7]
    octave = self.position//7
    if self.accidental < 0:
        t = "b" * -self.accidental
    else:
        t = "s" * self.accidental
    return f"{cls}{t}{octave}"

@stringify.register
def Float_stringify(self : float):
    return repr(self)

@stringify.register
def Int_stringify(self : int):
    return str(self)
