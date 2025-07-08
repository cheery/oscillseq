from fractions import Fraction
import measure
import math
import pygame
import rt

primem = [2, 3, 5, 7, 11, 15, 21, 25, 33, 35, 49, 55, 77, 121]
tuplem = [[], [3], [5], [7], [11], [3, 5], [3, 7], [5, 5], [3, 11],
          [5, 7], [7, 7], [5, 11], [7, 11], [11, 11]]

#def slurp2(n, prefix):
#    if len(prefix) > 3:
#        return []
#    results = []
#    for m, (hold, remain) in slurp(n):
#        if remain == 0:
#            results.append(prefix + [(m, hold)])
#        elif xs := slurp2(remain, prefix + [(m, hold)]):
#            results.extend(xs)
#    return results
#
#def slurp(n):
#    k = Fraction(highest_bit_mask(n.numerator), highest_bit_mask(n.denominator))
#    window = [k/i for i in primem]
#    while any(k < n for k in window):
#        for i in range(len(window)):
#            if window[i] < n:
#                window[i] *= 2
#    while any(k > n for k in window):
#        for i in range(len(window)):
#            if window[i] > n:
#                window[i] /= 2
#    return [(i, d) for i, k in zip(tuplem, window) for d in decompose_with(n, k)]

class DTree:
    @classmethod
    def from_seq(cls, seq):
        return DTree(1, [DTree("rn"[n], []) for n in seq])

    @classmethod
    def from_rt(cls, this):
        if isinstance(this, rt.Tree):
            children = [DTree.from_rt(x) for x in this]
            return DTree(1, None, children)
        if this is rt.s:
            return DTree(1, "s", [])
        return DTree(1, "n", [])

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
                tree.children.append(measure.Tree(tree.label))
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

    def __init__(self, weight, label, children):
        self.weight = weight
        self.label = label
        self.children = children

    @property
    def span(self):
        return sum(x.weight for x in self.children)

    def __repr__(self):
        if len(self.children) == 0:
            return str(self.weight) + ":" + str(self.label)
        return f"{self.weight}({''.join(map(repr, self.children))})"

    def copy(self):
        return DTree(self.weight, self.label, [x.copy() for x in self.children])

    def leaves_with_durations(self, decorator=lambda x: x, duration=Fraction(1)):
        output = []
        def visit(this, duration):
            if len(this.children) == 0:
                output.append((this, duration))
            else:
                duration *= this.weight
                duration /= decorator(this.span)
                for child in this.children:
                    visit(child, duration)
        visit(self, duration)
        return output

def highest_bit(n):
    return n.bit_length() - 1

def highest_bit_mask(n):
    return 1 << n.bit_length() - 1

def get_dots(n):
    if n.numerator == 3:
        return 1
    if n.numerator == 7:
        return 2
    return 0

def get_magnitude(n):
    return Fraction(highest_bit_mask(n.numerator), n.denominator)

def head_is_hollow(n):
    return get_magnitude(n)*2 >= 1

def get_beams(n):
    return max(0, highest_bit(get_magnitude(n).denominator) - 2)

# TODO: remove it from here.
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

class NoteLayout:
    stem = 16
    # Spacing configuration for note heads
    p = 20 # width of 1/128th beat note
    q = 50 # width of 1/1 beat note
    a = math.log(p / q) / math.log(1 / 128)

    def __init__(self, dtree, duration, pos, distance, spacing_mode="linear"):
        self.dtree = dtree
        self.details = {}
        self.distances = []
        self.note_distances = []
        self.values = []
        self.shapes = []
        self.ties   = []
        def layout_notes(ix1, dtree, duration, distance):
            ix0 = ix1
            duration *= dtree.weight
            distance *= dtree.weight
            if len(dtree.children) == 0:
                for k, d in enumerate(decompose(duration)):
                    self.distances.append(distance * (float(d) / float(duration)))
                    self.values.append(d)
                    if dtree.label == "s" or k > 0:
                        self.ties.append(ix1-1)
                        self.shapes.append(self.shapes[-1])
                    elif dtree.label == "r":
                        self.shapes.append('rest')
                    elif dtree.label in "n":
                        self.shapes.append('note')
                    ix1 += 1
                self.note_distances.append(distance)
            else:
                span = dtree.span
                distance /= span
                divider = highest_bit_mask(span)
                for subtree in dtree.children:
                    ix1 = layout_notes(ix1, subtree, duration / divider, distance)
                self.details[dtree] = ix0, ix1-1, duration, divider, span
            return ix1
        layout_notes(0, dtree, Fraction(duration), distance)

        px, py = self.pos = pos

        self.points = []
        if spacing_mode == "linear":
            for distance in self.distances:
                cx = px + distance*0.5
                self.points.append(cx - 2)
                px += distance
        elif spacing_mode == "exp":
            for value in self.values:
                d = self.q * value ** self.a
                cx = px + d*0.5
                self.points.append(cx - 2)
                px += d

    def draw(self, screen, font):
        px, py = self.pos
        beams  = [0] * len(self.points)
        def draw_tuplets(dtree, depth=0):
            deepest = depth
            if len(dtree.children) > 0:
                ix0, ix1, duration, divider, span = self.details[dtree]
                draw_tuplet = True
                if span == divider:
                    draw_tuplet = False
                for subtree in dtree.children:
                    deep = draw_tuplets(subtree, depth+1*draw_tuplet)
                    deepest = max(deep, deepest)
                bm = get_beams(duration / divider)
                for ix in range(ix0+1, ix1+1):
                    beams[ix] = max(beams[ix], bm)
                x0 = self.points[ix0] + 3
                x1 = self.points[ix1] + 3
                if draw_tuplet:
                    text = f"{span}:{divider}"
                    text = font.render(text, True, (200,200,200))
                    px0 = (x0+x1 - text.get_width()) / 2
                    px1 = px0 + text.get_width()
                    screen.blit(text, (px0, py + depth*15))
                    pygame.draw.rect(screen, (200, 200, 200), (x0,  py+5 + depth*15, px0-x0, 2))
                    pygame.draw.rect(screen, (200, 200, 200), (px1, py+5 + depth*15, x1-px1, 2))
                    pygame.draw.rect(screen, (200, 200, 200), (x0,  py+5 + depth*15, 1, 4))
                    pygame.draw.rect(screen, (200, 200, 200), (x1-1,py+5 + depth*15, 1, 4))
            return deepest

        py += 15*draw_tuplets(self.dtree)
        py += self.stem

        for ix in self.ties:
            x0 = self.points[ix]
            x1 = self.points[ix+1]
            pygame.draw.lines(screen, (200, 200, 200), False, [
                (x0, py + 8),
                ((x0+x1)/2, py + 12),
                (x1, py + 8)
            ])

        px = 0
        for cx, shape, value, beam in zip(self.points, self.shapes, self.values, beams):
            hollow = head_is_hollow(value)*1
            if shape == 'rest':
                pygame.draw.rect(screen, (200, 200, 200), (cx-4, py-1, 8, 2), hollow)
            else:
                pygame.draw.circle(screen, (200, 200, 200), (cx, py), 4, hollow)
            if get_magnitude(value) < 1:
                pygame.draw.rect(screen, (200, 200, 200), (cx+2, py-self.stem, 2, self.stem), 0)
            for i in range(get_beams(value)):
                if beam > i:
                    pygame.draw.rect(screen, (200, 200, 200), (px+2, py-self.stem + i*3, cx-px, 2))
                elif beam > 0:
                    pygame.draw.rect(screen, (200, 200, 200), (cx+2-5, py-self.stem + i*3, 5, 2))
                else:
                    pygame.draw.rect(screen, (200, 200, 200), (cx+2, py-self.stem + i*3, 5, 2))
            for i in range(get_dots(value)):
                pygame.draw.circle(screen, (200, 200, 200), (cx+6+i*4, py + 2), 2)
            px = cx
