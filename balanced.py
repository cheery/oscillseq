from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Union

@dataclass(eq=False)
class BalancedTree:
    height : int = field(init = False)

    def __post_init__(self):
        if self.is_empty:
            self.height = 0
        else:
            self.height = 1 + max(self.left.height, self.right.height)

    @property
    def balance(self):
        if self.height == 0:
            return 0
        else:
            return self.left.height - self.right.height

def pluck(left : BalancedTree, right : BalancedTree) -> BalancedTree:
    if left.height == 0:
        return right
    elif right.height == 0:
        return left
    else:
        successor = right
        spine = []
        while successor.left.height != 0:
            spine.append(successor)
            successor = successor.left
        newright = successor.right
        for node in reversed(spine):
            newright = rebalance(node.retain(newright, node.right))
        return rebalance(successor.retain(left, newright))

def rebalance(node : BalancedTree) -> BalancedTree:
    balance = node.balance
    if balance > 1:
        if node.left.balance >= 0:
            return right_rotate(node)
        else:
            temp = node.retain(left_rotate(node.left), node.right)
            return right_rotate(temp)
    elif balance < -1:
        if node.right.balance <= 0:
            return left_rotate(node)
        else:
            temp = node.retain(node.left, right_rotate(node.right))
            return left_rotate(temp)
    return node

def right_rotate(z : BalancedTree) -> BalancedTree:
    x = z.left
    y = x.right
    return x.retain(x.left, z.retain(y, z.right))

def left_rotate(x : BalancedTree) -> BalancedTree:
    z = x.right
    y = z.left
    return z.retain(x.retain(x.left, y), z.right)

@dataclass(eq=False)
class Rope(BalancedTree):
    is_empty = True
    length : int = field(init = False)
    newlines : int = field(init = False)

    def __iter__(self):
        return iter(())

    def segments(self, start, stop, sequence=None):
        sequence = [] if sequence is None else sequence
        if start == stop == 0:
            return sequence
        raise IndexError

    def __post_init__(self):
        self.length = 0
        self.newlines = 0
        BalancedTree.__post_init__(self)

    def insert(self, pos, text):
        if text == "":
            return self
        if pos != 0:
            raise IndexError
        return RopeSegment(text, self, self)

    def erase(self, start, stop):
        if start != 0 or stop != 0:
            raise IndexError
        return self

    def row(self, pos):
        if pos != 0:
            raise IndexError
        return 0

    def rowpos(self, row):
        if row != 0:
            raise IndexError
        return 0

blank = Rope()

@dataclass(eq=False)
class RopeSegment(Rope):
    is_empty = False
    text  : str
    left  : Rope
    right : Rope

    def __iter__(self):
        yield from self.segments(0, self.length)

    def segments(self, start, stop, sequence=None):
        sequence = [] if sequence is None else sequence
        ledge = self.left.length
        redge = self.left.length + len(self.text)
        if start < ledge:
            sequence = self.left.segments(start, min(ledge, stop), sequence)
        x = max(start, ledge) - ledge
        y = min(stop, redge) - ledge
        sequence.append(self.text[x:y])
        if redge < stop:
            sequence = self.right.segments(max(start - redge, 0), stop - redge, sequence)
        return sequence

    def __post_init__(self):
        self.length = len(self.text) + self.left.length + self.right.length
        self.newlines = self.text.count('\n') + self.left.newlines + self.right.newlines
        BalancedTree.__post_init__(self)

    def retain(self, left, right):
        return RopeSegment(self.text, left, right)

    def insert(self, pos, text):
        if text == "":
            return self
        ledge = self.left.length
        redge = self.left.length + len(self.text)
        cut = pos - ledge
        if pos < ledge:
            node = self.retain(self.left.insert(pos, text), self.right)
        elif pos > redge:
            node = self.retain(self.left, self.right.insert(pos - redge, text))
        elif len(self.text) + len(text) > 8:
            left = self.left.insert(self.left.length, self.text[:cut])
            right = self.right.insert(0, self.text[cut:])
            node = RopeSegment(text, left, right)
        else:
            text = self.text[:cut] + text + self.text[cut:]
            node = RopeSegment(text, self.left, self.right)
        return rebalance(node)

    def erase(self, start, stop):
        ledge = self.left.length
        redge = self.left.length + len(self.text)
        if start < ledge:
            left = self.left.erase(start, min(ledge, stop))
        else:
            left = self.left
        if redge < stop:
            right = self.right.erase(max(0, start - redge), stop - redge)
        else:
            right = self.right
        if start < redge and ledge < stop:
            start = max(ledge, min(redge, start)) - ledge
            stop  = max(ledge, min(redge, stop)) - ledge
            text = self.text[:start] + self.text[stop:]
            if len(text) > 0:
                node = RopeSegment(text, left, right)
            else:
                node = pluck(left, right)
        else:
            node = self.retain(left, right)
        return rebalance(node)

    def row(self, pos):
        if pos <= self.left.length:
            return self.left.row(pos)
        redge = self.left.length + len(self.text)
        if redge < pos:
            row = self.right.row(pos - redge)
            row += self.newlines - self.right.newlines
            return row
        cut = pos - self.left.length
        row = self.text.count('\n', 0, cut) + self.left.newlines
        return row

    def rowpos(self, row):
        if row <= self.left.newlines:
            return self.left.rowpos(row)
        redge = self.newlines - self.right.newlines
        if row <= redge:
            count = self.left.newlines
            for pos, ch in enumerate(self.text, self.left.length):
                if ch == "\n":
                    count += 1
                    if count == row:
                        return pos + 1
        pos = self.right.rowpos(row - redge)
        return pos + len(self.text) + self.left.length

@dataclass(eq=False)
class Avl(BalancedTree):
    def insert(self, key, *args):
        match self.compare(key):
            case -1:
                node = self.retain(self.left.insert(key, *args), self.right)
            case 1:
                node = self.retain(self.left, self.right.insert(key, *args))
            case 0:
                node = self.refine(*args)
        return rebalance(node)

    def delete(self, key):
        match self.compare(key):
            case -1:
                node = self.retain(self.left.delete(key), self.right)
            case 1:
                node = self.retain(self.left, self.right.delete(key))
            case 0:
                node = pluck(self.left, self.right)
        return rebalance(node)

    def query(self, key):
        match self.compare(key):
            case -1:
                return self.left.query(key)
            case 1:
                return self.right.query(key)
            case 0:
                return self.retrieve()
