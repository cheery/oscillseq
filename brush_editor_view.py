from model import Entity, ControlPoint, Key, Clip, ConstGen, PolyGen, Clap, Desc, DrawFunc, PitchLane, Cell, Document, json_to_brush
import measure
import pygame

class BrushEditorView:
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
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if ev.key == pygame.K_PAGEUP:
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

