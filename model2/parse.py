from lark import Lark, Transformer, v_args
from .schema import *

from .wadler_lindig import pformat_doc, text, sp, nl, pretty
from fractions import Fraction
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Any
import music

grammar = """
    start: "oscillseq" "aqua" declaration* synths connections

    declaration: CNAME "=" component ";" -> component_decl
               | CNAME "{" entity* "}" -> clip_decl

    entity: number number "gate" CNAME component ";" -> gate_entity
          | number number "quadratic" CNAME component ";" -> quadratic_entity
          | number number "once" CNAME component ";" -> once_entity
          | number number "clip" CNAME           ";" -> clip_entity
          | number "to" number number "pianoroll" CNAME value value ";" -> pianoroll_entity
          | number "to" number number "staves" CNAME staves number ";" -> staves_entity

    staves: /_*\\.+_*/

    synths: "@" "synths" synth+
          | ()
    synth: CNAME CNAME number number "multi" type_param synth_body -> m_synth
         | CNAME CNAME number number         type_param synth_body -> s_synth
    type_param: ("[" CNAME "]")?
    synth_body: "{" "}"
              | "{" synth_param ("," synth_param)* "}"
    synth_param: CNAME "=" value

    connections: "@" "connections" connection ("," connection)*
               | ()
    connection: CNAME ":" CNAME  CNAME ":" CNAME

    component: base_rhythm
           | component "/" group+ badge -> overlay
           | component "rename" CNAME "to" CNAME -> renamed
           | component "repeat" number -> repeated
           | component "duration" number -> durated

    command: "gate" -> gate_command

    badge: "[" CNAME ":" CNAME ":" CNAME "]"

    base_rhythm: west_rhythm
               | euclidean_rhythm
               | step_rhythm
               | "&" CNAME -> rhythm_ref
    
    group: value (":" value)*
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

#    0 10 2 2 pianoroll piano c3 e8;
#    0 10 4 3 staves xxx 1 1 1;
#    0 10 7 2 row yyy;

demo_seq = """oscillseq aqua

hello = q q. e q' q[emf efff e_];
feat = 001010101011;
baz = euclidean 0 5
  repeat 4
  / c4:d4 e5 [note:pitch:piano];

guux {
}

main {
    0 gate foobar &baz;
    0 2 clip guux;
}

@synths
  foobar synthname 0 0 multi [type_param] {
    coprolite = 5,
    funprolite = cs4
  }

@connections
  foob:out scene:out,
  bar:out scene:out
"""

@v_args(inline=True)
class ModelTransformer(Transformer):
    @v_args(inline=False)
    def start(self, group):
        connections  = group[-1]
        synths       = group[-2]
        declarations = group[:-2]
        return Document(declarations, synths, connections)

    def component_decl(self, name, component):
        return CompDecl(str(name), component)

    def clip_decl(self, name, *clip):
        return ClipDecl(str(name), list(clip))

    def gate_entity(self, shift, lane, instrument, component):
        return CommandEntity(shift, lane, "gate", instrument, component)

    def quadratic_entity(self, shift, lane, instrument, component):
        return CommandEntity(shift, lane, "quadratic", instrument, component)

    def once_entity(self, shift, lane, instrument, component):
        return CommandEntity(shift, lane, "once", instrument, component)

    def clip_entity(self, shift, lane, name):
        return ClipEntity(shift, lane, name)

    def pianoroll_entity(self, shift, end, lane, name, bot, top):
        duration = end - shift
        return PianorollEntity(shift, lane, duration, str(name), bot, top)

    def staves_entity(self, shift, end, lane, name, pattern, key):
        duration = end - shift
        above, count, below = pattern
        return StavesEntity(shift, lane, duration, str(name), above, count, below, key)

    def staves(self, pattern):
        count = str(pattern).count(".")
        above, below = map(len, str(pattern).split("."*count))
        return above, count, below

    @v_args(inline=False)
    def synths(self, synths):
        return list(synths)

    def m_synth(self, name, synth, x, y, type_param, params):
        return Synth(str(name), str(synth), (x,y), True, type_param, params)

    def s_synth(self, name, synth, x, y, type_param, params):
        return Synth(str(name), str(synth), (x,y), False, type_param, params)

    def type_param(self, name=None):
        if name is not None:
            return str(name)

    @v_args(inline=False)
    def synth_body(self, params):
        return dict(params)

    def synth_param(self, name, value):
        return str(name), value

    @v_args(inline=False)
    def connections(self, cons):
        return set(cons)

    def connection(self, srcname, srcport, dstname, dstport):
        return ((str(srcname), str(srcport)), (str(dstname), str(dstport)))

    def component(self, rh):
        return rh

    def overlay(self, obj, *group):
        name, dtype, view = group[-1]
        return Overlay(obj, list(group[:-1]), name, dtype, view)

    def renamed(self, obj, src, dst):
        return Renamed(obj, str(src), str(dst))

    def repeated(self, obj, num):
        return Repeated(obj, num)

    def durated(self, obj, num):
        return Durated(obj, num)

    def gate_command(self):
        return "gate"

    def rhythm_ref(self, name):
        return Ref(name)

    def badge(self, x, y, z):
        return str(x), str(y), str(z)

    def group(self, *data):
        return list(data)

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

parser = Lark(grammar, parser="lalr", transformer=ModelTransformer())

def from_string(source):
    return parser.parse(source)

def from_file(pathname):
    with open(pathname, "r", encoding="utf-8") as fd:
        return from_string(fd.read())

if __name__=="__main__":
    tree = parser.parse(demo_seq)
    print(tree)
