from .dtree import DTree
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any
from fractions import Fraction
import functools
import itertools

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

def range_to_segment(start, stop):
    assert start < stop
    if start == stop - 1:
        return SingleSegment(start, True)
    else:
        return MultiSegment(start, stop-1, None, None)

@dataclass(eq=True, frozen=True)
class MultiSegment:
    first : int
    last  : int
    leading  : Optional[float]
    trailing : Optional[float]
    offset   : float = 0.0

    def count(self):
        return self.last - self.first + 1

    def width(self, ioi):
        return sum(ioi[self.first+1:self.last]) + (self.leading or ioi[self.first]) + (self.trailing or ioi[self.last])

    def pieces(self, ioi, notes):
        first = self.first
        last = self.last
        if self.leading is not None:
            yield Piece(self.first, self.leading, (notes[self.first] if self.leading is None else "s"), False)
        for i in range(first+1*(self.leading is not None), last+1*(self.trailing is None)):
            yield Piece(i, ioi[i], notes[i], True)
        if self.trailing is not None:
            yield Piece(self.last, self.trailing, notes[self.last], True)

    def __repr__(self):
        prefix = "" if self.leading is None else "_"
        postfix = "" if self.trailing is None else "_"
        return f"{prefix}{self.first}:{self.last}{postfix}"

    @property
    def cmp(self):
        return self.first

@dataclass(eq=True, frozen=True)
class SingleSegment:
    index : int
    head  : bool
    offset : float = 0.0

    def count(self):
        return 1

    def width(self, ioi):
        return ioi[self.index]

    def pieces(self, ioi, notes):
        yield Piece(self.index, ioi[self.index], (notes[self.index] if self.head else "s"), False)

    def __repr__(self):
        if self.head:
            return f"{self.index}"
        else:
            return f"_{self.index}"

    @property
    def cmp(self):
        return self.index

@dataclass(eq=True, frozen=True)
class Piece:
    index : int
    width  : float
    note  : str
    head  : bool

    def split(self, x):
        a = Piece(self.index, x, self.note, self.head)
        b = Piece(self.index, self.width - x, "s", False)
        return a, b

def pieces_to_segment(pieces, offset):
    assert len(pieces) > 0
    if len(pieces) == 1:
        return SingleSegment(pieces[0].index, pieces[0].head, offset)
    else:
        first = pieces[0]
        last  = pieces[-1]
        leading = None if first.head else first.width
        trailing = last.width
        return MultiSegment(first.index, last.index, leading, trailing, offset)

@dataclass(eq=True, frozen=True)
class Slot:
    ref   : Nonterminal
    width : float

def knush_plass(pieces, slots):
    n_slots = len(slots)

    def calc_penalty(slot_idx, pieces_tuple):
        return slack*slack
        
    @functools.cache
    def dp(slot_idx, pieces_tuple):
        if slot_idx == n_slots - 1:
            width = sum(piece.width for piece in pieces_tuple)
            slack = (slots[slot_idx].width - width)
            return slack*slack, None
        slot_width = slots[slot_idx].width
        best_penalty = float('inf')
        best_break   = None
        total = 0
        for k in range(len(pieces_tuple)):
            piece = pieces_tuple[k]
            prev_total = total
            total += piece.width

            slack = slot_width - total
            next_pen, next_break = dp(slot_idx+1, pieces_tuple[k+1:])
            penalty = slack*slack + next_pen
            if penalty < best_penalty:
                best_penalty = penalty
                best_break = (k+1, None, next_break)

            if total > slot_width:
                needed = slot_width - prev_total
                if prev_total != 0 and needed < slot_width*0.5:
                    break
                if needed <= 0:
                    break
                prefix, suffix = piece.split(needed)
                next_pieces = (suffix,) + pieces_tuple[k+1:]
                next_pen, next_break = dp(slot_idx+1, next_pieces)
                if next_pen < best_penalty:
                    best_penalty = next_pen
                    best_break = (k, needed, next_break)
                break
        return best_penalty, best_break

    rem = tuple(pieces)
    _, brk = dp(0, rem)
    result = []
    slot_idx = 0
    offset = 0
    while brk:
        count, needed, brk = brk
        if needed is None:
            pieces = rem[:count]
            rem    = rem[count:]
        else:
            prefix, suffix = rem[count].split(needed)
            pieces = rem[:count] + (prefix,)
            rem    = (suffix,) + rem[count+1:]
        result.append((slots[slot_idx], pieces, offset))
        offset += sum(piece.width for piece in pieces) - slots[slot_idx].width
        slot_idx += 1
    result.append((slots[slot_idx], rem, offset))
    return result

def equivalent(nt, ioi, notes, alpha=1.0, beta=1.0):
    @functools.cache
    def produce(ref, segment):
        nt = Nonterminal(ref.name, segment)
        for w, dtree in ref.prod:
            for w, dtree in partition(w, dtree, segment):
                nt.prod.append((w * alpha, dtree))
        return nt
    def partition(weight, dtree, segment):
        leaves = dtree.leaves_with_durations(duration=1)
        if all(isinstance(x.label, Nonterminal) for x,_ in leaves):
            if segment.count() == 1:
                return
            width = segment.width(ioi)
            pieces = list(segment.pieces(ioi, notes))
            slots = [Slot(x.label, d*width) for x, d in leaves]
            results = knush_plass(pieces, slots)
            error = 0
            instances = [produce(slot.ref, pieces_to_segment(pcs, offset)) for slot, pcs, offset in results]
            new_leaves = [DTree(leaf.weight, nt, [], leaf.rule_id)
                          for (leaf,_), nt in zip(leaves, instances)]
            yield weight, dtree.instantiate(new_leaves, lambda x: isinstance(x.label, Nonterminal))
        elif len(leaves) == 1:
            width = segment.width(ioi)
            out = []
            error = 0
            offset = segment.offset
            for piece in segment.pieces(ioi, notes):
                if piece.head:
                    error += abs(offset)
                out.append(DTree(0, piece.note, []))
                offset += piece.width
            if out[0].label == leaves[0][0].label:
                out[-1].weight = 1
                out = [t for t in out if t.weight > 0 or t.label not in ("r", "s")]
                if len(out) == 1:
                    out[0].weight = dtree.weight
                    out[0].rule_id = dtree.rule_id
                    yield weight + error, out[0]
                else:
                    error += (len(out) - 1) * beta
                    yield weight + error, DTree(dtree.weight, None, out, dtree.rule_id)
        else:
            raise ValueError(f"The dtree {dtree} invalid for rhythm equivalence algorithm.")
    return produce(nt, range_to_segment(0, len(ioi)))

def dtree(nt, points, notes, alpha=1.0, beta=1.0):
    ioi = []
    pre_rms = []
    for i in range(len(points)-1):
        if points[i] < points[i+1]:
            ioi.append(points[i+1] - points[i])
            pre_rms.append(i)
    notes = [notes[i] for i in pre_rms]
    g = equivalent(nt, ioi, notes, alpha, beta)
    #print("DEBUG")
    #g.debug()
    for _, dtree in k_best(g):
        break
    rms = []
    i = 0
    for x in dtree.leaves():
        if x.label != "s" and x.weight > 0:
            rms.append(pre_rms[i])
            i += 1
    dtree = dtree.remove_grace_notes().reconnect_slurs()
    return dtree, rms
