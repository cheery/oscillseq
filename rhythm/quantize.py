from .dtree import DTree
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any
from fractions import Fraction
import functools
import itertools
import bisect

class Nonterminal:
    def __init__(self, name, segment=None, prod=None):
        self.name = name
        self.segment = segment
        self.prod = [] if prod is None else prod

    def __eq__(self, other):
        if self.name != other.name:
            return False
        elif self.segment != other.segment:
            return False
        elif self.stop != other.stop:
            return False
        else:
            return True

    def __lt__(self, other):
        return (self.name, self.segment.cmp) < (other.name, other.segment.cmp)

    def __hash__(self):
        return hash((self.name, self.segment))

    def __repr__(self):
        if self.segment is None:
            return f"{self.name}"
        return f"{self.name}:{self.segment}"

    def debug(self):
        visited = set()
        def visit(this):
            if not isinstance(this, Nonterminal) or this in visited:
                return
            visited.add(this)
            for w, dtree in this.prod:
                dtree.rewrite(lambda x: visit(x.label))
        visit(self)
        for nt in sorted(visited):
            print(f"{nt}")
            for w, dtree in nt.prod:
                print(f"  {nt} -> {w} {dtree}")
            print("")

class Exhausted(Exception):
    pass

def k_best(q):
    bests = {}
    cands = defaultdict(list)
    uncomputed = defaultdict(list)
    def initial(q):
        if q in bests:
            return q
        bests[q] = []
        for w, dtree in q.prod:
            run = [(initial(x.label), 0) for x in dtree.leaves() if isinstance(x.label, Nonterminal)]
            if len(run) == 0:
                cands[q].append((w, 0, run, dtree))
            else:
                uncomputed[q].append((w, run, dtree))
        cands[q].sort(key=lambda x: x[0])
        uncomputed[q].sort(key=lambda x: x[0])
        return q
    initial(q)
    def best(k, q):
        while len(cands[q]) + len(uncomputed[q]) > 0 and k >= len(bests[q]):
            while len(uncomputed[q]) > 0:
                if cands[q] and cands[q][0][0] <= uncomputed[q][0][0]:
                    break
                c, run, x = uncomputed[q].pop(0)
                try:
                    w = c + sum(best(i,r)[0] for r,i in run)
                except Exhausted:
                    continue
                cands[q].append((w, c, run, x))
                cands[q].sort(key=lambda x: x[0])
            if len(cands[q]) == 0:
                break
            w, c, run, x = cands[q].pop(0)
            bests[q].append((w, run, x))
            for j in range(len(run)):
                uncomputed[q].append((c, [(r,i + 1*(j==j1)) for j1,(r,i) in enumerate(run)], x))
            uncomputed[q].sort(key=lambda x: x[0])
        if k < len(bests[q]):
            return bests[q][k]
        raise Exhausted
    def rewrite(i, q):
        w, run, dtree = best(i, q)
        pattern = [rewrite(i, nt)[1] for nt,i in run]
        dtree = dtree.instantiate(pattern, lambda x: isinstance(x.label, Nonterminal))
        #dtree.label = repr(q) + (";" + dtree.label if dtree.label else "")
        return w, dtree
    i = 0
    while True:
        try:
            yield rewrite(i, q)
            i += 1
        except Exhausted:
            break

@dataclass(eq=True, frozen=True)
class Interval:
    start : float
    stop  : float

    def narrow(self, points, notes, inclusive=False):
        i = bisect.bisect_left(points, self.start)
        j = bisect.bisect_left(points, self.stop)
        if inclusive and points[j] == self.stop:
            j += 1
        return list(range(i, j))

    def index(self, point):
        return round((point - self.start) / (self.stop - self.start))

    def __getitem__(self, index):
        if index == 0:
            return self.start
        else:
            return self.stop

    @property
    def cmp(self):
        return self.start

    def __repr__(self):
        return str(self.start) + ":" + str(self.stop)

def bars(grammar, count):
    nt = Nonterminal(f"BARS_{count}")
    nt.prod.append((0, DTree(1, None, [DTree(1, grammar, [])]*count))) 
    return nt

def equivalent(nt, pts, notes, alpha=1.0):
    @functools.cache
    def produce(ref, segment):
        nt = Nonterminal(ref.name, segment)
        for w, dtree in ref.prod:
            nt.prod.extend(derive(w * alpha, dtree, segment))
        return nt
    def derive(weight, dtree, segment):
        indices = segment.narrow(pts, notes)
        leaves = dtree.leaves_with_durations(duration=Fraction(1))
        if len(leaves) > 1 and len(indices) > 0:
            inst = [produce(leaf.label, seg) for leaf, seg in divide(segment, leaves)]
            new_leaves = [DTree(leaf.weight, nt, [], leaf.rule_id)
                          for (leaf,_), nt in zip(leaves, inst)]
            yield weight, dtree.instantiate(new_leaves, lambda x: isinstance(x.label, Nonterminal))
        elif len(leaves) == 1:
            if dtree.label == "s" and len(indices) == 0:
                yield weight, dtree
            elif dtree.label != "s" and len(indices) > 0:
                penalty = 0
                bins = [[], []]
                for i in indices:
                    k = segment.index(pts[i])
                    penalty += abs(pts[i] - segment[k]) / (segment.stop - segment.start)
                    bins[k].append(notes[i])
                leading = bins[0].pop(-1) if bins[0] else bins[1].pop(0)
                if leading == dtree.label:
                    out = []
                    for early in bins[0]:
                        out.append(DTree(0, early, [], None))
                    out.append(DTree(1, leading, [], None))
                    for late in bins[1]:
                        out.append(DTree(0, late, [], None))
                    if len(out) > 1:
                        yield weight + penalty, DTree(dtree.weight, dtree.label, out, dtree.rule_id)
                    else:
                        out[0].weight = dtree.weight
                        out[0].rule_id = dtree.rule_id
                        yield weight + penalty, out[0]
        
    def divide(segment, leaves):
        width = segment.stop - segment.start
        offset = segment.start
        for leaf, dur in leaves:
            yield leaf, Interval(offset, min(offset + dur*width, segment.stop))
            offset += dur*width

    return produce(nt, Interval(pts[0], pts[-1]))

def dtree(nt, points, notes, alpha=0.01):
    pts = []
    pre_rms = []
    for i in range(len(points)-1):
        if points[i] < points[i+1]:
            pts.append(points[i])
            pre_rms.append(i)
    pts.append(points[-1])
    notes = [notes[i] for i in pre_rms]
    g = equivalent(nt, pts, notes, alpha)
    for _, dtree in k_best(g):
        break
    rms = []
    leaves = dtree.leaves()
    for i in range(len(leaves)-1):
        a, b = leaves[i:i+2]
        if a.weight == 0 and b.label == "s":
            b.label = a.label
            a.label = "s"
    i = 0
    for x in leaves:
        if x.label != "s" and x.weight > 0:
            rms.append(pre_rms[i])
            i += 1
    dtree = dtree.remove_grace_notes().reconnect_slurs()
    return dtree, rms
