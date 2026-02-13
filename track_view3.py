from gui.components import *
from gui.base import ComputedPan, NoCapture
from gui.event import uievent, invoke_at_event
from gui.compostor import composable, component, Compostor, layout, widget, context, key, Hook
from sarpasana import gutters, edges, pc
from model import Key, ControlPoint, Clip, Tracker, stringify
from simgui import Text
from rhythm import NotationRhythm
import rhythm
import heapq

# TODO: from here you should be able to enter a tracker
# TODO: copy/reference/make unique within program
# TODO: shift brush right/left
# TODO: add tracker
# TODO: add clip
# TODO: add control point
# TODO: add key
# TODO: increase/decrease duration
# TODO: toggle transition of controlpoint
# TODO: adjust key/control point value

class TrackView:
    def __init__(self, editor):
        self.editor = editor
        self.drag_pos = (0,0)
        self.drag_org = 0
        self.selection = []
        self.rhythm_control = Text("", 0, None)

    def select(self, entity):
        self.selection.append(entity)
        if isinstance(entity.brush, Tracker):
            if isinstance(entity.brush.rhythm, NotationRhythm):
                self.rhythm_control = Text(entity.brush.rhythm.text, 0, None)
            else:
                self.rhythm_control = Text(stringify(entity.brush.rhythm, 0, None))

    def present(self, ui):
        if self.selection:
            if ui.button("back", pygame.Rect(0, 24, 24*4, 24), "back-button"):
                last = self.selection.pop(-1)
            else:
                last = self.selection[-1]
            if isinstance(last.brush, Tracker):
                valid = None
                try:
                    valid = rhythm.from_string(self.rhythm_control.text) 
                except ValueError:
                    problem = rhythm.check_notation(self.rhythm_control.text)
                    if problem is None:
                        valid = NotationRhythm(self.rhythm_control.text)
                    else:
                        ui.label(problem, pygame.Rect(24, 60+24, self.editor.screen_width - 48, 24))
                if ui.textbox(self.rhythm_control, pygame.Rect(24, 60, self.editor.screen_width - 48, 24), "rhythm-ctl"):
                    if valid is not None:
                        last.brush.rhythm = valid
                        self.editor.refresh_layout()
        else:
            ui.widget(Trackline(self,
                pygame.Rect(
                    self.editor.MARGIN, 24,
                    self.editor.screen_width - self.editor.MARGIN,
                    self.editor.screen_height - 48), "screen"))

            w = self.editor.BAR_WIDTH
            heap = []
            lanes = []
            for e in self.editor.doc.brushes:
                duration = max(1, e.brush.duration)
                while heap and heap[0][0] < e.shift:
                    _, row = heapq.heappop(heap)
                    heapq.heappush(heap, (e.shift, row))
                if heap and heap[0][0] <= e.shift:
                    _, row = heapq.heappop(heap)
                    lanes[row].append(e)
                else:
                    row = len(lanes)
                    lanes.append([e])
                heapq.heappush(heap, (e.shift + duration, row))
            for k, row in enumerate(lanes):
                for e in row:
                    rect = pygame.Rect((e.shift * w, 24 + k * 48, e.brush.duration * w, 48))
                    if ui.widget(Lane(self, e, rect, f"lane:{e.brush.label}")):
                        self.select(e)

class Lane:
    def __init__(self, view, e, rect, widget_id):
        self.view = view
        self.e = e
        self.rect = rect
        self.widget_id = widget_id

    def behavior(self, ui):
        ui.grab_active(self)
        return ui.was_clicked(self)

    def draw(self, ui, screen):
        x = -self.view.editor.timeline_scroll * self.view.editor.BAR_WIDTH
        rect = self.rect.move((x + self.view.editor.MARGIN, 0))
        pygame.draw.rect(screen, (200,200,200), rect, 2, 4)

        brush = self.e.brush
        text = f"{brush.label}"
        if isinstance(brush, Key):
            text += f":key {brush.index}"
        elif isinstance(brush, ControlPoint):
            text += f":cp {brush.tag} {brush.value}"
        elif isinstance(brush, Clip):
            text += f":clip" # TODO: render subbrushes inside.
        elif isinstance(brush, Tracker):
            text += f":tracker {brush.rhythm}"
        surf = ui.font16.render(text, True, (200, 200, 200))
        rc = surf.get_rect(top=rect.top + 6, left=rect.left + 6)
        screen.blit(surf, rc)

        

class Trackline:
    def __init__(self, view, rect, widget_id):
        self.view = view
        self.rect = rect
        self.widget_id = widget_id

    def behavior(self, ui):
        view = self.view
        if ui.hot_id is None and self.rect.collidepoint(ui.mouse_pos):
            self.hot_id = self.widget_id
            if ui.r_mouse_just_pressed and ui.r_active_id is None:
                ui.r_active_id = self.widget_id
                view.drag_pos = ui.mouse_pos
                view.drag_org = view.editor.timeline_scroll
        if ui.r_active_id == self.widget_id:
            dx = view.drag_pos[0] - ui.mouse_pos[0]
            ix = int(dx // view.editor.BAR_WIDTH)
            view.editor.timeline_scroll = max(0, ix + view.drag_org)
            return True
        return False

    def draw(self, ui, screen):
        view = self.view
        w = view.editor.BAR_WIDTH
        for i in range(view.editor.BARS_VISIBLE + 1):
            x = i * w + self.rect.left
            if (i + view.editor.timeline_scroll) == view.editor.timeline_head:
                pygame.draw.line(screen, (0, 255, 255),
                                (x, self.rect.top), (x, self.rect.bottom))
            else:
                pygame.draw.line(screen, (200, 200, 200),
                                (x, self.rect.top), (x, self.rect.bottom))

#            layout().style_min_height = 100*pc
#            @widget().attach
#            def _draw_playback_(this, frame):
#                if (t := self.editor.get_playing()) is not None:
#                    x = (t - self.editor.timeline_scroll) * w + frame.rect.left
#                    pygame.draw.line(frame.screen, (255, 0, 0),
#                        (x, frame.rect.top), (x, frame.rect.bottom))
#                x0 = (self.editor.timeline_head - self.editor.timeline_scroll) * w + frame.rect.left
#                pygame.draw.line(frame.screen, (0, 255, 255),
#                    (x0, frame.rect.top), (x0, frame.rect.bottom), 2)
#                x1 = (self.editor.timeline_tail - self.editor.timeline_scroll) * w + frame.rect.left
#                pygame.draw.rect(frame.screen, (0, 255, 255), (min(x0, x1), frame.rect.top, abs(x0-x1), frame.rect.height), 1)
#            def _mousebuttondown_(this, frame):
#                if frame.ev.button == 1:
#                    i = round((frame.ev.pos[0] - frame.rect.x) / self.editor.BAR_WIDTH)
#                    self.editor.timeline_head = self.editor.timeline_scroll + i
#                    self.editor.timeline_tail = self.editor.timeline_head
#                    frame.press(TimelineSelect(self.editor))
#                elif frame.ev.button == 3:
#                    frame.press(TimelineScroll(self.editor, frame.ev.pos, self.timeline_menu))
#                else:
#                    raise NoCapture
#            widget().post_mousebuttondown = _mousebuttondown_
# 
#     def layout_entity(self, e, clips):
#         label(f"{e.shift}: {type(e.brush).__name__} {e.brush.label}")
#         def _mousebuttondown_(this, frame):
#             if frame.ev.button == 3:
#                 frame.press(TimelineScroll(self.editor, frame.ev.pos, self.entity_menu, e, clips))
#             else:
#                 raise NoCapture
#         widget().post_mousebuttondown = _mousebuttondown_
# 
#     def entity_menu(self, e, clips):
#         @context_menu(None, *pygame.mouse.get_pos())
#         def menu():
#             layout().style_padding = edges(10)
#             layout().style_gap = gutters(5)
#             layout().style_min_width = 100
#             with button(self.erase_brush(e, clips)):
#                 label("erase")
#         return menu
# 
#     @uievent
#     def erase_brush(self, e, clips):
#         if clips:
#             clips[-1].brushes.remove(e)
#         else:
#             self.editor.doc.brushes.remove(e)
#         self.editor.doc.rebuild_labels()
#         self.editor.refresh_layout()
# 
#     def timeline_menu(self):
#         @context_menu(None, *pygame.mouse.get_pos())
#         def menu():
#             layout().style_padding = edges(10)
#             layout().style_gap = gutters(5)
#             layout().style_min_width = 100
#             with button(self.set_playback_range):
#                 label("set playback range")
#             with button(self.clear_playback_range):
#                 label("clear playback range")
#         return menu
# 
#     @uievent
#     def set_playback_range(self):
#         start = min(self.editor.timeline_head, self.editor.timeline_tail)
#         stop  = max(self.editor.timeline_head, self.editor.timeline_tail)
#         if start < stop:
#             self.editor.playback_range = start, stop
#         else:
#             self.editor.playback_range = None
#         self.editor.leave_popup().invoke()
# 
#     @uievent
#     def clear_playback_range(self):
#         self.editor.playback_range = None
#         self.editor.leave_popup().invoke()
# 
#     def deploy(self):
#         pass
# 
#     def close(self):
#         pass
# 
# class TimelineScroll:
#     def __init__(self, editor, pos, menu, *args):
#         self.editor = editor
#         self.x = pos[0]
#         self.timeline_scroll = editor.timeline_scroll
#         self.show_menu = True
#         self.menu = menu
#         self.args = args
# 
#     def at_mousemotion(self, this, frame):
#         x = frame.ev.pos[0]
#         i = round((self.x - x) / self.editor.BAR_WIDTH)
#         self.editor.timeline_scroll = max(0, self.timeline_scroll + i)
#         if abs(x - self.x) > 10:
#             self.show_menu = False
# 
#     def at_mousebuttonup(self, this, frame):
#         if self.show_menu:
#             frame.emit(self.editor.enter_popup(self.menu, *self.args))
# 
# class TimelineSelect:
#     def __init__(self, editor):
#         self.editor = editor
# 
#     def at_mousemotion(self, this, frame):
#         i = round((frame.ev.pos[0] - frame.rect.x) / self.editor.BAR_WIDTH)
#         self.editor.timeline_head = self.editor.timeline_scroll + i
