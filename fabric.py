from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Callable, Tuple, Any, Union, DefaultDict
from descriptors import simple, bus, read_desc
from supriya import synthdef
from supriya.ugens import In, Out
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

@dataclass
class Relay:
    i : int
    o : int

class Fabric:
    def __init__(self, server, cells, connections, definitions_):
        definitions = {}
        synthdefs = []
        for cell in cells:
            if cell.definition not in definitions:
                d = definitions_.retrieve(cell.definition)
                definitions[cell.definition] = d
                synthdefs.append(d.synthdef)
        server.add_synthdefs(*synthdefs)
        server.sync()

        W = []
        R = ['output']
        for cell in cells:
            d = definitions[cell.definition]
            R.extend(f"{cell.label}:{name}" for name in d.inputs)
            W.extend(f"{cell.label}:{name}" for name in d.outputs)
        E = connections
        assignment, relays = bus_assignment(W,R,E)
        cells = cells + [Relay(*ii) for ii in relays]
        self.cells = topological_sort(cells, definitions, assignment)

        self.bus_groups = []

        def retrieve_type(name):
            cell_label, param_name = name.split(':')
            for cell in cells:
                if cell.label == cell_label:
                    d = definitions[cell.definition]
                    for n, ty in d.desc:
                        if n == param_name:
                            return ty

        def allocate_by_type(name):
            bustype = retrieve_type(name)
            bgroup = server.add_bus_group(bustype.rate, bustype.channel_count)
            self.bus_groups.append(bgroup)
            return bgroup

        dummies = {}
        def dummy_bus_by_type(name):
            bustype = retrieve_type(name)
            sm = bustype.sans_mode()
            if sm not in dummies:
                dummmies[sm] = server.add_bus_group(bustype.rate, bustype.channel_count)
                self.bus_groups.append(dummies[sm])
            return dummies[sm]

        output_busi = assignment['output']
        buses = {output_busi: 0}
        for name, busi in assignment.items():
            if ":" not in name:
                continue
            if busi not in buses and busi >= 0:
                buses[busi] = allocate_by_type(name)

        self.busmap = defaultdict(dict)
        for name, busi in assignment.items():
            if ":" not in name:
                continue
            cell_label, param_name = name.split(':')
            if busi >= 0:
                self.busmap[cell_label][param_name] = buses[busi]
            else:
                self.busmap[cell_label][param_name] = dummy_bus_by_type(name)

        relaydefs = {}
        def relay_synthdef(calculation_rate, count):
            if (calculation_rate, count) not in relaydefs:
                if calculation_rate == supriya.CalculationRate.AUDIO:
                    in_fn = In.ar
                    out_fn = Out.ar
                elif calculation_rate == supriya.CalculationRate.CONTROL:
                    in_fn = In.kr
                    out_fn = Out.kr
                @synthdef()
                def relay_synth(input_bus, output_bus):
                    out_fn(source=in_fn(bus=input_bus, channel_count=count))
                server.add_synthdefs(relay_synth)
                server.sync()
                relaydefs[(calculation_rate, count)] = relay_synth
            return relaydefs[(calculation_rate, count)]

        self.definitions = definitions
        self.synths = {}
        self.root = server.add_group()
        for c in reversed(self.cells):
            if isinstance(c, Relay):
                b = buses[c.i]
                sd = relay_synthdef(b.calculation_rate, b.count)
                self.root.add_synth(sd, input_bus=b, output_bus=buses[c.o])
            else:
                d = self.definitions[c.definition]
                params = self.map_params(c.params)
                params.update(self.busmap[c.label])
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
        if isinstance(param, music.Pitch):
            return int(param)
        return param

    def control(self, label, **args):
        self.synths[label][1].set(**self.map_params(args))

    def synth(self, label, **args):
        c, g = self.synths[label]
        d = self.definitions[c.definition]
        params = self.map_params(c.params)
        params.update(self.busmap[label])
        params.update(args)
        return g.add_synth(d.synthdef, **self.map_params(params))

def topological_sort(cells, definitions, assignment):
    var_to_producers : DefaultDict[str, List[int]] = defaultdict(list)
    for idx, cell in enumerate(cells):
        if isinstance(cell, Relay):
            var_to_producers[cell.o].append(idx)
        else:
            defn = definitions[cell.definition]
            for out_param in defn.outputs:
                if (a := assignment[f"{cell.label}:{out_param}"]) >= 0:
                    var_to_producers[a].append(idx)

    num_cells = len(cells)
    adj : Dict[int, Set[int]] = {i: set() for i in range(num_cells)}
    indegree = [0] * num_cells

    def mark(idx, a):
        for producer_idx in var_to_producers.get(a, []):
            if producer_idx != idx:
                if idx not in adj[producer_idx]:
                    adj[producer_idx].add(idx)
                    indegree[idx] += 1

    for idx, cell in enumerate(cells):
        if isinstance(cell, Relay):
            mark(idx, cell.i)
        else:
            defn = definitions[cell.definition]
            for in_param in defn.inputs:
                if (a := assignment[f"{cell.label}:{in_param}"]) >= 0:
                    mark(idx, a)

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

def biclique_decomposition(edges):
    """
    Perform an on-the-fly greedy biclique decomposition of a bipartite graph.

    Args:
        edges (Iterable[Tuple[U, V]]): list of edges (u, v) where u is from left set U and v from right set V.

    Returns:
        List of bicliques, each biclique is represented as a tuple (set_of_U, set_of_V).
    """
    # Build adjacency and reverse adjacency
    adj_u = defaultdict(set)
    adj_v = defaultdict(set)
    remaining_edges = set()
    for u, v in edges:
        adj_u[u].add(v)
        adj_v[v].add(u)
        remaining_edges.add((u, v))

    decomposition = []

    while remaining_edges:
        # pick an arbitrary edge
        u0, v0 = next(iter(remaining_edges))

        # initialize candidate sets
        U0 = set(adj_v[v0] & {u for u, _ in remaining_edges})
        V0 = set(adj_u[u0] & {v for _, v in remaining_edges})

        # grow biclique by pruning
        while True:
            # prune U0: keep only those u that connect to all v in V0
            U1 = {u for u in U0 if V0 <= adj_u[u]}
            # prune V0: keep only those v that connect to all u in U1
            V1 = {v for v in V0 if U1 <= adj_v[v]}
            if U1 == U0 and V1 == V0:
                break
            U0, V0 = U1, V1

        # record biclique
        decomposition.append((U0, V0))

        # remove its edges
        for u in U0:
            for v in V0:
                remaining_edges.discard((u, v))

    return decomposition

def bus_assignment(W, R, E):
    bicliques = biclique_decomposition(E)
    additional = []
    relays = []

    W_DUMMY = set()
    R_DUMMY = set()

    W_SET = set(W)
    R_SET = set(R)
    while W_SET:
        u = W_SET.pop()
        s = len(additional) + len(bicliques)
        ix    = [i for i, (U, V) in enumerate(bicliques) if u in U]
        group = [U for U, V in bicliques if u in U]
        if len(group) == 0:
            W_DUMMY.add(u)
        elif len(group) >= 2:
            NU = set.intersection(*group)
            for z, U in zip(ix, group):
                U.difference_update(NU)
                relays.append((s, z))
            additional.append((NU, set()))
            W_SET.difference_update(NU)
    while R_SET:
        v = R_SET.pop()
        s = len(additional) + len(bicliques)
        ix    = [i for i, (U, V) in enumerate(bicliques) if v in V]
        group = [V for U, V in bicliques if v in V]
        if len(group) == 0:
            R_DUMMY.add(v)
        elif len(group) >= 2:
            NV = set.intersection(*group)
            for z, V in zip(ix, group):
                V.difference_update(NV)
                relays.append((z, s))
            additional.append((set(), NV))
            R_SET.difference_update(NV)

    assignment = {}
    for i, (U, V) in enumerate(bicliques + additional):
        assignment.update({u: i for u in U})
        assignment.update({v: i for v in V})
    for u in W_DUMMY:
        assignment[u] = -1
    for v in R_DUMMY:
        assignment[v] = -1
    return assignment, relays


