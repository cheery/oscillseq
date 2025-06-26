from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Callable, Tuple, Any, Union, DefaultDict
from descriptors import simple, bus, read_desc
import supriya
import os
import music

if "SC_JACK_DEFAULT_INPUTS" not in os.environ:
    os.environ["SC_JACK_DEFAULT_INPUTS"] = "system"
if "SC_JACK_DEFAULT_OUTPUTS" not in os.environ:
    os.environ["SC_JACK_DEFAULT_OUTPUTS"] = "system"

class Definitions:
    def __init__(self, synthdef_directory):
        self.synthdef_directory = synthdef_directory
        self.table = {}

    def retrieve(self, name):
        if name in self.table:
            return self.table[name]
        filename = os.path.join(self.synthdef_directory, name)
        self.table[name] = d = load_definition(filename)
        return d

def load_definition(filename):
    with open(f"{filename}.synthdef", 'rb') as fd:
        data = fd.read()
    synthdef = supriya.ugens.decompile_synthdef(data)
    return Definition(synthdef, read_desc(f"{filename}.desc"))

@dataclass
class Definition:
    synthdef : Any
    desc : List[Tuple[str, Any]]

    @property
    def inputs(self):
        for name, spec in self.desc:
            if isinstance(spec, bus) and spec.mode == 'in':
                yield name
        
    @property
    def outputs(self):
        for name, spec in self.desc:
            if isinstance(spec, bus) and spec.mode == 'out':
                yield name

@dataclass
class Cell:
    label : str
    multi : bool
    definition : str
    pos : Tuple[int, int]
    params : Dict[str, Union[int, float, str, music.Pitch]]

class Fabric:
    def __init__(self, server, buses, cells, definitions_):
        definitions = {}
        synthdefs = []
        for cell in cells:
            if cell.definition not in definitions:
                d = definitions_.retrieve(cell.definition)
                definitions[cell.definition] = d
                synthdefs.append(d.synthdef)
        server.add_synthdefs(*synthdefs)
        server.sync()

        self.cells = topological_sort(cells, definitions)
        self.definitions = definitions
        self.busmap = {label: server.add_bus_group(rate, count)
                       for label, (rate, _, count) in buses.items()}
        self.busmap['output'] = 0
        self.synths = {}
        self.root = server.add_group()
        for c in reversed(self.cells):
            d = self.definitions[c.definition]
            params = self.map_params(c.params)
            if c.multi:
                subgroup = self.root.add_group()
                self.synths[c.label] = c, subgroup
            else:
                synth = self.root.add_synth(d.synthdef, **params)
                self.synths[c.label] = c, synth

    def close(self):
        self.root.free()

    def map_params(self, params):
        return {n: self.map_param(v)
                for n, v in params.items()}

    def map_param(self, param):
        if isinstance(param, str):
            return self.busmap[param]
        if isinstance(param, music.Pitch):
            return int(param)
        return param

    def control(self, label, **args):
        self.synths[label][1].set(**self.map_params(args))

    def synth(self, label, **args):
        c, g = self.synths[label]
        d = self.definitions[c.definition]
        params = self.map_params(c.params)
        params.update(args)
        return g.add_synth(d.synthdef, **self.map_params(params))

def topological_sort(cells: List[Cell], definitions: Dict[str, Definition]) -> List[Cell]:
    var_to_producers : DefaultDict[str, List[int]] = defaultdict(list)
    for idx, cell in enumerate(cells):
        defn = definitions[cell.definition]
        for out_param in defn.outputs:
            if out_param not in cell.params:
                continue
            var_name = cell.params[out_param]
            var_to_producers[var_name].append(idx)

    num_cells = len(cells)
    adj : Dict[int, Set[int]] = {i: set() for i in range(num_cells)}
    indegree = [0] * num_cells

    for idx, cell in enumerate(cells):
        defn = definitions[cell.definition]
        for in_param in defn.inputs:
            if in_param not in cell.params:
                continue
            var_name = cell.params[in_param]
            for producer_idx in var_to_producers.get(var_name, []):
                if producer_idx != idx:
                    if idx not in adj[producer_idx]:
                        adj[producer_idx].add(idx)
                        indegree[idx] += 1

    ready = deque(i for i, deg in enumerate(indegree) if deg == 0)
    sorted_order : List[Cell] = []

    while ready:
        current = ready.popleft()
        sorted_order.append(cells[current])
        for neighbor in adj[current]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                ready.append(neighbor)

    if len(sorted_order) != num_cells:
        raise ValueError("Cycle detected")

    return sorted_order
