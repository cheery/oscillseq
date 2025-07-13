from fractions import Fraction
from .tree import Tree
import math

__all__ = [
    'DTree',
    'highest_bit_mask',
    'decompose',
]

class DTree:
    @classmethod
    def from_seq(cls, seq):
        return DTree(1, [DTree("rn"[n], []) for n in seq])

    @classmethod
    def from_tree(cls, this):
        this = this.copy()
        assert this.is_valid(), str(this)
        if len(this) > 0:
            this.label = 1
        for tree in this.subtrees:
            if len(tree) > 0:
                tree.label = 1
        for tree in this.subtrees:
            if tree.is_chain():
                continue
            cousin = tree.prev_cousin()
            if cousin is not None and len(tree) == 0:
                tree.children.append(Tree(tree.label))
                tree.children[0].parent = tree
                tree.label = 1
            while cousin is not None and cousin.is_chain():
                cousin.label = 1
                tree.prune_cousin()
                cousin = tree.prev_cousin()
        def convert(tree, weight=1):
            if all(isinstance(x.label, int) for x in tree):
                divisor = math.gcd(*(x.label for x in tree))
                for x in tree:
                    x.label //= divisor
            if len(tree.children) == 1:
                return convert(tree.children[0], weight*tree.label)
            if isinstance(tree.label, str):
                return DTree(weight, tree.label, [])
            return DTree(weight*tree.label, None, list(map(convert, tree.children)))
        return convert(this, 1)

    def __init__(self, weight, label, children, rule_id=None):
        self.weight = weight
        self.label = label
        self.children = children
        self.rule_id = rule_id

    @property
    def span(self):
        return sum(x.weight for x in self.children)

    def copy(self):
        return DTree(self.weight, self.label, [x.copy() for x in self.children], self.rule_id)

    def leaves(self):
        output = []
        def visit(this):
            if len(this.children) == 0:
                output.append(this)
            else:
                for child in this.children:
                    visit(child)
        visit(self)
        return output

    def leaves_with_durations(self, decorator=lambda x: x, duration=Fraction(1)):
        output = []
        def visit(this, duration):
            duration *= this.weight
            if len(this.children) == 0:
                output.append((this, duration))
            else:
                duration /= decorator(this.span)
                for child in this.children:
                    visit(child, duration)
        visit(self, duration)
        return output

    def rewrite(self, rewriter):
        if (that := rewriter(self)) is not None:
            return that
        return DTree(self.weight, self.label, [that.rewrite(rewriter) for that in self.children], self.rule_id)

    def instantiate(self, instances, cond):
        i = -1
        def visit(this):
            nonlocal i
            if cond(this):
                i += 1
                return instances[i]
            return DTree(this.weight, this.label, [visit(that) for that in this.children], this.rule_id)
        return visit(self)

    def is_grace_note(self):
        return self.weight == 0

    def remove_grace_notes(self):
        children = [that.remove_grace_notes() for that in self.children if not that.is_grace_note()]
        if len(children) == 1:
            children[0].weight = self.weight
            children[0].rule_id = self.rule_id
            return children[0]
        else:
            return DTree(self.weight, self.label, children, self.rule_id)

    def reconnect_slurs(self, deep=False):
        children = [child.reconnect_slurs(True) for child in self.children]
        if self.weight == 1 or deep:
            i = 1
            while i < len(children):
                if children[i-1].label in ("n", "s") and children[i].label == "s":
                    children[i-1].weight += children[i].weight
                    del children[i]
                else:
                    i += 1
        return DTree(self.weight, self.label, children, self.rule_id)

    def show(self, debug=True):
        base = ''
        if self.rule_id and debug:
            base += str(self.rule_id) + ":"
        if self.weight != 1:
            base += str(self.weight)
        if self.label:
            base += str(self.label)
        if self.children:
            children_str = ' '.join(child.show(debug) for child in self.children)
            return f"{base}({children_str})"
        return base or '1'

    def __repr__(self):
        return self.show(False)

    def __str__(self):
        return self.show(False)

    def to_events(self, offset, duration):
        events = []
        last = None
        for dtree, dur in self.leaves_with_durations(duration=duration):
            if dtree.label == "n":
                events.append((offset, dur))
            if dtree.label == "s" and last == "n":
                events[-1] = events[-1][0], events[-1][1] + dur
            else:
                last = dtree.label
            offset += dur
        return events

    def to_notes(self):
        val = []
        for dtree, dur in self.leaves_with_durations():
            if dtree.label == "s":
                continue
            val.append(dtree.label)
        return val

    def to_val(self, duration=1):
        val = []
        for dtree, dur in self.leaves_with_durations(duration=duration):
            if dtree.label == "s":
                val[-1] += dur
            else:
                val.append(dur)
        return val

    def to_points(self, offset=0, duration=1):
        output = [offset]
        for dur in self.to_val(duration):
            offset += dur
            output.append(offset)
        return output

def highest_bit_mask(n):
    return 1 << n.bit_length() - 1

def decompose(n):
    if n.denominator != highest_bit_mask(n.denominator):
        return None
    prefix = []
    while n > 0:
        p = Fraction(highest_bit_mask(n.numerator), n.denominator)
        for p, n in decompose_with(n, p):
            prefix.append(p)
            break
    return prefix

def decompose_with(n, p):
    p32 = p*3/2
    p74 = p*7*4
    for q in [p74,p32,p]:
        if n >= q:
            yield q, n - q
