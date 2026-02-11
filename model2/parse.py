from lark import Lark, Transformer, v_args
from .wadler_lindig import pformat_doc, text, sp, nl, pretty
from fractions import Fraction
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Any
import music

grammar = """
    start: "oscillseq" "aqua" content (";" content)*

    content: base_rhythm
           | content "/" group+ badge -> overlay
           | content "=" CNAME -> stored
           | content command CNAME -> commanded
           | content "rename" CNAME "to" CNAME -> renamed
           | content "repeat" number -> repeated

    command: "gate" -> gate_command

    badge: "[" CNAME ":" CNAME ":" CNAME "]"

    base_rhythm: west_rhythm
               | euclidean_rhythm
               | step_rhythm
               | "&" CNAME -> rhythm_ref
    
    group: value (":" value)*
         | "_" -> skip
         | "~" -> discard

    value: number
         | pitch

    euclidean_rhythm: "euclidean" number number number?
    step_rhythm: /[01]+/
    west_rhythm: element+

    element: note
           | rest
           | tuplet

    tuplet: duration "[" element+ "]"
    note: duration style? DYNAMIC?
    rest: duration "~"

    style: "'" -> staccato
         | "_" -> tenuto

    duration: NOTE_TYPE modifier*
    modifier: "." -> dot

    DYNAMIC: "ppp" | "pp" | "p" | "mp" | "mf" | "f"  | "ff" | "fff"
    NOTE_TYPE: "x" | "w" | "h" | "q" | "e" | "s" | "t" | "u" | "v"

    int: INT
    signed_int: SIGNED_INT

    %import common.CNAME

    %import common.INT
    %import common.SIGNED_INT

    number: SIGNED_NUMBER
    %import common.SIGNED_NUMBER

    pitch: PIANOLETTER accidental? signed_int
    PIANOLETTER: "c" | "d" | "e" | "f" | "g" | "a" | "b"
    accidental: flat+
              | sharp+
    flat: "b"
    sharp: "s"
    
    %import common.WS
    %ignore WS
"""

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

demo_seq = """oscillseq aqua

q q. e q' q[emf efff e_] ;
001010101011 ;

euclidean 0 5 -6
 rename volume to bass
 repeat 4
 / c4:d4 e5 [note:pitch:piano] =hello gate foobar ;

& hello

"""

@dataclass
class Pattern:
    events : List[Tuple[float, float]]
    values : List[List[Dict[str, Any]]]
    duration : float

    def overlay(self, other : List[List[Dict[str, Any]]]):
        out = []
        L = len(other)
        for i,vg in enumerate(self.values):
            x = []
            for wg in other[i%L]:
                x.append(vg | wg)
            out.append(x)
        return Pattern(self.events, out, self.duration)

@dataclass
class Object:
     def __str__(self):
         return pformat_doc(self.__pretty__(), 80)

     def __repr__(self):
         return str(self)

@dataclass(repr=False)
class Setup(Object):
    contents : List[Any]
    def __pretty__(self):
        return (text(" ;") + sp).join(self.contents)

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
class Component(Object):
    pass

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
        blob = sp.join(text(":").join(x) for x in self.data).group()
        body = (text("/") + sp + blob + sp + text(f"[{self.name}:{self.dtype}:{self.view}]")).group()
        return base + sp + body

@dataclass(repr=False)
class Stored(Component):
    base : Component
    name : str

    def __pretty__(self):
        base = pretty(self.base)
        return base + sp + text("=" + self.name)

@dataclass(repr=False)
class Commanded(Component):
    base : Component
    method : str
    name : str

    def __pretty__(self):
        base = pretty(self.base)
        return base + sp + (text(self.method) + sp + text(self.name)).group()

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

@dataclass
class RhythmConfig:
    beats_per_measure : int = 4
    beat_division : int = 4
    volume : float = -6.0
    staccato : float = 0.25
    normal : float = 0.85
    tenuto : float = 1.0

@dataclass(repr=False)
class WestRhythm(Rhythm):
    sequence : List[Element]

    def to_pattern(self, config : RhythmConfig):
        events = []
        values = []
        rate = 4.0 / config.beat_division / config.beats_per_measure
        t = 0.0
        for note in sequence:
            duration = float(note.duration) * rate
            volume = dynamics_to_dbfs.get(note.dynamic, config.volume)
            match note.style:
                case "staccato":
                    d = duration * config.staccato
                case "tenuto":
                    d = duration * config.tenuto
                case None:
                    d = duration * config.normal
            v = {"volume": volume}
            events.append((t,d))
            values.append([v])
            t += duration
        return Pattern(events, values, start, duration=t)

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
        self.to_step_rhythm().to_west(note)

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

@v_args(inline=True)
class ModelTransformer(Transformer):
    def start(self, *stuff):
        return Setup(stuff)

    def content(self, rh):
        return rh

    def overlay(self, obj, *group):
        name, dtype, view = group[-1]
        return Overlay(obj, list(group[:-1]), name, dtype, view)

    def stored(self, obj, name):
        return Stored(obj, str(name))

    def commanded(self, obj, method, name):
        return Commanded(obj, method, str(name))

    def renamed(self, obj, src, dst):
        return Renamed(obj, str(src), str(dst))

    def repeated(self, obj, num):
        return Repeated(obj, num)

    def gate_command(self):
        return "gate"

    def rhythm_ref(self, name):
        return Ref(name)

    def badge(self, x, y, z):
        return str(x), str(y), str(z)

    def group(self, *data):
        return list(data)

    def keep(self):
        return [None]

    def discard(self):
        return []

    def base_rhythm(self, something):
        return something

    def west_rhythm(self, *elements):
        return WestRhythm(list(elements))

    def step_rhythm(self, sequence):
        return StepRhythm(list(map(int,sequence)))

    def euclidean_rhythm(self, pulses, steps, rotation=0):
        return EuclideanRhythm(pulses, steps, rotation)

    def element(self, something):
        return something

    def value(self, something):
        return something

    def duration(self, note_type, *args):
        duration = str(note_type)
        dots     = 0
        for arg in args:
            match arg:
                case "dot":
                    dots += 1
        return Duration(duration, dots)

    def tuplet(self, duration, *elements):
        return Tuplet(duration, list(elements))

    def note(self, duration, *args):
        style = None
        dynamic = None
        for arg in args:
            if arg == 'tenuto':
                style = 'tenuto'
            elif arg == 'staccato':
                style = 'staccato'
            else:
                dynamic = str(arg)
        return Note(duration, style, dynamic)

    def rest(self, duration):
        return Rest(duration)

    def dot(self, *_):
        return 'dot'

    def staccato(self, *_):
        return 'staccato'

    def tenuto(self, *_):
        return 'tenuto'

    def number(self, n):
        if n.count(".") == 0:
            return int(n)
        return float(n)

    def int(self, n):
        return int(n)

    def signed_int(self, n):
        return int(n)

    def pitch(self, cls, *args):
        cls = "cdefgab".index(cls.lower())
        if len(args) == 2:
            accidental = args[0]
        else:
            accidental = 0
        octave = args[-1]
        position = octave*7 + cls
        return music.Pitch(position, accidental)

    def accidental(self, *n):
        return sum(n)
    
    def sharp(self):
        return +1

    def flat(self):
        return -1

if __name__=="__main__":
    parser = Lark(grammar, parser="lalr", transformer=ModelTransformer())
    tree = parser.parse(demo_seq)
    print(tree)
