from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any
from fractions import Fraction
import bisect
import itertools
import math
import numpy as np
import functools

class Grid:
    def __init__(self, children):
        self.children = children
        self.start = children[0].start
        self.stop  = children[-1].stop

    def __iter__(self):
        return iter(self.children)

    def __len__(self):
        return len(self.children)

    def __getitem__(self, index):
        return self.children[index]

    def __str__(self):
        return f"({' '.join(str(x) for x in self)})"

    def __repr__(self):
        return str(self)

@dataclass(eq=True, frozen=True)
class Interval:
    start  : Fraction
    stop   : Fraction

    def interpolate(self, t):
        return self.start*(1-t) + self.stop*t

    def divide(self, p):
        out = []
        for i in range(p):
            start = self.interpolate(Fraction(i,   p))
            stop  = self.interpolate(Fraction(i+1, p))
            out.append(Interval(start, stop))
        return out

    def snap(self, point):
        t = (point - self.start) / float(self.stop - self.start)
        if t <= 0.5:
            return self.start
        else:
            return self.stop

    def select(self, points):
        i = bisect.bisect_left(points, self.start)
        j = bisect.bisect_left(points, self.stop)
        return points[i:j]

    def __str__(self):
        return f"{self.start}:{self.stop}"

    def __repr__(self):
        return str(self)

def normalize(points, start=None, stop=None):
    start = points[0] if start is None else start
    stop  = points[-1] if stop is None else stop
    length = stop - start
    offset = start
    return [(point - offset) / length for point in points]

#def stretch(points, start, stop):
#    width = stop - start
#    return [float(point) * width + start for point in points]

def snap_points(grid):
    out = []
    def visit(grid):
        if isinstance(grid, Interval):
            out.append(grid.start)
        else:
            for grid in grid:
                visit(grid)
    visit(grid)
    out.append(grid.stop)
    return out

def snap(grid, points):
    out = []
    def visit(grid, points):
        if isinstance(grid, Interval):
            out.extend(grid.snap(point) for point in points)
        else:
            bins = [[] for _ in grid]
            for point in points:
                i = bisect.bisect_right(grid, point, key=lambda x: x.start) - 1
                bins[max(0, i)].append(point)
            for grid, points in zip(grid, bins):
                visit(grid, points)
    visit(grid, points)
    return out

#def align(grid, points, start=None, stop=None):
#    start = points[0] if start is None else start
#    stop  = points[-1] if stop is None else stop
#    return stretch(snap(grid, normalize(points, start, stop)), start, stop)

# "A Supervised Approach for Rhythm Transcription Based on Tree Series Enumeration"

class Viterbi:
    """
        Alpha parameter weakens cost of distance error
        Beta parameter weakens cost of structure
    """
    costs = {2 : 0.9, 4 : 0.85, 3 : 0.8, 6 : 0.75, 8 : 0.7, 5 : 0.65, 7 : 0.55}
    best = 1

    def __init__(self, alpha = 0.0, beta = 0.75, grace=0.95):
        self.alpha = alpha
        self.beta  = beta
        self.grace = grace

    def cost(self, interval, points):
        total = 1
        for point in points:
            total *= 1 - float(abs(interval.snap(point) - point))*2
        for _ in range(1, len(points)):
            total *= self.grace
        return total + (1-total) * self.alpha

    def ordering(self, item):
        return -item[0]

    def better(self, i0, i1):
        return i0[0] >= i1[0]

    def evaluate(self, cost, costs):
        for k in costs:
            cost *= k
        return k + (1-k) * self.beta

class Tropical:
    costs = {2 : 0.2, 4 : 0.3, 3 : 0.4, 6 : 0.5, 8 : 0.6, 5 : 0.7, 7 : 0.8}
    best = 0

    def __init__(self, alpha = 0.9):
        self.alpha = alpha

    def cost(self, interval, points):
        total = 0
        for point in points:
            total += float(abs(interval.snap(point) - point))
        total /= float(interval.stop - interval.start) * 0.5
        return total * self.alpha

    def ordering(self, item):
        return item[0]

    def better(self, i0, i1):
        return i0[0] <= i1[0]

    def evaluate(self, cost, costs):
        return cost * (1 - self.alpha) + sum(costs)

class Exhausted(Exception):
    pass

def k_best(points, ring=Tropical()):
    @functools.cache
    def task(interval, points):
        solv = []
        cand = [(ring.cost(interval, points), 0, (), interval)]
        unco = []
        if int(interval.stop - interval.start) > 1:
            ivs = interval.divide(int(interval.stop - interval.start))
            run = [(0, iv, iv.select(points)) for iv in ivs]
            unco.append((ring.best, run))
        elif len(points) > 1:
            for p, w in ring.costs.items():
                run = [(0, iv, iv.select(points)) for iv in interval.divide(p)]
                unco.append((w, run))
        unco.sort(key=ring.ordering)
        return solv, cand, unco

    def best(k, interval, points):
        solv, cand, unco = task(interval, points)
        while len(cand) + len(unco) > 0 and k >= len(solv):
            while len(unco) > 0:
                if cand and ring.better(cand[0], unco[0]):
                    break
                try:
                    weight, run = unco.pop(0)
                    vector = [best(a,iv,pts) for a, iv, pts in run]
                    cost = ring.evaluate(weight, [v[0] for v in vector])
                    row = cost, weight, run, Grid([v[1] for v in vector])
                    bisect.insort(cand, row, key=ring.ordering)
                except Exhausted:
                    continue
            if len(cand) == 0:
                break
            cost, weight, run, grid = cand.pop(0)
            solv.append((cost, grid))
            for j in range(len(run)):
                new_run = [(a + 1*(j==j1), iv, pts) for j1,(a,iv,pts) in enumerate(run)]
                bisect.insort(unco, (weight, new_run), key=ring.ordering)
        if k < len(solv):
            return solv[k]
        raise Exhausted
    start    = math.floor(points[0])
    end      = math.ceil(points[-1])
    interval = Interval(Fraction(start), Fraction(end))
    points   = tuple(points)
    try:
        k = 0
        while True:
            yield best(k, interval, points)
            k += 1
    except Exhausted:
        pass


