from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
import measure
import music
import json
import random
import string

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
        "clap": Clap,
        "controlpoint": ControlPoint,
        "key": Key,
    }[obj["type"]].from_json(label, obj)

@dataclass(eq=False)
class ControlPoint:
    label : str
    tag : str
    transition : bool
    value : Any

    def construct(self, sequencer, offset, key, spec):
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

@dataclass(eq=False)
class Key:
    label : str
    lanes : int
    index : int

    def construct(self, sequencer, offset, key, spec):
        return

    def annotate(self, graph_key_map, offset):
        for graph in graph_key_map:
            if self.lanes & (1 << graph.lane):
                graph_key_map[graph].append((offset, self.index))

    @property
    def duration(self):
        return 0

    def to_json(self):
        return {
            "type": "key",
            "lanes": self.lanes,
            "index": self.index,
        }
        
    @classmethod
    def from_json(cls, label, obj):
        return cls(label,
            lanes = obj["lanes"],
            index = obj["index"],
        )

@dataclass(eq=False)
class Clip:
    label : str
    duration : int
    brushes : List[Entity]

    def construct(self, sequencer, offset, key, spec):
        for i, e in enumerate(self.brushes):
            kv = key + (i,)
            e.brush.construct(sequencer, offset + e.shift, kv, spec)

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

def json_to_gen(obj):
    return {
        "const": ConstGen,
        "poly": PolyGen,
    }[obj["type"]].from_json(obj)

@dataclass(eq=False)
class ConstGen:
    argslist : List[Args]
    def pull(self, index, key, close):
        for j, args in enumerate(self.argslist):
            kv = key + (index,j)
            yield kv, args

    def to_json(self):
        return {
            "type": "const",
            "argslist": [{name: value_to_json(a) for name,a in args.items()}
                     for args in self.argslist],
        }
        
    @classmethod
    def from_json(cls, obj):
        return cls(
            [{name: json_to_value(o) for name, o in args.items()}
             for args in obj["argslist"]]
        )

@dataclass(eq=False)
class PolyGen:
    argslists : List[List[Args]]
    def pull(self, index, key, close):
        if index < len(self.argslists):
            for j, args in enumerate(self.argslists[index]):
                kv = key + (index, j)
                yield kv, args

    def to_json(self):
        return {
            "type": "poly",
            "argslists": [
                [
                    {name: value_to_json(a) for name,a in args.items()}
                    for args in argslist
                ] for argslist in self.argslists]
        }
        
    @classmethod
    def from_json(cls, obj):
        return cls(
            [
                [
                    {name: json_to_value(o) for name,o in args.items()}
                    for args in argsl
                ]
            for argsl in obj["argslists"]]
        )

@dataclass(eq=False)
class Clap:
    label : str
    duration : int
    tree : measure.Tree
    generators : Dict[str, Any]

    def construct(self, sequencer, offset, key, spec):
        starts, stops = self.tree.offsets(self.duration, offset)
        for tag, gen in self.generators.items():
            assert False, "determine from spec"# TODO
            if tag not in descriptors:
                continue
            kind = descriptors[tag].kind
            if kind == "gate":
                for i, start in enumerate(starts):
                    for kv, args in gen.pull(i, key, False):
                        sequencer.gate(start, tag, kv, args)
                for i, stop in enumerate(stops):
                    for kv, args in gen.pull(i, key, True):
                        sequencer.gate(stop, tag, kv, args)
            elif kind == "oneshot":
                for i, start in enumerate(starts):
                    for kv, args in gen.pull(i, key, True):
                        sequencer.once(start, tag, args)

    def annotate(self, graph_key_map, offset):
        pass

    def to_json(self):
        return {
            "type": "clap",
            "duration": self.duration,
            "tree": str(self.tree),
            "generators": {tag: gen.to_json()
                           for tag, gen in self.generators.items()},
        }
        
    @classmethod
    def from_json(cls, label, obj):
        return cls(label,
            duration = obj["duration"],
            tree = measure.Tree.from_string(obj["tree"]),
            generators = {tag: json_to_gen(o)
                          for tag,o in obj["generators"].items()}
        )

@dataclass(eq=False)
class Desc:
    kind : str
    spec : List[Tuple[str, str]]

    def to_json(self):
        return {
            "kind": self.kind,
            "spec": [list(t) for t in self.spec],
        }
        
    @classmethod
    def from_json(cls, obj):
        return cls(
            kind = obj["kind"],
            spec = [tuple(l) for l in obj["spec"]],
        )

@dataclass(eq=False)
class DrawFunc:
    lane : int
    drawfunc : str
    tag : str
    params : Dict[str, str]

    def to_json(self):
        return {
            "lane": self.lane,
            "drawfunc": self.drawfunc,
            "tag": self.tag,
            "params": self.params,
        }
        
    @classmethod
    def from_json(cls, obj):
        return cls(
            lane = obj["lane"],
            drawfunc = obj["drawfunc"],
            tag = obj["tag"],
            params = obj["params"],
        )

@dataclass(eq=False)
class PitchLane:
    lane : int
    staves: int
    margin_above: int = 0
    margin_below: int = 0

    def to_json(self):
        return {
            "type": "pitch",
            "lane": self.lane,
            "staves": self.staves,
            "margin": [self.margin_above, self.margin_below],
        }
        
    @classmethod
    def from_json(cls, obj):
        return cls(
            lane = obj["lane"],
            staves = obj["staves"],
            margin_above = obj["margin"][0],
            margin_below = obj["margin"][1],
        )

@dataclass
class Cell:
    label : str
    multi : bool
    synth : str
    pos : Tuple[int, int]
    params : Dict[str, Union[int, float, music.Pitch]]

    # TODO: remove
    @property
    def definition(self):
        return self.synth

    def to_json(self):
        return {
            'label': self.label,
            'multi': self.multi,
            'synth': self.synth,
            'pos': tuple(self.pos),
            'params': {name: value_to_json(a) for name,a in self.params.items()}
        }

    @classmethod
    def from_json(cls, obj):
        return cls(
            label = obj['label'],
            multi = obj['multi'],
            synth = obj['synth'],
            pos = tuple(obj['pos']),
            params = {name: json_to_value(o) for name, o in obj['params'].items()})

@dataclass(eq=False)
class Document:
    brushes : List[Entity]
    duration : int
    labels : Dict[str, Brush]
    graphs : List[PitchLane]
    drawfuncs: List[DrawFunc]
    cells : List[Brush]
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
            labels[cell.label] = cell
        self.labels = labels
        

    def construct(self, sequencer, offset, key, definitions):
        spec = {cell.label: definitions.retrieve(cell.synth) for cell in self.cells}
        for i, e in enumerate(self.brushes):
            kv = key + (i,)
            e.brush.construct(sequencer, offset + e.shift, kv, spec)

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
        return {
            "brushes": brushes,
            "graphs": [r.to_json() for r in self.graphs],
            "drawfuncs": [r.to_json() for r in self.drawfuncs],
            "cells": [c.to_json() for c in self.cells],
            "connections": list(self.connections),
        }

    @classmethod
    def from_json(cls, obj):
        brushes = {label: json_to_brush(label,o) for label, o in obj["brushes"].items()}
        for brush in brushes.values():
            if isinstance(brush, Clip):
                brush.brushes = [Entity.from_json(brushes, e) for e in brush.brushes]
        root = brushes.pop("")
        cells = [Cell.from_json(o) for o in obj.get("cells", [])]
        for cell in cells:
            brushes[cell.label] = cell
        return cls(
            brushes = root.brushes,
            duration = root.duration,
            labels = brushes,
            graphs = [PitchLane.from_json(o) for o in obj["graphs"]],
            drawfuncs = [DrawFunc.from_json(o) for o in obj["drawfuncs"]],
            cells = cells,
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
