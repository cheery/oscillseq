# We may some day use bouillud's rhythm trees again,
# but for now they seem to be very troublesome to work with
# because the quantization into these trees is difficult.
# I switched to OpenMusic-style trees that can be found
# in the dtree -module.
#
# For now this code remains here because I spent lot of time into it
# and it may become useful later.
#
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

    def pinpoint(self, path):
        if path:
            ix = path[0]
            head = '0123456789ab'[len(self)] + "".join(map(repr, self.children[:ix]))
            tail = "".join(map(repr, self.children[ix+1:]))
            return head + "{" + self.children[ix].pinpoint(path[1:]) + "}" + tail
        return repr(self)

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
        return a or b

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
        #print("is chain:", self.root.pinpoint(self.get_path()), len(self) == 0 and self.label == 'o')
        return len(self) == 0 and self.label == 'o'

    def is_chained(self):
        cousin = self.prev_cousin()
        #print("is chained:", self.root.pinpoint(self.get_path()), cousin is not None and cousin.is_chain())
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
            print("prime violation")
            return False
        for tree in self.subtrees:
            sdur = tree.sdur()
            if len(tree) == 0 and tree.label == "o":
                cousin = tree.next_cousin(check=True)
                if cousin is None:
                    print("no cousin on 'o'", tree.root.pinpoint(tree.get_path()))
                    return False
                assert cousin.prev_cousin() == tree
                c_sdur = cousin.sdur()
                if sdur != c_sdur:
                    print("inconsistent sdur on 'o'")
                    return False
            if len(tree) > 0 and len(tree) not in primes:
                print("prime violation")
                return False
        for leaf in self.leaves:
            if leaf.label == "o":
                continue
            elif leaf.label == "s":
                print("starts with a slur")
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

    def score(self, costmap):
        if len(self) == 0:
            return costmap[self.label]
        else:
            return costmap[len(self)] + sum(x.score(costmap) for x in self)

def equivalences(tree):
    for subtree in [tree] + tree.subtrees:
        if len(subtree) > 0 and not any(x.shear() for x in subtree):
            for p in primes:
                if len(subtree) != p:
                    a = subtree.get_path()
                    deriv = tree.copy()
                    expansion(deriv.access(a), p)
                    #assert deriv.is_valid(), (deriv, tree)
                    yield deriv
        if (deriv := leaf_rewrite(tree, subtree,
                ("rs", "rr"), ("or", "rr"), ("os", "ss"), ("on", "ns"))) is not None:
            yield deriv
        if (deriv := branch_fold(tree, subtree)) is not None:
            yield deriv
        if (deriv := rechain(tree, subtree)) is not None:
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

def leaf_rewrite(tree, stree, *orgnew):
    if len(stree) == 0:
        cousin = stree.next_cousin()
        if cousin is not None and len(cousin) == 0:
            pat = stree.label + cousin.label
            for org, new in orgnew:
                if pat == org:
                    a = stree.get_path()
                    deriv = tree.copy()
                    stree = deriv.access(a)
                    stree.label = new[0]
                    stree.next_cousin().label = new[1]
                    return deriv

def branch_fold(tree, stree):
    if not stree.shear() and len(stree) > 0:
        fold_to = None
        if all(len(s) == 0 and s.label == "r" for s in stree):
            fold_to = "r"
        if all(len(s) == 0 and s.label == "s" for s in stree):
            fold_to = "s"
        if all(len(s) == 0 and s.label == "s" for s in stree.children[1:]) and len(stree.children[0]) == 0 and stree.children[0].label == "n":
            fold_to = "n"
        if fold_to is not None:
            a = stree.get_path()
            deriv = tree.copy()
            stree = deriv.access(a)
            stree.label = fold_to
            stree.children = []
            return deriv

def rechain(tree, stree):
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
        a = stree.get_path()
        deriv = tree.copy()
        stree = deriv.access(a)
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
    for exp in equivalences(tree):
        weights.append(1 / exp.penalty)
        choices.append(exp)
    return random.choices(choices, weights=weights, k=1)[0]

def walk_down(tree, pen):
    for exp in equivalences(tree):
        p = exp.penalty
        if p < pen:
            return walk_down(exp, p)
    return tree

collapse = { "o": 1.0, "n": 0.1, "r": 0.1, "s": 0.2, 2: 0, 3: 0.1, 5: 0.5, 7: 0.8, 11: 1.0 }
expand = { "o": 0.1, "n": 0.1, "r": 0.1, "s": 0.2, 2: 0, 3: 0.1, 5: 0.5, 7: 0.8, 11: 1.0 }

def normalize(tree, costmap, score=None):
    orig = tree.score(costmap) if score is None else score
    for exp in equivalences(tree):
        s = exp.score(costmap)
        if s < orig:
            return normalize(exp, costmap, s)
    return tree

def bump(tree):
    def fn(tree):
        tree = normalize(tree, collapse)
        yield tree.score(expand), tree
        for exp in equivalences(tree):
            exp = normalize(exp, collapse)
            yield exp.score(expand), exp
    return min(fn(tree), key=lambda k: k[0])[1]

def simplify(tree):
    tree = bump(tree)
    tree = normalize(tree, expand)
    return tree

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
#assert from_string("3no3son") is not None
#assert any(x.shear() for x in from_string("23ono3son"))
#print(simplify(from_string("3n2sns")))
#for tree in equivalences(from_string("3n23snssn")):
#    print("EQV", tree)
