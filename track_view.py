from gui.components import *
from gui.base import ComputedPan, NoCapture
from gui.event import uievent, invoke_at_event
from gui.compostor import composable, component, Compostor, layout, widget, context, key, Hook
from sarpasana import gutters, edges, pc
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
        self.scene = 0
        self.scroll = ScrollField()

    def refresh(self):
        self.scene += 1

    @composable
    def scene_layout(self, scene):
        layout().style_flex_grow = 1
        margin = edges(left=self.editor.MARGIN)
        with vscrollable(self.scroll, style_flex=1, style_margin = margin):
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
           pan = ComputedPan((lambda: w*self.editor.timeline_scroll), (lambda: 0))
           for lane in lanes:
               with frame():
                   layout().style_flex_direction = "row"
                   end = 0
                   for e in lane:
                       with frame():
                           widget().shifter = pan
                           layout().style_margin = edges(left=(e.shift - end)*w)
                           layout().style_width = max(1, e.brush.duration)*w
                           @widget().attach
                           def _borders_(this, frame):
                               pygame.draw.rect(frame.screen, (200,200,200), frame.rect, 1, 3)
                           self.layout_entity(e, ())
                       end = e.shift + max(1, e.brush.duration)
           layout().style_min_height = 100*pc
           @widget().attach
           def _draw_playback_(this, frame):
               if (t := self.editor.get_playing()) is not None:
                   x = (t - self.editor.timeline_scroll) * w + frame.rect.left
                   pygame.draw.line(frame.screen, (255, 0, 0),
                       (x, frame.rect.top), (x, frame.rect.bottom))
               x0 = (self.editor.timeline_head - self.editor.timeline_scroll) * w + frame.rect.left
               pygame.draw.line(frame.screen, (0, 255, 255),
                   (x0, frame.rect.top), (x0, frame.rect.bottom), 2)
               x1 = (self.editor.timeline_tail - self.editor.timeline_scroll) * w + frame.rect.left
               pygame.draw.rect(frame.screen, (0, 255, 255), (min(x0, x1), frame.rect.top, abs(x0-x1), frame.rect.height), 1)
           def _mousebuttondown_(this, frame):
               if frame.ev.button == 1:
                   i = round((frame.ev.pos[0] - frame.rect.x) / self.editor.BAR_WIDTH)
                   self.editor.timeline_head = self.editor.timeline_scroll + i
                   self.editor.timeline_tail = self.editor.timeline_head
                   frame.press(TimelineSelect(self.editor))
               elif frame.ev.button == 3:
                   frame.press(TimelineScroll(self.editor, frame.ev.pos, self.timeline_menu))
               else:
                   raise NoCapture
           widget().post_mousebuttondown = _mousebuttondown_

    def layout_entity(self, e, clips):
        label(f"{e.shift}: {type(e.brush).__name__} {e.brush.label}")
        def _mousebuttondown_(this, frame):
            if frame.ev.button == 3:
                frame.press(TimelineScroll(self.editor, frame.ev.pos, self.entity_menu, e, clips))
            else:
                raise NoCapture
        widget().post_mousebuttondown = _mousebuttondown_

    def entity_menu(self, e, clips):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            with button(self.erase_brush(e, clips)):
                label("erase")
        return menu

    @uievent
    def erase_brush(self, e, clips):
        if clips:
            clips[-1].brushes.remove(e)
        else:
            self.editor.doc.brushes.remove(e)
        self.editor.doc.rebuild_labels()
        self.editor.refresh_layout()

    def timeline_menu(self):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            with button(self.set_playback_range):
                label("set playback range")
            with button(self.clear_playback_range):
                label("clear playback range")
        return menu

    @uievent
    def set_playback_range(self):
        start = min(self.editor.timeline_head, self.editor.timeline_tail)
        stop  = max(self.editor.timeline_head, self.editor.timeline_tail)
        if start < stop:
            self.editor.playback_range = start, stop
        else:
            self.editor.playback_range = None
        self.editor.leave_popup().invoke()

    @uievent
    def clear_playback_range(self):
        self.editor.playback_range = None
        self.editor.leave_popup().invoke()

    def deploy(self):
        pass

    def close(self):
        pass

class TimelineScroll:
    def __init__(self, editor, pos, menu, *args):
        self.editor = editor
        self.x = pos[0]
        self.timeline_scroll = editor.timeline_scroll
        self.show_menu = True
        self.menu = menu
        self.args = args

    def at_mousemotion(self, this, frame):
        x = frame.ev.pos[0]
        i = round((self.x - x) / self.editor.BAR_WIDTH)
        self.editor.timeline_scroll = max(0, self.timeline_scroll + i)
        if abs(x - self.x) > 10:
            self.show_menu = False

    def at_mousebuttonup(self, this, frame):
        if self.show_menu:
            frame.emit(self.editor.enter_popup(self.menu, *self.args))

class TimelineSelect:
    def __init__(self, editor):
        self.editor = editor

    def at_mousemotion(self, this, frame):
        i = round((frame.ev.pos[0] - frame.rect.x) / self.editor.BAR_WIDTH)
        self.editor.timeline_head = self.editor.timeline_scroll + i
