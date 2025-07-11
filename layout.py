from fractions import Fraction
from rhythm import highest_bit_mask, decompose
import rhythm
import math
import pygame
import itertools

class LinSpacing:
    def __init__(self, width):
        self.width = width

    def __call__(self, x, offsets):
        output = []
        for offset in offsets:
            output.append(offset * self.width + x)
        return output

class ExpSpacing:
    def __init__(self, p = 20, q = 50):
        self.p = p # width of 1/128th beat note
        self.q = q # width of 1/1 beat note
        self.a = math.log(p / q) / math.log(1 / 128)

    def __call__(self, x, offsets):
        output = []
        last_offset = 0
        offsets = list(offsets)
        for offset in offsets:
            delta = self.q * (offset - last_offset) ** self.a
            output.append(x + delta)
            last_offset = offset
            x += delta
        return output

# TODO: consider where this code should reside.
def highest_bit(n):
    return n.bit_length() - 1

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

class NoteLayout:
    stem = 16

    def __init__(self, dtree, duration, spacing):
        self.dtree = dtree
        self.details = {}
        self.distances = []
        self.values = []
        self.shapes = []
        self.ties   = []
        ixs0 = []
        ixs1 = []
        def layout_notes(ix1, dtree, duration, distance):
            ix0 = ix1
            duration *= dtree.weight
            distance *= dtree.weight
            if len(dtree.children) == 0:
                for k, d in enumerate(decompose(duration)):
                    self.distances.append(distance * (float(d) / float(duration)))
                    self.values.append(d)
                    if dtree.label == "s" or k > 0:
                        if self.shapes[-1] == 'note':
                            self.ties.append(ix1-1)
                        self.shapes.append(self.shapes[-1])
                        ixs1[-1] = ix1+1
                    elif dtree.label == "r":
                        self.shapes.append('rest')
                        ixs0.append(ix1)
                        ixs1.append(ix1+1)
                    elif dtree.label == "n":
                        self.shapes.append('note')
                        ixs0.append(ix1)
                        ixs1.append(ix1+1)
                    ix1 += 1
            else:
                span = dtree.span
                distance /= span
                divider = highest_bit_mask(span)
                for subtree in dtree.children:
                    ix1 = layout_notes(ix1, subtree, duration / divider, distance)
                self.details[dtree] = ix0, ix1-1, duration, divider, span
            return ix1
        layout_notes(0, dtree, Fraction(duration), 1.0)

        raw_points = [0] + spacing(0, itertools.accumulate(self.distances))
        self.points = []
        px = 0
        for x in raw_points[1:]:
            self.points.append(px + (x - px)*0.5)
            px = x

        self.display_points = [raw_points[ix] for ix in ixs0] + [raw_points[-1]]
        self.rhythmd = []
        for ix0, ix1 in zip(ixs0, ixs1):
            px0 = raw_points[ix0]
            px1 = raw_points[ix1]
            if self.shapes[ix0] == "note":
                self.rhythmd.append((px0, px1 - px0))

    def draw(self, screen, font, pos):
        py = pos[1]
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
                x0 = self.points[ix0] + 3 + pos[0]
                x1 = self.points[ix1] + 3 + pos[0]
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
            x0 = self.points[ix] + pos[0]
            x1 = self.points[ix+1] + pos[0]
            pygame.draw.lines(screen, (200, 200, 200), False, [
                (x0, py + 8),
                ((x0+x1)/2, py + 12),
                (x1, py + 8)
            ])

        px = 0
        for cx, shape, value, beam in zip(self.points, self.shapes, self.values, beams):
            cx += pos[0]
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
