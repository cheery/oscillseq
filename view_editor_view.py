from components import ContextMenu, Toolbar
from model import Tracker, TrackerView, Staves, Grid, PianoRoll
from descriptors import kinds
import pygame

class ViewEditorView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = DummyTool(self)
        self.current = None
        self.refresh()

    def refresh(self):
        self.toolbar = Toolbar(
            pygame.Rect(0, 15, self.editor.SCREEN_WIDTH, 32),
            [(view.label, view) for view in self.editor.doc.views.values()]
            + [("new", None)],
            self.select_view,
            (lambda label, view: self.current is not None and self.current is view))
        if self.current is None:
            self.layout = []
        else:
            self.layout = layout_lanes(self.editor, self.current.lanes, 47)

    def draw(self, screen):
        font = self.editor.font
        self.toolbar.draw(screen, font)

        if self.current is None:
            text = self.editor.font.render("no view selected", True, (200,200,200))
            screen.blit(text, (32, 64))
        elif len(self.layout) == 0:
            text = self.editor.font.render("add new lane by right click", True, (200,200,200))
            screen.blit(text, (32, 64))
        else:
            for item in self.layout:
                item.draw(screen, font, self.editor)
            pygame.draw.line(screen, (70, 70, 70), item.rect.bottomleft, item.rect.bottomright)

    def handle_keydown(self, ev):
        pass

    def close(self):
        pass

    def select_view(self, ev, view):
        if ev.button == 1 and view is not None:
            self.current = view
            self.refresh()
        elif ev.button == 1:
            self.new_view()
        elif ev.button == 3 and view is not None:
            self.tool = ContextMenu(self.tool, ev.pos, [
                (f'erase {repr(view.label)}', self.erase_view),
            ], view)

    def new_view(self):
        self.current = self.editor.doc.intro(TrackerView("", []))
        self.editor.doc.views[self.current.label] = self.current
        self.refresh()

    def erase_view(self, view):
        if self.current is view:
            self.current = None
        self.editor.doc.views.pop(view.label)
        self.editor.doc.labels.pop(view.label)
        for brush in self.editor.doc.labels.values():
            if isinstance(brush, Tracker) and brush.view is view:
                brush.view = None
        self.refresh()

    def add_lane(self, pos, lane):
        if self.current is None:
            self.new_view()
        i = -1
        for i, elem in enumerate(self.layout):
            if pos[1] <= elem.rect.centery:
                break
        else:
            i += 1
        self.current.lanes.insert(i, lane)
        self.refresh()

    def discard_lane(self, index):
        del self.current.lanes[index]
        self.refresh()

    def editparam_menu(self, pos, elem):
        def add_editparam(label, name):
            def _impl_():
                elem.lane.edit.append((label, name))
                self.refresh()
            return _impl_
        def menu():
            choices = []
            descriptors = self.editor.definitions.descriptors(self.editor.doc.cells)
            for label, desc in descriptors.items():
                for name in desc.avail(elem.ty):
                    if (label,name) not in elem.lane.edit:
                        choices.append((editparam_text(label, name, self.editor), add_editparam(label, name)))
            self.tool = ContextMenu(self.tool, pygame.mouse.get_pos(), choices)
        return menu

    def kind_edit(self, elem):
        def set_to(kind):
            def _impl_():
                descriptors = self.editor.definitions.descriptors(self.editor.doc.cells)
                elem.lane.kind = kind
                for label, name in elem.lane.edit[:]:
                    if name not in descriptors[label].avail([kind]):
                        elem.lane.edit.remove((label, name))
                self.refresh()
            return _impl_
        def menu():
            choices = [(kind, set_to(kind)) for kind in kinds]
            self.tool = ContextMenu(self.tool, pygame.mouse.get_pos(), choices)
        return menu

class DummyTool:
    def __init__(self, view):
        self.view = view

    def draw(self, screen):
        pos = pygame.mouse.get_pos()
        text = self.view.editor.font.render("DUMMY", True, (200,200,200))
        screen.blit(text, pos)

    def handle_mousebuttondown(self, ev):
        if self.view.toolbar.handle_mousebuttondown(ev):
            pass
        elif ev.button == 3:
            options = []
            for i, elem in enumerate(self.view.layout):
                if elem.rect.collidepoint(ev.pos):
                    options.append((f'add editparam', self.view.editparam_menu(ev.pos, elem)))
                    if isinstance(elem.lane, Grid):
                        options.append((f'kind={elem.lane.kind}', self.view.kind_edit(elem)))
                    options.append((f'discard lane', (lambda i: lambda: self.view.discard_lane(i))(i)))
            self.view.tool = ContextMenu(self.view.tool, ev.pos, options + [
                (f'new staves', lambda: self.view.add_lane(ev.pos, Staves(1, 1, 1, []))),
                (f'new piano roll', lambda: self.view.add_lane(ev.pos, PianoRoll(top=69 + 12, bot=69 - 12, edit=[]))),
                (f'new grid', lambda: self.view.add_lane(ev.pos, Grid("number", []))),
            ])
        pass

    def handle_mousebuttonup(self, ev):
        pass

    def handle_mousemotion(self, ev):
        pass

def layout_lanes(editor, lanes, y):
    layout = []
    for lane in lanes:
        if isinstance(lane, Staves):
            height = lane.count + lane.above + lane.below
            height *= editor.layout.STAVE_HEIGHT * 2
            rect = pygame.Rect(0, y, editor.SCREEN_WIDTH, height)
            layout.append(StavesLayout(rect, lane))
        if isinstance(lane, PianoRoll):
            height = lane.top - lane.bot + 1
            height *= editor.layout.STAVE_HEIGHT * 2 / 12
            rect = pygame.Rect(0, y, editor.SCREEN_WIDTH, height)
            layout.append(PianoRollLayout(rect, lane))
        if isinstance(lane, Grid):
            height = max(1, len(lane.edit))
            height *= editor.layout.STAVE_HEIGHT * 6 / 12
            rect = pygame.Rect(0, y, editor.SCREEN_WIDTH, height)
            layout.append(GridLayout(rect, lane))
        y += height
    return layout

class StavesLayout:
    def __init__(self, rect, staves):
        self.rect = rect
        self.lane = staves
        self.staves = staves
        self.ty = ["pitch", "hz"]

    def draw(self, screen, font, editor):
        pygame.draw.line(screen, (70, 70, 70), self.rect.topleft, self.rect.topright)
        x, y = self.rect.topleft
        x += editor.MARGIN
        w = self.rect.width - editor.MARGIN
        k = self.rect.height / (self.staves.count + self.staves.above + self.staves.below)
        y += self.staves.above * k
        for _ in range(self.staves.count):
            for p in range(2, 12, 2):
                pygame.draw.line(screen, (70, 70, 70), (x, y+p*k/12), (x+w, y+p*k/12))
        x, y = self.rect.topleft
        draw_editparams(screen, font, x, y, self.lane.edit, editor)

class PianoRollLayout:
    def __init__(self, rect, pianoroll):
        self.rect = rect
        self.lane = pianoroll
        self.pianoroll = pianoroll
        self.ty = ["pitch", "hz"]

    def draw(self, screen, font, editor):
        pygame.draw.line(screen, (70, 70, 70), self.rect.topleft, self.rect.topright)
        x, y = self.rect.bottomleft
        x += editor.MARGIN
        w = self.rect.width - editor.MARGIN
        k = self.rect.height / (self.pianoroll.top - self.pianoroll.bot + 1)
        for note in range(self.pianoroll.bot, self.pianoroll.top + 1):
            py = y - k*(note - self.pianoroll.bot)
            rect = pygame.Rect(x, py-k, w, k)
            if note == 69:
                pygame.draw.rect(screen, (100*1.5, 50*1.5, 50*1.5), rect)
            elif note % 12 == 9:
                pygame.draw.rect(screen, (100, 50, 50), rect)
            elif note % 12 in [0, 2, 4, 5, 7, 9, 11]:
                pygame.draw.rect(screen, (50, 50, 50), rect)
            elif note == self.pianoroll.bot:
                pygame.draw.line(screen, (70, 70, 70), (x, py), (self.rect.right, py))
            else:
                pygame.draw.line(screen, (50, 50, 50), (x, py), (self.rect.right, py))
        x, y = self.rect.topleft
        draw_editparams(screen, font, x, y, self.lane.edit, editor)

class GridLayout:
    def __init__(self, rect, grid):
        self.rect = rect
        self.lane = grid
        self.grid = grid
        self.ty = [grid.kind]

    def draw(self, screen, font, editor):
        pygame.draw.line(screen, (70, 70, 70), self.rect.topleft, self.rect.topright)
        x, y = self.rect.topleft
        draw_editparams(screen, font, x, y, self.lane.edit, editor)

def draw_editparams(screen, font, x, y, edit, editor):
    for label, name in edit:
        text = font.render(editparam_text(label, name, editor), True, (200,200,200))
        screen.blit(text, (x + 10, y + 2))
        y += 15

def editparam_text(label, name, editor):
    text = f"{label}:{name}"
    if text not in ["tempo:~", "tempo:*"]:
        text = f"{label}:{editor.doc.labels[label].synth}:{name}"
    return text
