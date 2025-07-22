from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from controllers import quick_connect
from descriptors import bus, kinds
from fabric import Definitions, Fabric
from gui.base import ScrollField, UIEvent, UIState, move_focus, draw_widget, Widget, NoCapture, AnchorToCenter, Panner, DrawFrame
from gui.components import *
from gui.event import uievent, invoke_at_event
from gui.compostor import composable, component, Compostor, layout, widget, context, key, Hook
from model import Document, Cell, from_file, stringify, reader
from model import View, Staves, Grid, PianoRoll
from sarpasana import gutters, edges, pc
from sequencer import Player, Sequencer, SequenceBuilder2
from node_view import NodeView
import numpy as np
import math
import music
import os
import pygame
import spectroscope
import supriya
import sys

class MainView:
    def __init__(self, editor):
        self.editor = editor
        self.scene = None

    def refresh(self):
        pass

    @composable
    def scene_layout(self, scene):
        @widget().attach
        def _draw_scopes_(this, frame):
            self.s1.refresh()
            self.s2.refresh()
            y0 = frame.rect.top + frame.rect.height/4 - 100
            y1 = frame.rect.top + frame.rect.height*3/4 - 100
            self.s1.draw(frame.screen, self.editor.font, (255, 0, 0),
                self.editor.screen_width/2, y0)
            self.s2.draw(frame.screen, self.editor.font, (0, 255, 0),
                self.editor.screen_width/2, y1)
        layout().style_flex_grow = 1
        layout().style_padding = edges(20)
        label("oscillseq version 0")
        label(f"editing {repr(os.path.basename(self.editor.filename))}")
        label("select a view")

    def deploy(self):
        out = self.editor.server.audio_output_bus_group
        self.s1 = self.editor.make_spectroscope(bus=out[0])
        self.s2 = self.editor.make_spectroscope(bus=out[1])

    def close(self):
        self.s1.close()
        self.s2.close()

class TrackView:
    def __init__(self, editor):
        self.editor = editor
        self.scene = None

    def refresh(self):
        pass

    @composable
    def scene_layout(self, scene):
        layout().style_flex_grow = 1
        layout().style_padding = edges(20)

    def deploy(self):
        pass

    def close(self):
        pass

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

    # TODO: display lanes

    @composable
    def stave_layout(self, selected, index, count, above, below, edit):
        layout().style_min_height = 80
        self.common(selected, index, edit)
        with frame():
            @widget().attach
            def _draw_(this, frame):
                pygame.draw.rect(frame.screen, (250,0,0), frame.rect, 5, 5)

    @composable
    def grid_layout(self, selected, index, kind, edit):
        layout().style_min_height = 20
        self.common(selected, index, edit)
        with frame():
            @widget().attach
            def _draw_(this, frame):
                pygame.draw.rect(frame.screen, (250,0,0), frame.rect, 5, 5)

    @composable
    def pianoroll_layout(self, selected, index, bot, top, edit):
        layout().style_min_height = 50
        self.common(selected, index, edit)
        with frame():
            @widget().attach
            def _draw_(this, frame):
                pygame.draw.rect(frame.screen, (250,0,0), frame.rect, 5, 5)

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

class Editor:
    screen_width = 1200
    screen_height = 600
    fps = 30

    MARGIN = 220
    BARS_VISIBLE = 4

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(
            (self.screen_width, self.screen_height))
        pygame.display.set_caption("oscillseq")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Arial', 16)

        self.doc = Document(
            brushes = [],
            duration = 1,
            labels = {},
            cells = [],
            views = {},
            connections = set([]),
        )
        self.doc.cells.append(self.doc.intro(Cell("tempo",
            multi = False,
            synth = "quadratic",
            pos = (-400, 0),
            params = {},
            type_param = "number")))

        if len(sys.argv) > 1:
            self.filename = sys.argv[1]
        else:
            self.filename = "unnamed.seq.json"
        if os.path.exists(self.filename):
            self.doc = from_file(self.filename)
            if self.filename.endswith(".json"):
                self.filename = self.filename[:-5]
        self.png_directory = os.path.abspath(
            os.path.splitext(self.filename)[0] + ".png")
        self.wav_filename = os.path.abspath(
            os.path.splitext(self.filename)[0] + ".wav")
        directory = os.path.dirname(os.path.abspath(self.filename))
        self.definitions = Definitions(
            synthdef_directory = os.path.join(directory,"synthdefs"))

        self.midi_status = False
        self.midi_controllers = []

        self.transport_status = 0
        self.server = None
        self.fabric = None
        self.clavier = None
        self.player = None
        self.set_online()

        self.playback_range = None
        self.playback_loop  = True

        # Sequence is built so it could be visualized.
        self.group_ids = {}
        #sb = SequenceBuilder2(self.group_ids, self.definitions.descriptors(self.doc.cells))
        #self.doc.construct(sb, 0, ())
        #self.sequence = sb.build(self.doc.duration)

        #self.transport_bar = TransportBar(self)

        #self.toolbar = Toolbar(pygame.Rect(0, self.SCREEN_HEIGHT - 32, self.SCREEN_WIDTH, 32),
        #    [
        #        ("track editor", BrushEditorView),
        #        ("view editor", ViewEditorView),
        #        ("cell editor", NodeEditorView)
        #    ],
        #    (lambda ev, view: self.change_view(view)),
        #    (lambda name, cls: isinstance(self.view, cls)))

        self.timeline_head = 0
        self.timeline_tail = 0
        self.timeline_scroll = 0
        self.timeline_vertical_scroll = 0

        self.lane_tag = None
        #self.layout = TrackLayout(self.doc, offset = 30)
        self.view = MainView(self)
        self.view.deploy()

        self.popups = ()
        self.compostor = Compostor(self.screen_layout, self)
        self.ui = UIState(self.compostor.root)
        self.refresh_layout()

    def refresh_layout(self):
        if self.transport_status != 3:
            self.group_ids.clear()
        sb = SequenceBuilder2(self.group_ids, self.definitions.descriptors(self.doc.cells))
        self.doc.construct(sb, 0, ())
        self.sequence = sb.build(self.doc.duration)
        #self.layout = TrackLayout(self.doc, offset = 30)
        if (point := self.get_playing()) is not None:
            self.set_playing(Sequencer(self.sequence, point=self.sequence.t(point), **self.playback_params(self.sequence)))
        self.view.refresh()
        root = self.compostor(self.view.scene, self.popups)
        root.calculate_layout(self.screen_width, self.screen_height, "ltr")

    def set_offline(self):
        if self.transport_status > 0:
            self.set_online()
            self.server.quit()
            self.server = None
        self.transport_status = 0

    def set_online(self):
        if self.transport_status < 1:
            self.server = supriya.Server().boot()
            self.make_spectroscope = spectroscope.prepare(self.server)
        if self.transport_status > 1:
            self.set_fabric()
            self.fabric.close()
            self.fabric = None
            self.clavier = None
        self.transport_status = 1

    def set_fabric(self):
        if self.transport_status < 2:
            self.set_online()
            self.fabric = Fabric(
                self.server, self.doc.cells, self.doc.connections, self.definitions)
            self.clavier = {}
        if self.transport_status > 2:
            self.player.close()
            self.player = None
        self.transport_status = 2

    def set_fabric_and_stop(self):
        if self.transport_status > 2:
            self.set_fabric()
            for synth in self.clavier.values():
                synth.set(gate=0)
            self.clavier.clear()
        else:
            self.set_fabric()

    def set_playing(self, sequencer):
        if self.transport_status < 3:
            self.set_fabric()
        if self.player is not None:
            self.player.close()
        self.player = Player(self.clavier, self.fabric, sequencer)
        self.transport_status = 3

    def get_playing(self):
        if self.transport_status == 3:
            return self.player.sequencer.status

    def restart_fabric(self):
        if self.transport_status == 3:
            sequencer = self.player.sequencer
        else:
            sequencer = None
        if self.transport_status >= 2:
            self.set_online()
            self.set_fabric()
        if sequencer:
            self.set_playing(sequencer)

    def toggle_midi(self):
        if self.midi_status:
            self.set_midi_off()
        else:
            self.set_midi_on()

    def set_midi_on(self):
        if not self.midi_status:
            self.midi_controllers = quick_connect(self)
            self.midi_status = True

    def set_midi_off(self):
        self.midi_status = False
        for controller in self.midi_controllers:
            controller.close()
        self.midi_controllers.clear()

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(self.fps) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    self.handle_keydown(ev)
                else:
                    self.process_event(ev)

            self.screen.fill((30, 30, 30))
            draw_widget(self.ui, self.compostor.root, self.screen, self.screen.get_rect())
            pygame.display.flip()

        #self.view.close()
        self.set_offline()
        self.set_midi_off()
        pygame.quit()
        sys.exit()

    def screen_layout(self, scene, popups):
        layout().style_flex_direction = "column"
        with frame():
            layout().style_height = 20
            layout().style_flex_direction = "row"
            @widget().attach
            def _draw_top_background_(this, frame):
                pygame.draw.rect(frame.screen, (60, 60, 60), frame.rect, 0, 0)
            self.transport_bar_buttons()
            with frame():
                layout().style_flex_direction = "row"
                layout().style_flex_grow = 1
                @widget().attach
                def _draw_transport_bar_(this, frame):
                    w = frame.rect.width / self.BARS_VISIBLE
                    mg = []
                    for i in range(self.BARS_VISIBLE + 1):
                        x = i * w + frame.rect.left
                        if (i + self.timeline_scroll) == self.timeline_head:
                            pygame.draw.line(frame.screen, (0, 255, 255),
                                (x, frame.rect.top), (x, frame.rect.bottom))
                        else:
                            pygame.draw.line(frame.screen, (200, 200, 200),
                                (x, frame.rect.top), (x, frame.rect.bottom))
                        text = self.font.render(str(i + editor.timeline_scroll), True, (200, 200, 200))
                        frame.screen.blit(text, (x + 2, frame.rect.centery - text.get_height()/2))
                        mg.append(text.get_width())

                    if self.playback_range is not None:
                        i, j = self.playback_range
                        half_width  = 6 / 2
                        half_height = 6 / 2
                        if self.timeline_scroll <= i < self.timeline_scroll + self.BARS_VISIBLE:
                            centerx = (i - self.timeline_scroll) * w + 6 + mg[i - self.timeline_scroll] + frame.rect.left
                            centery = frame.rect.centery
                            top = (centerx, centery - half_height)
                            rig = (centerx + half_width, centery)
                            bot = (centerx, centery + half_height)
                            lef = (centerx - half_width, centery)
                            pygame.draw.polygon(frame.screen, (200, 200, 200), [top, rig, bot])

                        if self.timeline_scroll < j <= self.timeline_scroll + self.BARS_VISIBLE:
                            centerx = (j - self.timeline_scroll) * w - 6 + frame.rect.left
                            centery = frame.rect.centery
                            top = (centerx, centery - half_height)
                            rig = (centerx + half_width, centery)
                            bot = (centerx, centery + half_height)
                            lef = (centerx - half_width, centery)
                            pygame.draw.polygon(frame.screen, (200, 200, 200), [top, bot, lef])

                    if (t := self.get_playing()) is not None:
                        x = (t - editor.timeline_scroll) * w + frame.rect.left
                        pygame.draw.line(frame.screen, (255, 0, 0),
                            (x, frame.rect.top), (x, frame.rect.bottom))

        self.view.scene_layout(scene)

        with frame():
            layout().style_height = 32
            layout().style_flex_direction = "row"
            with button(uievent(self.change_view)(TrackView), keyboard=False):
                @widget().attach
                def _when_selected_(this, frame):
                    if isinstance(self.view, TrackView):
                        pygame.draw.rect(frame.screen, (70,70,70), frame.rect.inflate((-2,-2)))
                layout().style_align_items = "center"
                layout().style_justify_content = "center"
                layout().style_min_width = 100
                label("track")
            with button(uievent(self.change_view)(ViewView), keyboard=False):
                @widget().attach
                def _when_selected_(this, frame):
                    if isinstance(self.view, ViewView):
                        pygame.draw.rect(frame.screen, (70,70,70), frame.rect.inflate((-2,-2)))
                layout().style_align_items = "center"
                layout().style_justify_content = "center"
                layout().style_min_width = 100
                label("view")
            with button(uievent(self.change_view)(NodeView), keyboard=False):
                @widget().attach
                def _when_selected_(this, frame):
                    if isinstance(self.view, NodeView):
                        pygame.draw.rect(frame.screen, (70,70,70), frame.rect.inflate((-2,-2)))
                layout().style_align_items = "center"
                layout().style_justify_content = "center"
                layout().style_min_width = 100
                label("cell")

        for popup in popups:
            popup()
        def _mousebuttondown_(this, frame):
            frame.focus()
        widget().post_mousebuttondown = _mousebuttondown_
        def _keydown_(this, frame):
            mods = pygame.key.get_mods()
            shift_held = mods & pygame.KMOD_SHIFT
            ctrl_held = mods & pygame.KMOD_CTRL
            if frame.ev.key == pygame.K_TAB:
                frame.emit(self.tab(shift_held))
            elif frame.ev.key == pygame.K_SPACE and ctrl_held:
                self.set_online()
            elif frame.ev.key == pygame.K_SPACE:
                self.toggle_play()
        widget().at_keydown = _keydown_

    @composable
    def transport_bar_buttons(self):
        layout().style_flex_direction = "row"
        layout().style_width = self.MARGIN
        menu = self.enter_popup(self.open_system_menu)
        with button(uievent(self.set_online), None, menu, decor=False, keyboard=False):
            layout().style_width  = 20
            layout().style_height = 20
            @widget().attach
            def _draw_down_arrow_(this, frame):
                if self.transport_status == 1:
                    color = 10, 10, 155
                else:
                    color = 100, 100, 100
                pygame.draw.rect(frame.screen, color, frame.rect, 0, 0)
                centerx, centery = frame.rect.center
                half_width  = 6 / 2
                half_height = 6 / 2
                top = (centerx, centery - half_height)
                rig = (centerx + half_width, centery)
                bot = (centerx, centery + half_height)
                lef = (centerx - half_width, centery)
                pygame.draw.line(frame.screen, (200, 200, 200), top, bot)
                pygame.draw.line(frame.screen, (200, 200, 200), lef, bot)
                pygame.draw.line(frame.screen, (200, 200, 200), bot, rig)
                if frame.same(frame.ui.pressed):
                    pygame.draw.rect(frame.screen, (50, 150, 50), frame.rect, 1)

        with button(uievent(self.set_fabric_and_stop), None, menu, decor=False, keyboard=False):
            layout().style_width  = 20
            layout().style_height = 20
            @widget().attach
            def _draw_up_arrow_(this, frame):
                if self.transport_status >= 2:
                    color = 10, 155, 10
                else:
                    color = 100, 100, 100
                pygame.draw.rect(frame.screen, color, frame.rect, 0, 0)
                centerx, centery = frame.rect.center
                half_width  = 6 / 2
                half_height = 6 / 2
                top = (centerx, centery - half_height)
                rig = (centerx + half_width, centery)
                bot = (centerx, centery + half_height)
                lef = (centerx - half_width, centery)
                pygame.draw.line(frame.screen, (200, 200, 200), top, bot)
                pygame.draw.line(frame.screen, (200, 200, 200), lef, top)
                pygame.draw.line(frame.screen, (200, 200, 200), top, rig)
                if frame.same(frame.ui.pressed):
                    pygame.draw.rect(frame.screen, (50, 150, 50), frame.rect, 1)
        with button(self.at_play_button, None, menu, decor=False, keyboard=False):
            layout().style_width  = 20
            layout().style_height = 20
            @widget().attach
            def _draw_play_stop_(this, frame):
                pygame.draw.rect(frame.screen, (200, 200, 200), frame.rect, 1, 0)
                if (t := self.get_playing()) is not None:
                    pygame.draw.rect(frame.screen, (200, 200, 200),
                        frame.rect.inflate((-14, -14)), 0, 0)
                else:
                    centerx, centery = frame.rect.center
                    half_width  = 6 / 3
                    half_height = 6 / 2
                    points = [
                        (centerx - half_width, centery - half_height),  # top
                        (centerx + half_width, centery),   # right
                        (centerx - half_width, centery + half_height),  # bottom
                    ]
                    pygame.draw.polygon(frame.screen, (200, 200, 200), points)
                if frame.same(frame.ui.pressed):
                    pygame.draw.rect(frame.screen, (50, 150, 50), frame.rect, 1)
                elif frame.same(frame.ui.focus):
                    pygame.draw.rect(frame.screen, (50, 50, 150), frame.rect, 1)
        with button(uievent(self.toggle_midi), decor=False, keyboard=False):
            layout().style_width  = 70
            layout().style_height = 20
            @widget().attach
            def _midi_status_(this, frame):
                pygame.draw.rect(frame.screen, (200, 200, 200), frame.rect, 1, 0)
                midi_off_on = ["midi=off", "midi=on"][self.midi_status]
                text = self.font.render(midi_off_on, True, (200, 200, 200))
                frame.screen.blit(text,
                    (frame.rect.centerx - text.get_width()/2,
                     frame.rect.centery - text.get_height()/2))
                if frame.same(frame.ui.pressed):
                    pygame.draw.rect(frame.screen, (50, 150, 50), frame.rect, 1)
        with button(self.at_toggle_loop, decor=False, keyboard=False):
            layout().style_width  = 70
            layout().style_height = 20
            @widget().attach
            def _loop_status_(this, frame):
                pygame.draw.rect(frame.screen, (200, 200, 200), frame.rect, 1, 0)
                loop_off_on = ["loop=off", "loop=on"][self.playback_loop]
                text = self.font.render(loop_off_on, True, (200, 200, 200))
                frame.screen.blit(text,
                    (frame.rect.centerx - text.get_width()/2,
                     frame.rect.centery - text.get_height()/2))
                if frame.same(frame.ui.pressed):
                    pygame.draw.rect(frame.screen, (50, 150, 50), frame.rect, 1)

    def handle_keydown(self, ev):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        ctrl_held = mods & pygame.KMOD_CTRL
        if mods & ctrl_held:
            if ev.key == pygame.K_1:
                self.change_view(TrackView)
            elif ev.key == pygame.K_2:
                self.change_view(ViewView)
            elif ev.key == pygame.K_3:
                self.change_view(NodeView)
            #elif ev.key == pygame.K_4:
            #elif ev.key == pygame.K_6:
            #elif ev.key == pygame.K_7:
            elif ev.key == pygame.K_s:
                self.save_file()
            elif ev.key == pygame.K_r:
                self.render_score()
            #elif ev.key == pygame.K_v:
            #    self.change_view(VideoRendererView)
            else:
                self.process_event(ev)
        else:
            self.process_event(ev)

    def process_event(self, ev):
        invoke_at_event(self.ui, self.compostor.root, ev, self.screen.get_rect())

    def scan(self, matcher):
        frame = DrawFrame(self.ui, self.screen, self.screen.get_rect())
        return self.compostor.root.scan(frame, matcher)

    @uievent
    def tab(self, reverse):
        move_focus(self.ui, self.compostor.root, self.screen.get_rect(), reverse)

    @uievent
    def enter_popup(self, make_popup, *args):
        self.popups += (make_popup(*args),)
        self.refresh_layout()

    @uievent
    def leave_popup(self):
        self.popups = self.popups[:-1]
        self.refresh_layout()

    @uievent
    def leave_popups(self):
        self.popups = ()
        self.refresh_layout()

    @uievent
    def at_play_button(self):
        if self.transport_status <= 1:
            self.set_fabric()
        self.toggle_play()

    @uievent
    def at_toggle_loop(self):
        self.playback_loop = not self.playback_loop
        if (status := self.get_playing()) is not None:
            self.set_fabric()
            sequence = self.sequence
            self.set_playing(Sequencer(sequence, point=sequence.t(status), **self.playback_params(sequence)))

    def open_system_menu(self):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            with button(uievent(self.save_file)):
                label(f"save {repr(os.path.basename(self.filename))}")
            with button(uievent(self.render_score)):
                label(f"record {repr(os.path.basename(self.wav_filename))}")
        return menu

    def change_view(self, View):
        if not isinstance(self.view, View):
            if self.view is not None:
                self.view.close()
            self.view = View(self)
            self.view.deploy()
            self.refresh_layout()

    def toggle_play(self):
        if self.transport_status < 2:
            self.set_fabric()
        elif self.get_playing() is None:
            if self.transport_status == 3:
                self.set_fabric()
            sequence = self.sequence
            self.set_playing(Sequencer(sequence, point=sequence.t(min(self.timeline_head, self.timeline_tail)), **self.playback_params(sequence)))
        else:
            self.set_fabric_and_stop()

    def playback_params(self, sequence):
        if self.playback_loop and self.playback_range:
            a, b = self.playback_range
            loop_start = sequence.t(a)
            loop_point = sequence.t(b)
            end_point = sequence.end
        elif self.playback_range:
            a, b = self.playback_range
            loop_start = -1
            loop_point = -1
            end_point = sequence.t(b)
        elif self.playback_loop:
            loop_start = 0
            loop_point = sequence.end
            end_point = sequence.end
        else:
            loop_start = -1
            loop_point = -1
            end_point = sequence.end
        return {'loop_start': loop_start, 'loop_point': loop_point, 'end_point': end_point}

    def save_file(self):
        to_file(self.filename, self.doc)
        print("document saved!")

    def render_score(self):
        view = self.view
        self.view.close()
        self.view = None
        self.set_offline()

        sequence = self.sequence
        score = supriya.Score(output_bus_channel_count=2)
        clavier = {}
        with score.at(0):
            fabric = Fabric(score, self.doc.cells, self.doc.connections, self.definitions)
        for command in sequence.com:
            with score.at(command.time):
                command.send(clavier, fabric)
        with score.at(sequence.t(self.doc.duration)):
            score.do_nothing()
        supriya.render(score, output_file_path=self.wav_filename)
        print("saved", self.wav_filename)

        self.set_online()
        self.view = view.deploy()
        self.refresh_layout()

def draw_diamond(screen, color, center, size):
    center_x, center_y = center
    half_width = size[0] / 2
    half_height = size[1] / 2
    points = [
        (center_x, center_y - half_height),  # top
        (center_x + half_width, center_y),   # right
        (center_x, center_y + half_height),  # bottom
        (center_x - half_width, center_y),   # left
    ]
    pygame.draw.polygon(screen, color, points)

if __name__ == '__main__':
    editor = Editor()
    editor.run()
