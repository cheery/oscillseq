from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from descriptors import bus, kinds
from gui.base import ScrollField, UIEvent, UIState, move_focus, draw_widget, Widget, NoCapture, AnchorToCenter, Panner, DrawFrame
from gui.components import *
from gui.event import uievent
from gui.compostor import composable, component, Compostor, layout, widget, context, key, Hook
from model import View, Staves, Grid, PianoRoll
from sarpasana import gutters, edges, pc
import music
import pygame

class ViewView:
    def __init__(self, editor):
        self.editor = editor
        self.scene = None
        self.selected = None
        self.scroll = ScrollField()
        self.get_lanes = Hook(lambda n: self.editor.doc.views[n].lanes)

    def refresh(self):
        self.scene = tuple(name for name in self.editor.doc.views), self.selected

    @composable
    def scene_layout(self, scene):
        layout().style_flex_grow = 1
        selected = scene[1]
        with frame():
            layout().style_flex_direction = "row"
            layout().style_flex_wrap = "wrap"
            for name in scene[0]:
                with button(self.select_view(name), None, self.editor.enter_popup(self.view_menu_compact, name), keyboard=False):
                    if selected == name:
                        @widget().attach
                        def _on_selected_(this, frame):
                            rect = frame.rect.inflate((-2, -2))
                            pygame.draw.rect(frame.screen, (70, 70, 70), rect)
                    layout().style_min_width = 100
                    layout().style_justify_content = "center"
                    layout().style_flex_direction = "row"
                    with label(name):
                        layout().style_flex_shrink = 1
            with button(self.new_view, keyboard=False):
                layout().style_min_width = 100
                layout().style_justify_content = "center"
                layout().style_flex_direction = "row"
                with label("new"):
                    layout().style_flex_shrink = 1
        if selected is None:
            with frame():
                layout().style_padding = edges(20)
                label("no view selected")
        else:
            with vscrollable(self.scroll, style_flex=1):
                lanes = self.get_lanes(selected)
                if len(lanes) == 0:
                    with frame():
                        layout().style_padding = edges(20)
                        label("add a lane by right click")
                for i, lane in enumerate(lanes):
                    if isinstance(lane, Staves):
                        self.stave_layout(selected, i, lane.count, lane.above, lane.below, tuple(lane.edit))
                    if isinstance(lane, Grid):
                        self.grid_layout(selected, i, lane.kind, tuple(lane.edit))
                    if isinstance(lane, PianoRoll):
                        self.pianoroll_layout(selected, i, lane.bot, lane.top, tuple(lane.edit))
        def _mousebuttondown_(this, frame):
            if frame.ev.button == 3:
                frame.emit(self.editor.enter_popup(self.view_menu, selected))
            else:
                raise NoCapture
        widget().post_mousebuttondown = _mousebuttondown_

    @uievent
    def new_view(self):
        view = self.editor.doc.intro(View("", []))
        self.editor.doc.views[view.label] = view
        self.selected = view.label
        self.editor.refresh_layout()
        return view.label

    @uievent
    def select_view(self, name):
        self.selected = name
        self.editor.refresh_layout()

    def view_menu_compact(self, selected):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            with button(self.discard_view(selected)):
                label(f"discard {repr(selected)}")
        return menu

    def view_menu(self, selected, index=None, ins_index=None):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            if index is not None:
                lane = self.get_lanes(selected)[index]
                if isinstance(lane, Staves):
                    with button(self.editor.enter_popup(self.edit_count, lane)):
                        label(f"count={lane.count}")
                    with button(self.editor.enter_popup(self.edit_above, lane)):
                        label(f"above={lane.above}")
                    with button(self.editor.enter_popup(self.edit_below, lane)):
                        label(f"below={lane.below}")
                elif isinstance(lane, PianoRoll):
                    with button(self.editor.enter_popup(self.edit_top, lane)):
                        label(f"top={music.Pitch.from_midi(lane.top)}")
                    with button(self.editor.enter_popup(self.edit_bot, lane)):
                        label(f"bot={music.Pitch.from_midi(lane.bot)}")
                elif isinstance(lane, Grid):
                    with button(self.editor.enter_popup(self.edit_kind, lane)):
                        label(f"kind={lane.kind}")
                with button(self.discard_lane(selected, index)):
                    label("discard this lane")
            if selected is not None:
                with button(self.discard_view(selected)):
                    label(f"discard {repr(selected)}")
            with button(self.new_lane(selected, ins_index, "staves")):
                label("new staves")
            with button(self.new_lane(selected, ins_index, "pianoroll")):
                label("new piano roll")
            with button(self.new_lane(selected, ins_index, "grid")):
                label("new grid")
        return menu

    def edit_count(self, lane):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            for i in [4, 3, 2, 1]:
                with button(self.set_param(lane, "count", i)):
                    label(str(i))
        return menu

    def edit_above(self, lane):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            for i in [2, 1, 0]:
                with button(self.set_param(lane, "above", i)):
                    label(str(i))
        return menu

    def edit_below(self, lane):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            for i in [2, 1, 0]:
                with button(self.set_param(lane, "below", i)):
                    label(str(i))
        return menu

    def edit_top(self, lane):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            pitches = []
            pitches.extend(range(0,127,12))
            pitches.extend(range(9,127,12))
            pitches.sort()
            for i in reversed(pitches):
                with button(self.set_param(lane, "top", i)):
                    label(str(music.Pitch.from_midi(i)))
        return menu

    def edit_bot(self, lane):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            pitches = []
            pitches.extend(range(0,127,12))
            pitches.extend(range(9,127,12))
            pitches.sort()
            for i in reversed(pitches):
                with button(self.set_param(lane, "bot", i)):
                    label(str(music.Pitch.from_midi(i)))
        return menu

    def edit_kind(self, lane):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            for name in kinds:
                with button(self.set_param(lane, "kind", name)):
                    label(name)
        return menu

    @uievent
    def set_param(self, lane, name, value):
        setattr(lane, name, value)
        if name == "top":
            lane.bot = min(lane.bot, value)
        if name == "bot":
            lane.top = max(lane.top, value)
        if name == "kind":
            avail = list(self.available_editparams(lane))
            for entry in lane.edit[:]:
                 if entry not in avail:
                     lane.edit.remove(entry)
        self.get_lanes.invalidate()
        self.editor.leave_popup.invoke()

    @uievent
    def discard_lane(self, selected, index):
        del self.editor.doc.views[selected].lanes[index]
        self.get_lanes.invalidate()
        self.editor.leave_popup.invoke()

    @uievent
    def discard_view(self, name):
        if name == self.selected:
            self.selected = None
        self.editor.doc.views.pop(name)
        self.editor.doc.labels.pop(name)
        self.editor.leave_popups.invoke()

    @uievent
    def new_lane(self, selected, index, kind):
        if selected is None:
            selected = self.new_view.invoke()
        if kind == "staves":
            lane = Staves(1, 1, 1, [])
        elif kind == "pianoroll":
            lane = PianoRoll(top=69+12, bot=69-12, edit=[])
        elif kind == "grid":
            lane = Grid("number", [])
        view = self.editor.doc.views[selected]
        view.lanes.insert(len(view.lanes) if index is None else index, lane)
        self.get_lanes.invalidate()
        self.editor.leave_popups.invoke()

    @composable
    def stave_layout(self, selected, index, count, above, below, edit):
        layout().style_min_height = height = calculate_staves_heigth(self.editor, count, above, below)
        self.common(selected, index, edit)
        with frame():
            @widget().attach
            def _draw_(this, frame):
                pygame.draw.rect(frame.screen, (250,0,0), frame.rect, 5, 5)
        with frame():
            layout().style_flex_grow = 1
            layout().style_height = height
            layout().style_align_self = "center"
            widget().attach(draw_staves(self.editor, count, above, below))

    @composable
    def grid_layout(self, selected, index, kind, edit):
        layout().style_min_height = calculate_grid_height(self.editor, kind)
        self.common(selected, index, edit)
        with frame():
            @widget().attach
            def _draw_(this, frame):
                pygame.draw.rect(frame.screen, (250,0,0), frame.rect, 5, 5)

    @composable
    def pianoroll_layout(self, selected, index, bot, top, edit):
        layout().style_min_height = height = calculate_pianoroll_height(self.editor, bot, top)
        self.common(selected, index, edit)
        with frame():
            @widget().attach
            def _draw_(this, frame):
                pygame.draw.rect(frame.screen, (250,0,0), frame.rect, 5, 5)
        with frame():
            layout().style_flex_grow = 1
            layout().style_height = height
            layout().style_align_self = "center"
            widget().attach(draw_pianoroll(self.editor, bot, top))

    def common(self, selected, index, edit):
        layout().style_flex_direction = "row"
        @widget().attach
        def _draw_edges_(this, frame):
            pygame.draw.line(frame.screen, (70, 70, 70), frame.rect.topleft, frame.rect.topright)
            pygame.draw.line(frame.screen, (70, 70, 70), frame.rect.bottomleft, frame.rect.bottomright)
        with frame():
            @widget().attach
            def _draw_side_(this, frame):
                pygame.draw.line(frame.screen, (70, 70, 70), frame.rect.topright, frame.rect.bottomright)
            layout().style_flex_direction = "column"
            layout().style_width = self.editor.MARGIN
            for j, (name, param) in enumerate(edit):
                with frame():
                    label(editparam_text(self.editor, name, param))
                    widget().post_mousebuttondown = self.editparam_menu(selected, index, j)
            widget().post_mousebuttondown = self.editparam_menu(selected, index, len(edit))
        def _mousebuttondown_(this, frame):
            if frame.ev.button == 3:
                ins_index = index + 1*(frame.ev.pos[1] > frame.rect.center[1])
                frame.emit(self.editor.enter_popup(self.view_menu, selected, index, ins_index))
            else:
                raise NoCapture
        widget().post_mousebuttondown = _mousebuttondown_

    def editparam_menu(self, selected, index, j):
        def event_handler(this, frame):
            k = j + 1*(frame.ev.pos[1] > frame.rect.center[1])
            @context_menu(ScrollField(), *pygame.mouse.get_pos())
            def menu():
                layout().style_padding = edges(10)
                layout().style_gap = gutters(5)
                layout().style_min_width = 100
                lane = self.get_lanes(selected)[index]
                if j < len(lane.edit):
                    with button(self.discard_editparam(lane.edit, j)):
                        label(f"discard {repr(editparam_text(self.editor, *lane.edit[j]))}")
                for name, param in self.available_editparams(lane):
                    if (name, param) not in lane.edit:
                        with button(self.add_editparam(lane.edit, k, name, param)):
                            label("add " + editparam_text(self.editor, name, param))
            frame.emit(self.editor.enter_popup(lambda: menu))
        return event_handler

    def available_editparams(self, lane):
        if isinstance(lane, (Staves, PianoRoll)):
            ty = ['pitch', 'hz']
        else:
            ty = [lane.kind]
        descs = self.editor.definitions.descriptors(self.editor.doc.cells)
        def is_multi(label):
            if cell := self.editor.doc.labels.get(label, None):
                return cell.multi
            return False
        for name, desc in descs.items():
            for param in desc.avail(ty):
                yield name, param
            if "trigger" in ty and is_multi(name):
                yield name, "+"

    @uievent
    def discard_editparam(self, edit, index):
        del edit[index]
        self.get_lanes.invalidate()
        self.editor.leave_popup.invoke()

    @uievent
    def add_editparam(self, edit, index, name, param):
        edit.insert(index, (name, param))
        self.get_lanes.invalidate()
        self.editor.leave_popup.invoke()

    def deploy(self):
        pass

    def close(self):
        pass

def editparam_text(editor, label, name):
    text = f"{label}:{name}"
    if text not in ["tempo:~", "tempo:*"] and label in editor.doc.labels:
        text = f"{label}:{editor.doc.labels[label].synth}:{name}"
    return text

def calculate_staves_heigth(editor, count, above, below):
    return editor.STAVE_HEIGHT * 2 * (count + above + below)

def calculate_pianoroll_height(editor, bot, top):
    return editor.STAVE_HEIGHT * 2 / 12 * (top - bot + 1)

def calculate_grid_height(editor, kind):
    return editor.font.size("X")[1]

def draw_staves(editor, count, above, below):
    def _draw_(this, frame):
        rect = frame.rect
        x, y = rect.topleft
        w = rect.width
        k = rect.height / (count + above + below)
        y += above * k
        for _ in range(count):
            for p in range(2, 12, 2):
                pygame.draw.line(frame.screen, (70, 70, 70), (x, y+p*k/12), (x+w, y+p*k/12))
            y += k
    return _draw_

def draw_pianoroll(editor, bot, top):
    def _draw_(this, frame):
        rect = frame.rect
        x, y = rect.bottomleft
        w = rect.width
        k = rect.height / (top - bot + 1)
        for note in range(bot, top + 1):
            py = y - k*(note - bot)
            rect = pygame.Rect(x, py-k, w, k)
            if note == 69:
                pygame.draw.rect(frame.screen, (100*1.5, 50*1.5, 50*1.5), rect)
            elif note % 12 == 9:
                pygame.draw.rect(frame.screen, (100, 50, 50), rect)
            elif note % 12 in [0, 2, 4, 5, 7, 9, 11]:
                pygame.draw.rect(frame.screen, (50, 50, 50), rect)
            elif note == bot:
                pygame.draw.line(frame.screen, (70, 70, 70), (x, py), (rect.right, py))
            else:
                pygame.draw.line(frame.screen, (50, 50, 50), (x, py), (rect.right, py))
    return _draw_
