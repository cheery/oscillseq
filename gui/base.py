from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
import pygame
import sarpasana
import itertools

@dataclass(eq=False)
class ScrollField:
    offset : float = 0.0
    ratio  : float = 1.0

@dataclass(eq=False, frozen=True)
class UIEvent:
    name : str

    def __repr__(self):
        return f"UIEvent:{self.name}"

    def __call__(self, *args):
        return UIEventTuple(self, args)

    def match(self, this):
        return self is this

@dataclass(eq=True, frozen=True)
class UIEventTuple:
    event : UIEvent
    args  : Tuple[Any]
    def __call__(self, *args):
        return UIEventTuple(self.event, self.args + args)

    def match(self, this):
        return self.event is this

class UIState:
    def __init__(self, root):
        self.focus   = (root.site,)
        self.pressed = (root.site,)
        self.pointer = (0, 0)
        self.events  = []
        self.mouse_tool    = None
        self.keyboard_tool = None

def tuplize(site_vector):
    if site_vector is None:
        return ()
    else:
        return tuplize(site_vector[1]) + (site_vector[0],)

class UIFrame:
    def emit(self, event):
        self.ui.events.append(event)

    def same(self, site_tuple):
        return tuplize(self.site_vector) == site_tuple

    def focus(self, keyboard_tool = None):
        self.ui.focus = tuplize(self.site_vector)
        self.ui.keyboard_tool = keyboard_tool

    def press(self, mouse_tool = None):
        self.ui.pressed = tuplize(self.site_vector)
        self.ui.mouse_tool = mouse_tool

    @property
    def inside(self):
        return self.rect.collidepoint(self.ui.pointer)

@dataclass(eq=False, frozen=True)
class EventFrame(UIFrame):
    ui : UIState
    ev : Optional[pygame.event.Event]
    pointer : Tuple[float, float]
    rect   : pygame.Rect
    site_vector : Tuple[Any] = None
    def move(self, rect, shifter, site):
        pointer = self.pointer[0] - rect.left, self.pointer[1] - rect.top
        rect = rect.move(self.rect.topleft)
        if shifter:
            sx = shifter.calc_x(self.rect.width)
            sy = shifter.calc_y(self.rect.height)
            pointer = pointer[0] + sx, pointer[1] + sy
            rect = rect.move((-sx, -sy))
        site_vector = (site, self.site_vector)
        return EventFrame(self.ui, self.ev, pointer, rect, site_vector)

@dataclass(eq=False, frozen=True)
class DrawFrame(UIFrame):
    ui     : UIState
    screen : pygame.surface.Surface
    rect   : pygame.Rect
    site_vector : Tuple[Any] = None
    def move(self, rect, shifter, site):
        rect = rect.move(self.rect.topleft)
        site_vector = (site, self.site_vector)
        if shifter:
            sx = shifter.calc_x(self.rect.width)
            sy = shifter.calc_y(self.rect.height)
            rect = rect.move((-sx, -sy))
        return DrawFrame(self.ui, self.screen, rect, site_vector)

class NoCapture(Exception):
    pass

def no_capture(this, frame):
    raise NoCapture

def no_action(this, frame):
    pass

class Widget(sarpasana.Node):
    def __init__(self, site):
        super().__init__()
        self.site = site
        self.drawables = defaultdict(list)
        self.pre_mousebuttondown  = no_capture
        self.post_mousebuttondown = no_capture
        self.at_mousemotion       = no_action
        self.at_mousebuttonup     = no_action
        self.focusable            = 0
        self.at_focus             = no_action
        self.at_keydown           = no_action
        self.at_keyup             = no_action
        self.at_textinput         = no_action
        self.shifter              = None
        self.mouse_hit_rect       = True
        self.tag                  = None

    def debug_str(self, indent):
        header = " "*indent + f"{type(self).__name__} {self.left, self.top, self.width, self.height} {self.site}"
        return "\n".join([header] + [x.debug_str(indent+2) if x is not None else " "*indent + "  None" for x in self])

    @property
    def rect(self):
        return pygame.Rect(self.left, self.top, self.width, self.height)

    def attach(self, drawable):
        self.drawables[len(self)].append(drawable)

    def draw(self, frame):
        frame = frame.move(self.rect, self.shifter, self.site)
        for i, widget in enumerate(self):
            for drawable in self.drawables[i]:
                drawable(self, frame)
            widget.draw(frame)
        for drawable in self.drawables[len(self)]:
            drawable(self, frame)

    def mousebuttondown(self, frame):
        frame = frame.move(self.rect, self.shifter, self.site)
        if self.mouse_hit_rect and not frame.inside:
            return False
        try:
            self.pre_mousebuttondown(self, frame)
            return True
        except NoCapture:
            for child in reversed(self):
                if child.mousebuttondown(frame):
                    return True
        try:
            self.post_mousebuttondown(self, frame)
            return True
        except NoCapture:
            return False

    def fetch(self, site_tuple, frame):
        is_root = (frame.site_vector == None)
        if self.site == site_tuple[0]:
            site_tuple = site_tuple[1:]
            frame = frame.move(self.rect, self.shifter, self.site)
            if site_tuple == ():
                return self, frame
            for child in self:
                if res := child.fetch(site_tuple, frame):
                    return res
            if is_root:
                return self, frame

    def focusables(self, frame):
        frame = frame.move(self.rect, self.shifter, self.site)
        if self.focusable:
            yield self, frame
        for child in self:
            yield from child.focusables(frame)

    def subscan(self, frame, matcher):
        for child in self:
            yield from child.scan(frame, matcher)

    def scan(self, frame, matcher):
        frame = frame.move(self.rect, self.shifter, self.site)
        if matcher(self, frame):
            yield self, frame
        for child in self:
            yield from child.scan(frame, matcher)

    def nudge(self, site_tuple):
        if self.site == site_tuple[0]:
            site_tuple = site_tuple[1:]
            if site_tuple == ():
                return self.rect
            for child in self:
                if rect := child.nudge(site_tuple):
                    break
            else:
                return None
            x0, y0 = self.left, self.top
            if self.shifter:
                self.shifter.nudge(rect)
                x, y = self.shifter.estimate()
                return rect.move(x0 - x, y0 - y) # TODO: check that this is correct.
            return rect.move(x0, y0)

@dataclass(eq=False)
class ComputedPan:
    xf : Callable[[], float]
    yf : Callable[[], float]
    def calc_x(self, _):
        return self.xf()
    def calc_y(self, _):
        return self.yf()

    def nudge(self, rect):
        pass

    def estimate(self):
        return self.xf(), self.yf()

@dataclass(eq=False)
class Panner:
    x : float
    y : float
    def calc_x(self, _):
        return self.x
    def calc_y(self, _):
        return self.y

    def nudge(self, rect):
        pass

    def estimate(self):
        return self.x, self.y

@dataclass
class AnchorToCenter:
    position : Tuple[float, float]
    element : Widget
    def calc_x(self, _):
        return self.element.width * 0.5 - self.position[0]
    def calc_y(self, _):
        return self.element.height * 0.5 - self.position[1]
    def nudge(self, rect):
        pass

    def estimate(self):
        x = self.element.width * 0.5 - self.position[0]
        y = self.element.height * 0.5 - self.position[1]
        return x, y

@dataclass
class Mover:
    mv_x : float
    mv_y : float
    p_x : float
    p_y : float
    element : Widget
    def calc_x(self, width):
        m = width * (1 - self.p_x) / 2
        return - max(m, min(width - m - self.element.width, self.mv_x))

    def calc_y(self, height):
        m = height * (1 - self.p_y) / 2
        return - max(m, min(height - m - self.element.height, self.mv_y))

    def nudge(self, rect):
        pass

    def estimate(self):
        return 0, 0

@dataclass
class Scroller:
    pc_x : ScrollField
    pc_y : ScrollField
    inner_container : Widget

    def calc_x(self, width):
        t = 0.0
        if self.pc_x:
            t = self.pc_x.offset
            self.pc_x.ratio = min(1, width / self.inner_container.width if self.inner_container.width != 0 else 1.0)
        return t * max(0, self.inner_container.width - width)
 
    def calc_y(self, height):
        t = 0.0
        if self.pc_y:
            t = self.pc_y.offset
            self.pc_y.ratio = min(1, height / self.inner_container.height if self.inner_container.height != 0 else 1.0)
        return t * max(0, self.inner_container.height - height)

    def nudge(self, rect):
        x, y = self.estimate()
        width = self.inner_container.width * (self.pc_x.ratio if self.pc_x else 1)
        height = self.inner_container.height * (self.pc_y.ratio if self.pc_y else 1)
        view_rect = pygame.Rect(x, y, width, height)

        if view_rect.width < rect.width:
            dx = rect.left - view_rect.left # TODO: test this.
        elif view_rect.right < rect.right + 20:
            dx = 20 + rect.right - view_rect.right
        elif rect.left < view_rect.left + 20:
            dx = rect.left - view_rect.left - 20
        else:
            dx = 0.0
        denom_x = max(0, self.inner_container.width - width)
        if denom_x > 0:
            self.pc_x.offset = max(0, min(1, self.pc_x.offset + dx/denom_x))

        if view_rect.height < rect.height:
            dy = rect.top - view_rect.top # TODO: test this.
        if view_rect.bottom < rect.bottom + 20:
            dy = 20 + rect.bottom - view_rect.bottom
        elif rect.top < view_rect.top + 20:
            dy = rect.top - view_rect.top - 20
        else:
            dy = 0.0
        denom_y = max(0, self.inner_container.height - height)
        if denom_y > 0:
            self.pc_y.offset = max(0, min(1, self.pc_y.offset + dy/denom_y))

    def estimate(self):
        x = y = 0
        if self.pc_x:
            x = self.pc_x.offset * max(0, self.inner_container.width * (1 - self.pc_x.ratio))
        if self.pc_y:
            y = self.pc_y.offset * max(0, self.inner_container.height * (1 - self.pc_y.ratio))
        return x, y

def move_focus(ui, root, rect, reverse=False):
    frame = EventFrame(ui, None, ui.pointer, rect)
    if root.fetch(ui.focus, frame)[0] is root:
        ui.focus = (root.site,)
    it = root.focusables(frame)
    if reverse:
        it = reversed(list(it))
    top = (root.site,)
    if ui.focus == top:
        if wf := next(it, None):
            wf[1].focus(wf[0].at_focus(*wf))
    else:
        it = itertools.dropwhile(lambda x: not x[1].same(ui.focus), it)
        next(it, None)
        if wf := next(it, None):
            wf[1].focus(wf[0].at_focus(*wf))
        else:
            wf = root, EventFrame(ui, None, ui.pointer, rect).move(root.rect, root.shifter, root.site)
            wf[1].focus(wf[0].at_focus(*wf))
    root.nudge(ui.focus)

def draw_widget(ui, root, screen, rect):
    root.draw(DrawFrame(ui, screen, rect))

# TODO: calls to root.fetch are a bugfest waiting to happen.
def process_event(ui, root, ev, rect):
    ui.events.clear()
    if ev.type == pygame.KEYDOWN:
        frame = EventFrame(ui, ev, ui.pointer, rect)
        widget, frame = root.fetch(ui.focus, frame)
        if widget.focusable & 1 or widget is root:
            widget.at_keydown(widget, frame)
    elif ev.type == pygame.KEYUP:
        frame = EventFrame(ui, ev, ui.pointer, rect)
        widget, frame = root.fetch(ui.focus, frame)
        if widget.focusable & 1 or widget is root:
            widget.at_keyup(widget, frame)
    elif ev.type == pygame.TEXTINPUT:
        frame = EventFrame(ui, ev, ui.pointer, rect)
        widget, frame = root.fetch(ui.focus, frame)
        if widget.focusable & 2 or widget is root:
            widget.at_textinput(widget, frame)
    elif ev.type == pygame.MOUSEBUTTONDOWN:
        ui.pointer = ev.pos
        frame = EventFrame(ui, ev, ui.pointer, rect)
        root.mousebuttondown(frame)
    elif ev.type == pygame.MOUSEBUTTONUP:
        ui.pointer = ev.pos
        frame = EventFrame(ui, ev, ui.pointer, rect)
        widget, frame = root.fetch(ui.pressed, frame)
        if hasattr(ui.mouse_tool, "at_mousebuttonup"):
            ui.mouse_tool.at_mousebuttonup(widget, frame)
        widget.at_mousebuttonup(widget, frame)
        ui.pressed    = (root.site,)
        ui.mouse_tool = None
    elif ev.type == pygame.MOUSEMOTION:
        ui.pointer = ev.pos
        frame = EventFrame(ui, ev, ui.pointer, rect)
        widget, frame = root.fetch(ui.pressed, frame)
        if hasattr(ui.mouse_tool, "at_mousemotion"):
            ui.mouse_tool.at_mousemotion(widget, frame)
        widget.at_mousemotion(widget, frame)
    return ui.events[:]
