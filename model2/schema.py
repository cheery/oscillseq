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

Value = int | float | music.Pitch | Ref | Dynamic
Number = int | float

## BASE CLASSES
@dataclass(eq=False, repr=False)
class Action(Object):
    pass

@dataclass(eq=False, repr=False)
class Declaration(Object):
    name : str

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
                    if isinstance(x, Note):
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
        return d + text(f" {self.style} ") + format_group(self.group, header)

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
 
    def __pretty__(self):
        header = format_coordinates(*self.xy) + sp + text(self.name) + sp + text(self.synth)
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
    properties : Dict[str, Value]

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

## COMMANDS
@dataclass(eq=False, repr=False)
class Cont(Command):
    def __pretty__(self):
        return text("cont")

    def apply(self, target, cont, doc):
        if cont is None:
            raise Exception("cannot continue from no selection")
        return cont.apply(target, None, doc)

@dataclass(eq=False, repr=False)
class Mk(Command):
    name : str

    def __pretty__(self):
        return text("mk ") + pretty(self.name)

    def apply(self, target, cont, doc):
        target.declarations.append(clip := ClipDef(self.name, [], {}))
        return ByName(self.name), clip, None

@dataclass(eq=False, repr=False)
class ByName(Command):
    name : str
    def __pretty__(self):
        return text(":" + self.name)

    def apply(self, target, cont, doc):
        for declaration in target.declarations:
            if declaration.name == self.name:
                return self, declaration, None
        else:
            raise Exception("not present: " + str(self))

    def assign(self, target, value):
        raise Exception("cannot assign to clip")

    def remove(self, target, doc):
        for i, declaration in enumerate(list(target.declarations)):
            if declaration.name == self.name:
                del target.declarations[i]
                return None, None, None
        else:
            raise Exception("not present: " + str(self))

@dataclass(eq=False, repr=False)
class AttrOf(Command):
    command : Command
    name : str

    def __pretty__(self):
        return pretty(self.command) + text(f".{self.name}")

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if isinstance(obj, (ClipDef, Entity)):
            val = obj.properties.get(self.name, Unk("none"))
            return AttrOf(sel, self.name), val, hdr
        else:
            raise Exception("no attributes on: " + str(self.command))

    def assign(self, target, value, doc):
        sel, obj, hdr = self.command.apply(target, None, doc)
        if isinstance(obj, (ClipDef,Entity)):
            obj.properties[self.name] = value
            return AttrOf(sel, self.name), value, hdr
        else:
            raise Exception("no attributes on: " + str(self.command))

    def remove(self, target, doc):
        sel, obj, hdr = self.command.apply(target, None, doc)
        if isinstance(obj, ClipDef):
            if self.name in obj.properties:
                obj.properties.pop(self.name)
                return sel, obj, hdr
            else:
                raise Exception("no such attribute: " + str(self))
        else:
            raise Exception("no attributes on: " + str(self.command))

@dataclass(eq=False, repr=False)
class Assign(Command):
    command : Command
    value : Value

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if isinstance(self.value, Unk) and self.value.name == "none":
            return sel.remove(target)
        return sel.assign(target, self.value, doc)

    def __pretty__(self):
        return pretty(self.command) + text(" = ") + pretty(self.value)

@dataclass(eq=False, repr=False)
class Remove(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(" remove")

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        return sel.remove(target, doc)

@dataclass(eq=False, repr=False)
class Up(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(" up")

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if hasattr(sel, "command"):
            return sel.command.apply(target, None, doc)
        raise Exception("cannot ascend from: " + str(sel))

@dataclass(eq=False, repr=False)
class AttachClip(Command):
    command : Command
    name : str
    def __pretty__(self):
        return pretty(self.command) + text(f" &{self.name}")

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if hasattr(sel, "attach"):
            return sel.attach(target, doc, ClipEntity, self.name)
        raise Exception("cannot attach entity at: " + str(self.command))

@dataclass(eq=False, repr=False)
class AttachView(Command):
    command : Command
    name : str
    def __pretty__(self):
        return pretty(self.command) + text(f" @{self.name}")

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if hasattr(sel, "attach"):
            return sel.attach(target, doc, ViewEntity, self.name)
        raise Exception("cannot attach entity at: " + str(self.command))

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

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if hasattr(sel, "attach"):
            return sel.attach(target, doc, BrushEntity, self.header, self.expr)
        raise Exception("cannot attach entity at: " + str(self.command))

@dataclass(eq=False, repr=False)
class WriteSoup(Command):
    command : Command
    soup : List[Any]
    fxs  : List[Any]

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if hasattr(sel, "write"):
            return sel.write(target, doc, self.soup, self.fxs)
        raise Exception("cannot write to: " + str(sel))

def deep_apply(command, target, cont, doc):
    sel, obj, hdr = command.apply(target, cont, doc)
    if isinstance(obj, ClipEntity):
        for clip in doc.declarations:
            if clip.name == obj.name:
                return sel, clip, hdr
        else:
            raise Exception("clip not present at: " + str(self.command))
    return sel, obj, hdr

@dataclass(eq=False, repr=False)
class ByCoords(Command):
    command : Command
    x : int | float
    y : int
    def __pretty__(self):
        return pretty(self.command) + sp + format_coordinates(self.x, self.y)

    def apply(self, target, cont, doc):
        sel, obj, hdr = deep_apply(self.command, target, cont, doc)
        if isinstance(obj, ClipDef):
            for entity in sorted(obj.entities, key=lambda x: x.shift):
                if entity.shift <= self.x and entity.lane == self.y:
                    return ByCoords(sel, entity.shift, entity.lane), entity, hdr
            else:
                return ByCoords(sel, self.x, self.y), None, hdr
        else:
            raise Exception("not canvaic at: " + str(self.command))

    def attach(self, target, doc, cls, *args):
        sel, obj, hdr = deep_apply(self.command, target, None, doc)
        if isinstance(obj, ClipDef):
            ent = cls(self.x, self.y, {}, *args)
            if check_cycles(ent, doc, obj.name):
                raise Exception("creation of (" + str(ent) + ") would cause cycle issues into: " + str(self.command))
            obj.entities.append(ent)
            return ByCoords(sel, self.x, self.y), ent, hdr
        else:
            raise Exception("not canvaic at: " + str(self.command))

    def assign(self, target, value, doc):
        raise Exception("cannot assign at coordinates")

    def remove(self, target, doc):
        sel, obj, hdr = self.command.apply(target, None, doc)
        if isinstance(obj, ClipEntity):
            for clip in doc.declarations:
                if clip.name == obj.name:
                    obj = clip
                    break
            else:
                raise Exception("clip not present at: " + str(self))
        if isinstance(obj, ClipDef):
            for entity in sorted(obj.entities, key=lambda x: x.shift):
                if entity.shift <= self.x and entity.lane == self.y:
                    obj.entities.remove(entity)
                    return ByCoords(sel, entity.shift, entity.lane), None, hdr
            else:
                raise Exception("nothing to remove: " + str(self))
        else:
            raise Exception("not canvaic at: " + str(self.command))

def check_cycles(entity, doc, target):
    if isinstance(entity, ClipEntity) and entity.name == target:
        return True
    if cd := non_leaf(entity, doc):
        for e in cd.entities:
            if check_cycles(e, doc, target):
                return True
    return False

def non_leaf(entity, doc):
    if not isinstance(entity, ClipEntity):
        return None
    for cd in doc.declarations:
        if cd.name == entity.name and cd.entities:
            return cd
    return None

@dataclass(eq=False, repr=False)
class SearchCoords(Command):
    command : Command
    x : int | float
    y : int
    def __pretty__(self):
        return pretty(self.command) + text(" ... ") + format_coordinates(self.x, self.y)

    def apply(self, target, cont, doc):
        sel, obj, hdr = deep_apply(self.command, target, None, doc)
        if isinstance(obj, ClipDef):
            unvisited = [(sel, obj, self.x, self.y)]
            best = None
            this = None
            while unvisited:
                asel, obj, x, y = unvisited.pop()
                for entity in obj.entities:
                    if entity.shift <= x and entity.lane <= y:
                        dist = (y-entity.lane, x-entity.shift)
                        if cd := non_leaf(entity, doc):
                            bsel = ByCoords(asel, entity.shift, entity.lane)
                            unvisited.append((bsel, cd, x - entity.shift, y - entity.lane))
                        elif best is None or dist < best:
                            best = dist
                            this = ByCoords(asel, entity.shift, entity.lane), entity, hdr
            if this is not None:
                return this
            else:
                raise Exception("the clip at this location is empty: " + str(self))

@dataclass(eq=False, repr=False)
class RootFinger:
    top : Any
    tree : SequenceNode

    def writeback(self):
        if isinstance(self.top, BrushEntity):
            self.top.expr = self.tree
        else:
            self.top.writeback(self.tree)

    def __str__(self):
        p = formatted([], self.tree, False)
        return pformat_doc(p, 80)

@dataclass(eq=False, repr=False)
class Indexer:
    top : RootFinger
    start : int
    stop : int

    def writeback(self, tree):
        count = tree.length
        self.top.tree = self.top.tree.erase(self.start, self.stop).insert(self.start, tree)
        self.stop = self.start + count
        self.top.writeback()

    def __str__(self):
        p = formatted_range([], self.top.tree, False, self.start, self.stop)
        return pformat_doc(p, 80)

@dataclass(eq=False, repr=False)
class Side:
    top : RootFinger
    side : bool

    def writeback(self, tree):
        fx = self.top.tree
        if self.side:
            self.top.tree = Fx.mk(fx.lhs, fx.args, fx.header, tree)
        else:
            self.top.tree = Fx.mk(tree, fx.args, fx.header, fx.rhs)
        self.top.writeback()

    def __str__(self):
        if self.side:
            p = formatted([], self.top.tree.rhs, False)
        else:
            p = formatted([], self.top.tree.lhs, False)
        return pformat_doc(p, 80)

@dataclass(eq=False, repr=False)
class IndexOf(Command):
    command : Command
    index : int
    def __pretty__(self):
        return pretty(self.command) + text(f" [{self.index}]")

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if isinstance(obj, BrushEntity):
            hdr = obj.header
            obj = RootFinger(obj, obj.expr)
        if isinstance(obj, RootFinger):
            obj = RootFinger(Indexer(obj, self.index, self.index+1), obj.tree.pick(self.index))
            return IndexOf(sel, self.index), obj, hdr
        assert False, "TODO: something wrong"

    def write(self, target, doc, soup, fxs):
        sel, obj, hdr = self.command.apply(target, None, doc)
        if isinstance(obj, BrushEntity):
            hdr = obj.header
            obj = RootFinger(obj, obj.expr)
        if isinstance(obj, RootFinger):
            selection = obj.tree.pick(self.index).retain(empty, empty)
            nodes = read_soup(hdr, soup, fxs, selection)
            obj.tree = obj.tree.erase(self.index, self.index+1).insert(self.index, nodes)
            obj.writeback()
            if nodes.length == 1:
                return IndexOf(sel, self.index), Indexer(obj, self.index, self.index+nodes.length), hdr
            else:
                return RangeOf(sel, self.index, self.index+nodes.length), Indexer(obj, self.index, self.index+nodes.length), hdr
        assert False, "TODO: something wrong"

@dataclass(eq=False, repr=False)
class RangeOf(Command):
    command : Command
    start : int
    stop : int

    def __pretty__(self):
        return pretty(self.command) + text(f" [{self.start}:{self.stop}]")

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if isinstance(obj, BrushEntity):
            hdr = obj.header
            obj = RootFinger(obj, obj.expr)
        if isinstance(obj, RootFinger):
            if self.stop - self.start == 1:
                obj = RootFinger(Indexer(obj, self.start, self.stop), obj.tree.pick(self.start))
            else:
                obj = Indexer(obj, self.start, self.stop)
            return RangeOf(sel, self.start, self.stop), obj, hdr
        assert False, "TODO: something wrong"

    def write(self, target, doc, soup, fxs):
        sel, obj, hdr = self.command.apply(target, None, doc)
        if isinstance(obj, BrushEntity):
            hdr = obj.header
            obj = RootFinger(obj, obj.expr)
        if isinstance(obj, RootFinger):
            selection = empty
            for n in obj.tree.sequence(self.start, self.stop):
                selection = selection.insert(selection.length, n.retain(empty, empty))
            count = selection.length
            nodes = read_soup(hdr, soup, fxs, selection)
            obj.tree = obj.tree.erase(self.start, self.stop).insert(self.start, nodes)
            obj.writeback()
            return RangeOf(sel, self.start, self.start+nodes.length), Indexer(obj, self.start, self.start+nodes.length), hdr
        assert False, "TODO: something wrong"

@dataclass(eq=False, repr=False)
class LhsOf(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(f" <")

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if isinstance(obj, BrushEntity):
            hdr = obj.header
            obj = RootFinger(obj, obj.expr)
        if isinstance(obj, RootFinger):
            if isinstance(obj.tree, Fx):
                obj = RootFinger(Side(obj, False), obj.tree.lhs)
                return LhsOf(sel), obj, hdr
        raise Exception("selection not an FX: " + str(sel))

    def write(self, target, doc, soup, fxs):
        sel, obj, hdr = self.command.apply(target, None, doc)
        if isinstance(obj, BrushEntity):
            hdr = obj.header
            obj = RootFinger(obj, obj.expr)
        if isinstance(obj, RootFinger):
            selection = obj.tree.lhs
            nodes = read_soup(hdr, soup, fxs, selection)
            if isinstance(obj.tree, Fx):
                o = Side(obj, False)
                o.writeback(nodes)
                return LhsOf(sel), o, hdr
        raise Exception("selection not an FX: " + str(sel))

@dataclass(eq=False, repr=False)
class RhsOf(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(f" >")

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if isinstance(obj, BrushEntity):
            hdr = obj.header
            obj = RootFinger(obj, obj.expr)
        if isinstance(obj, RootFinger):
            if isinstance(obj.tree, Fx):
                o = RootFinger(Side(obj, True), obj.tree.rhs)
                return RhsOf(sel), o, obj.tree.header
        raise Exception("selection not an FX: " + str(sel))

    def write(self, target, doc, soup, fxs):
        sel, obj, hdr = self.command.apply(target, None, doc)
        if isinstance(obj, BrushEntity):
            hdr = obj.header
            obj = RootFinger(obj, obj.expr)
        if isinstance(obj, RootFinger):
            selection = obj.tree.lhs
            nodes = read_soup(hdr, soup, fxs, selection)
            if isinstance(obj.tree, Fx):
                o = Side(obj, True)
                o.writeback(nodes)
                return RhsOf(sel), o, obj.tree.header
        raise Exception("selection not an FX: " + str(sel))

@dataclass(eq=False, repr=False)
class SetConnection(Command):
    command : Command
    connection : Connection
    connect : bool

    def __pretty__(self):
        return pretty(self.command) + text(f" >")

    def apply(self, target, cont, doc):
        sel, obj, hdr = self.command.apply(target, cont, doc)
        if self.connect:
            doc.connections.add(self.connection)
        else:
            doc.connections.discard(self.connection)
        return sel, obj, hdr

@dataclass(eq=False, repr=False)
class SelectSynth(Command):
    name : str

    def __pretty__(self):
        out = text(f"synth ")
        out += text(self.name)
        return out

    def apply(self, target, cont, doc):
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

    def apply(self, target, cont, doc):
        assert False, "TODO"

@dataclass(eq=False, repr=False)
class ToggleMulti(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(f" multi")

    def apply(self, target, cont, doc):
        assert False, "TODO"

@dataclass(eq=False, repr=False)
class SetTypeParam(Command):
    command : Command
    type_param : str

    def __pretty__(self):
        return pretty(self.command) + text(f" *= ") + text(self.type_param)

    def apply(self, target, cont, doc):
        assert False, "TODO"

@dataclass(eq=False, repr=False)
class Eval(Command):
    command : Command

    def __pretty__(self):
        return pretty(self.command) + text(" eval")

    def apply(self, target, cont, doc):
        assert False, "TODO"

## ENTITIES
def format_coordinates(x, y):
    return text(f"({x}, {y})")

@dataclass(eq=False, repr=False)
class ClipEntity(Entity):
    name  : str
    def __pretty__(self):
        out = format_coordinates(self.shift, self.lane)
        out += text(" &" + self.name)
        return out

@dataclass(eq=False, repr=False)
class ViewEntity(Entity):
    name  : str
    def __pretty__(self):
        out = format_coordinates(self.shift, self.lane)
        out += text(" @" + self.name)
        return out

@dataclass(eq=False, repr=False)
class BrushEntity(Entity):
    header : List[Annotation]
    expr   : Expr

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
        items = group.pop(name, [])
        if len(items) == 0:
            sequence.append(text("~"))
        else:
            sequence.append(text(":").join(items))
    for name, value in group.items():
        if name == "":
            continue
        items = group.pop(name, [])
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

## EXPRESSIONS
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
            add(read_soup(header, expr.soup, expr.fxs))
        elif isinstance(expr, TupletProto):
            add(Tuplet.mk(expr.duration, read_soup(header, expr.soup, expr.fxs)))
        elif isinstance(expr, Placeholder) and selection is not None:
            add(selection)
        else:
            assert False, expr
    for fx in fxs:
        rhs = read_soup(header if fx.header is None else fx.header, fx.soup, [], selection)
        out = Fx.mk(out, fx.args, fx.header, rhs)
    return out

#     out = []
#     first = None
#     style = None
#     header_count = 0
#     group = []
#     for node in soup:
#         if isinstance(node, ListletProto):
#             out.append(read_soup(header, node.soup, node.fxs))
#         elif isinstance(node, Unk) and (node.name in note_durations or isinstance(node.name, int)):
#             if first is not None:
#                 out.append(Note(first, style, group))
#             first = Duration(node.name, 0)
#             style = "n"
#             header_count = 0
#             group = [{}]
#         elif group and isinstance(node, Unk) and node.name == ".":
#             first.dots += 1
#         elif group and isinstance(node, Unk) and node.name == "s":
#             style = "s"
#         elif group and isinstance(node, Unk) and node.name == "t":
#             style = "t"
#         elif group and isinstance(node, Unk) and node.name == "~":
#             assert len(group) == 1 and len(group[0]) == 0
#             out.append(Note(first, style, group))
#             group = []
#         elif first
#         else:
#             assert first
#             group[-1][header[header_count][0]] = node
#             header_count += 1
# 
#     if first is not None:
#         out.append(Note(first, style, group))
# 
#     out = Listlet(out)
#     for fx in fxs:
#         listlet = read_soup(fx.header if fx.header else header, fx.soup, [])
#         out = Fx(out, fx.args, fx.header, listlet.exprs)
#     return out

def mk_listlet(exprs, raw=False):
    out = []
    def visit(expr):
        if isinstance(expr, Listlet):
            for e in expr.exprs:
                visit(e)
        else:
            out.append(expr)
    for expr in exprs:
        visit(expr)
    if raw:
        return out
    if len(out) == 1:
        return out[0]
    return Listlet(out)

@dataclass(eq=False, repr=False)
class Listlet(Expr):
    exprs : List[Expr]

    def formatted(self, header, ins):
        out = text(", ").join(x.formatted(header, True) for x in self.exprs)
        if ins:
            return text("(") + out + text(")")
        return out

#@dataclass(eq=False, repr=False)
#class Fx(Expr):
#    base : Expr
#    args : List[Value]
#    header : List[Annotation]
#    exprs : List[Expr]
#

# @dataclass(eq=False, repr=False)
# class Invoke(Expr):
#     callee : Expr
#     action : Action
# 
#     def __pretty__(self):
#         return pretty(self.callee) + text(" / ") + pretty(self.action)
# 
# @dataclass(eq=False, repr=False)
# class WestRhythm(Expr):
#     header : List[Annotation]
#     elements : List[Element]
# 
#     def __pretty__(self):
#         annotation = format_annotations(self.header)
#         return annotation + text(", ").join(self.elements)
# 
# @dataclass(eq=False, repr=False)
# class StepRhythm(Expr):
#     sequence : List[int]
# 
#     def __pretty__(self):
#         return text("step ") + text("").join(self.sequence)
 
#     def to_west(self):
#         out = []
#         for i in self.sequence:
#             if i > 0:
#                 out.append(Note(Duration(i,0), [{}]))
#             else:
#                 out.append(Note(Duration(1,0), []))
#         return WestRhythm(self.header, out)

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

RhythmConfig = Dict[str, int | float | music.Pitch | Ref | Unk]

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

# @dataclass
# class Pattern:
#     events : List[Tuple[float, float]]
#     values : List[List[Dict[str, Any]]]
#     duration : float
# #     views : List[Tuple[str, str, str]]
# #     meta : List[Dict[str, int]]
# # 
# #     def overlay(self, other : List[List[Dict[str, Any]]], view : Tuple[str, str, str]):
# #         out = []
# #         meta = []
# #         L = len(other)
# #         for i,(vg,m) in enumerate(zip(self.values, self.meta)):
# #             x = []
# #             for w in other[i%L]:
# #                 for v in vg:
# #                     x.append(v | w)
# #             out.append(x)
# #             meta.append(m | {view[0]: i%L})
# #         return Pattern(self.events, out, self.duration, self.views + [view], meta)
# 
# @dataclass(repr=False, eq=False)
# class Skip(Object):
#     def __pretty__(self):
#         return text("*")
# 
# @dataclass(repr=False, eq=False)
# class Attrs(Object):
#     data : List[Tuple[str, Value]]
# 
#     def __pretty__(self):
#         return text("(" + ", ".join(f"{n}={v}" for n,v in self.data) + ")")
# 
# def format_cell(cell, header):
#     if isinstance(cell, list):
#         return sp.join(cell)
#     cell = cell.copy()
#     named = [pretty(cell.pop(a.name, "skip")) for a in header]
#     if len(cell) > 0:
#         rest = text(", ").join(text(x + "=") + pretty(v) for x,v in cell.items())
#         return sp.join(named + [text("(") + rest + text(")")])
#     return sp.join(named)
# 
# def format_values(values, header):
#     if len(values) == 0:
#         return text("~")
#     if len(values) == 1 and len(values[0]) == 0:
#         return text("")
#     return sp + text(":").join(format_cell(cell, header) for cell in values)
# 
# def canon(values, header):
#     out = {}
#     for i, val in enumerate(values):
#         if isinstance(val, Skip):
#             continue
#         if isinstance(val, Attrs):
#             out.update(val.data)
#         elif i < len(header):
#             out[header[i].name] = val
#     return out
#     
# @dataclass(repr=False, eq=False)
# class Ostinato(Action):
#     subheader : List[Annotation] | None
#     values : List[List[Dict[str, Value]]]
#     default : bool = False
# 
#     def canon(self, header):
#         if self.subheader is not None:
#             header = self.subheader
#         return Ostinato(self.subheader,
#             [[canon(v, header) for v in val] for val in self.values],
#             self.default)
# 
#     def __pretty__(self):
#         if self.default:
#             out = [text("default ")]
#         else:
#             out = [text("ostinato ")]
#         if self.subheader:
#             out.append(format_header(self.subheader))
#         out.append(text(",").join(format_values(v, self.subheader or []) for v in self.values))
#         return text("").join(out)
# 
# #@dataclass(repr=False)
# #class Overlay(Component):
# #    base : Component
# #    data : List[List[Any]]
# #    name : str
# #    dtype : str
# #    view : str
# #
# #    def to_values(self):
# #        return [[{self.name: v} for v in vg] for vg in self.data]
# #
# #    def __pretty__(self):
# #        base = pretty(self.base)
# #        def process(x):
# #            return text(":").join(x) if len(x) > 0 else text("~")
# #        blob = sp.join(process(x) for x in self.data).group()
# #        body = (text("/") + sp + blob + sp + text(f"[{self.name}:{self.dtype}:{self.view}]")).group()
# #        return base + sp + body
# 
# @dataclass(repr=False, eq=False)
# class Retrograde(Action):
#     def __pretty__(self):
#         return text("retrograde")
 
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
