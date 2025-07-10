import pygame
import bisect
from rhythm import quantize
import rhythm
from rhythm import DTree
from layout import NoteLayout

class RewriteView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = DummyTool(self)
        self.lines = [500, 800]
        self.alpha = 0.1
        self.beta = 0.1
        self.refresh()

    def refresh(self):
        #self.tree = quantize.quantize_to_tree(self.lines, self.alpha, self.beta)
        #self.tree2 = quantize.quantize_to_tree2(self.lines, self.alpha, self.beta)
        #self.dtree = quantize.quantize_to_dtree(self.lines, self.alpha, self.beta)
        #self.vals = quantize.quantize_to_val(self.lines, 1, self.alpha, self.beta)
        points = self.lines
        self.dtree2 = quantize.dtree(rhythm.grammar, points, ['n']*(len(points)-1))[0]

        notes = NoteLayout(self.dtree2, 1,
            (self.lines[0], 250), self.lines[-1]-self.lines[0], "linear")
        self.lines2 = [self.lines[0]]
        for d in notes.note_distances:
            self.lines2.append(self.lines2[-1] + d)
    
        #import rt
        #grammar = rt.equivalent_rhythms(rt.q1, self.vals)
        #self.rt = None
        #for _, row in rt.k_best(1, grammar):
        #    self.rt = row
        #tree = rhythm.simplify(self.tree)
        self.color = (200,200,200)
        #if tree:
        #    self.tree = tree
        #    self.color = (255,0,255)
        #xx = []
        #for x,d in self.tree.to_events(self.lines[0], self.lines[-1] - self.lines[0]):
        #    xx.append(x)
        #self.lines[:-1] = xx

        #xx = []
        #for x,d in self.tree2.to_events(self.lines[0], self.lines[-1] - self.lines[0]):
        #    xx.append(x)
        #self.lines2 = xx + [self.lines[-1]]

    def draw(self, screen):
        font = self.editor.font
        SCREEN_HEIGHT = screen.get_height()
        for x in self.lines:
            pygame.draw.line(screen, self.color, (x,0), (x,SCREEN_HEIGHT))

        for x in self.lines2:
            pygame.draw.line(screen, (255, 0, 0), (x,0), (x,SCREEN_HEIGHT))

        #for x in self.lines2:
        #    pygame.draw.line(screen, (0, 255, 0), (x,400), (x,SCREEN_HEIGHT))

        #for x,d in self.tree.to_events(self.lines[0], self.lines[-1] - self.lines[0]):
        #    pygame.draw.line(screen, (255, 0, 0), (x,0), (x,SCREEN_HEIGHT))
        

        #dtree = DTree.from_tree(self.tree)
        #notes = NoteLayout(dtree, 1,
        #    (100, 50), 350, "exp")
        #notes.draw(screen, font)

        #dtree = DTree.from_tree(self.tree2)
        #notes = NoteLayout(dtree, 1,
        #    (100, 150), 350, "exp")
        #notes.draw(screen, font)

        #notes = NoteLayout(self.dtree, 1,
        #    (100, 250), 350, "linear")
        #notes.draw(screen, font)

        notes = NoteLayout(self.dtree2, 1,
            (self.lines[0], 250), self.lines[-1]-self.lines[0], "linear")
        notes.draw(screen, font)

        #if self.rt is not None:
        #    notes = NoteLayout(DTree.from_rt(self.rt), 1,
        #        (100, 350), 350, "exp")
        #    notes.draw(screen, font)
        #else:
        #    px = 100
        #    for v in self.vals:
        #        dist = float(v) * 350
        #        text = font.render(f"{v.numerator}/{v.denominator}", True, (200,200,200))
        #        screen.blit(text, (px + (dist-text.get_width())/2, 350))
        #        prim = [p for p in rhythm.primes if v.denominator % p == 0]
        #        text = font.render(f"{prim}", True, (200,200,200))
        #        screen.blit(text, (px + (dist-text.get_width())/2, 400))
        #        px += dist

    def handle_keydown(self, ev):
        pass

    def close(self):
        pass

class DummyTool:
    def __init__(self, view):
        self.view = view

    def draw(self, screen):
        pos = pygame.mouse.get_pos()
        self.view.beta = pos[1] / screen.get_height()
        text = self.view.editor.font.render(f"{self.view.beta}", True, (200,200,200))
        screen.blit(text, pos)

    def handle_mousebuttondown(self, ev):
        lines = self.view.lines
        if ev.button == 1:
            lines.append(ev.pos[0])
            lines.sort()
            self.view.refresh()
        if ev.button == 3 and len(lines) > 2:
            ix = bisect.bisect_right(lines, ev.pos[0]) - 1
            if 0 <= ix < len(lines) - 1:
                del lines[ix]
            else:
                del lines[max(ix,1)-1]
            self.view.refresh()

    def handle_mousebuttonup(self, ev):
        pass

    def handle_mousemotion(self, ev):
        pass

