from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any
from fractions import Fraction
import bisect
import itertools
import measure

costs = {2 : 0.2, 4 : 0.3, 3 : 0.4, 6 : 0.5, 8 : 0.6, 5 : 0.7, 7 : 0.8, 11 : 0.9}

class Quant:
   def __init__(self, children=None):
       self.children = children if children is not None else []

   def __iter__(self):
       return iter(self.children)

   def __len__(self):
       return len(self.children)

   def __getitem__(self, index):
       return self.children[index]

   def __setitem__(self, index, value):
       self.children[index] = value

   def copy(self):
       return Quant([c.copy() for c in self])

   def __str__(self):
       return f"({','.join(str(c) for c in self)})"

   def dist(self, points):
       return sum(a.dist(points) for a in self)

@dataclass(eq=False)
class Interval:
   start  : float
   stop   : float
   denom  : int = 1

   def narrow(self, points):
       i = bisect.bisect_left(points, self.start)
       j = bisect.bisect_left(points, self.stop)
       return points[i:j]

   def divide(self, p):
       span = (self.stop - self.start) / p
       out = []
       for i in range(p):
           out.append(Interval(self.start + span*i, self.start + span*(i+1), self.denom*p))
       return Quant(out)

   def index(self, point):
       return round((point - self.start) / (self.stop - self.start))

   def snap(self, point):
       return [self.start, self.stop][self.index(point)]

   def dist(self, points):
       return sum(abs(self.snap(pt)-pt) for pt in self.narrow(points))

   def cost(self, points, alpha):
       return self.dist(points)*alpha

   def __repr__(self):
       return f"{self.start}"

   def copy(self):
       return self

def intervals(rt):
    intervals = []
    def visit(rt):
        if isinstance(rt, Quant):
            for x in rt:
                visit(x)
        else:
            intervals.append(rt)
    visit(rt)
    return intervals

def snaps(rt, points):
    snaps = [0]
    for iv in intervals(rt):
        snaps.append(0)
        for pt in iv.narrow(points):
            snaps[-2 + iv.index(pt)] += 1
    if iv.stop == points[-1]:
        snaps[-1] += 1
    return snaps

def grace(rt, points):
    return sum(k-1 for k in snaps(rt, points) if k > 1)

def grid(rt):
    output = [0]
    for iv in intervals(rt):
        output.append(iv.stop)
    return output

def snap(rt, points):
    offsets = []
    for k, pt in zip(snaps(rt, points), grid(rt)):
        offsets.extend([pt]*k)
    return offsets

def val(rt, points, m=1):
    fractions = [Fraction(1, iv.denom) for iv in intervals(rt)]
    g = grid(rt)
    ix = []
    for pt in snap(rt,points):
        ix.append(bisect.bisect_left(g, pt))
    val = []
    for i in range(len(ix)-1):
        val.append(m*sum(fractions[ix[i]:ix[i+1]]))
    return val

def tree(rt, points):
    s = snaps(rt, points)
    def visit(rt, ix):
        if isinstance(rt, Quant):
            trees = []
            for x in rt:
                tree, ix = visit(x, ix)
                trees.append(tree)
            return measure.Tree("", trees), ix
        else:
            return measure.Tree("n", []) if s[ix] > 0 else measure.Tree("s", []), ix+1
    return visit(rt, 0)[0]

class Exhausted(Exception):
    pass

def k_best(k, interval, points, alpha=0.5, costs=costs):
    bests = {}
    cands = {}
    uncomputed = {}
    def get_cand(interval):
        h = interval.start,interval.stop
        if h in cands:
            return cands[h], uncomputed[h], bests[h]
        c = interval.cost(points, alpha)
        bests[h] = best = []
        cands[h] = cand = [(c+(1-alpha)*grace(interval, points), c, 0, (), interval)]
        uncomputed[h] = unc = []
        for p, w in costs.items():
            unc.append((w, [(0, ii) for ii in interval.divide(p)]))
        unc.sort(key=lambda x: x[0])
        return cand, unc, best

    def best(k, interval, depth=5):
        if depth == 0:
            raise Exhausted
        h = interval.start,interval.stop
        cand, unc, solved = get_cand(interval)
        while len(cand) + len(unc) > 0 and k >= len(solved):
            while len(unc) > 0:
                if cand and cand[0][0] <= unc[0][0]:
                    break
                c, run = unc.pop(0)
                try:
                    vector = [best(a,iv,depth-1) for a,iv in run]
                    w = (1-alpha)*c + sum(v[1] for v in vector)
                    q = Quant([v[3] for v in vector])
                except Exhausted:
                    continue
                cand.append((w+(1-alpha)*grace(q,points),w,c,run,q))
                cand.sort(key=lambda x: x[0])
            if len(cand) == 0:
                break
            t, w, c, run,q = cand.pop(0)
            solved.append((t, w, run, q))
            for j in range(len(run)):
                unc.append((c, [(a + 1*(j==j1), r) for j1,(a,r) in enumerate(run)]))
            unc.sort(key=lambda x: x[0])
        if k < len(solved):
            return solved[k]
        raise Exhausted
    for n in range(k):
        try:
            w, _, run, q = best(n, interval)
            yield w, q
        except Exhausted:
            break

def quantize_to_val(k, points, duration):
    for w, rt in k_best(k, Interval(points[0], points[-1]), points):
        yield w, val(rt, points, Fraction(duration))

def quantize_to_dtree(k, points, duration):
    for w, rt in k_best(k, Interval(points[0], points[-1]), points):
        yield w, dtree(rt, points)

def quantize_to_tree(k, points, alpha=0.5):
    costs = {2 : 0.2, 3 : 0.4, 5 : 0.7, 7 : 0.8, 11 : 0.9}
    for w, rt in k_best(k, Interval(points[0], points[-1]), points, alpha, costs=costs):
        return tree(rt, points)

#def partition(t, arity):
#    target = sum(v for v,_ in t) / arity
#    current = 0
#    part = []
#    parts = []
#    penalty = 0
#    for d, tree in t:
#        current += d
#        part.append([d, tree])
#        while current > target:
#            penalty += 1
#            p = current - target
#            part[-1][0] -= p
#            parts.append(tuple(map(tuple, part)))
#            current = p
#            part = [[p, measure.Tree("s")]]
#        if current == target:
#            parts.append(tuple(map(tuple, part)))
#            current = 0
#            part = []
#    return costs[arity]*penalty, parts
#
#def val_to_tree(val, notes=None):
#    tasks = {}
#    if notes is None:
#        notes = [True] * len(val)
#    val = tuple((v, measure.Tree("n" if w else "r")) for v,w in zip(val, notes))
#    def fetch(val):
#        if val in tasks:
#            return tasks[val]
#        work = [partition(val, p) + ([],) for p in measure.primes]
#        work.sort(key=lambda x: x[0])
#        tasks[val] = task = work
#        return task
#    def explore(val, depth=4):
#        if len(val) == 1:
#            return 0, val[0][1]
#        work = fetch(val)
#        if not isinstance(work, list):
#            return work
#        if depth == 0 or not work:
#            raise Exhausted
#        penalty, remain, ready = work.pop(0)
#        while remain:
#            try:
#                pen, tree = explore(remain.pop(0), depth-1)
#            except Exhausted:
#                if len(work) == 0:
#                    raise Exhausted
#                penalty, remain, ready = work.pop(0)
#                continue
#            penalty += pen
#            ready.append(tree)
#            if work and work[0][0] < penalty:
#                work.append((penalty, remain, ready))
#                penalty, remain, ready = work.pop(0)
#                work.sort(key=lambda x: x[0])
#        tasks[val] = pt = (penalty, measure.Tree("", ready))
#        return pt
#    return explore(val)[1]

#points = [0, 0.5, 1.0, 5.0, 5.5, 7.0, 10.0]
#for w, v in quantize_to_val(10, points, 4):
#    t = val_to_tree(v)
#    print("TREE", t)
