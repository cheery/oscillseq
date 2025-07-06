# https://www.pdonatbouillud.com/project/rythm-quantization/
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any
from fractions import Fraction
import itertools
import re
import math
import bisect

primes = [2,3,5,7,11]

class Tree:
    def __init__(self, label, children=None, parent=None):
        self.label = label
        self.children = children if children is not None else []
        self.parent = parent
        for c in self.children:
            c.parent = self

    def __iter__(self):
        return iter(self.children)

    def __len__(self):
        return len(self.children)

    def copy(self):
        return Tree(self.label, [c.copy() for c in self])

    def __str__(self):
        if len(self) == 0:
            return f"{self.label}"
        return f"{'0123456789ab'[len(self)]}{''.join(str(c) for c in self.children)}"

    def __repr__(self):
        if len(self) == 0:
            return f"{self.label}"
        return f"{len(self)}({''.join(repr(c) for c in self.children)})"

    @classmethod
    def from_string(cls, s):
        if len(s) == 0 or not all(ch in '2357bnsro' for ch in s):
            return None
        s = iter(s)
        def make_tree():
            i = '2357bnsro'.index(next(s))
            if i == 5:
                return Tree('n')
            elif i == 6:
                return Tree('s')
            elif i == 7:
                return Tree('r')
            elif i == 8:
                return Tree('o')
            else:
                return Tree('', [make_tree() for _ in range(primes[i])])
        tree = make_tree()
        if tree.is_valid():
            return tree

    @classmethod
    def from_list(cls, value):
        if isinstance(value, list):
            return Tree("", [Tree.from_list(v) for v in value])
        else:
            return Tree(value)

    @property
    def subtrees(self):
        output = []
        def visit(tree):
            for stree in tree:
                output.append(stree)
                visit(stree)
        visit(self)
        return output

    @property
    def branches(self):
        output = []
        def visit(tree):
            if len(tree) > 0:
                output.append(tree)
                for stree in tree:
                    visit(stree)
        visit(self)
        return output

    @property
    def leaves(self):
        output = []
        def visit(tree):
            if len(tree) == 0:
                output.append(tree)
            else:
                for stree in tree:
                    visit(stree)
        visit(self)
        return output

    # checks whether shifting this element up/down will shear it.
    def shear(self):
        a = any(x.is_chained() for x in self.down(0))
        b = any(x.is_chain() for x in self.down(-1))
        return a and b

    def down(self, side=0):
        yield self
        while len(self) > 0:
            self = self.children[side]
            yield self

    @property
    def first_leaf(self):
        while len(self) > 0:
            self = self.children[0]
        return self

    @property
    def last_leaf(self):
        while len(self) > 0:
            self = self.children[-1]
        return self

    def is_chain(self):
        return len(self) == 0 and self.label == 'o'

    def is_chained(self):
        cousin = self.prev_cousin()
        return cousin is not None and cousin.is_chain()

    def prev_cousin(self):
        if self.parent is None:
            return None
        siblings = self.parent.children
        idx = siblings.index(self)
        if idx > 0:
            return siblings[idx-1]
        p_cousin = self.parent.prev_cousin()
        if p_cousin is None or len(p_cousin) == 0:
            return None
        return p_cousin.children[-1]

    def next_cousin(self, check=False):
        if self.parent is None:
            return None
        siblings = self.parent.children
        idx = siblings.index(self)
        if idx + 1 < len(siblings):
            return siblings[idx+1]
        if check and self.parent.is_chained():
            return None
        p_cousin = self.parent.next_cousin(check)
        if p_cousin is None or len(p_cousin) == 0:
            return None
        return p_cousin.children[0]

    def count_o(self):
        p = self
        count = 0
        while (p := p.prev_cousin()) is not None:
            if p.label != "o":
                break
            count += 1
        return count

    def durations(self, duration):
        durs = {self: duration}
        for tree in self.subtrees:
            sdur = durs[tree.parent] / len(tree.parent)
            cousin = tree.prev_cousin()
            if cousin is not None and len(cousin) == 0 and cousin.label == "o":
                cdur = durs[cousin]
            else:
                cdur = 0
            durs[tree] = sdur + cdur
        return durs

    def sequence(self, duration):
        durs = self.durations(duration)
        output = []
        leaves = []
        for leaf in self.leaves:
            if leaf.label == "o":
                continue
            elif leaf.label == "s" and len(output) > 0:
                output[-1] += durs[leaf]
            elif leaf.label == "r" and len(output) > 0 and leaves[-1] == "r":
                output[-1] += durs[leaf]
            else:
                output.append(durs[leaf])
                leaves.append(leaf.label)
        #assert sum(output) == duration, (sum(output), duration)
        return list(zip(output, leaves))

    # TODO: figure out if this is needed.
    #def to_edges(self, start, duration):
    #    edges = [start]
    #    for duration, label in self.sequence(duration):
    #        start += duration
    #        edges.append(start)
    #    return edges

    def to_events(self, start, duration):
        starts, stops = self.offsets(duration, start)
        return [(start, stop-start) for start, stop in zip(starts, stops)]

    def offsets(self, duration, start = 0.0):
        starts = []
        stops  = []
        for duration, label in self.sequence(duration):
            if label == "n":
                starts.append(start)
                stops.append(start + duration)
            start += duration
        return starts, stops

    def sdur(self):
        sd = Fraction(1)
        while self.parent:
            sd /= len(self.parent)
            self = self.parent
        return sd

    def is_valid(self):
        if len(self) == 0 and (self.label == "n" or self.label == "r"):
            return True
        if len(self) not in primes:
            return False
        for tree in self.subtrees:
            sdur = tree.sdur()
            if len(tree) == 0 and tree.label == "o":
                cousin = tree.next_cousin(check=True)
                if cousin is None:
                    return False
                assert cousin.prev_cousin() == tree
                c_sdur = cousin.sdur()
                if sdur != c_sdur:
                    return False
            if len(tree) > 0 and len(tree) not in primes:
                return False
        for leaf in self.leaves:
            if leaf.label == "o":
                continue
            elif leaf.label == "s":
                return False
            else:
                return True

    @property
    def root(self):
        while self.parent:
            self = self.parent
        return self

    @property
    def depth(self):
        return max(len(leaf.get_path()) for leaf in self.leaves)

    def get_path(self):
        path = []
        while self.parent:
            path.insert(0, self.parent.children.index(self))
            self = self.parent
        return path

    def access(self, path):
        for i in path:
            self = self.children[i]
        return self

    def prune_cousin(self):
        siblings = self.parent.children
        idx = siblings.index(self)
        if idx == 0:
            self.parent.prune_cousin()
            idx = siblings.index(self)
        a = siblings.pop(idx-1)
        self.label += a.label
        self.children[:0] = a.children
        for x in a.children:
            x.parent = self

    @property
    def penalty(self):
        if self.label == "s":
            return 1
        if self.label == "o":
            return 0.01
        if self.label == "r":
            return 0.1
        if self.label == "n":
            return 0.1
        c = primes.index(len(self)) * 0.1 + 0.1
        return c + sum(x.penalty for x in self)

def expansions(tree):
    for i, stree in enumerate(tree.branches):
        for p in primes:
            if not any(x.shear() for x in stree):
                deriv = tree.copy()
                expansion(deriv.branches[i], p)
                if deriv.is_valid():
                    yield deriv
        if (deriv := leaf_rewrite(tree, i, stree,
                ("rs", "rr"), ("or", "rr"), ("os", "ss"), ("on", "ns"))) is not None:
            yield deriv
        if (deriv := branch_fold(tree, i, stree)) is not None:
            yield deriv
        if (deriv := rechain(tree, i, stree)) is not None:
            yield deriv

def expansion(tree, p):
    a = len(tree)
    nchildren = []
    for child in tree:
        for _ in range(p - 1):
            nchildren.append(Tree("o"))
        nchildren.append(child)
    tree.children = []
    for i in range(p):
        child = Tree("", nchildren[i*a:i*a+a])
        tree.children.append(child)
        child.parent = tree

def leaf_rewrite(tree, i, stree, *orgnew):
    if len(stree) == 0:
        cousin = stree.next_cousin()
        if cousin is not None and len(cousin) == 0:
            pat = stree.label + cousin.label
            for org, new in orgnew:
                if pat == org:
                    deriv = tree.copy()
                    deriv.branches[i].label = new[0]
                    deriv.branches[i].next_cousin().label = new[1]
                    return deriv

def branch_fold(tree, i, stree):
    if not stree.shear() and len(stree) > 0:
        fold_to = None
        if all(len(s) == 0 and s.label == "r" for s in stree):
            fold_to = "r"
        if all(len(s) == 0 and s.label == "s" for s in stree):
            fold_to = "s"
        if all(len(s) == 0 and s.label == "s" for s in stree.children[1:]) and len(stree.children[0]) == 0 and stree.children[0].label == "n":
            fold_to = "n"
        if fold_to is not None:
            deriv = tree.copy()
            deriv.branches[i].label = fold_to
            deriv.branches[i].chilren = []
            return deriv

def rechain(tree, i, stree):
    if len(stree) == 0:
        return
    def get_chain(stree):
        chain = [stree]
        cousin = stree.prev_cousin()
        while cousin is not None and len(cousin) == 0 and cousin.label == "o":
            chain.insert(0, cousin)
            cousin = cousin.prev_cousin()
        return chain
    chain = get_chain(stree)
    total = len(chain)
    if total % len(stree) == 0:
        deriv = tree.copy()
        stree = deriv.branches[i]
        chain = get_chain(stree)
        k = total // len(stree)
        for i, subtree in enumerate(stree, 1):
            this = chain[k*i - 1]
            this.label = subtree.label
            this.children = subtree.children
            for child in subtree.children:
                child.parent = this
        return deriv

import random

def random_step(tree):
    weights = [1 / tree.penalty]
    choices = [tree]
    for exp in expansions(tree):
        weights.append(1 / exp.penalty)
        choices.append(exp)
    return random.choices(choices, weights=weights, k=1)[0]

def walk_down(tree, pen):
    for exp in expansions(tree):
        p = exp.penalty
        if p < pen:
            return walk_down(exp, p)
    return tree

def simplify(tree):
    print(tree)
    orig = tree.penalty
    for i in range(10):
        tree = random_step(tree)
        tree = walk_down(tree, tree.penalty)
        assert tree.is_valid(), str(tree)
    print("SCORE", orig - tree.penalty, tree)
    return tree
    #orig = tree.penalty
    #best = tree.penalty
    #result = tree
    #queue = [(best, tree)]
    #visited = {str(tree)}
    #while queue:
    #    pen, this = queue.pop(0)
    #    if pen < best:
    #        result = this
    #        best = pen
    #    for exp in expansions(this):
    #        pen = exp.penalty
    #        s_exp = str(exp)
    #        if s_exp in visited:
    #            continue
    #        visited.add(s_exp)
    #        #bisect.insort(queue, ((pen, exp)), key=lambda x: x[0])
    #print("improvement:", orig - best)
    #return result

def trees_offsets(durations, trees, start = 0.0):
    starts = []
    stops  = []
    for duration, tree in zip(durations, trees):
        for duration, label in tree.sequence(duration):
            if label == "n":
                starts.append(start)
                stops.append(start + duration)
            start += duration
    return starts, stops

#tree1 = Tree.from_list(['n', ['o', ["n", "n"], 'n']])
#tree2 = Tree.from_list([["n", "o"], [["n", "r"], "n"]])
#tree3 = Tree.from_list(['n', ['s', 'n'], 's'])
#for tree in [tree1, tree2, tree3]:
#    print(str(tree), Tree.from_string(str(tree)))
#    print("S:", simplify(tree))

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

class EuclideanRhythm:
    def __init__(self, pulses, steps, rotation):
        self.pulses = pulses
        self.steps = steps
        self.rotation = rotation

    def to_step_sequence(self):
        table = rotate(bjorklund(self.pulses, self.steps), self.rotation)
        return StepRhythm(table)

    def to_events(self, start, duration):
        return self.to_step_sequence().to_events(start, duration)

    def __str__(self):
        return f"E({self.pulses}, {self.steps}, {self.rotation})"

class StepRhythm:
    def __init__(self, table):
        self.table = table

    def to_events(self, start, duration):
        events = []
        duration /= len(self.table)
        for i, on in enumerate(self.table):
            if on:
                events.append((start + i*duration, duration))
        return events

    def __str__(self):
        return "".join(map(str, self.table))

_EUC_RE = re.compile(
    r'^\s*E'
    r'\(\s*'
      r'(-?\d+)\s*,\s*'          # pulses
      r'(-?\d+)\s*,\s*'          # steps
      r'(-?\d+)\s*'              # rotation (can be negative)
    r'\)\s*$'
)

_RAW_RE = re.compile(r'^\s*([01]+)\s*$')

def from_string(s):
    m = _EUC_RE.match(s)
    if m:
        pulses = int(m.group(1))
        steps  = int(m.group(2))
        rot    = int(m.group(3))
        return EuclideanRhythm(pulses, steps, rot)

    m = _RAW_RE.match(s)
    if m:
        bits = [int(ch) for ch in m.group(1)]
        return StepRhyhm(bits)

    return Tree.from_string(s)

assert from_string("3no3son") is not None
