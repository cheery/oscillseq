import pygame
import bisect
from rhythm import quantize
import rhythm
from rhythm import DTree
from layout import NoteLayout, LinSpacing, ExpSpacing
import numpy as np
import colorsys
from voice_separation import voice_separation



class RewriteView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = DummyTool(self)
        self.onset = [1, 3]
        self.offset = [1.5, 4]
        self.pitch = [69, 70]

        #self.lines = [500, 800]
        #self.alpha = 0.1
        self.beta = 0.1
        self.refresh()

    def refresh(self):
        indices = list(range(len(self.onset)))
        indices.sort(key=lambda x: self.onset[x])
        self.onset = [self.onset[i] for i in indices]
        self.offset = [self.offset[i] for i in indices]
        self.pitch = [self.pitch[i] for i in indices]

        points = self.onset + self.offset
        points.sort()
        for _, grid in rhythm.grid.k_best(points):
            break
        self.grid = grid
        self.points = set(rhythm.grid.snap(grid, points))
        onset = rhythm.grid.snap(grid, self.onset)
        offset = rhythm.grid.snap(grid, self.offset)
        assert len(onset) == len(offset) == len(self.pitch), (onset, offset, self.pitch)

        self.voices = voice_separation(np.array(onset, np.double), np.array(offset, np.double), self.pitch)

        onset = rhythm.grid.snap(grid, self.onset)
        offset = rhythm.grid.snap(grid, self.offset)
        self.dtrees = []
        for voice in self.voices:
            if len(voice) == 0: continue
            chord = 0
            points = []
            notes  = []
            on     = None
            off    = grid.start
            for i, _ in voice:
                if on is None or on < onset[i]:
                    if off < onset[i]:
                        points.append(off)
                        notes.append("r")
                    points.append(onset[i])
                    notes.append("n")
                    on = onset[i]
                off = max(off, offset[i])
            points.append(off)
            if off < grid.stop:
                points.append(grid.stop)
                notes.append("r")
            g = quantize.bars(rhythm.grammar, int(self.grid.stop - self.grid.start))
            dtree = quantize.dtree(g, points, notes)[0]
            self.dtrees.append(dtree)
        
        #self.tree = quantize.quantize_to_tree(self.lines, self.alpha, self.beta)
        #self.tree2 = quantize.quantize_to_tree2(self.lines, self.alpha, self.beta)
        #self.dtree = quantize.quantize_to_dtree(self.lines, self.alpha, self.beta)
        #self.vals = quantize.quantize_to_val(self.lines, 1, self.alpha, self.beta)
        #points = self.lines
        #self.dtree2 = quantize.dtree(rhythm.grammar, points, ['n']*(len(points)-1))[0]

        #self.lines2 = self.dtree2.to_points(self.lines[0], self.lines[-1]-self.lines[0])
    
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
        SCREEN_WIDTH = screen.get_width()
        SCREEN_HEIGHT = screen.get_height()

        w = SCREEN_WIDTH / 4

        for x in self.points:
            pygame.draw.line(screen, (100,100,100), (x*w,0), (x*w,SCREEN_HEIGHT))

        #for x in self.lines2:
        #    pygame.draw.line(screen, (255, 0, 0), (x,0), (x,SCREEN_HEIGHT))

        for k, voice in enumerate(self.voices):
            color = [c * 255 for c in golden_ratio_color_varying(k)]
            for i, chord in voice:
                x0 = self.onset[i]*w
                x1 = self.offset[i]*w
                p  = self.pitch[i]
                y  = (69 - p) * 25 + SCREEN_HEIGHT/2
                pygame.draw.line(screen, color, (x0,y), (x1,y))

        #for x in self.lines2:
        #    pygame.draw.line(screen, (0, 255, 0), (x,400), (x,SCREEN_HEIGHT))

        #for x,d in self.tree.to_events(self.lines[0], self.lines[-1] - self.lines[0]):
        #    pygame.draw.line(screen, (255, 0, 0), (x,0), (x,SCREEN_HEIGHT))
        
        y = 0
        for dtree in self.dtrees:
            color = [c * 255 for c in golden_ratio_color_varying(y)]
            duration = int(self.grid.stop - self.grid.start)
            notel = NoteLayout(dtree, duration, LinSpacing(duration*w))
            notel.draw(screen, font, (self.grid.start*w, 50 + y))
            for x in notel.display_points:
                x += self.grid.start*w
                pygame.draw.line(screen, color, (x,0), (x,SCREEN_HEIGHT))
            y += 50

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

        #notes = NoteLayout(self.dtree2, 1, LinSpacing(self.lines[-1]-self.lines[0]))
        #notes.draw(screen, font, (self.lines[0], 250))

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
        if ev.button == 1:
            p = 69 - round((ev.pos[1] - self.view.editor.SCREEN_HEIGHT/2) / 25)
            self.view.tool = DrawTool(self.view, self, ev.pos[0], p)
        if ev.button == 3:
            self.view.refresh()
        #lines = self.view.lines
        #if ev.button == 1:
        #    lines.append(ev.pos[0])
        #    lines.sort()
        #    self.view.refresh()
        #if ev.button == 3 and len(lines) > 2:
        #    ix = bisect.bisect_right(lines, ev.pos[0]) - 1
        #    if 0 <= ix < len(lines) - 1:
        #        del lines[ix]
        #    else:
        #        del lines[max(ix,1)-1]

    def handle_mousebuttonup(self, ev):
        pass

    def handle_mousemotion(self, ev):
        pass

class DrawTool:
    def __init__(self, view, tool, x, p):
        self.view = view
        self.tool = tool
        self.x = x
        self.p = p

    def draw(self, screen):
        pos = pygame.mouse.get_pos()
        #self.view.beta = pos[1] / screen.get_height()
        #text = self.view.editor.font.render(f"{self.view.beta}", True, (200,200,200))
        #screen.blit(text, pos)
        y  = (69 - self.p) * 25 + self.view.editor.SCREEN_HEIGHT/2
        pygame.draw.line(screen, (255, 255, 255), (self.x,y), (pos[0],y))

    def handle_mousebuttondown(self, ev):
        #lines = self.view.lines
        #if ev.button == 1:
        #    lines.append(ev.pos[0])
        #    lines.sort()
        #    self.view.refresh()
        #if ev.button == 3 and len(lines) > 2:
        #    ix = bisect.bisect_right(lines, ev.pos[0]) - 1
        #    if 0 <= ix < len(lines) - 1:
        #        del lines[ix]
        #    else:
        #        del lines[max(ix,1)-1]
        #    self.view.refresh()
        pass

    def handle_mousebuttonup(self, ev):
        w = self.view.editor.SCREEN_WIDTH / 4
        x0 = min(self.x, ev.pos[0]) / w
        x1 = max(self.x, ev.pos[0]) / w
        for i in range(len(self.view.onset)):
            if self.p == self.view.pitch[i] and max(x0, self.view.onset[i]) <= min(x1, self.view.offset[i]):
                break
        else:
            self.view.onset.append(x0)
            self.view.offset.append(x1)
            self.view.pitch.append(self.p)
        self.view.tool = self.tool
        self.view.refresh()

    def handle_mousemotion(self, ev):
        pass

#                                        1.0            0.5
def golden_ratio_color(index, saturation=0.7, lightness=0.5, alpha=1.0):
    """
    Generate an approximately evenly distributed color based on the index.

    Parameters:
    - index: int, the index of the color to generate.
    - saturation: float, the saturation of the color (0.0 to 1.0, default is 0.7).
    - lightness: float, the lightness of the color (0.0 to 1.0, default is 0.5).
    - alpha: float, the alpha transparency of the color (0.0 to 1.0, default is 1.0).

    Returns:
    - tuple (r, g, b, a): The color in (R, G, B, A) format.
    """
    golden_ratio_conjugate = 0.61803398875
    hue = (index * golden_ratio_conjugate) % 1.0
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return (r, g, b, alpha)

def golden_ratio_color_varying(index, alpha=1.0):
    """
    Generate an approximately evenly distributed color with varying lightness and saturation based on the index.

    Parameters:
    - index: int, the index of the color to generate.
    - alpha: float, the alpha transparency of the color (0.0 to 1.0, default is 1.0).

    Returns:
    - tuple (r, g, b, a): The color in (R, G, B, A) format.
    """
    golden_ratio_conjugate = 0.61803398875
    hue = (index * golden_ratio_conjugate) % 1.0
    
    lightness = 0.55 - 0.2 * ((index % 5) - 2) / 4.0
    saturation = 0.75 - 0.3 * ((index % 3) - 1) / 2.0
    
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return (r, g, b, alpha)

