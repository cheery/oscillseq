from lark import Lark, Transformer, v_args
from .schema import *
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Any
import music
import re

from .sequences import *

_NOTE = re.compile(r"^([A-Ga-g])(s|ss|b|bb|n)?(-?\d+)$")


grammar = r"""
    file: "oscillseq" "aqua" [declarations] [synths] [connections]

    bigcmd: cmd header soup fx* -> attach_brush
          | cmd -> as_it
          | cmd ":=" soup fx* -> write_soup

    cmd: "cont" -> cont
       | () -> cont
       | "mk" identifier -> mk
       | cmd ":" identifier  -> by_name
       | cmd "." identifier -> attr_of
       | cmd "=" value -> assign
       | cmd "remove" -> remove
       | cmd "up" -> up
       | cmd "&" identifier -> attach_clip
       | cmd "@" identifier -> attach_view
       | cmd coordinates -> by_coords
       | cmd "move" coordinates -> move_to
       | cmd "..." coordinates -> search_coords
       | bigcmd ">>" -> as_it
       | cmd "[" value "]" -> index_of
       | cmd "[" value ":" value "]" -> range_of
       | cmd "*" -> by_ref
       | cmd "<" -> lhs_of
       | cmd ">" -> rhs_of
       | cmd "rename" identifier -> rename
       | cmd "connect" connection -> connect
       | cmd "disconnect" connection -> disconnect
       | "synth" identifier -> select_synth
       | cmd "config" coordinates identifier identifier -> set_synth
       | cmd "multi" -> toggle_multi
       | cmd "*" "=" identifier -> set_type_param
       | cmd "eval" -> _eval_
       | cmd "loop" "all" -> all_loop
       | cmd "loop" value [":" value] -> loop_range
       | cmd "cursor" value -> cursor_to

    declarations: declaration+ -> as_list
    declaration: identifier "{" [entities] [properties] "}" -> clipdef

    entities: (entity_line)+ -> as_list

    entity_line: entity ";" -> as_it
               | entity "{" [properties] "}" -> with_properties
 
    entity: coordinates "&" identifier -> clip
          | coordinates "@" identifier -> view
          | coordinates header soup fx* -> brush

    header: "%" "%" -> as_list
          | "%" annotation ("," annotation)* "%" -> as_list
    annotation: identifier [":" identifier] ["@" identifier] -> as_tuple

    fx: "/" values [header soup]
    values: value+ -> as_list

    soup: () -> as_list
        | expr ("," expr)* -> as_list

    expr: duration ["@" style] group -> note
        | "$"                    -> placeholder
        | duration "[" soup fx* "]" -> tuplet
        | "(" soup fx* ")" -> listlet

    style: T_OR_S_OR_G -> as_str
    T_OR_S_OR_G: "s" | "t" | "g"

    duration: "|" number "|" dot* -> duration
            | DLETTER dot*        -> duration_s
            | "*"                 -> duration_nope

    group: cellet* -> as_list

    cellet: [identifier "="] value_cell -> as_tuple
    value_cell: value (":" value)* -> as_list
              | "_"                -> as_none
              | "~"                -> as_list

    dot: "."
    DLETTER: /[xwhqestuv]/

    coordinates: "(" number "," number ")" -> as_tuple

    synths: "@" "synths" synth+ -> as_list
    synth: coordinates identifier identifier [multi] [type_param] "{" [properties] "}"
    multi: "multi" -> as_true
         | ()      -> as_false
    type_param: "[" identifier "]" -> as_it
 
    connections: "@" "connections" connection ("," connection)* -> as_list
    connection: port port -> as_tuple
    port: identifier ":" identifier -> as_tuple
 
    properties: property+ -> as_dict
    property: identifier "=" value ";" -> as_tuple

    value: "&" identifier -> ref
         | number -> as_it
         | identifier -> special
 
    identifier: CNAME -> as_str
    number: SIGNED_NUMBER

    %import common.CNAME
    %import common.INT
    %import common.SIGNED_INT
    %import common.SIGNED_NUMBER

    %import common.WS
    %ignore WS
"""

@v_args(inline=True)
class ModelTransformer(Transformer):
    def file(self, declarations, synths, connections):
        return Document(
            declarations or [],
            synths or [],
            set(connections or []))
 
    def cont(self):
        return Cont()
 
    def mk(self, name):
        return Mk(name)

    def by_name(self, cmd, name):
        return ByName(cmd, name)

    def attr_of(self, sel, a):
        return AttrOf(sel, a)

    def assign(self, cmd, val):
        return Assign(cmd, val)
 
    def remove(self, cmd):
        return Remove(cmd)
 
    def up(self, cmd):
        return Up(cmd)

    def attach_clip(self, cmd, name):
        return AttachClip(cmd, name)

    def attach_view(self, cmd, name):
        return AttachView(cmd, name)

    def attach_brush(self, cmd, header, soup, *fxs):
        expr = read_soup(header, soup, fxs)
        return AttachBrush(cmd, header, expr)

    def write_soup(self, cmd, soup, *fxs):
        return WriteSoup(cmd, soup, fxs)
 
    def by_coords(self, cmd, xy):
        return ByCoords(cmd, *xy)

    def by_ref(self, cmd):
        return ByRef(cmd)

    def move_to(self, cmd, xy):
        return MoveTo(cmd, *xy)

    def search_coords(self, cmd, xy):
        return SearchCoords(cmd, *xy)

    def index_of(self, cmd, i):
        return IndexOf(cmd, i)

    def range_of(self, cmd, i, j):
        return RangeOf(cmd, i, j)

    def lhs_of(self, cmd):
        return LhsOf(cmd)

    def rhs_of(self, cmd):
        return RhsOf(cmd)

    def rename(self, cmd, name):
        return Rename(cmd, name)

    def connect(self, cmd, connection):
        return SetConnection(cmd, connection, True)

    def disconnect(self, cmd, connection):
        return SetConnection(cmd, connection, False)

    def select_synth(self, cmd, name):
        return SelectSynth(name)

    def set_synth(self, cmd, xy, synth):
        return SetSynth(cmd, xy, synth)

    def toggle_multi(self, cmd):
        return ToggleMulti(cmd)

    def set_type_param(self, cmd, type_param):
        return SetTypeParam(cmd, type_param)

    @v_args(inline=True)
    def _eval_(self, cmd):
        return Eval(cmd)

    def all_loop(self, cmd):
        return LoopAll(cmd)

    def loop_range(self, cmd, start, stop=None):
        return Loop(cmd, start, stop or start + 1)

    def cursor_to(self, cmd, head):
        return CursorTo(cmd, head)

    def clipdef(self, name, entities, properties):
        return ClipDef(name, properties or {}, entities or [])

    def with_properties(self, entity, properties):
        entity.properties.update(properties)
        return entity

    def clip(self, coordinates, name):
        shift, lane = coordinates
        return ClipEntity(shift, lane, {}, name)

    def view(self, coordinates, name):
        shift, lane = coordinates
        return ViewEntity(shift, lane, {}, name)

    def brush(self, coordinates, header, soup, *fxs):
        shift, lane = coordinates
        elements = read_soup(header, soup, fxs)
        return BrushEntity(shift, lane, {}, header, elements)

    def fx(self, args, header=None, soup=None):
        return FxProto(args, header or [], soup or [])

    def listlet(self, soup, *fxs):
        return ListletProto(soup, fxs)

    def tuplet(self, duration, soup, *fxs):
        return TupletProto(duration, soup, fxs)

    def attr(self, name, value):
        return AttrProto(name, value)

    def note(self, duration, style, group):
        return NoteProto(duration, style, group)

    def placeholder(self):
        return Placeholder()
 
    def tuplet(self, duration, soup, *fxs):
        return TupletProto(duration, soup, fxs)

    def listlet(self, soup, *fxs):
        return ListletProto(soup, fxs)

    def duration(self, note, *dots):
        return Duration(note, len(dots))

    def duration_s(self, note, *dots):
        return Duration(str(note), len(dots))

    def duration_nope(self):
        return None
 
    def synth(self, xy, name, synth, multi, type_param, params):
        return Synth(xy, name, synth, multi, type_param, params or {})
 
    def special(self, s):
        _ACCIDENTALS = {"bb": -2, "b": -1, "n": 0, None: 0, "s": 1, "ss": 2}
        if g := _NOTE.match(s):
            pc = "cdefgab".index(g.group(1).lower())
            acc    = _ACCIDENTALS[g.group(2)]
            octave = int(g.group(3))
            return music.Pitch(pc + octave*7, acc)
        if s in dynamics_to_dbfs:
            return Dynamic(s)
        return Unk(s)
 
    def number(self, value):
        if value.count(".") == 0:
            return int(value)
        return float(value)
 
    def as_tuple(self, *sequence):
        return sequence

    @v_args(inline=False)
    def as_list(self, sequence):
        return sequence

    @v_args(inline=False)
    def as_dict(self, sequence):
        return dict(sequence)

    def as_str(self, value):
        return str(value)

    def as_it(self, value):
        return value

    def as_true(self, *_):
        return True

    def as_false(self, *_):
        return True

    def as_none(self, *_):
        return None

file_parser = Lark(grammar, parser="lalr", start="file", transformer=ModelTransformer())
command_parser = Lark(grammar, parser="lalr", start="bigcmd", transformer=ModelTransformer())
 
def from_string(source):
    return file_parser.parse(source)

def from_file(pathname):
    with open(pathname, "r", encoding="utf-8") as fd:
        return from_string(fd.read())
 
def command_from_string(source):
    return command_parser.parse(source)

stuff = """
oscillseq aqua

moin {
    (0, 0) %note:pitch, foo:int% q c3, |1| 59, q t 32, q s 70 stuf=9 ;
    (0, 1) %note:pitch, foo:int% (q c3, |1| 59), q t 32, q s 70 stuf=9 ;
    (0, 2) %note:pitch, foo:int% (q c3, |1| 59 / foobar %% w, w), q t 32, q s 70 stuf=9 ;
    (0, 3) %note:pitch, foo:int% |4| [q c3, |1| 59 / ksk 5], q t 32, q s 70 stuf=9 ;
}
"""
 
if __name__=="__main__":
    document = from_string(stuff)
    cont = None
    cont, detail, _ = command_from_string("mk main").apply(document, cont, document)
    cont, detail, _ = command_from_string("cont.foo").apply(document, cont, document)
    cont, detail, _ = command_from_string("cont = c4").apply(document, cont, document)
    cont, detail, _ = command_from_string("cont").apply(document, cont, document)
    cont, detail, _ = command_from_string("cont up").apply(document, cont, document)
    cont, detail, _ = command_from_string("mk baaz").apply(document, cont, document)
    cont, detail, _ = command_from_string("cont (1, 0) &main").apply(document, cont, document)
    cont, detail, _ = command_from_string("mk guux").apply(document, cont, document)
    cont, detail, _ = command_from_string("cont (1, 4) &baaz").apply(document, cont, document)
    cont, detail, _ = command_from_string(":guux ... (2, 6) remove &raaz").apply(document, cont, document)
    cont, detail, _ = command_from_string(":guux remove").apply(document, cont, document)
    cont, detail, _ = command_from_string(":baaz remove").apply(document, cont, document)
    cont, detail, _ = command_from_string(":main (0, 5) @hmmm").apply(document, cont, document)
    cont, detail, _ = command_from_string(":main (0, 6) %% q, q, q ").apply(document, cont, document)
    cont, detail, _ = command_from_string(":main (0, 6) [1:3]").apply(document, cont, document)
    cont, detail, _ = command_from_string(":moin (0, 2) [0] [0:1]").apply(document, cont, document)
    cont, detail, _ = command_from_string(":moin (0, 2) [0] < [0:5]").apply(document, cont, document)
    cont, detail, hdr = command_from_string(":moin (0, 2) [0] < [0:2] := q, q, q / fakka").apply(document, cont, document)
    cont, detail, hdr = command_from_string(":moin (0, 2) [0] < > := q").apply(document, cont, document)
    cont, detail, hdr = command_from_string(":moin (0, 2) [0] < > := q").apply(document, cont, document)

    print(document)
    if cont is not None:
        print(">>> " + str(cont))
    if isinstance(detail, Expr):
        print("is: " + pformat_doc(detail.formatted(hdr, False), 80))
    elif detail is not None:
        print("is: " + str(detail))
