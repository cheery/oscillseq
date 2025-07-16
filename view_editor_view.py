from components import ContextMenu, Toolbar
from model import Tracker, TrackerView, Staves, Grid, PianoRoll
from descriptors import kinds
import music
import pygame

class ViewEditorView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = ViewEditorTool(self)
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
            self.layout = layout_lanes(self.editor, self.current.lanes, 47, [])

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
                x, y = item.rect.topleft
                draw_editparams(screen, font, x, y, item.lane.edit, self.editor)
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

    def discard_editparam(self, elem, label, name):
        def _impl_():
            elem.lane.edit.remove((label, name))
        return _impl_

    def editparam_menu(self, pos, elem):
        def add_editparam(label, name):
            def _impl_():
                k = (pos[1] - elem.rect.y - 7) // 15
                elem.lane.edit.insert(k, (label, name))
                self.refresh()
            return _impl_
        def is_multi(label):
            if cell := self.editor.doc.labels.get(label, None):
                return cell.multi
            return False
        def menu():
            choices = []
            descriptors = self.editor.definitions.descriptors(self.editor.doc.cells)
            for label, desc in descriptors.items():
                for name in desc.avail(elem.ty):
                    if (label,name) not in elem.lane.edit:
                        choices.append((editparam_text(label, name, self.editor), add_editparam(label, name)))
                if "trigger" in elem.ty and is_multi(label):
                    choices.append((editparam_text(label, "+", self.editor), add_editparam(label, "+")))
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

    def edit_top(self, elem):
        def set_to(top):
            def _impl_():
                elem.lane.top = top
                elem.lane.bot = min(elem.lane.bot, top)
                self.refresh()
            return _impl_
        def menu():
            pitches = []
            pitches.extend(range(0,127,12))
            pitches.extend(range(9,127,12))
            pitches.sort()
            choices = [(str(music.Pitch.from_midi(m)), set_to(m)) for m in reversed(pitches)]
            self.tool = ContextMenu(self.tool, pygame.mouse.get_pos(), choices)
        return menu

    def edit_bot(self, elem):
        def set_to(bot):
            def _impl_():
                elem.lane.bot = bot
                elem.lane.top = max(elem.lane.top, bot)
                self.refresh()
            return _impl_
        def menu():
            pitches = []
            pitches.extend(range(0,127,12))
            pitches.extend(range(9,127,12))
            pitches.sort()
            choices = [(str(music.Pitch.from_midi(m)), set_to(m)) for m in reversed(pitches)]
            self.tool = ContextMenu(self.tool, pygame.mouse.get_pos(), choices)
        return menu

    def edit_above(self, elem):
        def set_to(value):
            def _impl_():
                elem.lane.above = value
                self.refresh()
            return _impl_
        def menu():
            choices = [(str(m), set_to(m)) for m in range(0, 3)]
            self.tool = ContextMenu(self.tool, pygame.mouse.get_pos(), choices)
        return menu

    def edit_below(self, elem):
        def set_to(value):
            def _impl_():
                elem.lane.below = value
                self.refresh()
            return _impl_
        def menu():
            choices = [(str(m), set_to(m)) for m in range(0, 3)]
            self.tool = ContextMenu(self.tool, pygame.mouse.get_pos(), choices)
        return menu

    def edit_count(self, elem):
        def set_to(value):
            def _impl_():
                elem.lane.count = value
                self.refresh()
            return _impl_
        def menu():
            choices = [(str(m), set_to(m)) for m in range(1, 5)]
            self.tool = ContextMenu(self.tool, pygame.mouse.get_pos(), choices)
        return menu

class ViewEditorTool:
    def __init__(self, view):
        self.view = view

    def draw(self, screen):
        pass

    def handle_mousebuttondown(self, ev):
        if self.view.toolbar.handle_mousebuttondown(ev):
            pass
        elif ev.button == 3:
            options = []
            for i, elem in enumerate(self.view.layout):
                if elem.rect.collidepoint(ev.pos):
                    for k, (label, name) in enumerate(elem.lane.edit):
                        if 0 <= ev.pos[1] - elem.rect.y - k*15 < 15:
                            options.append((f'discard {editparam_text(label, name, self.view.editor)}', self.view.discard_editparam(elem, label, name)))
                    options.append((f'add editparam', self.view.editparam_menu(ev.pos, elem)))
                    if isinstance(elem.lane, Grid):
                        options.append((f'kind={elem.lane.kind}', self.view.kind_edit(elem)))
                    if isinstance(elem.lane, Staves):
                        options.append((f'count={elem.lane.count}', self.view.edit_count(elem)))
                        options.append((f'above={elem.lane.above}', self.view.edit_above(elem)))
                        options.append((f'below={elem.lane.below}', self.view.edit_below(elem)))
                    if isinstance(elem.lane, PianoRoll):
                        options.append((f'top={music.Pitch.from_midi(elem.lane.top)}', self.view.edit_top(elem)))
                        options.append((f'bot={music.Pitch.from_midi(elem.lane.bot)}', self.view.edit_bot(elem)))
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

def layout_lanes(editor, lanes, y, generators):
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
            height += sum(1 for tag,param in lane.edit for gen in generators if gen.tag == tag)
            height *= 15
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
            y += k

    def query_pitch(self, editor, pointer, rhythmd, get_accidentals, accidental, editparam, w):
        k = self.rect.height / (self.staves.count + self.staves.above + self.staves.below)
        x = self.rect.left + editor.MARGIN
        y = self.rect.top + self.staves.above*k
        for i, (b, span) in enumerate(rhythmd):
            if 0 <= pointer[0] - x - b <= span:
                y1 = (pointer[1] - y) // (k/12) * (k/12) + y
                if self.rect.top < y1 < self.rect.bottom:
                    position = 40 - int((pointer[1] - y) // (k/12))
                    acci = get_accidentals(i)
                    acc = accidental if accidental is not None else acci[position%7]
                    return music.Pitch(position, acc)

    def draw_tracks(self, screen, font, editor, rhythmd, generators, get_accidentals, pointer, w, accidental):
        k = self.rect.height / (self.staves.count + self.staves.above + self.staves.below)
        x = self.rect.left + editor.MARGIN
        y = self.rect.top + self.staves.above*k
        colors = [(0,0,128), (0,0,255), (255,128,0), (255, 0, 0), (128,0,0)]
        for tag,param in self.lane.edit:
            for gen in generators:
                if gen.tag != tag:
                    continue
                for i, (b, span) in enumerate(rhythmd):
                    acci = get_accidentals(i)
                    args = gen.track[i % len(gen.track)]
                    if args is None:
                        continue
                    pitch = args.get(param, music.Pitch(33))
                    if not isinstance(pitch, music.Pitch):
                        pitch = music.Pitch.from_midi(pitch)
                    color = colors[pitch.accidental + 2]
                    if pitch.accidental == acci[pitch.position % 7]:
                        color = (255,255,255)
                    y1 = y + (40 - pitch.position) * k / 12
                    pygame.draw.line(screen, color, (x + b + span*0.05, y1), (x + b + span*0.95, y1), int(k/9))

        for i, (b, span) in enumerate(rhythmd):
            if 0 <= pointer[0] - x - b <= span:
                y1 = (pointer[1] - y) // (k/12) * (k/12) + y
                if self.rect.top < y1 < self.rect.bottom:
                    rect = pygame.Rect(x + b + span*0.05, y1 - k / 24, span*0.9, k / 12)
                    if accidental is None:
                        color = (255,255,255)
                    else:
                        color = colors[accidental + 2]
                    pygame.draw.rect(screen, color, rect, 1)

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

    def query_pitch(self, editor, pointer, rhythmd, get_accidentals, accidental, editparam, w):
        if editparam not in self.lane.edit:
            return
        k = self.rect.height / (self.pianoroll.top - self.pianoroll.bot + 1)
        x = self.rect.left + editor.MARGIN
        y = self.rect.bottom
        for i, (b, span) in enumerate(rhythmd):
            if 0 <= pointer[0] - x - b <= span:
                y1 = (pointer[1] - y) // k * k + y
                if self.rect.top <= y1 < self.rect.bottom:
                    return self.pianoroll.bot - int((pointer[1] - y) // k) - 1

    def draw_tracks(self, screen, font, editor, rhythmd, generators, get_accidentals, pointer, w, accidental):
        k = self.rect.height / (self.pianoroll.top - self.pianoroll.bot + 1)
        x = self.rect.left + editor.MARGIN
        y = self.rect.bottom
        for tag,param in self.lane.edit:
            for gen in generators:
                if gen.tag != tag:
                    continue
                for i, (b, span) in enumerate(rhythmd):
                    args = gen.track[i % len(gen.track)]
                    if args is None:
                        continue
                    pitch = int(args.get(param, music.Pitch(33)))
                    color = (255,255,255)
                    if self.pianoroll.bot <= pitch <= self.pianoroll.top:
                        y1 = y - (pitch - self.pianoroll.bot + 1)*k
                        pygame.draw.rect(screen, color, (x + b + span*0.05, y1 + k * 0.05, span*0.90, k * 0.9))

        for i, (b, span) in enumerate(rhythmd):
            if 0 <= pointer[0] - x - b <= span:
                y1 = (pointer[1] - y) // k * k + y
                if self.rect.top <= y1 < self.rect.bottom:
                    rect = pygame.Rect(x + b + span*0.05, y1, span*0.9, k)
                    if accidental is None:
                        color = (255,255,255)
                    else:
                        color = colors[accidental + 2]
                    pygame.draw.rect(screen, color, rect, 1)

class GridLayout:
    def __init__(self, rect, grid):
        self.rect = rect
        self.lane = grid
        self.grid = grid
        self.ty = [grid.kind]

    def draw(self, screen, font, editor):
        pygame.draw.line(screen, (70, 70, 70), self.rect.topleft, self.rect.topright)

    def query_pitch(self, editor, pointer, rhythmd, get_accidentals, accidental, editparam, w):
        return None

    def draw_tracks(self, screen, font, editor, rhythmd, generators, get_accidentals, pointer, w, accidental):
        y = self.rect.top
        x = self.rect.left + editor.MARGIN
        for tag,param in self.lane.edit:
            for gen in generators:
                if gen.tag != tag:
                    continue
                text = font.render(editparam_text(tag, param, editor), True, (200,200,200))
                screen.blit(text, (x - text.get_width() - 10, y + 2))
                for i, (b, span) in enumerate(rhythmd):
                    args = gen.track[i % len(gen.track)]
                    if param == "+":
                        text = "x" if args is not None else "o"
                    elif args is None:
                        text = " "
                    else:
                        text = str(args.get(param, "_"))
                    text = font.render(text, True, (200,200,200))
                    screen.blit(text, (x + b, y + 2))
                    if 0 <= pointer[0] - x - b <= span and y <= pointer[1] <= y + 15:
                        rect = pygame.Rect(x + b + span*0.05, y, span*0.9, 15)
                        pygame.draw.rect(screen, (200,200,200), rect, 1)
                y += 15
            text = font.render(editparam_text(tag, param, editor), True, (200,200,200))
            screen.blit(text, (x - text.get_width() - 10, y + 2))
            for i, (b, span) in enumerate(rhythmd):
                if 0 <= pointer[0] - x - b <= span and y <= pointer[1] <= y + 15:
                    rect = pygame.Rect(x + b + span*0.05, y, span*0.9, 15)
                    pygame.draw.rect(screen, (200,200,200), rect, 1)
            y += 15

def draw_editparams(screen, font, x, y, edit, editor, selected=None):
    for label, name in edit:
        text = font.render(editparam_text(label, name, editor), True, (200,200,200))
        screen.blit(text, (x + 10, y + 2))
        if (label,name) == selected:
            rect = pygame.Rect(editor.MARGIN - 10, y+2, 5, 11)
            pygame.draw.rect(screen, (100,255,100), rect)
        y += 15

def editparam_text(label, name, editor):
    text = f"{label}:{name}"
    if text not in ["tempo:~", "tempo:*"] and label in editor.doc.labels:
        text = f"{label}:{editor.doc.labels[label].synth}:{name}"
    return text
