from model import Entity, ControlPoint, Key, Clip, ConstGen, PolyGen, Clap, Desc, DrawFunc, PitchLane, Cell, Document, json_to_brush
import pygame

# boolean, unipolar, number, bipolar, pitch, hz, db, duration
drawfunc_table = {
    "string": [("value", ["boolean", "number", "pitch", "db"])],
    "band": [("value", ["unipolar", "db"])],
    "note": [("pitch", ["pitch"])],
    "rhythm": [],
}

class LaneEditorView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = LaneTool(self)

    def draw(self, screen):
        font = self.editor.font
        SCREEN_WIDTH = screen.get_width()
        SCREEN_HEIGHT = screen.get_height()
        w = (SCREEN_WIDTH - self.editor.MARGIN) / self.editor.BARS_VISIBLE
        self.editor.layout.draw(screen, font, self.editor)

        x = SCREEN_WIDTH/4
        y = SCREEN_HEIGHT/4
        rect = pygame.Rect(x, y, SCREEN_WIDTH/2, SCREEN_HEIGHT/2)
        pygame.draw.rect(screen, (30, 30, 30), rect, False)
        pygame.draw.rect(screen, (0, 255, 0), rect, True)

        py = y
        if self.editor.lane_tag is None:
            text = font.render("select tag with [down] [up]", True, (200, 200, 200))
            screen.blit(text, (x, y))
        else:
            for df in self.editor.doc.drawfuncs:
                if df.tag == self.editor.lane_tag:
                    break
            else:
                df = None
            if df is not None:
                dfn = self.editor.get_dfn(df.tag)
                if dfn is None:
                    text = font.render("cannot fetch dfn for this drawfunc", True, (200, 200, 200))
                    screen.blit(text, (x + 10, y))
                else:
                    for drawfuncs in [["string", "band"], ["note"], ["rhythm"]]:
                        px = x + 10
                        for drawfunc in drawfuncs:
                            active = (drawfunc == df.drawfunc)
                            drawfunc = "[" + drawfunc[0] + "]" + drawfunc[1:]
                            text = font.render(drawfunc, True, [(200, 200, 200), (0, 255, 0)][active])
                            screen.blit(text, (px, py))
                            px += text.get_width() + 10
                        py += 15

                    px = x + 10
                    for i, (name, ty) in enumerate(drawfunc_table[df.drawfunc], 1):
                        tag = df.params[name]
                        ok = (tag in dfn.avail(ty))
                        text = font.render("[" + str(i) + "] " + name + "->" + tag, True, [(255, 128, 128), (200, 200, 200)][ok])
                        screen.blit(text, (px, py))
                        px += text.get_width() + 10

    def handle_keydown(self, ev):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if ev.key == pygame.K_PAGEUP:
            self.editor.timeline_vertical_scroll -= self.editor.SCREEN_HEIGHT / 4
            self.editor.timeline_vertical_scroll = max(0, self.editor.timeline_vertical_scroll)
        elif ev.key == pygame.K_PAGEDOWN:
            self.editor.timeline_vertical_scroll += self.editor.SCREEN_HEIGHT / 4
        elif ev.key == pygame.K_UP:
            if shift_held:
                self.editor.shift_lane_tag(False)
            else:
                self.editor.walk_lane_tag(False)
        elif ev.key == pygame.K_DOWN:
            if shift_held:
                self.editor.shift_lane_tag(True)
            else:
                self.editor.walk_lane_tag(True)
        elif ev.key == pygame.K_u:
            if g := self.get_pitchlane():
                g.margin_above += 1
                self.editor.refresh_layout()
        elif ev.key == pygame.K_i:
            if g := self.get_pitchlane():
                g.margin_above = max(0, g.margin_above - 1)
                self.editor.refresh_layout()
        elif ev.key == pygame.K_o:
            if g := self.get_pitchlane():
                g.margin_below = max(0, g.margin_below - 1)
                self.editor.refresh_layout()
        elif ev.key == pygame.K_p:
            if g := self.get_pitchlane():
                g.margin_below += 1
                self.editor.refresh_layout()
        elif ev.key == pygame.K_DELETE:
            tag = self.editor.lane_tag
            if any(tag == df.tag for df in self.editor.doc.drawfuncs):
                self.editor.walk_lane_tag(direction=True)
                self.editor.erase_drawfunc(tag)
                self.editor.refresh_layout()
        elif ev.key == pygame.K_PLUS:
            for df in self.editor.doc.drawfuncs:
                if df.tag == self.editor.lane_tag:
                    for g in self.editor.doc.graphs:
                        if g.lane == df.lane:
                            g.staves += 1
                            break
                    else:
                        self.editor.doc.graphs.append(PitchLane(df.lane, 1, 0, 0))
                        self.editor.doc.graphs.sort(key=lambda g: g.lane)
            self.editor.refresh_layout()
        elif ev.key == pygame.K_MINUS:
            for df in self.editor.doc.drawfuncs:
                if df.tag == self.editor.lane_tag:
                    for g in list(self.editor.doc.graphs):
                        if g.lane == df.lane and g.staves > 1:
                            g.staves -= 1
                        elif g.lane == df.lane and 1 == sum(1 for f in self.editor.doc.drawfuncs if df.lane == f.lane):
                            self.editor.doc.graphs.remove(g)
            self.editor.refresh_layout()
        else:
            for df in self.editor.doc.drawfuncs:
                if df.tag == self.editor.lane_tag:
                    self.change_drawfunc(df, ev.unicode)

    def change_drawfunc(self, df, text):
        if dfn := self.editor.get_dfn(df.tag):
            if text.isdigit():
                ix = int(text)-1
                dspec = drawfunc_table[df.drawfunc]
                if 0 <= ix < len(dspec):
                    name, ty = dspec[ix]
                    fields = dfn.avail(ty)
                    if df.params[name] in fields:
                        jx = fields.index(df.params[name]) + 1
                        df.params[name] = fields[jx] if jx < len(fields) else fields[0]
                    else:
                        df.params[name] = dfn.autoselect(ty)
            else:
                for drawfunc, dspec in drawfunc_table.items():
                    if text == drawfunc[0]:
                        df.drawfunc = drawfunc
                        df.params = {name:dfn.autoselect(ty) for name, ty in dspec}

    def get_pitchlane(self):
        for df in self.editor.doc.drawfuncs:
            if df.tag == self.editor.lane_tag:
                for g in self.editor.doc.graphs:
                    if g.lane == df.lane and isinstance(g, PitchLane):
                        return g

    def close(self):
        pass

class LaneTool:
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
