from .wadler_lindig import pformat_doc, text, sp, nl, pretty
from .sequences import empty, SequenceNode
from fractions import Fraction
from dataclasses import dataclass
from typing import Set, List, Tuple, Dict, Optional, Any
import itertools
import random
import string
import music

@dataclass
class Object:
     def __str__(self):
         return pformat_doc(self.__pretty__(), 80)

     def __repr__(self):
         return str(self)

## ANNOTATIONS
Annotation = Tuple[str, str | None, str | None]

## VALUES
@dataclass
class Ref(Object):
    name : str
    def __pretty__(self):
        return text("&" + self.name)

@dataclass
class Dynamic(Object):
    name : str

    def __float__(self):
        return dynamics_to_dbfs[self.name]

    def __pretty__(self):
        return text(self.name)

@dataclass
class Unk(Object):
    name : str
    def __pretty__(self):
        return text(self.name)

Value = int | float | music.Pitch | Ref | Dynamic | Unk
Number = int | float

## BASE CLASSES
@dataclass(eq=False, repr=False)
class Action(Object):
    pass

@dataclass(eq=False, repr=False)
class Declaration(Object):
    name : str
    properties : Dict[str, Value]

@dataclass(eq=False, repr=False)
class Expr(Object):
    def __pretty__(self):
        return self.formatted([], False)

@dataclass(eq=False, repr=False)
class Command(Object):
    pass

@dataclass(eq=False, repr=False)
class Entity(Object):
    shift : int | float
    lane  : int | float
    properties : Dict[str, Value]

## DURATION AND ELEMENTS
@dataclass(repr=False)
class Duration(Object):
    symbol   : str | int
    dots     : int = 0

    def __pretty__(self):
        if isinstance(self.symbol, int):
            return text("|" + str(self.symbol) + "|" + "."*self.dots)
        return text(self.symbol + "."*self.dots)

## EXPRESSIONS (ANNOTATED)
Cell = Dict[str, List[Value]]

def formatted(header, seq, inside):
    inside = seq.length > 1 or inside
    return text(", ").join(item.formatted(header, inside) for item in seq)

def formatted_range(header, seq, inside, start, stop):
    inside = seq.length > 1 or inside
    return text(", ").join(item.formatted(header, inside) for item in seq.sequence(start, stop))

def evaluate_all(config, exprs):
    out = empty
    for expr in exprs:
        expr = expr.evaluate(config)
        out = out.insert(out.length, expr)
    return out

def combine_headers(a, b):
    a = list(a)
    cols = dict((x[0],i) for i, x in enumerate(a))
    for name, dtype, view in b:
        if name in cols:
            name, dtype2, view2 = a[cols[name]]
            a[cols[name]] = name, dtype or dtype2, view or view2
        else:
            cols[name] = len(a)
            a.append((name, dtype, view))
    return a

def is_rest(group):
    return any(len(v)==0 for v in group.values())

@dataclass(eq=False, repr=False)
class Fx(SequenceNode):
    lhs : SequenceNode
    args : List[Value]
    header : List[Annotation]
    rhs : SequenceNode

    def retain(self, left, right):
        return Fx(left, right, self.lhs, self.args, self.header, self.rhs)

    @classmethod
    def mk(cls, lhs, args, header, rhs):
        return cls(empty, empty, lhs, args, header, rhs)

    def formatted(self, header, inside):
        out = formatted(header, self.lhs, False) + text(" / ")
        out += sp.join(self.args)
        if self.rhs.length > 0 or self.header:
            out += sp + format_annotations(self.header)
            out += formatted(self.header, self.rhs, True)
        if inside:
            return text("(") + out + text(")")
        return out

    def __str__(self):
        return pformat_doc(formatted([], self, True), 80)

    def evaluate(self, config):
        lhs = evaluate_all(config, self.lhs)
        rhs = evaluate_all(config, self.rhs)
        assert self.args
        if self.args[0].name == "euclidean" and len(self.args) == 3:
            pulses = self.args[1]
            steps = self.args[2]
            out = empty
            for x in bjorklund(pulses, steps):
                if x > 0:
                    note = Note.mk(Duration(1,0), None, {})
                else:
                    note = Note.mk(Duration(1,0), None, {"":[]})
                out = out.insert(out.length, note)
            return out
        if self.args[0].name == "repeat" and len(self.args) == 2:
            count = self.args[1]
            out = empty
            for i in range(count):
                for x in lhs:
                    out = out.insert(out.length, x.retain(empty, empty))
            return out
        if self.args[0].name == "rotate" and len(self.args) == 2:
            amount = self.args[1]
            out = empty
            for x in rotate(list(lhs), amount):
                out = out.insert(out.length, x.retain(empty, empty))
            return out
        if self.args[0].name == "retrograde" and len(self.args) == 2:
            amount = self.args[1]
            def reverse_all(xs):
                out = empty
                for x in reversed(list(lhs)):
                    if isinstance(x, Tuplet):
                        x = Tuplet.mk(x.duration, reverse_all(x.mhs))
                    out = out.insert(out.length, x.retain(empty, empty))
                return out
            return reverse_all(lhs)
        if self.args[0].name == "ostinato":
            ostinato = list(rhs)
            k = 0
            def apply_ostinato(xs):
                nonlocal k
                out = empty
                for x in list(xs):
                    if isinstance(x, Note) and not is_rest(x.group):
                        o = ostinato[k % len(ostinato)]
                        k += 1
                        gg = x.group.copy()
                        for name, values in o.group.items():
                            gg[name] = gg.get(name,[]) + values
                        x = Note.mk(o.duration or x.duration,
                            x.style or o.style,
                            gg)
                    if isinstance(x, Tuplet):
                        x = Tuplet.mk(x.duration, apply_ostinato(x.mhs))
                    out = out.insert(out.length, x.retain(empty, empty))
                return out
            return apply_ostinato(lhs)
        out = empty
        for x in self.args[0].name:
            if x == "T":
                note = Note.mk(Duration(1,0), None, {})
            else:
                note = Note.mk(Duration(1,0), None, {"":[]})
            out = out.insert(out.length, note)
        return out

@dataclass(eq=False, repr=False)
class Note(SequenceNode):
    duration : Duration | None
    style : str | None
    group : Cell

    def retain(self, left, right):
        return Note(left, right, self.duration, self.style, self.group)

    @classmethod
    def mk(cls, duration, style, group):
        return cls(empty, empty, duration, style, group)
 
    def formatted(self, header, inside):
        hax = pformat_doc(self.__hack__(header), 80)
        return text(hax.strip())
 
    def __hack__(self, header):
        d = text("*") if self.duration is None else pretty(self.duration)
        if not self.style:
            return d + text(" ") + format_group(self.group, header)
        return d + text(f"@{self.style} ") + format_group(self.group, header)

    def __str__(self):
        return pformat_doc(formatted([], self, True), 80)

    def evaluate(self, config):
        return self.retain(empty, empty)

@dataclass(eq=False, repr=False)
class Tuplet(SequenceNode):
    duration : Duration | None
    mhs : SequenceNode

    def retain(self, left, right):
        return Tuplet(left, right, self.duration, self.mhs)

    @classmethod
    def mk(cls, duration, mhs):
        return cls(empty, empty, duration, mhs)

    def formatted(self, header, inside):
        d = text("*") if self.duration is None else pretty(self.duration)
        return d + text("[") + formatted(header, self.mhs, False) + text("]")

    def __str__(self):
        return pformat_doc(formatted([], self, True), 80)

    def evaluate(self, config):
        mhs = evaluate_all(config, self.mhs)
        return Tuplet.mk(self.duration, mhs)

## FABRIC
Connection = Tuple[Tuple[str, str], Tuple[str, str]]

@dataclass(eq=False, repr=False)
class Synth(Object):
    pos : Tuple[int, int]
    name : str
    synth : str
    multi : bool
    type_param : Optional[str]
    params : Dict[str, Value]

    def reset(self, pos=None, name=None, synth=None, multi=None, type_param=None, params=None):
        if pos is None:
            pos = self.pos
        if name is None:
            name = self.name
        if synth is None:
            synth = self.synth
        if multi is None:
            multi = self.multi
        if type_param is None:
            type_param = self.type_param
        if params is None:
            params = self.params
        return Synth(pos, name, synth, multi, type_param, params)
 
    def __pretty__(self):
        header = format_coordinates(*self.pos) + sp + text(self.name) + sp + text(self.synth)
        if self.multi:
            header += sp + text("multi")
        if self.type_param:
            header += sp + text("[" + self.type_param + "]")
        params = nl.join(text(name + "=") + pretty(value) + text(";") for name, value in self.params.items())
        body = text("{") + (nl + params).nest(2).group() + nl + text("}")
        return header.nest(2).group() + sp + body

## DOCUMENT MODEL
@dataclass(eq=False, repr=False)
class Document(Object):
    declarations : List[Declaration]
    synths : List[Synth]
    connections : Set[Connection]

    def reset(self, declarations=None, synths=None, connections=None):
        if declarations is None:
            declarations = self.declarations
        if synths is None:
            synths = self.synths
        if connections is None:
            connections = self.connections
        return Document(declarations, synths, connections)

    def __pretty__(self):
        out = text("oscillseq aqua")
        for decl in self.declarations:
            out += nl + nl + pretty(decl)
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

## DECLARATIONS
@dataclass(eq=False, repr=False)
class ClipDef(Declaration):
    entities : List[Entity]

    def reset(self, name=None, properties=None, entities=None):
        if name is None:
            name = self.name
        if properties is None:
            properties = self.properties
        if entities is None:
            entities = self.entities
        return ClipDef(name, properties, entities)

    def __pretty__(self):
        head = text(self.name + " {")
        entities = [nl + pretty(e) + format_entity_properties(e)
            for e in self.entities]
        properties = [nl + pretty(n) + text("=") + pretty(p) + text(";")
            for n, p in self.properties.items()]
        return (head
            + text("").join(entities + properties).nest(2)
            + nl + text("}"))

def format_entity_properties(e):
    if len(e.properties) == 0:
        return text(";")
    else:
        properties = [nl + pretty(n) + text("=") + pretty(p) + text(";")
            for n, p in e.properties.items()]
        return text(" {") + text("").join(properties).nest(2) + nl + text("}")

## FINGERS
@dataclass(eq=False, repr=False)
class Finger:
    def to_command(self):
        raise NotImplemented

    def write(self):
        raise NotImplemented

    def writeback(self):
        raise NotImplemented

    def reapply(self, doc):
        raise Exception(f"reapply not supported on: {self.to_command()}")

    #def by_coords(self, shift, lane):
    #    raise Exception(f"Cannot coordinate from: {self.to_command()}")

    #def read_value(self):
    #    raise Exception(f"Cannot present as value: {self.to_command()}")

    #def attach(self, cls, *args):
    #    raise Exception(f"Cannot attach to: {self.to_command()}")

    def assign(self, value):
        raise Exception(f"Cannot assign to: {self.to_command()}")

    def remove(self):
        raise Exception(f"Cannot remove: {self.to_command()}")

    def get_header(self):
        raise Exception(f"Cannot sequence to: {self.to_command()}")

    def get_config_views(self, base):
        return base, {}

    def get_track_selection(self):
        raise Exception(f"No track selection: {self.to_command()}")

    #def write_attribute(self, name, value):
    #    raise Exception(f"Cannot write attribute to: {self.to_command()}")

    #def write_entity(self, name, value):
    #    raise Exception(f"Cannot write entity to: {self.to_command()}")

@dataclass(eq=False, repr=False)
class DeepFinger(Finger):
    parent : Finger

    def writeback(this):
        while isinstance(this, DeepFinger):
            this = this.write()
        return this.write()

    def read_attribute(self, name):
        return self.write().read_attribute(name)

    def read_declaration(self, name):
        return self.write().read_declaration(name)

    def write_declaration(self, name, declaration):
        return self.write().write_declaration(name, declaration)

    def get_config_views(self, base):
        return self.parent.get_config_views(base)

@dataclass(eq=False, repr=False)
class DocumentFinger(Finger):
    doc : Document

    def __post_init__(self):
        assert isinstance(self.doc, Document)

    def to_command(self):
        return Cont()

    def write(self):
        return self.doc

    def writeback(self):
        return self.write()

    def reapply(self, doc):
        return DocumentFinger(doc)

    def read_declaration(self, name):
        for this in self.doc.declarations:
            if this.name == name:
                return DeclarationFinger(self, this)
        raise Exception(f"No such declaration as {name!r}")

    def write_declaration(self, name, declaration):
        new_declarations = []
        for this in self.doc.declarations:
            if this.name == name:
                if declaration is not None:
                    new_declarations.append(declaration)
                name = None
            else:
                new_declarations.append(this)
        if name is not None and declaration is not None:
            new_declarations.append(declaration)
        return DocumentFinger(self.doc.reset(declarations=new_declarations))

def get_by_coords(clip, shift, lane):
    for entity in reversed(clip.entities):
        if entity.shift <= shift and entity.lane == lane:
            return entity
    return None

def do_search(root, shift, lane):
    doc  = root.writeback()
    root = root.reapply(doc)
    if isinstance(root, DeclarationFinger) and not isinstance(root.declaration, ClipDef):
        raise Exception(f"cannot initiate search from non-clip declaration: {root.to_command()}")
    def by_clip(finger, entity):
        finger = CoordsFinger(finger, entity.shift, entity.lane, entity)
        if isinstance(entity, ClipEntity):
            for declaration in doc.declarations:
                if isinstance(declaration, ClipDef) and declaration.name == entity.name:
                    return ClipFinger(finger, declaration)
        return None
    unvisited = [(root, shift, lane)]
    best = None
    this = None
    while unvisited:
        finger, shift, lane = unvisited.pop()
        if isinstance(finger, DeclarationFinger):
            entities = finger.declaration.entities
        else:
            entities = finger.clip.entities
        for entity in entities:
            if entity.shift <= shift and entity.lane <= lane:
                dist = lane-entity.lane, shift-entity.shift
                if deeper := by_clip(finger, entity):
                    unvisited.append((deeper, shift - entity.shift, lane - entity.lane))
                elif best is None or dist < best:
                    best = dist
                    this = CoordsFinger(finger, entity.shift, entity.lane, entity)
    if this is None:
        raise Exception(f"the given clip is empty at this location: {root.to_command()}")
    return this

def check_cycles(entity, doc, target):
    if isinstance(entity, ClipEntity):
        if entity.name == target:
            return True
        for declaration in doc.declarations:
            if declaration.name == entity.name:
                for subentity in declaration.entities:
                    if check_cycles(subentity, doc, target):
                        return True
    return False

@dataclass(eq=False, repr=False)
class DeclarationFinger(DeepFinger):
    declaration : Declaration

    def to_command(self):
        cmd = self.parent.to_command()
        return ByName(cmd, self.declaration.name)

    def write(self):
        return self.parent.write_declaration(self.declaration.name, self.declaration)

    def reapply(self, doc):
        return self.parent.reapply(doc).read_declaration(self.declaration.name)

    def read_attribute(self, name):
        return AttributeFinger(self, name, self.declaration.properties.get(name, Unk("none")))

    def write_attribute(self, name, value):
        properties = self.declaration.properties.copy()
        properties.pop(name, None)
        if value != Unk("none"):
            properties[name] = value
        return DeclarationFinger(self.parent, self.declaration.reset(properties=properties))

    def remove(self):
        return self.parent.write_declaration(self.declaration.name, None)

    def by_coords(self, shift, lane):
        if not isinstance(self.declaration, ClipDef):
            return super().by_coords(shift, lane)
        entity = get_by_coords(self.declaration, shift, lane)
        return CoordsFinger(self, shift, lane, entity)

    def search(self, shift, lane):
        return do_search(self, shift, lane)

    def check_entity(self, entity):
        if not isinstance(self.declaration, ClipDef):
            return super().check_entity(entity)
        doc = self.writeback()
        if check_cycles(entity, doc, self.declaration.name):
            raise Exception(f"Attaching clip entity here would cause a cycle")
        return CoordsFinger(self, entity.shift, entity.lane, entity)

    def write_entity(self, entity, new_entity=None):
        if not isinstance(self.declaration, ClipDef):
            return super().write_entity(entity, new_entity)
        new_entities = [e for e in self.declaration.entities if (e.shift,e.lane) != (entity.shift,entity.lane)]
        if new_entity is not None:
            new_entities.append(new_entity)
            new_entities.sort(key=lambda e: (e.lane, e.shift))
        return DeclarationFinger(self.parent, self.declaration.reset(entities=new_entities))

    def get_config_views(self, base):
        config, views = self.parent.get_config_views(base)
        config = config | self.declaration.properties
        if isinstance(self.declaration, ClipDef):
            for entity in self.declaration.entities:
                if isinstance(entity, ViewEntity):
                    views[entity.name] = config | entity.properties
        return config, views

@dataclass(eq=False, repr=False)
class AttributeFinger(DeepFinger):
    name : str
    value : Value

    def to_command(self):
        cmd = self.parent.to_command()
        return AttrOf(cmd, self.name)

    def write(self):
        return self.parent.write_attribute(self.name, self.value)

    def reapply(self, doc):
        return self.parent.reapply(doc).read_attribute(self.name)

    def assign(self, value):
        return AttributeFinger(self.parent, self.name, value)

    def remove(self):
        return AttributeFinger(self.parent, self.name, Unk("none"))

@dataclass(eq=False, repr=False)
class ClipFinger(DeepFinger):
    clip : ClipDef

    def to_command(self):
        return ByRef(self.parent.to_command())

    def writeback(self):
        return self.parent.write_declaration(self.clip.name, self.clip).writeback()

    def write(self):
        doc = self.parent.write_declaration(self.clip.name, self.clip).writeback()
        return self.parent.reapply(doc)

    def reapply(self, doc):
        return self.parent.reapply(doc).by_ref()

    def read_attribute(self, name):
        return AttributeFinger(self, name, self.clip.properties.get(name, Unk("none")))

    def write_attribute(self, name, value):
        properties = self.clip.properties.copy()
        properties.pop(name, None)
        if value != Unk("none"):
            properties[name] = value
        return ClipFinger(self.parent, self.clip.reset(properties=properties))

    def by_coords(self, shift, lane):
        entity = get_by_coords(self.clip, shift, lane)
        return CoordsFinger(self, shift, lane, entity)

    def search(self, shift, lane):
        return do_search(self, shift, lane)

    def check_entity(self, entity):
        doc = self.writeback()
        if check_cycles(entity, doc, self.clip.name):
            raise Exception(f"Attaching clip entity here would cause a cycle")
        return CoordsFinger(self, entity.shift, entity.lane, entity)

    def write_entity(self, entity, new_entity=None):
        new_entities = [e for e in self.declaration.entities if (e.shift,e.lane) != (entity.shift,entity.lane)]
        if new_entity is not None:
            new_entities.append(new_entity)
            new_entities.sort(key=lambda e: (e.lane, e.shift))
        return ClipFinger(self.parent, self.clip.reset(entities=new_entities))

    def get_config_views(self, base):
        config, views = self.parent.get_config_views(base)
        config = config | self.clip.properties
        if isinstance(self.clip, ClipDef):
            for entity in self.clip.entities:
                if isinstance(entity, ViewEntity):
                    views[entity.name] = config | entity.properties
        return config, views

@dataclass(eq=False, repr=False)
class CoordsFinger(DeepFinger):
    shift : int | float
    lane : int
    entity : Entity | None

    def to_command(self):
        return ByCoords(self.parent.to_command(), self.shift, self.lane)

    def write(self):
        return self.parent.write_entity(self.entity, self.entity)

    def reapply(self, doc):
        return self.parent.reapply(doc).by_coords(self.shift, self.lane)

    def read_attribute(self, name):
        return AttributeFinger(self, name, self.entity.properties.get(name, Unk("none")))

    def write_attribute(self, name, value):
        properties = self.entity.properties.copy()
        properties.pop(name, None)
        if value != Unk("none"):
            properties[name] = value
        return CoordsFinger(self.parent, self.shift, self.lane, self.entity.reset(properties=properties))

    def remove(self):
        finger = self.parent.write_entity(self.entity, None)
        return CoordsFinger(finger, self.shift, self.lane, None)

    def by_ref(self):
        if isinstance(self.entity, ClipEntity):
            decl = self.read_declaration(self.entity.name)
            if not isinstance(decl.declaration, ClipDef):
                raise Exception(f"Declaration is not a clip: {self.to_command()}")
            return ClipFinger(self, decl.declaration)
        if isinstance(self.entity, BrushEntity):
            return SequenceFinger(self, "root", self.entity.expr)
        return super().by_ref()

    def attach(self, cls, *args):
        entity = cls(self.shift, self.lane, {}, *args)
        return self.parent.check_entity(entity)

    def move_to(self, shift, lane):
        if self.entity is None:
            raise Exception(f"Nothing to move here: {self.to_command()}")
        entity = self.entity.reset(shift=shift, lane=lane)
        finger = self.parent.write_entity(self.entity, entity)
        return CoordsFinger(finger, shift, lane, entity)

    def store_expr(self, expr, flavor):
        if isinstance(self.entity, BrushEntity) and flavor == "root":
            entity = self.entity.reset(expr=expr)
            finger = self.parent.write_entity(self.entity, entity)
            return CoordsFinger(finger, self.shift, self.lane, entity)
        return super().store_expr(expr, flavor)

    def get_config_views(self, base):
        config, views = self.parent.get_config_views(base)
        if self.entity is not None:
            config = config | self.entity.properties
        return config, views

@dataclass(eq=False, repr=False)
class SequenceFinger(DeepFinger):
    flavor : str
    expr : SequenceNode

    def to_command(self):
        cmd = self.parent.to_command()
        if self.flavor == "root":
            return ByRef(cmd)
        if self.flavor == "mhs" or self.flavor == "lhs":
            return LhsOf(cmd)
        if self.flavor == "rhs":
            return RhsOf(cmd)

    def write(self):
        return self.parent.store_expr(self.expr, self.flavor)

    def store_range(self, start, stop, expr):
        new_expr = self.expr.erase(start, stop).insert(start, expr)
        return SequenceFinger(self.parent, self.flavor, new_expr)

    def index_of(self, index):
        if index < self.expr.length:
            return IndexFinger(self, index, self.expr.pick(index).retain(empty, empty))
        raise IndexError

    def range_of(self, head, tail):
        head = max(0, min(self.expr.length, head))
        tail = max(0, min(self.expr.length, tail))
        if 0 <= head <= self.expr.length and 0 <= tail <= self.expr.length:
            return RangeFinger(self, head, tail)
        raise IndexError

    def lhs_of(self):
        if self.expr.length == 1:
            return self.index_of(0).lhs_of()
        raise Exception(f"cannot access: {self.to_command()}")

    def rhs_of(self):
        if self.expr.length == 1:
            return self.index_of(0).rhs_of()
        raise Exception(f"cannot access: {self.to_command()}")

    def write_sequence(self, expr):
        return SequenceFinger(self.parent, self.flavor, expr)

    def write_sequence_range(self, start, stop, expr):
        new_expr = self.expr.erase(start, stop).insert(start, expr)
        return SequenceFinger(self.parent, self.flavor, new_expr)

    def get_header(self):
        if self.flavor == "root":
            return self.parent.entity.header
        if self.flavor == "rhs":
            return self.parent.expr.header
        return self.parent.get_header()

    def get_selection(self):
        return self.expr

    def get_track_selection(self):
        if self.flavor == "root":
            return self.parent, []
        else:
            root, path = self.parent.get_track_selection()
            path.append(self.flavor)
            return root, path

@dataclass(eq=False, repr=False)
class IndexFinger(DeepFinger):
    index : int
    expr : SequenceNode

    def to_command(self):
        return IndexOf(self.parent.to_command(), self.index)

    def write(self):
        finger = self.parent.store_range(self.index, self.index+1, self.expr)
        if finger.expr.length == 1:
            return finger.write()
        return finger

    def store_expr(self, expr, flavor):
        if flavor == "mhs":
            return IndexFinger(self.parent, self.index, Tuplet.mk(self.expr.duration, expr))
        if flavor == "lhs":
            fx = self.expr
            return IndexFinger(self.parent, self.index, Fx.mk(expr, fx.args, fx.header, fx.rhs))
        if flavor == "rhs":
            fx = self.expr
            return IndexFinger(self.parent, self.index, Fx.mk(fx.lhs, fx.args, fx.header, expr))
        super().stope_expr(expr, flavor)

    def lhs_of(self):
        if isinstance(self.expr, Tuplet):
            return SequenceFinger(self, "mhs", self.expr.mhs)
        if isinstance(self.expr, Fx):
            return SequenceFinger(self, "lhs", self.expr.lhs)
        raise Exception(f"cannot access: {self.to_command()}")

    def rhs_of(self):
        if isinstance(self.expr, Fx):
            return SequenceFinger(self, "rhs", self.expr.rhs)
        raise Exception(f"cannot access: {self.to_command()}")

    def write_sequence(self, expr):
        finger = self.parent.write_sequence_range(self.index, self.index+1, expr)
        if expr.length == 1:
            return IndexFinger(finger, self.index, expr)
        return RangeFinger(finger, self.index+expr.length, self.index)

    def get_header(self):
        return self.parent.get_header()

    def get_selection(self):
        return self.expr

    def get_track_selection(self):
        root, path = self.parent.get_track_selection()
        path.append(self.index)
        return root, path

@dataclass(eq=False, repr=False)
class RangeFinger(DeepFinger):
    head : int
    tail : int

    def to_range(self):
        return min(self.head, self.tail), max(self.head, self.tail)

    def to_command(self):
        return RangeOf(self.parent.to_command(), self.head, self.tail)

    def write(self):
        return self.parent

    def write_sequence(self, expr):
        start, stop = self.to_range()
        finger = self.parent.write_sequence_range(start, stop, expr)
        if self.head < self.tail:
            return RangeFinger(finger, start, start+expr.length)
        else:
            return RangeFinger(finger, start+expr.length, start)

    def lhs_of(self):
        start, stop = self.to_range()
        if start+1 == stop:
            return self.parent.index_of(start).lhs_of()
        raise Exception(f"cannot access: {self.to_command()}")

    def rhs_of(self):
        start, stop = self.to_range()
        if start+1 == stop:
            return self.parent.index_of(start).rhs_of()
        raise Exception(f"cannot access: {self.to_command()}")

    def get_header(self):
        return self.parent.get_header()

    def get_selection(self):
        start, stop = self.to_range()
        selection = empty
        for n in self.parent.expr.sequence(start, stop):
            selection = selection.insert(selection.length, n.retain(empty, empty))
        return selection

    def get_track_selection(self):
        root, path = self.parent.get_track_selection()
        path.append(self.to_range())
        return root, path

## COMMANDS
@dataclass(eq=False, repr=False)
class Cont(Command):
    def __pretty__(self):
        return text("cont")

    def apply(self, cont, doc, editor):
        if cont is None:
            return DocumentFinger(doc)
        return cont.apply(None, doc, editor)

@dataclass(eq=False, repr=False)
class Mk(Command):
    name : str

    def __pretty__(self):
        return text("mk ") + pretty(self.name)

    def apply(self, cont, doc, editor):
        clip = ClipDef(self.name, {}, [])
        finger = DocumentFinger(doc)
        return DeclarationFinger(finger, clip)

@dataclass(eq=False, repr=False)
class ByName(Command):
    command : Command
    name : str
    def __pretty__(self):
        return pretty(self.command) + text(" :" + self.name)

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.read_declaration(self.name)

@dataclass(eq=False, repr=False)
class AttrOf(Command):
    command : Command
    name : str

    def __pretty__(self):
        return pretty(self.command) + text(f".{self.name}")

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.read_attribute(self.name)

@dataclass(eq=False, repr=False)
class Assign(Command):
    command : Command
    value : Value

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.assign(self.value)

    def __pretty__(self):
        return pretty(self.command) + text(" = ") + pretty(self.value)

@dataclass(eq=False, repr=False)
class Remove(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(" remove")

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.remove()

@dataclass(eq=False, repr=False)
class Up(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(" up")

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        if isinstance(finger, DeepFinger):
            return finger.write()
        raise Exception(f"Cannot ascend from: {finger.to_command()}")

@dataclass(eq=False, repr=False)
class AttachClip(Command):
    command : Command
    name : str
    def __pretty__(self):
        return pretty(self.command) + text(f" &{self.name}")

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.attach(ClipEntity, self.name)

@dataclass(eq=False, repr=False)
class AttachView(Command):
    command : Command
    name : str
    def __pretty__(self):
        return pretty(self.command) + text(f" @{self.name}")

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.attach(ViewEntity, self.name)

@dataclass(eq=False, repr=False)
class AttachBrush(Command):
    command : Command
    header : List[Annotation]
    expr : Expr

    def __pretty__(self):
        out = pretty(self.command) + text(f" ")
        out += format_annotations(self.header)
        out += sp + self.expr.formatted(self.header, False)
        return out

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.attach(BrushEntity, self.header, self.expr)

@dataclass(eq=False, repr=False)
class WriteSoup(Command):
    command : Command
    soup : List[Any]
    fxs : List[Any]

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        header = finger.get_header()
        selection = finger.get_selection()
        expr = read_soup(header, self.soup, self.fxs, selection)
        return finger.write_sequence(expr)

@dataclass(eq=False, repr=False)
class WriteSequence(Command):
    command : Command
    expr : SequenceNode

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.write_sequence(self.expr)
 
@dataclass(eq=False, repr=False)
class ByCoords(Command):
    command : Command
    shift : int | float
    lane : int

    def __pretty__(self):
        return pretty(self.command) + sp + format_coordinates(self.shift, self.lane)

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.by_coords(self.shift, self.lane)

@dataclass(eq=False, repr=False)
class ByRef(Command):
    command : Command
    def __pretty__(self):
        return pretty(self.command) + sp + text("*")

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.by_ref()

@dataclass(eq=False, repr=False)
class MoveTo(Command):
    command : Command
    shift : int | float
    lane : int
    def __pretty__(self):
        return pretty(self.command) + text(" ... ") + format_coordinates(self.x, self.y)

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.move_to(self.shift, self.lane)

@dataclass(eq=False, repr=False)
class SearchCoords(Command):
    command : Command
    shift : int | float
    lane : int

    def __pretty__(self):
        return pretty(self.command) + text(" ... ") + format_coordinates(self.x, self.y)

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.search(self.shift, self.lane)

#def header_of(thing):
#    while isinstance(thing, Finger):
#        if isinstance(thing, Side) and thing.side:
#            return thing.top.tree.header
#        thing = thing.top
#    return thing.header
#
#def topmost(thing):
#    while isinstance(thing, Finger):
#        thing = thing.top
#    return thing
#
#@dataclass(eq=False, repr=False)
#class RootFinger(Finger):
#    top : Any
#    tree : SequenceNode
#    def __post_init(self):
#        assert isinstance(tree, SequenceNode)
#
#    def writeback(self):
#        if isinstance(self.top, BrushEntity):
#            self.top.expr = self.tree
#        else:
#            self.top.writeback(self.tree)
#
#    def __str__(self):
#        p = formatted([], self.tree, False)
#        return pformat_doc(p, 80)
#
#@dataclass(eq=False, repr=False)
#class Indexer(Finger):
#    top : RootFinger
#    start : int
#    stop : int
#
#    def writeback(self, tree):
#        count = tree.length
#        self.top.tree = self.top.tree.erase(self.start, self.stop).insert(self.start, tree)
#        self.stop = self.start + count
#        self.top.writeback()
#
#    def __str__(self):
#        p = formatted_range([], self.top.tree, False, self.start, self.stop)
#        return pformat_doc(p, 80)
#
#@dataclass(eq=False, repr=False)
#class Side(Finger):
#    top : RootFinger
#    side : bool
#
#    def writeback(self, tree):
#        fx = self.top.tree
#        if self.side:
#            self.top.tree = Fx.mk(fx.lhs, fx.args, fx.header, tree)
#        else:
#            self.top.tree = Fx.mk(tree, fx.args, fx.header, fx.rhs)
#        self.top.writeback()
#
#    def __str__(self):
#        if self.side:
#            p = formatted([], self.top.tree.rhs, False)
#        else:
#            p = formatted([], self.top.tree.lhs, False)
#        return pformat_doc(p, 80)
#
#@dataclass(eq=False, repr=False)
#class Middle(Finger):
#    top : RootFinger
#
#    def writeback(self, tree):
#        tuplet = self.top.tree
#        self.top.tree = Tuplet.mk(tuplet.duration, tree)
#        self.top.writeback()
#
#    def __str__(self):
#        p = formatted([], self.top.tree.mhs, False)
#        return pformat_doc(p, 80)

@dataclass(eq=False, repr=False)
class IndexOf(Command):
    command : Command
    index : int
    def __pretty__(self):
        return pretty(self.command) + text(f" [{self.index}]")

    def apply(self, cont, doc, editor):
        return self.command.apply(cont, doc, editor).index_of(self.index)

    #def apply(self, target, cont, doc, editor):
    #    sel, obj, epath = self.command.apply(target, cont, doc, editor)
    #    epath.append(obj)
    #    if isinstance(obj, BrushEntity):
    #        obj = RootFinger(obj, obj.expr)
    #    if isinstance(obj, RootFinger):
    #        obj = RootFinger(Indexer(obj, self.index, self.index+1), obj.tree.pick(self.index))
    #        return IndexOf(sel, self.index), obj, epath
    #    assert False, "TODO: something wrong"

    #def write(self, target, doc, editor, soup, fxs):
    #    sel, obj, epath = self.command.apply(target, None, doc, editor)
    #    epath.append(obj)
    #    if isinstance(obj, BrushEntity):
    #        obj = RootFinger(obj, obj.expr)
    #    if isinstance(obj, RootFinger):
    #        selection = obj.tree.pick(self.index).retain(empty, empty)
    #        nodes = read_soup(header_of(obj), soup, fxs, selection)
    #        obj.tree = obj.tree.erase(self.index, self.index+1).insert(self.index, nodes)
    #        obj.writeback()
    #        if nodes.length == 1:
    #            return IndexOf(sel, self.index), Indexer(obj, self.index, self.index+nodes.length), epath
    #        else:
    #            return RangeOf(sel, self.index, self.index+nodes.length), Indexer(obj, self.index, self.index+nodes.length), epath
    #    assert False, "TODO: something wrong"

@dataclass(eq=False, repr=False)
class RangeOf(Command):
    command : Command
    head : int
    tail : int

    def __pretty__(self):
        return pretty(self.command) + text(f" [{self.head}:{self.tail}]")

    def apply(self, cont, doc, editor):
        return self.command.apply(cont, doc, editor).range_of(self.head, self.tail)

    #def apply(self, target, cont, doc, editor):
    #    sel, obj, epath = self.command.apply(target, cont, doc, editor)
    #    epath.append(obj)
    #    if isinstance(obj, BrushEntity):
    #        obj = RootFinger(obj, obj.expr)
    #    if isinstance(obj, RootFinger):
    #        if self.stop - self.start == 1:
    #            obj = RootFinger(Indexer(obj, self.start, self.stop), obj.tree.pick(self.start))
    #        else:
    #            obj = Indexer(obj, self.head, self.tail)
    #        return RangeOf(sel, self.head, self.tail), obj, epath
    #    assert False, "TODO: something wrong"

    #def write(self, target, doc, editor, soup, fxs):
    #    sel, obj, epath = self.command.apply(target, None, doc, editor)
    #    epath.append(obj)
    #    if isinstance(obj, BrushEntity):
    #        obj = RootFinger(obj, obj.expr)
    #    if isinstance(obj, RootFinger):
    #        selection = empty
    #        for n in obj.tree.sequence(self.start, self.stop):
    #            selection = selection.insert(selection.length, n.retain(empty, empty))
    #        count = selection.length
    #        nodes = read_soup(header_of(obj), soup, fxs, selection)
    #        obj.tree = obj.tree.erase(self.start, self.stop).insert(self.start, nodes)
    #        obj.writeback()
    #        return RangeOf(sel, self.start, self.start+nodes.length), Indexer(obj, self.start, self.start+nodes.length), epath
    #    assert False, "TODO: something wrong"

@dataclass(eq=False, repr=False)
class LhsOf(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(f" <")

    def apply(self, cont, doc, editor):
        return self.command.apply(cont, doc, editor).lhs_of()

#    def apply(self, target, cont, doc, editor):
#        sel, obj, epath = self.command.apply(target, cont, doc, editor)
#        epath.append(obj)
#        if isinstance(obj, BrushEntity):
#            obj = RootFinger(obj, obj.expr)
#        if isinstance(obj, RootFinger):
#            if isinstance(obj.tree, Tuplet):
#                o = RootFinger(Middle(obj), obj.tree.mhs)
#                return LhsOf(sel), o, epath
#            if isinstance(obj.tree, Fx):
#                obj = RootFinger(Side(obj, False), obj.tree.lhs)
#                return LhsOf(sel), obj, epath
#        raise Exception("selection not an FX: " + str(sel))
#
#    def write(self, target, doc, editor, soup, fxs):
#        sel, obj, epath = self.command.apply(target, None, doc, editor)
#        epath.append(obj)
#        if isinstance(obj, BrushEntity):
#            obj = RootFinger(obj, obj.expr)
#        if isinstance(obj, RootFinger):
#            if isinstance(obj.tree, Tuplet):
#                selection = obj.tree.mhs
#                nodes = read_soup(header_of(obj), soup, fxs, selection)
#                o = Middle(obj)
#                o.writeback(nodes)
#                return LhsOf(sel), o, epath
#            if isinstance(obj.tree, Fx):
#                selection = obj.tree.lhs
#                nodes = read_soup(header_of(obj), soup, fxs, selection)
#                o = Side(obj, False)
#                o.writeback(nodes)
#                return LhsOf(sel), o, epath
#        raise Exception("selection not an FX: " + str(sel))

@dataclass(eq=False, repr=False)
class RhsOf(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(f" >")

    def apply(self, cont, doc, editor):
        return self.command.apply(cont, doc, editor).rhs_of()

    #def apply(self, target, cont, doc, editor):
    #    sel, obj, epath = self.command.apply(target, cont, doc, editor)
    #    epath.append(obj)
    #    if isinstance(obj, BrushEntity):
    #        obj = RootFinger(obj, obj.expr)
    #    if isinstance(obj, RootFinger):
    #        if isinstance(obj.tree, Tuplet):
    #            o = RootFinger(Middle(obj), obj.tree.mhs)
    #            return RhsOf(sel), o, epath
    #        if isinstance(obj.tree, Fx):
    #            o = RootFinger(Side(obj, True), obj.tree.rhs)
    #            return RhsOf(sel), o, epath
    #    raise Exception("selection not an FX: " + str(sel))

    #def write(self, target, doc, editor, soup, fxs):
    #    sel, obj, epath = self.command.apply(target, None, doc, editor)
    #    epath.append(obj)
    #    if isinstance(obj, BrushEntity):
    #        obj = RootFinger(obj, obj.expr)
    #    if isinstance(obj, RootFinger):
    #        if isinstance(obj.tree, Tuplet):
    #            selection = obj.tree.mhs
    #            nodes = read_soup(header_of(obj), soup, fxs, selection)
    #            o = Middle(obj)
    #            o.writeback(nodes)
    #            return RhsOf(sel), o, epath
    #        if isinstance(obj.tree, Fx):
    #            selection = obj.tree.rhs
    #            nodes = read_soup(header_of(obj), soup, fxs, selection)
    #            o = Side(obj, True)
    #            o.writeback(nodes)
    #            return RhsOf(sel), o, epath
    #    raise Exception("selection not an FX: " + str(sel))

@dataclass(eq=False, repr=False)
class SetConnection(Command):
    command : Command
    connection : Connection
    connect : bool

    def __pretty__(self):
        return pretty(self.command) + text(f" >")

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        return finger.set_connection(self.connection, connect)

        # TODO: recon
        #sel, obj, epath = self.command.apply(target, cont, doc, editor)
        #epath.append(obj)
        #if self.connect:
        #    doc.connections.add(self.connection)
        #else:
        #    doc.connections.discard(self.connection)
        #return sel, obj, epath

@dataclass(eq=False, repr=False)
class SelectSynth(Command):
    name : str

    def __pretty__(self):
        out = text(f"synth ")
        out += text(self.name)
        return out

    def apply(self, cont, doc, editor):
        assert False, "TODO"

@dataclass(eq=False, repr=False)
class SetSynth(Command):
    command : Command
    xy : Tuple[float | int, float | int]
    synth : str

    def __pretty__(self):
        out = pretty(self.command) + text(f" config ")
        out += format_coordinates(*self.xy) + sp
        out += sp + text(self.synth)
        return out

    def apply(self, cont, doc, editor):
        assert False, "TODO"

@dataclass(eq=False, repr=False)
class ToggleMulti(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(f" multi")

    def apply(self, cont, doc, editor):
        assert False, "TODO"

@dataclass(eq=False, repr=False)
class SetTypeParam(Command):
    command : Command
    type_param : str

    def __pretty__(self):
        return pretty(self.command) + text(f" *= ") + text(self.type_param)

    def apply(self, cont, doc, editor):
        assert False, "TODO"

@dataclass(eq=False, repr=False)
class Eval(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(" eval")

    def apply(self, cont, doc, editor):
        assert False, "TODO"

@dataclass(eq=False, repr=False)
class LoopAll(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(" loop all")

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        editor.transport.playback_range = None
        return finger

@dataclass(eq=False, repr=False)
class Loop(Command):
    command : Command
    start : int | float
    stop  : int | float

    def __pretty__(self):
        return pretty(self.command) + text(f" eval {self.start} : {self.stop}")

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        editor.transport.playback_range = self.start, self.stop
        return finger

@dataclass(eq=False, repr=False)
class CursorTo(Command):
    command : Command
    point : int | float

    def __pretty__(self):
        return pretty(self.command) + text(" cursor " + str(self.point))

    def apply(self, cont, doc, editor):
        finger = self.command.apply(cont, doc, editor)
        editor.transport.cursor_head = self.point
        editor.transport.cursor_tail = self.point
        return finger

## ENTITIES
def format_coordinates(x, y):
    return text(f"({x}, {y})")

@dataclass(eq=False, repr=False)
class ClipEntity(Entity):
    name  : str
    def reset(self, shift=None, lane=None, properties=None, name=None):
        if shift is None:
            shift = self.shift
        if lane is None:
            lane = self.lane
        if properties is None:
            properties = self.properties
        if name is None:
            name = self.name
        return ClipEntity(shift, lane, properties, name)

    def __pretty__(self):
        out = format_coordinates(self.shift, self.lane)
        out += text(" &" + self.name)
        return out

@dataclass(eq=False, repr=False)
class ViewEntity(Entity):
    name  : str
    def reset(self, shift=None, lane=None, properties=None, name=None):
        if shift is None:
            shift = self.shift
        if lane is None:
            lane = self.lane
        if properties is None:
            properties = self.properties
        if name is None:
            name = self.name
        return ViewEntity(shift, lane, properties, name)

    def __pretty__(self):
        out = format_coordinates(self.shift, self.lane)
        out += text(" @" + self.name)
        return out

@dataclass(eq=False, repr=False)
class BrushEntity(Entity):
    header : List[Annotation]
    expr   : Expr
    def reset(self, shift=None, lane=None, properties=None, header=None, expr=None):
        if shift is None:
            shift = self.shift
        if lane is None:
            lane = self.lane
        if properties is None:
            properties = self.properties
        if header is None:
            header = self.header
        if expr is None:
            expr = self.expr
        return BrushEntity(shift, lane, properties, header, expr)

    def __pretty__(self):
        out = format_coordinates(self.shift, self.lane)
        out += sp + format_annotations(self.header)
        out += (nl + formatted(self.header, self.expr, False)).nest(2).group()
        return out

def format_annotation(name, dtype, view):
    out = text(name)
    if dtype is not None:
        out += text(":" + dtype)
    if view is not None:
        out += text("@" + view)
    return out

def format_annotations(a):
    return text("%") + text(", ").join(format_annotation(*x) for x in a) + text("%") + sp

def format_group(group, header):
    group = group.copy()
    sequence = []
    for name, _, _ in header:
        items = group.pop(name, None)
        if items is None:
            if group:
                sequence.append(text("_"))
        elif len(items) == 0:
            sequence.append(text("~"))
        else:
            sequence.append(text(":").join(items))
    for name, items in group.items():
        if name == "":
            continue
        if len(items) == 0:
            sequence.append(text(name + "=~"))
        else:
            sequence.append(text(name + "=") + text(":").join(items))
    if "" in group:
        sequence.append(text("~"))
    return sp.join(sequence)

def format_cell(cell, header):
    c = cell.copy()
    out = []
    blanks = 0
    for name, _, _ in header:
        if name in c:
            while blanks > 0:
                blanks -= 1
                out.append(text("_"))
            out.append(pretty(c.pop(name)))
        else:
            blanks += 1
    for name, val in c.items():
        out.append(text(name + "=") + pretty(val))
    return sp.join(out)

## EXPRESSION PROTOTYPES
@dataclass
class NoteProto:
    duration : Optional[Duration]
    style : str | None
    group : List[List[Any]]

@dataclass
class AttrProto:
    name : str
    value : Value

@dataclass
class FxProto:
    args : List[Value]
    header : List[Annotation]
    soup : List[Any]

@dataclass
class ListletProto:
    soup : List[Any]
    fxs : List[FxProto]

@dataclass
class TupletProto:
    duration : Optional[Duration]
    soup : List[Any]
    fxs : List[FxProto]

@dataclass
class Placeholder:
    pass

def read_soup(header, soup, fxs, selection=None):
    def process(group):
        out = {}
        for i, (name, attrs) in enumerate(group):
            if attrs is None:
                continue
            if name is not None:
                out[name] = attrs
            elif i < len(header):
                out[header[i][0]] = attrs
            elif len(attrs) == 0:
                out[""] = []
            else:
                assert False, "TODO: a parse error?" + str((i, x))
        return out
    out = empty
    def add(item):
        nonlocal out
        out = out.insert(out.length, item)
    for expr in soup:
        if isinstance(expr, NoteProto):
            gs = process(expr.group)
            add(Note.mk(expr.duration, expr.style, gs))
        elif isinstance(expr, ListletProto):
            add(read_soup(header, expr.soup, expr.fxs, selection))
        elif isinstance(expr, TupletProto):
            add(Tuplet.mk(expr.duration, read_soup(header, expr.soup, expr.fxs, selection)))
        elif isinstance(expr, Placeholder) and selection is not None:
            add(selection)
        else:
            assert False, expr
    for fx in fxs:
        rhs = read_soup(header if fx.header is None else fx.header, fx.soup, [], selection)
        out = Fx.mk(out, fx.args, fx.header, rhs)
    return out

def random_name():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
 
note_durations = {
    'x': Fraction(2),
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

RhythmConfig = Dict[str, Value]

default_rhythm_config = {
    'beats_per_measure': 4,
    'beat_division': 4,
    'volume': -6.0,
    'staccato': 0.25,
    'normal': 0.85,
    'tenuto': 1.00,
    'synth': Unk("default"),
    'brush': Unk("gate"),
}
 
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
