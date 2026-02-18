from balanced import BalancedTree, rebalance, pluck
from dataclasses import dataclass, field

@dataclass(eq=False)
class Sequence(BalancedTree):
    is_empty = True
    length : int = field(init = False)

    def __iter__(self):
        return iter(())

    def pick(self, pos):
        return IndexError

    def sequence(self, start, stop, sequence=None):
        if start == stop == 0:
            return [] if sequence is None else sequence
        raise IndexError

    def __post_init__(self):
        self.length = 0
        BalancedTree.__post_init__(self)

    def insert(self, pos, tree):
        if tree.length == 0:
            return self
        if pos != 0:
            raise IndexError
        return tree

    def erase(self, start, stop):
        if start != 0 or stop != 0:
            raise IndexError
        return self

@dataclass(eq=False)
class SequenceNode(Sequence):
    is_empty = False
    left : Sequence
    right : Sequence

    def __iter__(self):
        yield from self.sequence(0, self.length)

    def pick(self, pos):
        if pos < self.left.length:
            return self.left.pick(pos)
        elif pos == self.left.length:
            return self
        else:
            return self.right.pick(pos - self.left.length - 1)

    def sequence(self, start, stop, sequence=None):
        sequence = [] if sequence is None else sequence
        ledge = self.left.length
        redge = self.left.length + 1
        if start < ledge:
            sequence = self.left.sequence(start, min(ledge, stop), sequence)
        if ledge < stop:
            sequence.append(self)
            sequence = self.right.sequence(max(start - redge, 0), stop - redge, sequence)
        return sequence

    def __post_init__(self):
        self.length = 1 + self.left.length + self.right.length
        BalancedTree.__post_init__(self)

    def retain(self, left, right):
        raise NotImplemented

    def insert(self, pos, tree):
        if tree.length == 0:
            return self
        ledge = self.left.length
        redge = self.left.length + 1
        if pos <= ledge:
            node = self.retain(self.left.insert(pos, tree), self.right)
        else:
            node = self.retain(self.left, self.right.insert(pos - redge, tree))
        return rebalance(node)

    def erase(self, start, stop):
        ledge = self.left.length
        redge = self.left.length + 1
        if start < ledge:
            left = self.left.erase(start, min(ledge, stop))
        else:
            left = self.left
        if redge < stop:
            right = self.right.erase(max(0, start - redge), stop - redge)
        else:
            right = self.right
        if start <= ledge and redge <= stop:
            node = pluck(left, right)
        else:
            node = self.retain(left, right)
        return rebalance(node)

empty = Sequence()
