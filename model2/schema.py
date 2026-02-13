from .wadler_lindig import pformat_doc, text, sp, nl, pretty
from fractions import Fraction
from dataclasses import dataclass
from typing import Set, List, Tuple, Dict, Optional, Any
import itertools
import random
import string
import music

def random_name():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

note_durations = {
    'w': Fraction(1),
    'h': Fraction(1, 2),
    'q': Fraction(1, 4),
    'e': Fraction(1, 8),
    's': Fraction(1, 16),
    't': Fraction(1, 32),
    'u': Fraction(1, 64),
    'v': Fraction(1, 128),
}

dynamics_to_dbfs = {
    'ppp': -40,
    'pp': -30,
    'p': -20,
    'mp': -12,
    'mf': -6,
    'f': -3,
    'ff': -1,
    'fff': 0
}

@dataclass
class Object:
     def __str__(self):
         return pformat_doc(self.__pretty__(), 80)

     def __repr__(self):
         return str(self)

@dataclass(repr=False)
class Component(Object):
    pass

@dataclass(eq=False, repr=False)
class Declaration(Object):
    name : str

@dataclass(repr=False)
class Entity(Object):
    shift : int
    lane : int

@dataclass(eq=False, repr=False)
class CompDecl(Declaration):
    component  : Component

    def __pretty__(self):
        return (text(self.name) + sp + text("=") + sp + pretty(self.component).nest(2) + text(";")).group()

@dataclass(eq=False, repr=False)
class ClipDecl(Declaration):
    entities : List[Entity]

    def __pretty__(self):
        header = (text(self.name) + sp + text("{")).group()
        tail = nl + text("}")
        return header + (nl + nl.join(self.entities)).nest(2).group() + tail

@dataclass(eq=False, repr=False)
class CommandEntity(Entity):
    flavor : str
    instrument : str
    component : Component

    def __pretty__(self):
        total = pretty(self.shift) + sp + pretty(self.lane)
        total += sp + text(self.flavor)
        total += sp + text(self.instrument)
        total += sp + pretty(self.component)
        total += text(";")
        return total.nest(2).group()

@dataclass(eq=False, repr=False)
class ClipEntity(Entity):
    name : str

    def __pretty__(self):
        return (pretty(self.shift) + sp + pretty(self.lane) + sp + text("clip") + sp + text(self.name) + text(";")).nest(2).group()

@dataclass(eq=False, repr=False)
class PianorollEntity(Entity):
    duration : int
    name : str
    bot : int | float | music.Pitch
    top : int | float | music.Pitch

    def __pretty__(self):
        p = pretty(self.shift) + sp + text("to") + sp + pretty(self.shift + self.duration)
        p += sp + pretty(self.lane)
        p += sp + text("pianoroll")
        p += sp + text(self.name)
        p += sp + pretty(self.bot)
        p += sp + pretty(self.top)
        p += text(";")
        return p.nest(2).group()

@dataclass(eq=False, repr=False)
class StavesEntity(Entity):
    duration : int
    name : str
    above : int
    count : int
    below : int
    key : int

    def __pretty__(self):
        p = pretty(self.shift) + sp + text("to") + sp + pretty(self.shift + self.duration)
        p += sp + pretty(self.lane)
        p += sp + text("staves")
        p += sp + text(self.name)
        p += sp + text("_"*self.above + "."*self.count + "_"*self.below)
        p += sp + pretty(self.key)
        p += text(";")
        return p.nest(2).group()

@dataclass(eq=False, repr=False)
class Synth(Object):
    name : str
    synth : str
    pos : Tuple[int, int]
    multi : bool
    type_param : Optional[str]
    params : Dict[str, int | float | music.Pitch]

    def __pretty__(self):
        header = text(self.name) + sp + text(self.synth)
        header += sp + pretty(self.pos[0]) + sp + pretty(self.pos[1])
        if self.multi:
            header += sp + text("multi")
        if self.type_param:
            header += sp + text("[" + self.type_param + "]")
        params = (text(",") + sp).join(text(name + "=") + pretty(value) for name, value in self.params.items())
        body = text("{") + (nl + params).nest(2).group() + nl + text("}")
        return header.nest(2).group() + sp + body

@dataclass(eq=False, repr=False)
class Document(Object):
    declarations : List[Declaration]
    synths : List[Synth]
    connections : Set[Tuple[Tuple[str, str], Tuple[str, str]]]

    def __pretty__(self):
        out = text("oscillseq aqua") + nl
        for decl in self.declarations:
            out += nl + pretty(decl)
        if self.synths:
            out += nl + nl + text("@synths")
            for synth in self.synths:
                out += (nl + pretty(synth)).nest(2).group()
        if self.connections:
            out += nl + nl + text("@connections")
            xs = []
            for (sname, sport), (dname, dport) in self.connections:
                xs.append(f"{sname}:{sport} {dname}:{dport}")
            out += (nl + (text(",") + nl).join(xs)).nest(2)
        return out

@dataclass
class Pattern:
    events : List[Tuple[float, float]]
    values : List[List[Dict[str, Any]]]
    duration : float
    views : List[Tuple[str, str, str]]

    def overlay(self, other : List[List[Dict[str, Any]]], view : Tuple[str, str, str]):
        out = []
        L = len(other)
        for i,vg in enumerate(self.values):
            x = []
            for w in other[i%L]:
                for v in vg:
                    x.append(v | w)
            out.append(x)
        return Pattern(self.events, out, self.duration, self.views + [view])

@dataclass(repr=False)
class Duration(Object):
    symbol   : str
    dots     : int = 0

    def __float__(self):
        duration = note_durations[self.symbol]
        dot      = duration / 2
        for _ in range(self.dots):
            duration += dot
            dot /= 2
        return float(duration)

    def __pretty__(self):
        return text(self.symbol + "."*self.dots)

@dataclass(repr=False)
class Element(Object):
    pass

@dataclass(repr=False)
class Ref(Component):
    name : str

    def __pretty__(self):
        return text("&" + self.name)

@dataclass(repr=False)
class Overlay(Component):
    base : Component
    data : List[List[Any]]
    name : str
    dtype : str
    view : str

    def to_values(self):
        return [[{self.name: v} for v in vg] for vg in self.data]

    def __pretty__(self):
        base = pretty(self.base)
        def process(x):
            return text(":").join(x) if len(x) > 0 else text("~")
        blob = sp.join(process(x) for x in self.data).group()
        body = (text("/") + sp + blob + sp + text(f"[{self.name}:{self.dtype}:{self.view}]")).group()
        return base + sp + body

@dataclass(repr=False)
class Renamed(Component):
    base : Component
    src : str
    dst : str

    def __pretty__(self):
        base = pretty(self.base)
        return base + sp + text(f"rename {self.src} to {self.dst}")

@dataclass(repr=False)
class Repeated(Component):
    base : Component
    count : int

    def __pretty__(self):
        base = pretty(self.base)
        return base + sp + text(f"repeat {self.count}")

@dataclass(repr=False)
class Durated(Component):
    base : Component
    duration : int | float

    def __pretty__(self):
        base = pretty(self.base)
        return base + sp + text(f"duration {self.duration}")

@dataclass(repr=False)
class Tuplet(Element):
    duration : Duration
    elements : List[Element]

    def __pretty__(self):
        d = pretty(self.duration)
        o = sp.join(self.elements)
        return d + text("[") + o + text("]")

@dataclass(repr=False)
class Note(Element):
    duration : Duration
    style : Optional[str]
    dynamic : Optional[str]

    def __pretty__(self):
        p = pretty(self.duration)
        if self.style:
            p += text({"tenuto":"_", "staccato":"'"}[self.style])
        if self.dynamic:
            p += text(self.dynamic)
        return p

quarter = Note(Duration("q"), None, None)

@dataclass(repr=False)
class Rest(Element):
    duration : Duration

    def __pretty__(self):
        return pretty(self.duration) + text("~")

@dataclass(repr=False)
class Rhythm(Component):
    pass

RhythmConfig = Dict[str, int | float | music.Pitch]

default_rhythm_config = {
    'beats_per_measure': 4,
    'beat_division': 4,
    'volume': -6.0,
    'staccato': 0.25,
    'normal': 0.85,
    'tenuto': 1.00,
}

@dataclass(repr=False)
class WestRhythm(Rhythm):
    sequence : List[Element]

    def to_pattern(self, config : RhythmConfig):
        events = []
        values = []
        def process_note(t, note, duration):
            if isinstance(note, Note):
                volume = dynamics_to_dbfs.get(note.dynamic, config['volume'])
                match note.style:
                    case "staccato":
                        d = duration * config['staccato']
                    case "tenuto":
                        d = duration * config['tenuto']
                    case None:
                        d = duration * config['normal']
                v = {"volume": volume}
                events.append((t,d))
                values.append([v])
            elif isinstance(note, Tuplet):
                subt = t
                subrate = duration / sum(float(n.duration) for n in note.elements)
                for subnote in note.elements:
                    subduration = float(subnote.duration) * subrate
                    process_note(subt, subnote, subduration)
                    subt += subduration
            elif isinstance(note, Rest):
                pass
        t = 0.0
        rate = config['beats_per_measure'] / config['beat_division']
        for note in self.sequence:
            duration = float(note.duration) * rate
            process_note(t, note, duration)
            t += duration
        return Pattern(events, values, duration=t, views=[])

    def __pretty__(self):
        return sp.join(self.sequence)

@dataclass(repr=False)
class StepRhythm(Rhythm):
    sequence : List[int]

    def __pretty__(self):
        return text("".join(map(str,self.sequence)))

    def to_west(self, note=quarter):
        out = []
        for s in self.sequence:
            if s > 0:
                out.append(note)
            else:
                out.append(Rest(note.duration))
        return WestRhythm(out)

@dataclass(repr=False)
class EuclideanRhythm(Rhythm):
    pulses : int
    steps : int
    rotation : int = 0

    def __pretty__(self):
        if self.rotation == 0:
            return (text("euclidean") + sp
                  + text(str(self.pulses)) + sp
                  + text(str(self.steps))).group()
        return (text("euclidean") + sp
              + text(str(self.pulses)) + sp
              + text(str(self.steps)) + sp
              + text(str(self.rotation))).group()

    def to_west(self, note=quarter):
        return self.to_step_rhythm().to_west(note)

    def to_step_rhythm(self):
        table = rotate(bjorklund(self.pulses, self.steps), self.rotation)
        return StepRhythm(table)

def bjorklund(pulses: int, steps: int) -> list[int]:
    """
    Generate a Euclidean rhythm pattern using the Bjorklund algorithm.
    Returns a list of 1s (onsets) and 0s (rests).
    """
    if pulses <= 0:
        return [0] * steps
    if pulses >= steps:
        return [1] * steps
    # Initialize
    pattern = [[1] for _ in range(pulses)] + [[0] for _ in range(steps - pulses)]
    # Repeatedly distribute
    while True:
        # Stop when grouping is no longer possible
        if len(pattern) <= 1:
            break
        # Partition into two parts: first group, rest
        first, rest = pattern[:pulses], pattern[pulses:]
        if not rest:
            break
        # Append each element of rest into first, one by one
        for i in range(min(len(rest), len(first))):
            first[i] += rest[i]
        # Rebuild pattern
        pattern = first + rest[min(len(first), len(rest)):]
    # Flatten
    return list(itertools.chain.from_iterable(pattern))

def rotate(l, n):
    return l[n:] + l[:n]
