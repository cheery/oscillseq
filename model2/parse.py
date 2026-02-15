from lark import Lark, Transformer, v_args
from .schema import *
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Any
import music

grammar = """
    start: "oscillseq" "aqua" declaration* synths connections

    declaration: CNAME "=" component ";" -> component_decl
               | CNAME "{" (entity ";")* "}" -> clip_decl

    entity: number number "gate" CNAME component -> gate_entity
          | number number "quadratic" CNAME component -> quadratic_entity
          | number number "once" CNAME component -> once_entity
          | number number "slide" CNAME component -> slide_entity
          | number number "clip" CNAME           -> clip_entity
          | number "to" number number "pianoroll" CNAME value value -> pianoroll_entity
          | number "to" number number "staves" CNAME staves number -> staves_entity

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
         | "%" CNAME -> cname_value

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

    cmd: "cont" -> previous
       | "&" CNAME -> by_name
       | SIGNED_NUMBER "," SIGNED_NUMBER ";" -> by_coords
       | cmd "." SIGNED_INT -> by_index
       | cmd "." CNAME      -> attribute
       | cmd "=" "from" cmd -> assign
       | cmd "=" value -> assign
       | cmd "=" component -> assign
       | cmd "=" entity -> assign
       | cmd "clip" -> make_clip
       | cmd "eval" -> make_eval
       | cmd "before" value -> before
       | cmd "before" entity -> before
       | cmd "before" "from" cmd -> before
       | cmd "after" value -> after
       | cmd "after" entity -> after
       | cmd "after" "from" cmd -> after
       | cmd "[" SIGNED_INT "]" -> select_range
       | cmd "[" SIGNED_INT ":" SIGNED_INT "]" -> select_range
       | cmd "west" element* -> replace_selection
       | cmd "up"            -> climb_selection
       | cmd "stack" component -> stack
       | cmd "fill" CNAME group+ -> fill

"""

@v_args(inline=True)
class DataModelTransformer(Transformer):
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

    def slide_entity(self, shift, lane, instrument, component):
        return CommandEntity(shift, lane, "slide", instrument, component)

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

    def cname_value(self, name):
        return CName(name)

data_parser = Lark(grammar, parser="lalr", transformer=DataModelTransformer())

def from_string(source):
    return data_parser.parse(source)

def from_file(pathname):
    with open(pathname, "r", encoding="utf-8") as fd:
        return from_string(fd.read())

@v_args(inline=True)
class CommandModelTransformer(DataModelTransformer):
    def cmd(self, cmd):
        return cmd

    def previous(self):
        return PreviousSelection()

    def assign(self, attribute, obj):
        return Assign(attribute, obj)

    def make_clip(self, selection):
        return MakeClip(selection)

    def make_eval(self, selection):
        return MakeEval(selection)

    def before(self, cmd, obj):
        return Before(cmd, obj)

    def after(self, cmd, obj):
        return After(cmd, obj)

    def select_range(self, cmd, start, stop=None):
        return SelectRange(cmd, start, stop)

    def replace_selection(self, cmd, *elements):
        return ReplaceSelection(cmd, list(elements))

    def climb_selection(self, cmd):
        return ClimbSelection(cmd)

    def stack(self, cmd, component):
        return Stack(cmd, component)

    def fill(self, cmd, name, *data):
        return Fill(cmd, name, list(data))

    def by_name(self, name):
        return ByName(str(name))

    def by_index(self, base, index):
        return ByIndex(base, int(index))

    def by_coords(self, x, y):
        return Coordinates(self.number(x), self.number(y))

    def attribute(self, base, name):
        return AttributeOf(base, str(name))

command_parser = Lark(grammar, parser="lalr", start="cmd", transformer=CommandModelTransformer())

def command_from_string(source):
    return command_parser.parse(source)

print(command_from_string("&HELLO.5.2.1.foo = 0 0 clip foo"))
print(command_from_string("&HELLO.5.2.1.foo = 01010101"))
print(command_from_string("&HELLO.5.2 = 0 5 gate foo euclidean 1 10 repeat 4"))
print(command_from_string("&HELLO.5.2.bar = c4 "))
print(command_from_string("&HELLO.5.2.bar = q q e e "))
print(command_from_string("&HELLO clip "))
print(command_from_string("&HELLO = from &FOOBAR "))
print(command_from_string("&HELLO [5:2] "))
print(command_from_string("&HELLO [5:2] west q q q up"))
print(command_from_string("&HELLO stack &self / 1 [guux:pitch:_]"))
print(command_from_string("&HELLO fill foo 1 2 3"))
print(command_from_string("4, 6; fill foo 1 2 3"))
