from model import Entity, ControlPoint, Key, Clip, ConstGen, PolyGen, Clap, Desc, DrawFunc, PitchLane, Cell, Document, json_to_brush
import collections
import measure
import pygame
import bisect
import music

class BrushEditorView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = NoTool(self)
        self.selection = []
        self.reference = None

    def draw(self, screen):
        font = self.editor.font
        SCREEN_WIDTH = screen.get_width()
        SCREEN_HEIGHT = screen.get_height()
        w = (SCREEN_WIDTH - self.editor.MARGIN) / self.editor.BARS_VISIBLE
        self.editor.layout.draw(screen, font, self.editor)

        #self.screen.set_clip(pygame.Rect(self.MARGIN, 0, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT))
        start = min(self.editor.timeline_head, self.editor.timeline_tail)
        stop  = max(self.editor.timeline_head, self.editor.timeline_tail)
        rect = pygame.Rect((start - self.editor.timeline_scroll)*w + self.editor.MARGIN, 15, (stop-start)*w, SCREEN_HEIGHT - 32 - 15)
        pygame.draw.rect(screen, (128,200,200), rect, 1)
        #self.screen.set_clip(None)

        bx = (self.editor.timeline_head - self.editor.timeline_scroll)*w + self.editor.MARGIN
        pygame.draw.line(screen, (0,255,255), (bx, 0), (bx, SCREEN_HEIGHT), 2)

    def handle_keydown(self, ev):
        if isinstance(self.tool, NoteEditorTool):
            if ev.key == pygame.K_ESCAPE:
                self.tool = NoTool(self)
            return
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if ev.key == pygame.K_RETURN:
            brush = self.get_brush()
            if isinstance(brush, Clap):
                self.tool = NoteEditorTool(self, brush, sum(e.shift for e in self.selection))
        elif ev.key == pygame.K_PAGEUP:
            self.editor.timeline_vertical_scroll -= self.editor.SCREEN_HEIGHT / 4
            self.editor.timeline_vertical_scroll = max(0, self.editor.timeline_vertical_scroll)
        elif ev.key == pygame.K_PAGEDOWN:
            self.editor.timeline_vertical_scroll += self.editor.SCREEN_HEIGHT / 4
        elif ev.key == pygame.K_8:
            start = min(self.editor.timeline_head, self.editor.timeline_tail)
            stop  = max(self.editor.timeline_head, self.editor.timeline_tail)
            if start < stop:
                self.editor.playback_range = start, stop
            else:
                self.editor.playback_range = None
        elif ev.key == pygame.K_9:
            if shift_held:
                self.editor.shift_lane_tag(False)
            else:
                self.editor.walk_lane_tag(False)
        elif ev.key == pygame.K_0:
            if shift_held:
                self.editor.shift_lane_tag(True)
            else:
                self.editor.walk_lane_tag(True)
        elif ev.key == pygame.K_q:
            self.reference = self.selection[-1].brush if self.selection else None
        elif ev.key == pygame.K_w:
            if self.reference:
                self.insert_brush(self.reference.duration, lambda duration: self.reference)
        elif ev.key == pygame.K_e:
            if self.selection:
                brush = self.selection[-1].brush
                brush = self.editor.doc.intro(json_to_brush("", brush.to_json()))
                self.selection[-1].brush = brush
        elif ev.key == pygame.K_o:
            sel = self.selection
            if sel:
                sel[-1].shift = max(0, sel[-1].shift - 1)
            else:
                if all(e.shift > 0 for e in self.editor.doc.brushes):
                    for e in self.editor.doc.brushes:
                        e.shift -= 1
        elif ev.key == pygame.K_p:
            sel = self.selection
            if sel:
                sel[-1].shift = sel[-1].shift + 1
            else:
                for e in self.editor.doc.brushes:
                    e.shift += 1
            a = adjust_boundaries(self.editor.doc)
            self.editor.timeline_head -= a
            self.editor.timeline_tail -= a
            self.editor.timeline_scroll = min(self.editor.timeline_head, self.editor.timeline_scroll)
            self.editor.timeline_scroll = max(self.editor.timeline_head - self.editor.BARS_VISIBLE + 1, self.editor.timeline_scroll)
        elif ev.key == pygame.K_t and shift_held:
            sel = self.selection
            if sel:
                brush = sel[-1].brush
                if isinstance(brush, Clip):
                    adjust_boundaries(brush, self.editor.doc, True)
            else:
                adjust_boundaries(self.editor.doc, self.editor.doc, True)
        elif ev.key == pygame.K_LEFT:
            self.editor.timeline_head = max(0, self.editor.timeline_head - 1)
            if not shift_held:
                self.editor.timeline_tail = self.editor.timeline_head
            self.editor.timeline_scroll = min(self.editor.timeline_head, self.editor.timeline_scroll)
        elif ev.key == pygame.K_RIGHT:
            self.editor.timeline_head += 1
            if not shift_held:
                self.editor.timeline_tail = self.editor.timeline_head
            self.editor.timeline_scroll = max(self.editor.timeline_head - self.editor.BARS_VISIBLE + 1, self.editor.timeline_scroll)
        elif ev.key == pygame.K_UP and shift_held:
            sel = self.selection
            if sel:
                clip = self.get_brush(sel[:-1])
                i = clip.brushes.index(sel[-1])
                if i > 0:
                    clip.brushes[i-1], clip.brushes[i] = clip.brushes[i], clip.brushes[i-1]
        elif ev.key == pygame.K_DOWN and shift_held:
            sel = self.selection
            if sel:
                clip = self.get_brush(sel[:-1])
                i = clip.brushes.index(sel[-1])
                if i+1 < len(clip.brushes):
                    clip.brushes[i+1], clip.brushes[i] = clip.brushes[i], clip.brushes[i+1]
        elif ev.key == pygame.K_UP:
            brushlist = dfs_list(self.editor.doc.brushes)
            sel = self.selection
            if sel:
                ix = brushlist.index(sel) - 1
                self.selection = brushlist[ix] if ix >= 0 else []
            else:
                self.selection = brushlist[-1] if brushlist else []
        elif ev.key == pygame.K_DOWN:
            brushlist = dfs_list(self.editor.doc.brushes)
            sel = self.selection
            if sel:
                ix = brushlist.index(sel) + 1
                self.selection = brushlist[ix] if ix < len(brushlist) else []
            else:
                self.selection = brushlist[0] if brushlist else []
        elif ev.key == pygame.K_a:
            self.insert_brush(1, lambda duration: (Clap("", duration, measure.Tree.from_string("n"), {})))
        elif ev.key == pygame.K_s:
            self.insert_brush(1, lambda duration: (Clip("", duration, [])))
        elif ev.key == pygame.K_c and self.editor.lane_tag is not None:
            #desc = self.doc.descriptors[self.editor.lane_tag]
            #dspec = dict(desc.spec)
            #if "value" in dspec and desc.kind == "control":
            #    ty = dspec["value"]
            #    v = music.Pitch(33) if ty == "pitch" else 0
            # TODO: come up with a good solution to this.
            v = 0
            self.insert_brush(0, lambda duration: (ControlPoint("", tag=self.editor.lane_tag, transition=True, value=v)))
        elif ev.key == pygame.K_k:
            self.insert_brush(1, lambda duration: Key("", -1, 0))
        elif ev.key == pygame.K_DELETE and shift_held:
            self.erase_brush(self.get_brush())
        elif ev.key == pygame.K_DELETE:
            self.erase_selection()
        elif ev.key == pygame.K_PLUS:
            brush = self.get_brush()
            if isinstance(brush, ControlPoint):
                brush.transition = not brush.transition
            elif isinstance(brush, Clap):
                brush.duration += 1
                a = adjust_boundaries(self.editor.doc)
                self.editor.timeline_head -= a
                self.editor.timeline_tail -= a
                self.editor.timeline_scroll = min(self.editor.timeline_head, self.editor.timeline_scroll)
                self.editor.timeline_scroll = max(self.editor.timeline_head - self.editor.BARS_VISIBLE + 1, self.editor.timeline_scroll)
        elif ev.key == pygame.K_MINUS:
            brush = self.get_brush()
            if isinstance(brush, Clap):
                brush.duration = max(1, brush.duration-1)
        elif ev.key == pygame.K_j:
            self.modify_control_point(+1)
        elif ev.key == pygame.K_m:
            self.modify_control_point(-1)
        elif ev.key == pygame.K_h:
            self.modify_control_point(+10)
        elif ev.key == pygame.K_n:
            self.modify_control_point(-10)
        elif ev.key == pygame.K_g:
            self.modify_control_point(+100)
        elif ev.key == pygame.K_b:
            self.modify_control_point(-100)
        elif ev.key == pygame.K_f:
            self.modify_control_point(+1000)
        elif ev.key == pygame.K_v:
            self.modify_control_point(-1000)
        self.editor.refresh_layout()

    def close(self):
        pass

    def insert_brush(self, min_duration, mkbrush):
        shift = min(self.editor.timeline_head, self.editor.timeline_tail)
        duration = max(self.editor.timeline_head, self.editor.timeline_tail) - shift
        duration = max(min_duration, duration)
        bobj = self.editor.doc.intro(mkbrush(duration))
        self.editor.doc.duration = max(self.editor.doc.duration, shift + duration)
        brushlist = dfs_list(self.editor.doc.brushes)
        sel = self.selection
        if sel:
            if isinstance(sel[-1].brush, Clip):
                brushes = sel[-1].brush.brushes
                i_point = len(brushes)
            elif len(sel) > 1:
                brushes = sel[-2].brush.brushes
                i_point = brushes.index(sel[-1])
                sel = sel[:-1]
            else:
                brushes = self.editor.doc.brushes
                i_point = brushes.index(sel[-1])
                sel = []
            for e in sel:
                if bobj == e.brush:
                    return
                shift = shift - e.shift
        else:
            brushes = self.editor.doc.brushes
            i_point = len(brushes)
            sel = []
        obj = Entity(shift, bobj)
        brushes.insert(i_point, obj)
        self.selection = sel + [obj]
        a = adjust_boundaries(self.editor.doc)
        self.editor.timeline_head -= a
        self.editor.timeline_tail -= a
        self.editor.timeline_scroll = min(self.editor.timeline_head, self.editor.timeline_scroll)
        self.editor.timeline_scroll = max(self.editor.timeline_head - self.editor.BARS_VISIBLE + 1, self.editor.timeline_scroll)

    def modify_control_point(self, amount):
        cp = self.get_brush()
        if isinstance(cp, ControlPoint):
            #desc = self.doc.descriptors[cp.tag]
            #ty = dict(desc.spec)["value"]
            # TODO: think of a good solution to this.
            cp.value = modify(cp.value, amount, "number")
        if isinstance(cp, Key):
            cp.index = max(-7, min(+7, modify(cp.index, amount, "number")))

    def get_brush(self, selection=None):
        if selection is None:
            selection = self.selection
        if len(selection) > 0:
            return selection[-1].brush
        else:
            return self.editor.doc

    def erase_brush(self, target):
        def do_erase():
            for brush in [self.editor.doc] + list(self.editor.doc.labels.values()):
                if isinstance(brush, (Clip, Document)):
                    for e in list(brush.brushes):
                        if e.brush == target:
                            brush.brushes.remove(e)
            self.editor.doc.labels.pop(target.label)
        for i, e in enumerate(self.selection):
            if e.brush == target:
                self.selection[i:] = []
                clip = self.get_brush()
                index = clip.brushes.index(e)
                do_erase()
                if index < len(clip.brushes):
                    self.selection.append(clip.brushes[index])
                break
        else:
            do_erase()

    def erase_selection(self):
        brushlist = dfs_list(self.editor.doc.brushes)
        selection = self.selection
        if selection:
            if len(selection) > 1:
                brushes = selection[-2].brush.brushes
            else:
                brushes = self.editor.doc.brushes
            i = min(brushes.index(selection[-1]), len(brushes)-2)
            brushes.remove(selection[-1])
            if i >= 0:
                selection[-1] = brushes[i]
            else:
                selection.pop(-1)
            self.editor.doc.rebuild_labels()
        else:
            self.editor.doc.brushes = []
            self.editor.doc.rebuild_labels()

class NoTool:
    def __init__(self, view):
        self.view = view

    def draw(self, screen):
        pass

    def handle_mousebuttondown(self, ev):
        pass

    def handle_mousebuttonup(self, ev):
        pass

    def handle_mousemotion(self, ev):
        pass

def dfs_list(brushes):
    output = []
    def dfs(brushes, path):
        for e in brushes:
            output.append(path + [e])
            if isinstance(e.brush, Clip):
                dfs(e.brush.brushes, path + [e])
    dfs(brushes, [])
    return output

def adjust_boundaries(selection, doc=None, tighten=False):
    visited = set()
    sequence = []
    def postorder(clip):
        if clip not in visited:
            visited.add(clip)
            for e in clip.brushes:
                if isinstance(e.brush, Clip):
                    postorder(e.brush)
            sequence.append(clip)
    postorder(selection)
    shifts = {}
    for clip in sequence:
        shift = 0
        duration = clip.duration
        if tighten:
            shift = duration - 1
            duration = 1
        for e in clip.brushes:
            e.shift += shifts.get(e.brush, 0)
            shift = min(e.shift, shift)
            duration = max(e.shift + e.brush.duration, duration)
        for e in clip.brushes:
            e.shift -= shift
        if len(clip.brushes) == 0:
            shift = 0
        clip.duration = duration
        shifts[clip] = shift
    postorder(doc or clip)
    shift = shifts[selection]
    for clip in sequence:
        for e in clip.brushes:
            if e.brush == selection:
                e.shift += shift
    return shifts.get(doc or clip, 0)

class NoteEditorTool:
    PATTERNS = [
        "r",
        "n",
        "2nn",
        "3nnn",
        "22nn2nn",
        "5nnnnn",
        "32nn2nn2nn",
        "7nnnnnnn",
        "222nn2nn22nn2nn",
        "33nnn3nnn3nnn",
        "52nn2nn2nn2nn2nn",
        "bnnnnnnnnnnn",
    ]

    def __init__(self, view, clap, location):
        self.view = view
        self.clap = clap
        self.location = location
        self.accidental = None             # note editor accidental
        self.note_tool = 'draw'            # note editor current tool
        self.note_tail = None              # note editor tail selection (when dragging).
        self.pattern = "n"                 # note editor after-split pattern.

    def note_editor(self):
        for df in self.view.editor.doc.drawfuncs:
            if df.tag == self.view.editor.lane_tag and df.drawfunc == "note":
                break
        else:
            return
        for graph in self.view.editor.doc.graphs:
            if graph.lane == df.lane and isinstance(graph, PitchLane):
                break
        else:
            return
        return df, graph

    def draw(self, screen):
        brush = self.clap
        editor = self.view.editor
        layout = editor.layout
        font = self.view.editor.font
        SCREEN_WIDTH = editor.SCREEN_WIDTH
        SCREEN_HEIGHT = editor.SCREEN_HEIGHT
        w = (SCREEN_WIDTH - self.view.editor.MARGIN) / self.view.editor.BARS_VISIBLE

        x = editor.MARGIN
        y = SCREEN_HEIGHT/4
        rect = pygame.Rect(x, y, SCREEN_WIDTH - editor.MARGIN, SCREEN_HEIGHT/2)
        pygame.draw.rect(screen, (30, 30, 30), rect, False)
        pygame.draw.rect(screen, (0, 255, 0), rect, True)

        def draw_tree(x, y, span, tree):
            color = (200, 200, 200)
            if len(tree) == 0:
                text = font.render(tree.label, True, color)
                w = span/2 - text.get_width() / 2
                screen.blit(text, (x + w, y))
            else:
                w = span / len(tree)
                rect = pygame.Rect(x + w/2, y, span - w, 1)
                pygame.draw.rect(screen, color, rect)
                for i, stree in enumerate(tree):
                    rect = pygame.Rect(x + i*w + w/2 - 1, y, 2, 3)
                    pygame.draw.rect(screen, color, rect)
                    draw_tree(x + i*w, y+3, w, stree)
        draw_tree(x, y + 3, min(4, brush.duration)*w, brush.tree)
        y1 = y + SCREEN_HEIGHT / 2
        y += 3*brush.tree.depth + 23

        starts, stops = brush.tree.offsets(min(4, brush.duration), 0)

        setup = self.note_editor()
        if setup is None:
            return
        df, graph = setup

        mx, my = pygame.mouse.get_pos()

        for point in starts + stops:
            if 0 < point < 4:
                pygame.draw.line(screen, (70, 70, 70), (x + point*w, y + 1), (x + point*w, y1 - 2))

        y += graph.margin_above * layout.STAVE_HEIGHT * 2
        yg = y
        for _ in range(graph.staves):
            for p in range(2, 12, 2):
                pygame.draw.line(screen, (70, 70, 70), (x, y + p*(layout.STAVE_HEIGHT*2 / 12)), (SCREEN_WIDTH, y + p*(layout.STAVE_HEIGHT*2 / 12)))
            y += layout.STAVE_HEIGHT * 2
        y += graph.margin_below * layout.STAVE_HEIGHT * 2

        colors = [(0,0,128), (0,0,255), (255,128,0), (255, 0, 0), (128,0,0)]

        location = self.location

        graph_key_map = {graph: [(0, 0)]}
        editor.doc.annotate(graph_key_map, 0)
        graph_key = graph_key_map[graph]
        graph_key.sort(key=lambda x: x[0])
        d_ratio = brush.duration / min(4, brush.duration)
        def get_accidentals(b):
            ix = bisect.bisect_right(graph_key, d_ratio * b + location, key=lambda z: z[0])
            return music.accidentals(graph_key[ix-1][1])

        if df.tag in brush.generators:
            gen = brush.generators[df.tag]
            for i, (s, e) in enumerate(zip(starts, stops)):
                acci = get_accidentals(s)
                for _, args in gen.pull(i, (), False):
                    pitch = args.get(df.params["pitch"], music.Pitch(33))
                    color = colors[pitch.accidental + 2]
                    if pitch.accidental == acci[pitch.position % 7]:
                        color = (255,255,255)
                    yp = yg + (40 - pitch.position) * layout.STAVE_HEIGHT*2 / 12
                    span = (e-s)*w
                    pygame.draw.line(screen, color, (x + s*w + span*0.05, yp), (x + e*w - span*0.05, yp), int(layout.STAVE_HEIGHT/9))

        for i, (s, e) in enumerate(zip(starts, stops)):
            if s*w <= mx - x <= e*w:
                yp = (my - yg) // (layout.STAVE_HEIGHT*2/12) * (layout.STAVE_HEIGHT*2/12) + yg
                span = (e-s)*w
                rect = pygame.Rect(x + s*w + span*0.05, yp - layout.STAVE_HEIGHT * 0.25 / 2, span*0.9, layout.STAVE_HEIGHT * 0.25)
                if self.accidental is None:
                    color = (255,255,255)
                else:
                    color = colors[self.accidental + 2]
                pygame.draw.rect(screen, color, rect, 1)

        band1 = ["bb", "b", "n", "s", "ss"]
        band2 = ["draw", "r", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
        px = 0
        py = SCREEN_HEIGHT - 96
        for i, text in enumerate(band1):
            selected = (self.accidental == i-2)
            rect = pygame.Rect(px, py, 32, 32)
            pygame.draw.rect(screen, (100, 100 + 50 * selected, 100), rect, 0)
            pygame.draw.rect(screen, (200, 200, 200), rect, 1)
            text = font.render(text, True, (200, 200, 200))
            screen.blit(text, (px + 16 - text.get_width()/2, py + 16 - text.get_height()/2))
            px += 32
        px = 0
        py = SCREEN_HEIGHT - 64
        for i, text in enumerate(band2):
            if i == 0:
                selected = (self.note_tool == "draw")
            else:
                selected = (self.note_tool == "split" and self.pattern == self.PATTERNS[i-1])
            rect = pygame.Rect(px, py, 32, 32)
            pygame.draw.rect(screen, (100, 100 + 50 * selected, 100), rect, 0)
            pygame.draw.rect(screen, (200, 200, 200), rect, 1)
            text = font.render(text, True, (200, 200, 200))
            screen.blit(text, (px + 16 - text.get_width()/2, py + 16 - text.get_height()/2))
            px += 32
        px = SCREEN_WIDTH / 2
        py = SCREEN_HEIGHT - 64
        band3 = ["r -> n"]
        for i, text in enumerate(band3):
            selected = False
            rect = pygame.Rect(px, py, 64, 32)
            pygame.draw.rect(screen, (100, 100 + 50 * selected, 100), rect, 0)
            pygame.draw.rect(screen, (200, 200, 200), rect, 1)
            text = font.render(text, True, (200, 200, 200))
            screen.blit(text, (px + 32 - text.get_width()/2, py + 16 - text.get_height()/2))
            px += 64

    def handle_mousebuttondown(self, ev):
        brush = self.clap
        editor = self.view.editor
        layout = editor.layout
        font = self.view.editor.font
        SCREEN_WIDTH = editor.SCREEN_WIDTH
        SCREEN_HEIGHT = editor.SCREEN_HEIGHT
        w = (SCREEN_WIDTH - self.view.editor.MARGIN) / self.view.editor.BARS_VISIBLE
        setup = self.note_editor()
        if setup is None:
            return
        df, graph = setup

        band1 = ["bb", "b", "n", "s", "ss"]
        band2 = ["draw", "r", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
        px = 0
        py = SCREEN_HEIGHT - 96
        for i, text in enumerate(band1):
            rect = pygame.Rect(px, py, 32, 32)
            if rect.collidepoint(ev.pos) and ev.type == pygame.MOUSEBUTTONDOWN:
                acc = i-2
                if self.accidental == acc:
                    self.accidental = None
                else:
                    self.accidental = acc
                return
            px += 32
        px = 0
        py = SCREEN_HEIGHT - 64
        for i, text in enumerate(band2):
            rect = pygame.Rect(px, py, 32, 32)
            if rect.collidepoint(ev.pos) and ev.type == pygame.MOUSEBUTTONDOWN:
                if i == 0:
                    self.note_tool = "draw"
                else:
                    self.note_tool = "split"
                    self.pattern = self.PATTERNS[i-1]
                return
            px += 32
        px = SCREEN_WIDTH / 2
        py = SCREEN_HEIGHT - 64
        band3 = ["r -> n"]
        for i, text in enumerate(band3):
            rect = pygame.Rect(px, py, 64, 32)
            if rect.collidepoint(ev.pos) and ev.type == pygame.MOUSEBUTTONDOWN:
                if i == 0:
                    self.remove_rests()
                return
            px += 64
        # TODO: avoid repeating this code
        x = editor.MARGIN
        y = SCREEN_HEIGHT/4
        y += 3*brush.tree.depth + 23
        yg = y + graph.margin_above * layout.STAVE_HEIGHT * 2
        starts, stops = brush.tree.offsets(min(4, brush.duration), 0)

        location = self.location
        graph_key_map = {graph: [(0, 0)]}
        editor.doc.annotate(graph_key_map, 0)
        graph_key = graph_key_map[graph]
        graph_key.sort(key=lambda x: x[0])
        d_ratio = brush.duration / min(4, brush.duration)
        def get_accidentals(b):
            ix = bisect.bisect_right(graph_key, d_ratio * b + location, key=lambda z: z[0])
            return music.accidentals(graph_key[ix-1][1])

        if self.note_tool == "split":
            mx, my = ev.pos
            self.note_tail = None
            for i, (s, e) in enumerate(zip(starts, stops)):
                if s*w <= mx - x <= e*w:
                    self.note_tail = i

        if self.note_tool == "draw":
            mx, my = ev.pos
            position = 40 - int((my - yg) // (layout.STAVE_HEIGHT*2/12))
            for i, (s, e) in enumerate(zip(starts, stops)):
                if s*w <= mx - x <= e*w:
                    acci = get_accidentals(s)
                    acc = self.accidental or acci[position%7]
                    total = sum(1 for leaf in brush.tree.leaves if leaf.label == "n")
                    gen = brush.generators.get(df.tag, None)
                    if isinstance(gen, ConstGen):
                        a = [ [args.copy() for args in gen.argslist] for _ in range(total)]
                        gen = brush.generators[df.tag] = PolyGen(a)
                    elif gen is None:
                        a = [ [] for _ in range(total)]
                        gen = brush.generators[df.tag] = PolyGen(a)
                    argslist = gen.argslists[i]
                    gen.argslists[i] = []
                    if ev.button == 1:
                        found = False
                        for args in argslist:
                            pitch = args.get(df.params["pitch"], music.Pitch(33))
                            if pitch.position == position:
                                args[df.params["pitch"]] = music.Pitch(position, acc)
                                found = True
                            gen.argslists[i].append(args)
                        if not found:
                            gen.argslists[i].append({df.params["pitch"]: music.Pitch(position, acc)})
                    elif ev.button == 3:
                        for args in argslist:
                            pitch = args.get(df.params["pitch"], music.Pitch(33))
                            if pitch.position != position:
                                gen.argslists[i].append(args)
        self.editor.refresh_layout()

    def handle_mousebuttonup(self, ev):
        brush = self.clap
        editor = self.view.editor
        layout = editor.layout
        font = self.view.editor.font
        SCREEN_WIDTH = editor.SCREEN_WIDTH
        SCREEN_HEIGHT = editor.SCREEN_HEIGHT
        w = (SCREEN_WIDTH - self.view.editor.MARGIN) / self.view.editor.BARS_VISIBLE
        setup = self.note_editor()
        if setup is None:
            return
        df, graph = setup

        # TODO: avoid repeating this code
        x = editor.MARGIN
        y = SCREEN_HEIGHT/4
        y += 3*brush.tree.depth + 23
        yg = y + graph.margin_above * layout.STAVE_HEIGHT * 2
        starts, stops = brush.tree.offsets(min(4, brush.duration), 0)

        location = self.location
        graph_key_map = {graph: [(0, 0)]}
        editor.doc.annotate(graph_key_map, 0)
        graph_key = graph_key_map[graph]
        graph_key.sort(key=lambda x: x[0])
        d_ratio = brush.duration / min(4, brush.duration)
        def get_accidentals(b):
            ix = bisect.bisect_right(graph_key, d_ratio * b + location, key=lambda z: z[0])
            return music.accidentals(graph_key[ix-1][1])

        if self.note_tool == "split" and self.note_tail is not None:
            mx, my = ev.pos
            note_head = self.note_tail
            for i, (s, e) in enumerate(zip(starts, stops)):
                if s*w <= mx - x <= e*w:
                    note_head = i
            first = min(note_head, self.note_tail)
            last  = max(note_head, self.note_tail)
            def segments(tree):
                segs = []
                for leaf in tree.leaves:
                    if leaf.label == "n" or leaf.label == "r":
                        segs.append([leaf])
                    elif leaf.label == "s":
                        segs[-1].append(leaf)
                return [seg for seg in segs if seg[0].label == "n"]
            xs = segments(brush.tree)
            first_leaf = xs[first][0]
            last_leaf = xs[last][-1]
            def left_corner(leaf):
                while True:
                    cousin = leaf.prev_cousin()
                    if cousin is not None and cousin.label == "o":
                        leaf = cousin
                        continue
                    if leaf.parent and leaf.parent.children[0] is leaf:
                        leaf = leaf.parent
                        continue
                    break
                return leaf
            first_leaf = left_corner(first_leaf)
            def right_corner(leaf):
                while leaf.parent and leaf.parent.children[-1] is leaf:
                    leaf = leaf.parent
                return leaf
            last_leaf = right_corner(last_leaf)

            def extrapolate(tree, path, side):
                for ix in path:
                    tree = tree.children[ix]
                    yield tree
                while tree.children:
                    tree = tree.children[side]
                    yield tree

            lca = brush.tree
            ex1 = extrapolate(lca, first_leaf.get_path(), 0)
            ex2 = extrapolate(lca, last_leaf.get_path(), -1)
            for lca0, lca1 in zip(ex1, ex2):
                if lca0 is lca1:
                    lca = lca0
                    if lca.parent is first_leaf:
                        first_leaf = lca
                    if lca.parent is last_leaf:
                        last_leaf = lca
                else:
                    break
            if lca is first_leaf and lca is last_leaf:
                lca.label = "n"
                lca.children = []
                first_leaf = last_leaf = lca
            else:
                if lca is first_leaf:
                    first_leaf = lca.children[0]
                first_leaf.label = "n"
                first_leaf.children = []
                if lca is last_leaf:
                    last_leaf = lca.children[-1]
                last_leaf.label = "s"
                last_leaf.children = []
                branch0 = first_leaf
                while branch0.parent is not lca:
                    parent = branch0.parent
                    for this in parent.children[parent.children.index(branch0)+1:]:
                        this.label = "s"
                        this.children = []
                    branch0 = parent
                branch1 = last_leaf
                while branch1.parent is not lca:
                    parent = branch1.parent
                    for this in parent.children[:parent.children.index(branch1)]:
                        this.label = "s"
                        this.children = []
                    branch1 = parent
                i = lca.children.index(branch0)
                j = lca.children.index(branch1)
                for this in lca.children[i+1:j]:
                    this.label = "s"
                    this.children = []
                assert first_leaf.label == "n"

            leaves = brush.tree.leaves
            ix0 = leaves.index(first_leaf)
            first1 = sum(1 for leaf in leaves[:ix0] if leaf.label == "n")
            ix1 = leaves.index(last_leaf)
            last1 = sum(1 for leaf in leaves[:ix1] if leaf.label == "n")
            d0 = (last + 1 - first)
            d1 = (last1 + 1 - first1)

            if self.pattern != "n":
                block = leaves[ix0:ix1+1]
                def collect(tree):
                    lst = []
                    while tree.parent:
                        tree = tree.parent
                        lst.append(len(tree))
                    return lst
                exponents = [collections.Counter(collect(leaf)) for leaf in block]

                t_exponent = {p: max(counter.get(p, 0) for counter in exponents) for p in measure.primes}
                for counter, leaf in zip(exponents, block):
                    add_counts = {p: t_exponent[p] - counter.get(p, 0) for p in measure.primes}
                    to_add = []
                    for p, count in add_counts.items():
                        to_add.extend([p] * count)
                    def explode(leaf, to_add):
                        if to_add:
                            leaf.label = ""
                            leaf.children = []
                            for _ in range(to_add[0]):
                                subleaf = measure.Tree("o")
                                leaf.children.append(subleaf)
                                subleaf.parent = leaf
                                explode(subleaf, to_add[1:])
                        else:
                            leaf.label = "o"
                    explode(leaf, to_add)
                leaf.last_leaf.label = "n"
                n_tree = measure.Tree.from_string(self.pattern)
                ll = leaf.last_leaf
                ll.label = n_tree.label
                ll.children = n_tree.children
                for child in n_tree.children:
                    child.parent = ll
                d1 = sum(1 for leaf in ll.leaves if leaf.label == "n")

            for name, gen in brush.generators.items():
                if isinstance(gen, PolyGen) and d1 != d0 and d0 == 1:
                    pat = gen.argslists[first]
                    gen.argslists[first:last+1] = [[a.copy() for a in pat] for _ in range(d1)]
                elif isinstance(gen, PolyGen) and d1 != d0:
                    gen.argslists[first:last+1] = [[{}] for _ in range(d1)]

            tree = measure.simplify(brush.tree.copy())
            if tree and tree.is_valid():
                brush.tree = tree
        self.editor.refresh_layout()

    def handle_mousemotion(self, ev):
        pass

    def remove_rests(self):
        brush = self.clap
        ix = 0
        for leaf in brush.tree.leaves:
            if leaf.label == "n":
                ix += 1
            if leaf.label == "r":
                leaf.label = "n"
                for name, gen in brush.generators.items():
                    if isinstance(gen, PolyGen):
                        gen.argslists.insert(ix, [{}])
                ix += 1

