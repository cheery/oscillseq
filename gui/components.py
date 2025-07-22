from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from .base import ScrollField, UIEvent, UIState, move_focus, draw_widget, process_event, Widget, Scroller, Mover, NoCapture
from .compostor import composable, component, Composition, Compostor, layout, widget, context, key
from sarpasana import edges, pc
import sarpasana
import pygame
import functools

@dataclass(eq=False)
class UIContextBase:
    screen_width : float
    screen_height : float
    font : pygame.font.Font
    tab  : UIEvent
    enter_popup : UIEvent
    leave_popup : UIEvent

def toplevel(popups):
    tab = context().tab
    for popup in popups:
        popup()
    def _key_down_(this, frame):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if frame.ev.key == pygame.K_TAB:
            frame.emit(tab(shift_held))
    widget().at_keydown = _key_down_

@component
def frame(widget):
    pass

@component
def label(widget, text):
    font = context().font
    @widget.attach
    def _draw_(this, frame):
        surface = font.render(text, True, (200,200,200))
        frame.screen.blit(surface, frame.rect.topleft)
    width, height = font.size(text)
    widget.style_width = width
    widget.style_height = height

@dataclass(eq=True)
class TextField:
    text : str
    head : int
    tail : int
    edit : UIEvent

@component
def textbox(widget, field):
    font = context().font
    tab = context().tab
    width, height = font.size(field.text)
    @widget.attach
    def _draw_(this, frame):
        pygame.draw.rect(frame.screen, (200,200,200), frame.rect, 1)
        rect = frame.rect.inflate((-20,-20))
        caret = font.size(field.text[:field.head])[0] + rect.left
        tail  = font.size(field.text[:field.tail])[0] + rect.left
        x0 = min(caret, tail)
        x1 = max(caret, tail)

        if x0 < x1:
            pygame.draw.rect(frame.screen, (0,100,255), (x0, rect.top, x1-x0, rect.height))
        text = font.render(field.text, True, (200, 200, 200))
        frame.screen.blit(text, rect.topleft)
        if frame.same(frame.ui.focus):
            pygame.draw.line(frame.screen, (200,200,200), (caret, rect.top), (caret, rect.bottom), 2)

    widget.style_padding = edges(10.0)
    def _measure_(this, avail_width, wm, avail_height, hm):
        return (width, height)
    widget.measure_func = _measure_
    widget.node_type = "text"

    def _mousebuttondown_(this, frame):
        x = frame.pointer[0] - 10
        meas = lambda i: font.size(field.text[:i])[0]
        i = min((abs(x - meas(i)), i) for i in range(len(field.text)+1))[1]
        frame.emit(field.edit(TextField(field.text, i, i, field.edit)))
        frame.focus(None)
        frame.press(DragOnText(font, field.text, i, field.edit))
    widget.post_mousebuttondown = _mousebuttondown_

    widget.focusable = 3
    def _key_down_(this, frame):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if frame.ev.key == pygame.K_TAB:
            frame.emit(tab(shift_held))
    widget.at_keydown = _key_down_

    def _textinput_(this, frame):
        i = min(field.head, field.tail)
        j = max(field.head, field.tail)
        prefix = field.text[:i] + frame.ev.text
        suffix = field.text[j:]
        head = len(prefix)
        frame.emit(field.edit(TextField(prefix + suffix, head, head, field.edit)))
        
    widget.at_textinput = _textinput_

@dataclass
class DragOnText:
    font : pygame.font.Font
    text : str
    tail : int
    edit : Any

    def at_mousemotion(self, this, frame):
        x = frame.pointer[0] - 10
        meas = lambda i: self.font.size(self.text[:i])[0]
        i = min((abs(x - meas(i)), i) for i in range(len(self.text)+1))[1]
        frame.emit(self.edit(TextField(self.text, i, self.tail, self.edit)))

@component
def button(widget, left=None, middle=None, right=None, decor=True, keyboard=True):
    if decor:
        @widget.attach
        def _draw_(this, frame):
            if frame.same(frame.ui.pressed):
                pygame.draw.rect(frame.screen, (50, 150, 50), frame.rect, 1)
            elif frame.same(frame.ui.focus):
                pygame.draw.rect(frame.screen, (50, 50, 150), frame.rect, 2)
            else:
                pygame.draw.rect(frame.screen, (150, 50, 50), frame.rect, 1)
        widget.style_padding = edges(5.0)
    def _down_(this, frame):
        if frame.ev.button == 1 and left is not None:
            frame.press(ButtonClick(left))
            if keyboard:
                frame.focus()
        elif frame.ev.button == 2 and middle is not None:
            frame.press(ButtonClick(middle))
        elif frame.ev.button == 3 and right is not None:
            frame.press(ButtonClick(right))
        else:
            raise NoCapture
    widget.pre_mousebuttondown = _down_

    if keyboard:
        tab = context().tab
        widget.focusable = 1
        def _key_down_(this, frame):
            mods = pygame.key.get_mods()
            shift_held = mods & pygame.KMOD_SHIFT
            if frame.ev.key == pygame.K_SPACE and left is not None:
                frame.emit(left)
            elif frame.ev.key == pygame.K_TAB:
                frame.emit(tab(shift_held))
        widget.at_keydown = _key_down_

@dataclass(eq=False)
class ButtonClick:
    evt : Any
    def at_mousebuttonup(self, this, frame):
        if frame.inside:
            frame.emit(self.evt)

def hscrollbar(site, x, both=False):
    sb = Widget(site)
    @sb.attach
    def _draw_(this, frame):
        pygame.draw.rect(frame.screen, (200, 200, 200), frame.rect, 0)
        pygame.draw.rect(frame.screen, (0, 0, 0), frame.rect, 1)
        outer = frame.rect.inflate((-4, -4))
        rect = pygame.Rect(outer)
        rect.width = max(15, x.ratio*rect.width)
        rect.x = outer.x + x.offset*(outer.width - rect.width)
        pygame.draw.rect(frame.screen, (0, 0, 0), rect, 0)
    sb.style_position_type = "absolute"
    sb.style_position = edges(left=0, right=15*both, bottom=0)
    sb.style_height = 15
    def _mousebuttondown_(this, frame):
        frame.press(HorizontalScroll(x))
    sb.post_mousebuttondown = _mousebuttondown_
    return sb

@dataclass
class HorizontalScroll:
    x : ScrollField
    def at_mousemotion(self, this, frame):
        bar_width = frame.rect.inflate((-4, -4)).width * self.x.ratio
        hnd_width = max(15, bar_width * self.x.ratio)
        if bar_width - hnd_width > 0:
            rel_x = 0.5 * frame.ev.rel[0] / (bar_width - hnd_width)
            self.x.offset = max(0, min(1, self.x.offset + rel_x))

def vscrollbar(site, y, both=False):
    sb = Widget(site)
    @sb.attach
    def _draw_(this, frame):
        pygame.draw.rect(frame.screen, (200, 200, 200), frame.rect, 0)
        pygame.draw.rect(frame.screen, (0, 0, 0), frame.rect, 1)
        outer = frame.rect.inflate((-4, -4))
        rect = pygame.Rect(outer)
        rect.height = max(15, y.ratio*rect.height)
        rect.y = outer.y + y.offset*(outer.height - rect.height)
        pygame.draw.rect(frame.screen, (0, 0, 0), rect, 0)
    sb.style_position_type = "absolute"
    sb.style_position = edges(top=0, right=0, bottom=15*both)
    sb.style_width = 15
    def _mousebuttondown_(this, frame):
        frame.press(VerticalScroll(y))
    sb.post_mousebuttondown = _mousebuttondown_
    return sb

@dataclass
class VerticalScroll:
    y : ScrollField
    def at_mousemotion(self, this, frame):
        bar_height = frame.rect.inflate((-4, -4)).height * self.y.ratio
        hnd_height = max(15, bar_height * self.y.ratio)
        if bar_height - hnd_height > 0:
            rel_y = 0.5 * frame.ev.rel[1] / (bar_height - hnd_height)
            self.y.offset = max(0, min(1, self.y.offset + rel_y))

@component
def scrollable(view, x, y, flex_direction="column", **attributes):
    inner_container = Widget("inner_container")
    inner_container.style_flex_direction = flex_direction
    inner_container.style_overflow = "visible"
    outer_container = Widget("outer_container")
    outer_container.style_flex_direction = {"column":"row", "row":"column"}[flex_direction]
    outer_container.mouse_hit_rect = False
    outer_container.shifter = Scroller(x, y, inner_container)
    outer_container.style_padding = edges(right=15, bottom=15)
    @view.attach
    def _clip_contents_(this, frame):
        frame.screen.set_clip(frame.rect)
    view.append(outer_container)
    outer_container.append(inner_container)
    @view.attach
    def _clip_contents_(this, frame):
        frame.screen.set_clip(None)
    for name, value in attributes.items():
        setattr(view, name, value)
    view.append(hscrollbar("hscroll", x, both=True))
    view.append(vscrollbar("vscroll", y, both=True))
    def _mousebuttondown_(this, frame):
        pc = 150 / inner_container.height if inner_container.height > 0 else 0
        if frame.ev.button == 4:
            y.offset = max(0, min(1, y.offset - pc))
        elif frame.ev.button == 5:
            y.offset = max(0, min(1, y.offset + pc))
        else:
            raise NoCapture
    view.post_mousebuttondown = _mousebuttondown_
    return inner_container

@component
def hscrollable(view, x, **attributes):
    inner_container = Widget("inner_container")
    inner_container.style_overflow = "visible"
    outer_container = Widget("outer_container")
    outer_container.style_overflow = "scroll"
    outer_container.style_flex_direction = "row"
    outer_container.mouse_hit_rect = False
    outer_container.shifter = Scroller(x, None, inner_container)
    outer_container.style_padding = edges(bottom=15)
    @view.attach
    def _clip_contents_(this, frame):
        frame.screen.set_clip(frame.rect)
    view.append(outer_container)
    outer_container.append(inner_container)
    @view.attach
    def _clip_contents_(this, frame):
        frame.screen.set_clip(None)
    for name, value in attributes.items():
        setattr(view, name, value)
    view.append(hscrollbar("hscroll", x))
    def _mousebuttondown_(this, frame):
        pc = 150 / inner_container.width if inner_container.width > 0 else 0
        if frame.ev.button == 4:
            x.offset = max(0, min(1, x.offset - pc))
        elif frame.ev.button == 5:
            x.offset = max(0, min(1, x.offset + pc))
        else:
            raise NoCapture
    view.post_mousebuttondown = _mousebuttondown_
    return inner_container

@component
def vscrollable(view, y, **attributes):
    inner_container = Widget("inner_container")
    inner_container.style_overflow = "visible"
    outer_container = Widget("outer_container")
    outer_container.style_overflow = "scroll"
    outer_container.style_flex_direction = "column"
    outer_container.mouse_hit_rect = False
    outer_container.shifter = Scroller(None, y, inner_container)
    outer_container.style_padding = edges(right=15)
    @view.attach
    def _clip_contents_(this, frame):
        frame.screen.set_clip(frame.rect)
    view.append(outer_container)
    outer_container.append(inner_container)
    @view.attach
    def _clip_contents_(this, frame):
        frame.screen.set_clip(None)
    for name, value in attributes.items():
        setattr(view, name, value)
    view.append(vscrollbar("vscroll", y))
    def _mousebuttondown_(this, frame):
        pc = 150 / inner_container.height if inner_container.height > 0 else 0
        if frame.ev.button == 4:
            y.offset = max(0, min(1, y.offset - pc))
        elif frame.ev.button == 5:
            y.offset = max(0, min(1, y.offset + pc))
        else:
            raise NoCapture
    view.post_mousebuttondown = _mousebuttondown_
    return inner_container

# TODO: reconsider where the sy should come from.
def context_menu(sy, x, y, leave_with=None):
    def _context_menu_(fn):
        @composable
        @functools.wraps(fn)
        def menu(*args, **kwargs):
            layout().style_position_type = "absolute"
            layout().style_position = edges(top=0, left=0)
            layout().style_max_width = 95*pc
            layout().style_max_height = 95*pc
            layout().shifter = Mover(x, y, 0.95, 0.95, widget())
            @widget().attach
            def _draw_(this, frame):
                pygame.draw.rect(frame.screen, (30, 30, 30), frame.rect, 0, 3)
                pygame.draw.rect(frame.screen, (200, 200, 200), frame.rect, 1, 3)
            leave_popup = context().leave_popup if leave_with is None else leave_with
            def _mousebuttondown_(this, frame):
                if frame.ev.button not in (1,2,3):
                    raise NoCapture
                if not frame.inside:
                    frame.emit(leave_popup)
            widget().mouse_hit_rect = False
            widget().post_mousebuttondown = _mousebuttondown_
            if sy is None:
                fn(*args, **kwargs)
            else:
                with vscrollable(sy, style_flex_shrink=1):
                    fn(*args, **kwargs)
        return menu
    return _context_menu_

def splash_screen(leave_with=None):
    def _decorator_(fn):
        @composable
        @functools.wraps(fn)
        def splash(*args, **kwargs):
            layout().style_position_type = "absolute"
            layout().style_position = edges(5*pc,5*pc,5*pc,5*pc)
            @widget().attach
            def _draw_(this, frame):
                pygame.draw.rect(frame.screen, (30, 30, 30), frame.rect, 0, 3)
                pygame.draw.rect(frame.screen, (200, 200, 200), frame.rect, 1, 3)
            leave_popup = context().leave_popup if leave_with is None else leave_with
            def _mousebuttondown_(this, frame):
                if frame.ev.button not in (1,2,3):
                    raise NoCapture
                if not frame.inside:
                    frame.emit(leave_popup)
            widget().mouse_hit_rect = False
            widget().post_mousebuttondown = _mousebuttondown_
            fn(*args, **kwargs)
        return splash
    return _decorator_
