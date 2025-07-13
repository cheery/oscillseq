from .dtree import DTree, decompose
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any
from fractions import Fraction
import bisect
import itertools
import rhythm as measure
import math
import numpy as np

#costs = {2 : 0, 4 : 0.5, 3 : 1, 6 : 2, 8 : 3, 5 : 4, 7 : 5}

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

   def narrow(self, points, inclusive=False):
       i = bisect.bisect_left(points, self.start)
       j = bisect.bisect_left(points, self.stop)
       if inclusive and points[j] == self.stop:
           j += 1
       return points[i:j]

   def divide(self, p):
       span = (self.stop - self.start) / p
       out = []
       for i in range(p):
           out.append(Interval(self.start + span*i, self.start + span*(i+1), self.denom*p))
       return Quant(out)

   def index(self, point):
       return max(0, min(1, round((point - self.start) / (self.stop - self.start))))

   def snap(self, point):
       try:
           return [self.start, self.stop][self.index(point)]
       except IndexError:
           print("IX", self.index(point))
           raise

   def dist(self, points):
       delta = self.stop - self.start
       return sum(abs(self.snap(pt)-pt) for pt in self.narrow(points)) / delta

   def cost(self, points, alpha):
       return self.dist(points)*10*alpha

   def __repr__(self):
       return f"{self.start}"

   def copy(self):
       return self

class Exhausted(Exception):
    pass

def k_best(k, interval, points, alpha=0.5, beta=0.2, costs=costs):
    bests = {}
    cands = {}
    uncomputed = {}
    def get_cand(interval):
        h = interval.start,interval.stop
        if h in cands:
            return cands[h], uncomputed[h], bests[h]
        c = interval.cost(points, alpha)
        bests[h] = best = []
        cands[h] = cand = [(c+beta*grace(interval, points), c, 0, (), interval)]
        uncomputed[h] = unc = []
        for p, w in costs.items():
            unc.append((w, [(0, ii) for ii in interval.divide(p)]))
        unc.sort(key=lambda x: x[0])
        return cand, unc, best

    def best(k, interval, depth=3):
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
                cand.append((w+beta*grace(q,points),w,c,run,q))
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

#def quantize_to_val(points, duration, alpha=0.5, beta=0.2):
#    for w, rt in k_best(1, Interval(points[0], points[-1]), points, alpha):
#        return val(rt, points, Fraction(duration))
#
#def quantize_to_dtree(points, alpha=0.5, beta=0.2):
#    for w, rt in k_best(1, Interval(points[0], points[-1]), points, alpha, beta):
#        return dtree(rt, points)
#
#def quantize_to_tree(points, alpha=0.5, beta=0.2):
#    costs = {2 : 0.2, 3 : 0.4, 5 : 0.7, 7 : 0.8, 11 : 0.9}
#    for w, rt in k_best(1, Interval(points[0], points[-1]), points, alpha, beta, costs=costs):
#        return tree(rt, points)
#
#def quantize_to_tree2(points, alpha=0.5, beta=0.2):
#    return measure.simplify(quantize_to_tree(points, alpha, beta))

@dataclass(frozen=True)
class Boundary:
    arity : int
    count : int = 0
    granularity : Optional[Fraction] = None

    @property
    def boundary(self):
        return self.granularity * self.arity

    @property
    def cumulative(self):
        return self.granularity * self.count

    @property
    def finished(self):
        return self.arity == self.count

    def step(self, n):
        assert highest_bit_mask(n.denominator) == n.denominator
        m = Fraction(1, n.denominator)
        while n.numerator & highest_bit_mask(m.numerator) == 0:
            m *= 2
        granularity = self.granularity or m
        count = self.count
        while m < granularity and count <= self.arity:
            granularity /= 2
            count *= 2
        count += int(n / granularity)
        if self.count == 0 and count == self.arity:
            return None
        if count <= self.arity:
            assert m >= granularity, (m, granularity)
            boundary = Boundary(self.arity, count, granularity)
            return boundary

@dataclass(frozen=True)
class ParseState:
    index : int
    arity : int
    prev  : Optional['ParseState']
    up    : Optional['ParseState']
    boundary : Boundary
    cost  : float
    ns    : List[Fraction]
    correction : Fraction = 0
    complete : Optional['Parsestate'] = None

    @classmethod
    def initial(cls, arity):
        return ParseState(
            index = 0,
            arity = arity,
            prev  = None,
            up    = None,
            boundary   = Boundary(arity),
            cost       = 0,
            ns = [])

    @property
    def key(self):
        if self.up:
            return (self.index, self.arity) + self.up.key
        return self.index, self.arity

    @property
    def depth(self):
        return self.up.depth+1 if self.up else 1

    @property
    def arities(self):
        return self.up.arities * self.arity if self.up else 1

    def advance(self, boundary, cost, ns, correction=0):
        assert not self.boundary.finished
        assert len(ns) > 0
        return ParseState(
            index = self.index + 1,
            arity = self.arity,
            prev  = self,
            up    = self.up,
            boundary = boundary,
            cost = cost,
            ns = ns,
            correction = correction)

    def descend(self, arity, cost):
        return ParseState(
            index = self.index,
            arity = arity,
            prev  = None,
            up    = self,
            boundary = Boundary(arity),
            cost = cost,
            ns = [])

    def climb(self):
        my_boundary = self.up.boundary.step(self.boundary.cumulative)
        if my_boundary:
            return ParseState(
                index = self.index,
                arity = self.up.arity,
                prev  = self.up,
                up    = self.up.up,
                boundary = my_boundary,
                cost = self.cost,
                ns = [],
                complete = self,
                correction = self.correction*self.arity)

    def unroll(self):
        result = []
        while self:
            result.append(self)
            self = self.prev
        result.reverse()
        return result

def granulate(granularity, ns):
    return min(granularity, min(Fraction(1, n.denominator) for n in ns))

def check_path(DTree, quant, points, duration=1):
    vs = val(quant, points, duration)
    if len(vs) == 1:
        return DTree(1, "n", [])
    total = sum(vs)
    tuplet_penalty = {2: 0.05, 4: 0.075, 3: 0.1, 5: 0.2, 7: 0.3, 11: 0.4}
    def penalty(ns, correction):
        return len(ns) * 0.1 + abs(float(correction)) * 10.0
    def stepforward(state):
        p = state.arities
        boundary = state.boundary
        value = vs[state.index]/p + state.correction
        if state.index + 1 == len(vs):
            v = (boundary.arity - boundary.count) * boundary.granularity if boundary.granularity else total
            ns = decompose(v)
            for n in ns:
                boundary = boundary.step(n)
            correction = v - value
            pen = penalty(ns, correction)
            assert sum(ns) == v, (ns, v)
            assert boundary.finished
            state = state.advance(boundary, state.cost + pen, ns)
            while state and state.boundary.finished and state.up:
                state = state.climb()
            if state:
                yield state
        else:
            if state.depth < 3:
                for q in (2,3,4,5,7,11):
                    yield state.descend(q, state.cost + tuplet_penalty[q])
            w = (boundary.arity - boundary.count) * (boundary.granularity or 0)
            if 0 < w <= value and state.up:
                ns = decompose(w)
                bnd = boundary
                for n in ns:
                    bnd = bnd.step(n)
                assert sum(ns) == w, (ns, w)
                assert bnd.finished
                state = state.advance(bnd, state.cost + penalty(ns, w - value), ns, w - value)
                while state and state.boundary.finished and state.up:
                    state = state.climb()
                if state and state.up:
                    yield state
            w = Fraction(round(value * 256), 256)
            correction = value
            ns = []
            for n in decompose(w):
                boundary = boundary.step(n)
                if not boundary or boundary.finished:
                    break
                correction -= n
                ns.append(n)
                yield state.advance(boundary, state.cost + penalty(ns, correction), ns.copy(), correction)
    def make_notes(ns):
        out = []
        label = "n"
        for n in ns:
            out.append(DTree(n, label, []))
            label = "s"
        return out
    def lowest_bit_mask(n):
        k = 1
        while n & 1 == 0:
            n >>= 1
            k <<= 1
        return k
    def make_seq(state):
        seq = []
        for st in state.unroll():
            seq.extend(make_notes(st.ns))
            if st.complete:
                seq.append(make_tree(st.complete))
        return seq
    def make_tree(state):
        seq = make_seq(state)
        total = sum(item.weight for item in seq)
        for item in seq:
            item.weight = int(item.weight / total * state.arity)
            assert item.weight > 0, (seq, state.boundary)
        assert sum(item.weight for item in seq) == state.boundary.arity, (seq, state.boundary)
        return DTree(state.boundary.cumulative, None, seq)
    graph = {}
    queue = [ParseState.initial(i) for i in (2,3,4,5,7,11)]
    while len(queue) > 0:
        state = queue.pop(0)
        if state.index == len(vs):
            if state.boundary.finished and state.up is None:
                tree =  make_tree(state)
                tree.weight = 1
                return tree
            continue
        if state.key in graph:
            continue
        graph[state.key] = state
        for state in stepforward(state):
            bisect.insort(queue, state, key=lambda x: x.cost)

    print(make_seq(max((state for state in graph.values() if state.up is None), key=lambda st: (st.index, -st.cost))))

    return DTree(1, "n", [])

def val_to_dtree(vs, notes, alpha=0.8):
    N = len(vs)
    if N == 1:
        return DTree(1, notes[0], [])
    total = sum(vs)
    tuplet_penalty = {2: 0.05, 4: 0.05, 3: 0.13, 5: 0.15, 7: 0.17, 11: 0.2}
    def penalty(xs):
        a, b = xs
        return a*alpha + b*(1-alpha)
    def penalty0(xs):
        return penalty(xs[0])
    def distortion(m, x):
        return abs(m - x) / x
    def estimate(k, i, n):
        segment = float(sizes[k][i] / n)
        for s in range(k):
            x = sizes[k-1-s][i]
            y = sizes[s][i+k-s]
            jx = max(1, min(n-1, round(x / segment)))
            jy = n - jx
            pc1 = np.array([distortion(segment*jx, x), 0])
            pc2 = np.array([distortion(segment*jy, y), 0])
            pc = pc1 + pc2 / 2
            three = np.array([3, 3])
            yield (pc + estim[1][k-1-s][i] + estim[jy][s][k+i-s]) / three, s, -jx, jy
            yield (pc + estim[jx][k-1-s][i] + estim[1][s][k+i-s]) / three, s, jx, -jy
            yield (pc + estim[jx][k-1-s][i] + estim[jy][s][k+i-s]) / three, s, jx, jy
    def basis(k,i):
        for n in tuplet_penalty:
            yield estim[n][k][i] + np.array([0, tuplet_penalty[n]]), n
    estim = [[[np.array([0,0])]*(N-k) for k in range(0, N)] for _ in range(12)]
    sizes = [vs] + [[0]*(N-k) for k in range(1, N)]
    for i in range(N):
        for n in range(1, 12):
            estim[n][0][i] = np.array([len(decompose(n))**3, len(decompose(n))**3])
    for k in range(1, N):
        for i in range(N-k):
            sizes[k][i] = sizes[k-1][i] + sizes[0][i+k]
            for n in range(2, 12):
                estim[n][k][i] = min(estimate(k,i,n), key=penalty0)[0]
            estim[1][k][i] = min(basis(k,i), key=penalty0)[0]
    def make_tree(k, i, w):
        if k == 0:
            return DTree(w, notes[i], [])
        pen, n = min(basis(k,i), key=penalty0)
        return DTree(w, None, make_seq(k, i, n))
    def make_seq(k, i, n):
        if k == 0 or n <= 1:
            return [make_tree(k, i, abs(n))]
        else:
            s, jx, jy = min(estimate(k, i, n), key=penalty0)[1:]
            return make_seq(k-1-s, i, jx) + make_seq(s, k+i-s, jy)
    return make_tree(N-1, 0, 1)

def dtree(points, notes, alpha=0.5, beta=0.2, delta=0.75):
    vs = []
    rms = []
    for i in range(len(points)-1):
        if points[i] < points[i+1]:
            vs.append(points[i+1] - points[i])
            rms.append(i)
    return val_to_dtree(vs, [notes[i] for i in rms], delta), rms
