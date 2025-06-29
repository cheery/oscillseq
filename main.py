from dataclasses import dataclass, field
from fractions import Fraction
from model import Entity, ControlPoint, Key, Clip, ConstGen, PolyGen, Clap, Desc, DrawFunc, PitchLane, Document, json_to_brush
from pythonosc import udp_client, dispatcher, osc_server
from typing import List, Dict, Optional, Callable, Tuple, Any
from sequencer import Player, Sequencer, SequenceBuilder
from fabric import Definitions, Cell, Fabric
from components import ContextMenu
from controllers import quick_connect
import numpy as np
import bisect
import collections
import heapq
import math
import measure
import music
import os
import pygame
import supriya
import sys
import spectroscope
from node_editor_view import NodeEditorView

class DummyView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = DummyTool(self)

    def draw(self, screen):
        font = self.editor.font

    def handle_keydown(self, ev):
        pass

    def close(self):
        pass

class LaneEditorView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = DummyTool(self)

    def draw(self, screen):
        font = self.editor.font
        self.editor.layout.draw(screen, font, self.editor)

    def handle_keydown(self, ev):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if ev.key == pygame.K_UP:
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
            tag = self.lane_tag
            self.editor.walk_lane_tag(direction=True)
            self.editor.erase_drawfunc(tag)
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

    def get_pitchlane(self):
        for df in self.editor.doc.drawfuncs:
            if df.tag == self.editor.lane_tag:
                for g in self.editor.doc.graphs:
                    if g.lane == df.lane and isinstance(g, PitchLane):
                        return g

    def close(self):
        pass

class VideoRendererView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = DummyTool(self)
        self.s1 = editor.make_spectroscope(bus=0)
        self.s2 = editor.make_spectroscope(bus=1)
        self.frame = 0
        self.frame_step = (1.0 / 60)
        self.last_frame = (editor.sequence.end / self.frame_step)

    def draw(self, screen):
        font = self.editor.font
        text = font.render("HERE COMES A VIDEO RENDERING VIEW", True, (200,200,200))
        screen.blit(text, (0, 0))

            #    if not os.path.exists(self.pngs_record_path):
            #        os.mkdir(self.pngs_record_path)
            #    FPS = 60
            #    duration = self.transport.tempo.bar_to_time(self.doc.duration)
            #    self.calculate_brush_lanes()
            #    ix = 0
            #    while ix * (1.0 / FPS) < duration:
            #        self.clock.tick(self.FPS)
            #        t = ix * (1.0 / FPS)
            #        u = self.transport.tempo.time_to_bar(t)
            #        self.bar = (u // self.BARS_VISIBLE) * self.BARS_VISIBLE
            #        for ev in pygame.event.get():
            #            pass
            #        self.screen.fill((30, 30, 30))
            #        text = self.font.render(str(self.bar), True, (200, 200, 200))
            #        self.screen.blit(text, (0, 0))
            #        event_line = 15 + 15 + (self.brush_heights[self.doc] - 15) - self.scroll_y
            #        self.draw_grid(event_line)
            #        self.draw_events(event_line)
            #        self.draw_transport(t)
            #        pygame.image.save(self.screen, os.path.join(self.pngs_record_path, f"{ix}.png"))
            #        pygame.display.flip()
            #        ix += 1

    def handle_keydown(self, ev):
        pass

    def close(self):
        pass

class DummyTool:
    def __init__(self, view):
        self.view = view

    def draw(self, screen):
        pos = pygame.mouse.get_pos()
        text = self.view.editor.font.render("DUMMY", True, (200,200,200))
        screen.blit(text, pos)

    def handle_mousebuttondown(self, ev):
        pass

    def handle_mousebuttonup(self, ev):
        pass

    def handle_mousemotion(self, ev):
        pass

class Editor:
    SCREEN_WIDTH = 1200
    SCREEN_HEIGHT = 600
    FPS = 30

    MARGIN = 200
    BARS_VISIBLE = 4

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((self.SCREEN_WIDTH, self.SCREEN_HEIGHT))
        pygame.display.set_caption("oscillseq")
        self.clock = pygame.time.Clock()

        self.doc = Document(
            brushes = [],
            duration = 1,
            labels = {},
            graphs = [
            ],
            drawfuncs = [
                DrawFunc(0, "string", "tempo", {"value": "value"}),
            ],
            cells = [
            ],
            connections = set([
            ]),
        )

        if len(sys.argv) > 1:
            self.filename = sys.argv[1]
        else:
            self.filename = "unnamed.seq.json"
        if os.path.exists(self.filename):
            self.doc = Document.from_json_file(self.filename)
        self.pngs_record_path = os.path.abspath(os.path.splitext(self.filename)[0] + ".pngs")
        self.record_path = os.path.abspath(os.path.splitext(self.filename)[0] + ".wav")

        directory = os.path.dirname(os.path.abspath(self.filename))

        self.font = pygame.font.SysFont('Arial', 14)
        self.writing = False

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

        self.playback_range = (0, 2)
        self.playback_loop  = True

        # Sequence is built so it could be visualized.
        self.group_ids = {}
        if self.transport_status != 3:
            self.group_ids.clear()
        sb = SequenceBuilder(self.group_ids)
        #self.doc.construct(sb, 0, ())
        sb.gate(1 / 4, 'm', 0, {'note': 80})
        sb.gate(2 / 4, 'm', 0, {})
        sb.gate(3 / 4, 'm', 1, {'note': 79})
        sb.gate(4 / 4, 'm', 1, {})
        self.sequence = sb.build(2)

        self.transport_bar = TransportBar(self)

        self.toolbar = Toolbar(pygame.Rect(0, self.SCREEN_HEIGHT - 32, self.SCREEN_WIDTH, 32),
            [
                ("dummy", DummyView),
                ("lane editor", LaneEditorView),
                ("cell editor", NodeEditorView)
            ],
            (lambda view: self.change_view(view)),
            (lambda name, cls: isinstance(self.view, cls)))

        self.timeline_head = 0
        self.timeline_scroll = 0
        self.timeline_vertical_scroll = 0

        self.lane_tag = None
        self.layout = TrackLayout(self.doc, offset = 30)

        self.view = NodeEditorView(self)

    def refresh_layout(self):
        self.layout = TrackLayout(self.doc, offset = 30)

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
            dt = self.clock.tick(self.FPS) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    self.handle_keydown(ev)
                elif ev.type == pygame.TEXTINPUT and self.writing:
                    self.view.handle_textinput(ev)
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    if self.toolbar.handle_mousebuttondown(ev):
                        pass
                    elif self.transport_bar.handle_mousebuttondown(ev):
                        pass
                    else:
                        self.view.tool.handle_mousebuttondown(ev)
                elif ev.type == pygame.MOUSEBUTTONUP:
                    self.view.tool.handle_mousebuttonup(ev)
                elif ev.type == pygame.MOUSEMOTION:
                    self.view.tool.handle_mousemotion(ev)

            self.screen.fill((30, 30, 30))
            self.view.draw(self.screen)
            self.transport_bar.draw(self.screen, self.font)
            self.toolbar.draw(self.screen, self.font)
            self.view.tool.draw(self.screen)
            pygame.display.flip()

        self.view.close()
        self.set_offline()
        self.set_midi_off()
        pygame.quit()
        sys.exit()

    def handle_keydown(self, ev):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        ctrl_held = mods & pygame.KMOD_CTRL
        if mods & ctrl_held:
            if ev.key == pygame.K_1:
                self.change_view(DummyView)
            if ev.key == pygame.K_2:
                self.change_view(LaneEditorView)
            #elif ev.key == pygame.K_3:
            #elif ev.key == pygame.K_4:
            #elif ev.key == pygame.K_5:
            #elif ev.key == pygame.K_6:
            elif ev.key == pygame.K_7:
                self.change_view(NodeEditorView)
            elif ev.key == pygame.K_s:
                self.doc.to_json_file(self.filename)
                print("document saved!")
            elif ev.key == pygame.K_r:
                self.render_score()
            elif ev.key == pygame.K_v:
                self.change_view(VideoRendererView)
            elif ev.key == pygame.K_SPACE and not self.writing:
                self.set_online()
        elif ev.key == pygame.K_SPACE and not self.writing:
            self.toggle_play()
        else:
            self.view.handle_keydown(ev)

    def change_view(self, View):
        if not isinstance(self.view, View):
            if self.view is not None:
                self.view.close()
            self.view = View(self)

    def toggle_play(self):
        if self.transport_status < 2:
            self.set_fabric()
        elif self.get_playing() is None:
            if self.transport_status == 3:
                self.set_fabric()
            sequence = self.sequence
            self.set_playing(Sequencer(sequence, point=sequence.t(self.timeline_head), **self.playback_params(sequence)))
        else:
            self.set_fabric()
            for synth in self.clavier.values():
                synth.set(gate=0)
            self.clavier.clear()

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
            loop_point = sequence_end
            end_point = sequence.end
        else:
            loop_start = -1
            loop_point = -1
            end_point = sequence.end
        return {'loop_start': loop_start, 'loop_point': loop_point, 'end_point': end_point}

    def render_score(self):
        View = type(self.view)
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
        with score.at(sequence.t(2)):
            score.do_nothing()
        supriya.render(score, output_file_path=self.record_path)
        print("saved", self.record_path)

        self.set_online()
        self.change_view(View)

    def walk_lane_tag(self, direction):
        sequence = [df.tag for df in self.doc.drawfuncs]
        if self.lane_tag in sequence:
            i = sequence.index(self.lane_tag) + (2*direction - 1)
        else:
            i = [len(sequence)-1, 0][direction]
        if 0 <= i < len(sequence):
            self.lane_tag = sequence[i]
        else:
            self.lane_tag = None
        for df in list(self.doc.drawfuncs):
            if df.tag == "":
                self.doc.drawfuncs.remove(df)

    def shift_lane_tag(self, direction):
        lane = 0
        for i, df in enumerate(list(self.doc.drawfuncs)):
            if df.tag == self.lane_tag:
                self.walk_in_lane(i, direction)
                self.refresh_layout()
                return
            lane = df.lane + 1

    def shift_lanes(self, lane, shift=1):
        for df in self.doc.drawfuncs:
            if df.lane >= lane:
                df.lane += shift
        for df in self.doc.graphs:
            if df.lane >= lane:
                df.lane += shift

    def erase_lane(self, lane):
        if 0 == sum(1 for f in self.doc.drawfuncs if f.lane == lane):
            for graph in list(self.doc.graphs):
                if graph.lane == lane:
                    self.doc.graphs.remove(graph)
                elif graph.lane > lane:
                    graph.lane -= 1
            for df in self.doc.drawfuncs:
                if df.lane > lane:
                    df.lane -= 1

    def walk_in_lane(self, i, direction):
        x = self.doc.drawfuncs[i]
        oldlane = x.lane
        j = i + 2*direction - 1
        if 0 <= j < len(self.doc.drawfuncs):
            y = self.doc.drawfuncs[j]
            if x.lane == y.lane:
                self.doc.drawfuncs[i] = y
                self.doc.drawfuncs[j] = x
            elif x.lane == y.lane - 1 or x.lane == y.lane + 1:
                if y.lane in [g.lane for g in self.doc.graphs]:
                    lane = x.lane
                    x.lane = y.lane
                    self.erase_lane(lane)
                elif x.lane in [g.lane for g in self.doc.graphs]:
                    df = self.doc.drawfuncs[i]
                    lane = df.lane + 1*direction
                    self.shift_lanes(lane, 1)
                    df.lane = lane
                    self.doc.drawfuncs.sort(key=lambda df: df.lane)
                else:
                    x.lane, y.lane = y.lane, x.lane
                    self.doc.drawfuncs.sort(key=lambda df: df.lane)
            else:
                x.lane += 2*direction - 1
        elif direction:
            x.lane += 1
        else:
            lane = x.lane + 1*direction
            self.shift_lanes(lane, 1)
            x.lane = lane
            self.doc.drawfuncs.sort(key=lambda df: df.lane)
        if oldlane not in [g.lane for g in self.doc.graphs]:
            self.erase_lane(oldlane)
        if oldlane+1 not in [g.lane for g in self.doc.graphs]:
            self.erase_lane(oldlane+1)

    def erase_drawfunc(self, tag):
        for df in list(self.doc.drawfuncs):
            if df.tag == tag:
                self.doc.drawfuncs.remove(df)
                self.erase_lane(df.lane)


class Toolbar:
    def __init__(self, rect, items, action, selected, button_width=32*3):
        self.rect = rect
        self.items = items
        self.action = action
        self.selected = selected
        self.button_width = button_width

    def draw(self, screen, font):
        pygame.draw.rect(screen, (60, 60, 60), self.rect, 0, 0)
        for i, (name, obj) in enumerate(self.items):
            rect = pygame.Rect(self.rect.x + i*self.button_width, self.rect.y, self.button_width, self.rect.height)
            if self.selected(name, obj):
                pygame.draw.rect(screen, (20, 20, 20), rect, 0, 0)
            pygame.draw.rect(screen, (200, 200, 200), rect, 1, 0)
            text = font.render(name, True, (200, 200, 200))
            screen.blit(text, (rect.centerx - text.get_width()/2, rect.centery - text.get_height()/2))

    def handle_mousebuttondown(self, ev):
        for i, (name, obj) in enumerate(self.items):
            rect = pygame.Rect(self.rect.x + i*self.button_width, self.rect.y, self.button_width, self.rect.height)
            if rect.collidepoint(ev.pos):
                self.action(obj)
                return True
        return False

class TransportBar:
    def __init__(self, editor):
        self.editor = editor
        self.rect = pygame.Rect(0, 0, editor.SCREEN_WIDTH, 15)
        self.to_online = pygame.Rect(0, 0, 15, 15)
        self.to_fabric = pygame.Rect(15, 0, 15, 15)
        self.to_play   = pygame.Rect(30, 0, 15, 15)
        self.to_midi   = pygame.Rect(45, 0, 15*4, 15)
        self.to_loop   = pygame.Rect(105, 0, 15*4, 15)

    def draw(self, screen, font):
        pygame.draw.rect(screen, (60, 60, 60), self.rect, 0, 0)

        c = (10, 10, 155) if self.editor.transport_status == 1 else (100,100,100)
        pygame.draw.rect(screen, c, self.to_online, 0, 0)
        centerx, centery = self.to_online.centerx, self.to_online.centery
        half_width  = 6 / 2
        half_height = 6 / 2
        top = (centerx, centery - half_height)
        rig = (centerx + half_width, centery)
        bot = (centerx, centery + half_height)
        lef = (centerx - half_width, centery)
        pygame.draw.line(screen, (200, 200, 200), top, bot)
        pygame.draw.line(screen, (200, 200, 200), lef, bot)
        pygame.draw.line(screen, (200, 200, 200), bot, rig)

        c = (10, 155, 10) if self.editor.transport_status >= 2 else (100,100,100)
        pygame.draw.rect(screen, c, self.to_fabric, 0, 0)
        centerx, centery = self.to_fabric.centerx, self.to_fabric.centery
        half_width  = 6 / 2
        half_height = 6 / 2
        top = (centerx, centery - half_height)
        rig = (centerx + half_width, centery)
        bot = (centerx, centery + half_height)
        lef = (centerx - half_width, centery)
        pygame.draw.line(screen, (200, 200, 200), top, bot)
        pygame.draw.line(screen, (200, 200, 200), lef, top)
        pygame.draw.line(screen, (200, 200, 200), top, rig)

        SCREEN_WIDTH = screen.get_width()
        w = (SCREEN_WIDTH - editor.MARGIN) / editor.BARS_VISIBLE
        mg = []
        for i in range(editor.BARS_VISIBLE + 1):
            x = i * w + editor.MARGIN
            if (i + editor.timeline_scroll) == editor.timeline_head:
                pygame.draw.line(screen, (0, 255, 255), (x, self.rect.top), (x, self.rect.bottom), 2)
            else:
                pygame.draw.line(screen, (200, 200, 200), (x, self.rect.top), (x, self.rect.bottom))
            text = font.render(str(i + editor.timeline_scroll), True, (200, 200, 200))
            screen.blit(text, (x + 2, self.rect.top))
            mg.append(text.get_width())

        if editor.playback_range is not None:
            i, j = editor.playback_range
            half_width  = 6 / 2
            half_height = 6 / 2
            if editor.timeline_scroll <= i < editor.timeline_scroll + editor.BARS_VISIBLE:
                centerx = (i - editor.timeline_scroll) * w + editor.MARGIN + 6 + mg[i - editor.timeline_scroll]
                centery = self.rect.centery
                top = (centerx, centery - half_height)
                rig = (centerx + half_width, centery)
                bot = (centerx, centery + half_height)
                lef = (centerx - half_width, centery)
                pygame.draw.polygon(screen, (200, 200, 200), [top, rig, bot])

            if editor.timeline_scroll < j <= editor.timeline_scroll + editor.BARS_VISIBLE:
                centerx = (j - editor.timeline_scroll) * w + editor.MARGIN - 6
                centery = self.rect.centery
                top = (centerx, centery - half_height)
                rig = (centerx + half_width, centery)
                bot = (centerx, centery + half_height)
                lef = (centerx - half_width, centery)
                pygame.draw.polygon(screen, (200, 200, 200), [top, bot, lef])

        pygame.draw.rect(screen, (200, 200, 200), self.to_play, 1, 0)
        if (t := self.editor.get_playing()) is not None:
            pygame.draw.rect(screen, (200, 200, 200), self.to_play.inflate((-10, -10)), 0, 0)
            x = (t - editor.timeline_scroll) * w + editor.MARGIN
            if editor.MARGIN <= x <= SCREEN_WIDTH:
                pygame.draw.line(screen, (255, 0, 0), (x, self.rect.top), (x, self.rect.bottom))
        else:
            centerx, centery = self.to_play.centerx, self.to_play.centery
            half_width  = 6 / 2
            half_height = 6 / 2
            points = [
                (centerx, centery - half_height),  # top
                (centerx + half_width, centery),   # right
                (centerx, centery + half_height),  # bottom
            ]
            pygame.draw.polygon(screen, (200, 200, 200), points)

        midi_off_on = ["midi=off", "midi=on"][self.editor.midi_status]
        pygame.draw.rect(screen, (200, 200, 200), self.to_midi, 1, 0)
        text = font.render(midi_off_on, True, (200, 200, 200))
        screen.blit(text, (self.to_midi.centerx - text.get_width()/2, self.to_midi.centery - text.get_height()/2))

        loop_off_on = ["loop=off", "loop=on"][self.editor.playback_loop]
        pygame.draw.rect(screen, (200, 200, 200), self.to_loop, 1, 0)
        text = font.render(loop_off_on, True, (200, 200, 200))
        screen.blit(text, (self.to_loop.centerx - text.get_width()/2, self.to_loop.centery - text.get_height()/2))

    def handle_mousebuttondown(self, ev):
        if ev.button == 3:
            if self.to_online.collidepoint(ev.pos) or self.to_fabric.collidepoint(ev.pos) or self.to_play.collidepoint(ev.pos):
                self.editor.view.tool = ContextMenu(self.editor.view.tool,
                    np.array(ev.pos),
                    [("record to wav", self.editor.render_score)])
                return True
        if self.to_online.collidepoint(ev.pos):
            self.editor.set_online()
            return True
        if self.to_fabric.collidepoint(ev.pos):
            self.editor.set_fabric()
            return True
        if self.to_play.collidepoint(ev.pos):
            if self.editor.transport_status <= 1:
                self.editor.set_fabric()
            self.editor.toggle_play()
            return True
        if self.to_midi.collidepoint(ev.pos):
            self.editor.toggle_midi()
            return True
        if self.to_loop.collidepoint(ev.pos):
            self.editor.playback_loop = not self.editor.playback_loop
            if (status := self.editor.get_playing()) is not None:
                self.editor.set_fabric()
                sequence = self.editor.sequence
                self.editor.set_playing(Sequencer(sequence, point=sequence.t(status), **self.editor.playback_params(sequence)))
            return True
        return False

class TrackLayout:
    LANE_HEIGHT = 16
    STAVE_HEIGHT = 3 * 12

    def __init__(self, doc, offset=0):
        self.doc = doc
        self.offset = offset
        max_lanes = 1 + max(
           [g.lane for g in self.doc.graphs]
           + [df.lane for df in self.doc.drawfuncs], default=0)
        heights = [self.LANE_HEIGHT] * max_lanes
        graphs = [None] * max_lanes
        for g in self.doc.graphs:
            heights[g.lane] = (g.staves + g.margin_above + g.margin_below) * self.STAVE_HEIGHT
            graphs[g.lane] = g
        drawfuncs = [[] for _ in range(max_lanes)]
        for df in self.doc.drawfuncs:
            drawfuncs[df.lane].append(df)
        lanes = []
        for i, h in enumerate(heights):
            lanes.append((offset, h, drawfuncs[i], graphs[i]))
            offset += h
        self.lanes = lanes

    def draw(self, screen, font, editor):
        SCREEN_WIDTH = screen.get_width()
        SCREEN_HEIGHT = screen.get_height()
        w = (SCREEN_WIDTH - editor.MARGIN) / editor.BARS_VISIBLE
        pygame.draw.line(screen, (40, 40, 40), (0, self.offset), (SCREEN_WIDTH, self.offset))
        for y, height, drawfuncs, graph in self.lanes:
            for k, df in enumerate(drawfuncs):
                # TODO: recreate validation logic
#                ok = validate(df, self.doc.descriptors)
                ok = True
                text = font.render(df.tag, True, [(255, 100, 100), (200, 200, 200)][ok])
                screen.blit(text, (10, y + 15 * k))

                if df.tag == editor.lane_tag:
                    center_x = editor.MARGIN - 15
                    center_y = y + 15 * k + 8
                    draw_diamond(screen, (0, 255, 0), (center_x, center_y), (4, 4))

            if isinstance(graph, PitchLane):
                y += graph.margin_above * self.STAVE_HEIGHT
                for _ in range(graph.staves):
                    for p in range(2, 12, 2):
                        pygame.draw.line(screen, (70, 70, 70), (editor.MARGIN, y + p*(self.STAVE_HEIGHT / 12)), (SCREEN_WIDTH, y + p*(self.STAVE_HEIGHT / 12)))
                    y += self.STAVE_HEIGHT
                y += graph.margin_below * self.STAVE_HEIGHT
            else:
                y += height
            pygame.draw.line(screen, (40, 40, 40), (0, y), (SCREEN_WIDTH, y))

        for i in range(editor.BARS_VISIBLE + 1):
            x = i * w + editor.MARGIN
            pygame.draw.line(screen, (70, 70, 70), (x, 0), (x, SCREEN_HEIGHT))

        if editor.timeline_scroll <= self.doc.duration <= editor.timeline_scroll + editor.BARS_VISIBLE:
            x = (self.doc.duration - editor.timeline_scroll) * w + editor.MARGIN
            pygame.draw.line(screen, (70, 255, 70), (x, 0), (x, SCREEN_HEIGHT), 3)

        # transport line
        if (t := editor.get_playing()) is not None:
            x = (t - editor.timeline_scroll) * w + editor.MARGIN
            if editor.MARGIN <= x <= SCREEN_WIDTH:
                pygame.draw.line(screen, (255, 0, 0), (x, 0), (x, SCREEN_HEIGHT))
            
# "bool", "unipolar", "number", "pitch", "db", "dur"

drawfunc_avail_for = {
    "string": ["control"],
    "band":   ["control"],
    "note":   ["control", "oneshot", "gate"],
    "rhythm": ["oneshot", "gate"],
}
drawfunc_table = {
    "string": [("value", ["bool", "number", "pitch", "db"])],
    "band": [("value", ["unipolar", "db"])],
    "note": [("pitch", ["pitch"])],
    "rhythm": [],
}

def validate(df, descs):
    desc = descs[df.tag]
    if desc.kind not in drawfunc_avail_for[df.drawfunc]:
        return False
    return all(df.params[name] in avail(desc.spec, ty) for name, ty in drawfunc_table[df.drawfunc])

def avail(spec, ty):
    spec = [("n/a", "n/a")] + spec
    if len(ty) == 0:
        return [name for name,t in spec]
    return [name for name,t in spec if t in ty]

def autoselect(spec, ty):
    spec = avail(spec, ty)
    return spec[0] if len(spec) > 0 else "n/a"

def rebuild_labels(brushes):
    labels = {}
    def visit(brush):
        labels[brush.label] = brush
        if isinstance(brush, Clip):
            for e in brush.brushes:
                visit(e.brush)
    for e in brushes:
        visit(e.brush)
    return labels

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

class SequencerEditor:
    SCREEN_WIDTH = 1200
    SCREEN_HEIGHT = 600
    FPS = 30
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

    def calculate_brush_lanes(self):
        self.clip_lanes = {}
        self.brush_heights = {}
        def process(brush):
            if brush in self.brush_heights:
                return
            if isinstance(brush, Clip):
                process_clip(brush)
            elif isinstance(brush, Clap):
                self.brush_heights[brush] = 15 + 3 * (brush.tree.depth) + 20
            else:
                self.brush_heights[brush] = 15
        def process_clip(clip):
            if clip in self.clip_lanes:
                return
            clip.brushes.sort(key=lambda e: e.shift)#, e.brush.duration))
            heap = []
            self.clip_lanes[clip] = assignments, lane_offsets, lane_heights = [], [], []
            for e in clip.brushes:
                process(e.brush)
                height = self.brush_heights[e.brush]
                duration = max(1, e.brush.duration)
                while heap and heap[0][0] < e.shift:
                    _, row = heapq.heappop(heap)
                    heapq.heappush(heap, (e.shift, row))
                if heap and heap[0][0] <= e.shift:
                    end_time, row = heapq.heappop(heap)
                    lane_heights[row] = max(lane_heights[row], height)
                else:
                    row = len(lane_heights)
                    lane_heights.append(height)
                assignments.append(row)
                heapq.heappush(heap, (e.shift + duration, row))
            offset = 4
            for height in lane_heights:
                lane_offsets.append(offset)
                offset += height + 4
            self.brush_heights[clip] = offset + 15
        process_clip(self.doc)

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((self.SCREEN_WIDTH, self.SCREEN_HEIGHT))
        pygame.display.set_caption("OSC Sequencer Editor")
        self.clock = pygame.time.Clock()

        self.scroll_y = 0
        self.bar = 0           # Shifts the view
        self.bar_head = 0      # For selecting items from the timeline.
        self.bar_tail = 0
        self.sel = []          # Selection from the brush graph.
        self.reference = None  # Reference to brush for moving values around.
        self.tag_name = None   # For modifying and inserting tags.

        self.te_tag_name = ""              # tag editor destination name
        self.te_desc = Desc("control", []) # tag editor descriptor
        self.te_past = {}                  # map that tells where values go to.
        self.te_future = {}                # map that tells where values came from.
        self.tag_i = 0                     # tag editor index
        self.tag_k = 0                     # tag editor row index
        self.accidental = None             # note editor accidental
        self.note_tool = 'draw'            # note editor current tool
        self.note_tail = None              # note editor tail selection (when dragging).
        self.pattern = "n"                 # note editor after-split pattern.

        self.doc = Document(
            brushes = [],
            duration = 1,
            labels = {},
            descriptors = {
                "tempo": Desc(kind="control", spec=[("value", "number")]),
            #    "arp": Desc(kind="gate", spec=[]),
            #    "saw": Desc(kind="gate", spec=[("note","pitch"), ("mystery", "number")]),
            #    "drum": Desc(kind="oneshot", spec=[]),
            #    "kick": Desc(kind="oneshot", spec=[]),
            #    "foobar": Desc(kind="gate", spec=[("note","pitch")]),
            #    "sawnote": Desc(kind="control", spec=[("value", "pitch")]),
            },
            graphs = [
            #    PitchLane(lane=1, staves=1, margin_above=1, margin_below=1),
            #    PitchLane(lane=4, staves=2, margin_above=1, margin_below=1),
            ],
            drawfuncs = [
                DrawFunc(0, "string", "tempo", {"value": "value"}),
            #    DrawFunc(1, "rhythm", "arp", {}),
            #    DrawFunc(1, "note", "saw", {"pitch":"note"}),
            #    DrawFunc(2, "rhythm", "drum", {}),
            #    DrawFunc(3, "rhythm", "kick", {}),
            #    DrawFunc(4, "note", "foobar", {"pitch":"note"}),
            #    DrawFunc(4, "note", "sawnote", {"pitch":"value"}),
            ],
        )

        #clip0 = self.doc.intro(Clip("", 2, [
        #    Entity(0, self.doc.intro(ControlPoint("", tag="tempo", transition=False, value=70))),
        #    Entity(1, self.doc.intro(ControlPoint("", tag="tempo", transition=True, value=90))),
        #    Entity(2, self.doc.intro(ControlPoint("", tag="tempo", transition=True, value=30))),
        #    Entity(0, self.doc.intro(ControlPoint("", tag="sawnote", transition=False, value=music.Pitch(35)))),
        #    Entity(1, self.doc.intro(ControlPoint("", tag="sawnote", transition=True, value=music.Pitch(45)))),
        #    Entity(2, self.doc.intro(ControlPoint("", tag="sawnote", transition=True, value=music.Pitch(32)))),
        #    Entity(0, self.doc.intro(Clap("", 1, measure.Tree.from_string("2nn"), {'drum': ConstGen([{}])}))),
        #    Entity(0, self.doc.intro(Clap("", 1, measure.Tree.from_string("22r2nn2rn"), {'kick': ConstGen([{}])}))),
        #    Entity(0, self.doc.intro(Clap("", 1, measure.Tree.from_string("22nn2n2nn"), {
        #        'saw': PolyGen([
        #            [{"note": music.Pitch(28)}, {"note": music.Pitch(42)}],
        #            [{"note": music.Pitch(30)}],
        #            [{"note": music.Pitch(33)}],
        #            [{"note": music.Pitch(35)}],
        #            [{"note": music.Pitch(25)}],
        #        ]),
        #        'foobar': PolyGen([
        #            [{"note": music.Pitch(25)}],
        #            [{"note": music.Pitch(27)}],
        #            [{"note": music.Pitch(20)}],
        #            [{"note": music.Pitch(21)}],
        #        ]),
        #    }))),
        #]))

        #self.doc.brushes = [
        #    Entity(0, clip0),
        #    Entity(4, clip0),
        #    Entity(8, clip0),
        #    Entity(3, self.doc.intro(ControlPoint("", tag="tempo", transition=True, value=50))),
        #    Entity(3, self.doc.intro(Clap("", 1, measure.Tree.from_string("22nn2nn"), {'drum': ConstGen([{}])}))),
        #    Entity(6, self.doc.intro(Clap("", 1, measure.Tree.from_string("222nn2nn22nn2nn"), {'drum': ConstGen([{}])}))),
        #    Entity(8, self.doc.intro(Clap("", 1, measure.Tree.from_string("3nnn"), {'drum': ConstGen([{}])}))),
        #]

        if len(sys.argv) > 1:
            self.filename = sys.argv[1]
            if os.path.exists(self.filename):
                self.doc = Document.from_json_file(self.filename)
        else:
            self.filename = "demo.seq.json"
        self.pngs_record_path = os.path.abspath(os.path.splitext(self.filename)[0] + ".pngs")
        self.record_path = os.path.abspath(os.path.splitext(self.filename)[0] + ".wav")

        # Editor modes
        self.mode = 1
        self.font = pygame.font.SysFont('Arial', 14)

        # Row editor
        self.rw_head = 0
        self.rw_tail = 0

        # Clap editor
        self.p_index = -1
        self.p_head = 0
        self.p_tail = 0
        self.p_head0 = 0
        self.p_tail0 = 0

        self.p_selection = [0]

        # Event editor
        self.e_patch = -1
        self.e_index = 0
        self.e_focus = -1

        self.e_v_focus = 0

        self.sequencer = osc_control.Sequencer()
        self.doc.construct(self.sequencer, 0, ())

        self.transport = osc_control.TransportThread(
            *self.sequencer.build()
        )
        self.transport.start()

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(self.FPS) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    self.handle_key(ev)
                elif ev.type == pygame.TEXTINPUT:
                    self.handle_textinput(ev.text)
                elif ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                    if self.mode == 6:
                        self.handle_note_editor_mouse(ev)

            self.screen.fill((30, 30, 30))
            text = self.font.render(str(self.bar), True, (200, 200, 200))
            self.screen.blit(text, (0, 0))

            self.calculate_brush_lanes()
            event_line = 15 + 15 + (self.brush_heights[self.doc] - 15) - self.scroll_y

            self.draw_grid(event_line)
            self.draw_events(event_line)
            self.draw_transport()
            if self.mode == 1:
                self.draw_brush_editor()
            if self.mode == 2:
                self.draw_lane_editor()
            elif self.mode == 3:
                self.draw_tag_editor()
            elif self.mode == 4:
                self.draw_clap_editor()
            elif self.mode == 5:
                self.draw_event_editor()
            elif self.mode == 6:
                self.draw_note_editor()

            pygame.display.flip()

        self.transport.shutdown()
        pygame.quit()
        sys.exit()

    def get_brush(self, selection=None):
        if selection is None:
            selection = self.sel
        if len(selection) > 0:
            return selection[-1].brush
        else:
            return self.doc

    # control commands
    def erase_brush(self, target):
        def do_erase():
            for brush in [self.doc] + list(self.doc.labels.values()):
                if isinstance(brush, (Clip, Document)):
                    for e in list(brush.brushes):
                        if e.brush == target:
                            brush.brushes.remove(e)
            self.doc.labels.pop(target.label)
        for i, e in enumerate(self.sel):
            if e.brush == target:
                self.sel[i:] = []
                clip = self.get_brush()
                index = clip.brushes.index(e)
                do_erase()
                if index < len(clip.brushes):
                    self.sel.append(clip.brushes[index])
                break
        else:
            do_erase()

    def erase_selection(self):
        brushlist = dfs_list(self.doc.brushes)
        selection = self.sel
        if selection:
            if len(selection) > 1:
                brushes = selection[-2].brush.brushes
            else:
                brushes = self.doc.brushes
            i = min(brushes.index(selection[-1]), len(brushes)-2)
            brushes.remove(selection[-1])
            if i >= 0:
                selection[-1] = brushes[i]
            else:
                selection.pop(-1)
            self.doc.labels = rebuild_labels(self.doc.brushes)
        else:
            self.doc.brushes = []
            self.doc.labels = {}

    def handle_key(self, ev):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        ctrl_held = mods & pygame.KMOD_CTRL
        if mods & ctrl_held:
            if ev.key == pygame.K_1:
                self.mode = 1
            elif ev.key == pygame.K_2:
                self.mode = 2
            elif ev.key == pygame.K_3:
                self.mode = 3
            elif ev.key == pygame.K_4:
                self.mode = 4
            elif ev.key == pygame.K_5:
                self.mode = 5
            elif ev.key == pygame.K_6:
                self.mode = 6
            elif ev.key == pygame.K_7:
                self.mode = 7
            elif ev.key == pygame.K_s:
                self.doc.to_json_file(self.filename)
                print("document saved!")
            elif ev.key == pygame.K_PAGEUP:
                self.scroll_y -= self.SCREEN_HEIGHT / 4
                self.scroll_y = max(0, self.scroll_y)
            elif ev.key == pygame.K_PAGEDOWN:
                self.scroll_y += self.SCREEN_HEIGHT / 4
            elif ev.key == pygame.K_r:
                if not os.path.exists(self.pngs_record_path):
                    os.mkdir(self.pngs_record_path)
                FPS = 60
                duration = self.transport.tempo.bar_to_time(self.doc.duration)
                self.calculate_brush_lanes()
                ix = 0
                while ix * (1.0 / FPS) < duration:
                    self.clock.tick(self.FPS)
                    t = ix * (1.0 / FPS)
                    u = self.transport.tempo.time_to_bar(t)
                    self.bar = (u // self.BARS_VISIBLE) * self.BARS_VISIBLE
                    for ev in pygame.event.get():
                        pass
                    self.screen.fill((30, 30, 30))
                    text = self.font.render(str(self.bar), True, (200, 200, 200))
                    self.screen.blit(text, (0, 0))
                    event_line = 15 + 15 + (self.brush_heights[self.doc] - 15) - self.scroll_y
                    self.draw_grid(event_line)
                    self.draw_events(event_line)
                    self.draw_transport(t)
                    pygame.image.save(self.screen, os.path.join(self.pngs_record_path, f"{ix}.png"))
                    pygame.display.flip()
                    ix += 1
            elif ev.key == pygame.K_SPACE and self.mode in [1,4,5,6]:
                if self.transport.playing:
                    self.transport.cmd.put("stop")
                else:
                    self.transport.shift = 0
                    self.transport.record_path = self.record_path
                    self.transport.duration = self.transport.tempo.bar_to_time(self.doc.duration)
                    self.transport.cmd.put("play")
        elif ev.key == pygame.K_SPACE and self.mode in [1,4,5,6]:
            if self.transport.playing:
                self.transport.cmd.put("stop")
            else:
                self.transport.shift = self.transport.tempo.bar_to_time(self.bar_head)
                self.transport.record_path = None
                self.transport.duration = self.transport.tempo.bar_to_time(self.doc.duration)
                self.transport.cmd.put("play")
        elif self.mode == 1:
            self.handle_brush_editor_key(ev)
        elif self.mode == 2:
            self.handle_lane_editor_key(ev)
        elif self.mode == 3:
            self.handle_tag_editor_key(ev)
        elif self.mode == 4:
            self.handle_clap_editor_key(ev)
        elif self.mode == 5:
            self.handle_event_editor_key(ev)
        elif self.mode == 6:
            self.handle_note_editor_key(ev)
        self.sequencer = osc_control.Sequencer()
        self.doc.construct(self.sequencer, 0, ())
        self.transport.tempo, self.transport.events = self.sequencer.build()

    def handle_textinput(self, text):
        if self.mode == 3:
            value = self.get_tag_line()
            i = min(self.tag_i, len(value))
            value = value[:i] + text + value[i:]
            if text.isalpha() or text.isdigit() or text == '_':
                self.update_tag_line(i + len(text), value)
        if self.mode == 2:
            for df in self.doc.drawfuncs:
                if df.tag == self.tag_name:
                    self.change_drawfunc(df, text)

    def change_drawfunc(self, df, text):
        desc = self.doc.descriptors[df.tag]
        if text.isdigit():
            ix = int(text)-1
            dspec = drawfunc_table[df.drawfunc]
            if 0 <= ix < len(dspec):
                name, ty = dspec[ix]
                tags = avail(desc.spec, ty)
                if df.params[name] in tags:
                    jx = tags.index(df.params[name]) + 1
                    df.params[name] = tags[jx] if jx < len(tags) else tags[0]
                else:
                    df.params[name] = autoselect(desc.spec, ty)
        else:
            for drawfunc, dspec in drawfunc_table.items():
                if text == drawfunc[0]:
                    df.drawfunc = drawfunc
                    df.params = {name:autoselect(desc.spec, ty) for name, ty in dspec}

    def get_tag_line(self):
        lines = [self.te_tag_name or ""] + [x for x, _ in self.te_desc.spec]
        return lines[self.tag_k]

    def update_tag_line(self, offset, value):
        desc = self.te_desc
        if self.tag_k == 0:
        #    if value not in self.doc.descriptors:
        #        desc = self.doc.descriptors.pop(self.tag_name, Desc("control", []))
        #        found = False
        #        for row in self.doc.rows:
        #            if self.tag_name in [df.tag for df in row.drawfuncs]:
        #                ix = [df.tag for df in row.drawfuncs].index(self.tag_name)
        #                row.drawfuncs[ix].tag = value
        #                found = True
        #        if found == False:
        #            for row in reversed(self.doc.rows):
        #                if (row.staves == 0 and len(row.tags) == 0) or row.staves > 0:
        #                    row.drawfuncs.append(DrawFunc("string", value, {"value":"n/a"}))
        #                    found = True
        #                    break
        #        if found == False:
        #            self.doc.rows.append(Row([DrawFunc("string", value, {"value":"n/a"})], staves=0))
        #        self.doc.descriptors[value] = desc
            self.te_tag_name = value
            self.tag_i = offset
        else:
            was, t = desc.spec[self.tag_k - 1]
            if value not in [name for name, _ in desc.spec]:
                desc.spec[self.tag_k - 1] = value, t
                self.tag_i = offset
                past = self.te_future.pop(was, was)
                if past is not None:
                    self.te_past[past] = value
                self.te_future[value] = past

    def draw_descriptor_table(self):
        y = 15 + 15
        rect = pygame.Rect(self.SCREEN_WIDTH - self.MARGIN, 0, self.MARGIN, self.SCREEN_HEIGHT)
        pygame.draw.rect(self.screen, (30, 30, 30), rect, 0)
        pygame.draw.rect(self.screen, (100, 255, 100), rect, 1)

        for tag in sorted(list(self.doc.descriptors)):
            if tag == self.tag_name:
                center_x = self.SCREEN_WIDTH - self.MARGIN + 5
                center_y = y + 8
                pygame.draw.line(self.screen, (0, 128, 0), (center_x, center_y), (self.SCREEN_WIDTH/2, self.SCREEN_HEIGHT/2))
                self.draw_diamond((0, 255, 0), (center_x, center_y), (4, 4))
            text = self.font.render(tag, True, (200, 200, 200))
            self.screen.blit(text, (self.SCREEN_WIDTH - self.MARGIN + 10, y))
            y += 15

    def draw_grid(self, event_line):
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE

        if not self.sel:
            text = self.font.render("document selected", True, (0,255,0))
            self.screen.blit(text, (10, 15+15))

        self.screen.set_clip(pygame.Rect(self.MARGIN, 15 + 15, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT - 15 + 15))

        def draw_clip_contents(clip, shift, py):
            assignments, lane_offsets, lane_heights = self.clip_lanes[clip]
            for i, e in zip(assignments, clip.brushes):
                start = (shift + e.shift - self.bar)
                duration = e.brush.duration
                y = lane_offsets[i] + py
                height = self.brush_heights[e.brush]
                if duration == 0:
                    pygame.draw.circle(self.screen, (200, 200, 200), (start*w + self.MARGIN, y+7.5), 7.5, 0, True, False, False, True)
                else:
                    rect = pygame.Rect(start*w + self.MARGIN, y, duration*w, height)
                    pygame.draw.rect(self.screen, (200,200,200), rect, 1, 3)
                selected = 1*(self.sel != [] and self.sel[-1] == e)
                selected += 2*(e.brush == self.reference)
                name = "???"
                if isinstance(e.brush, Clip):
                    name = f"{e.brush.label}"
                if isinstance(e.brush, Clap):
                    name = f"{e.brush.label}"
                if isinstance(e.brush, ControlPoint):
                    name = f"{e.brush.tag} {' ~'[e.brush.transition]} {e.brush.value}"
                if isinstance(e.brush, Key):
                    name = f"key {e.brush.lanes} {e.brush.index} {music.major[e.brush.index]}"
                text = self.font.render(name, True, [(200, 200, 200), (0,255,0), (200, 0, 200), (200, 255, 100)][selected])
                self.screen.blit(text, (start*w + 10 + self.MARGIN, y))
                if isinstance(e.brush, Clip):
                    draw_clip_contents(e.brush, shift + e.shift, y + 15)
                if isinstance(e.brush, Clap):
                    leafs = []
                    def draw_tree(x, y, span, tree):
                        color = (200, 200, 200) #[(200, 200, 200), (255, 0, 255)][tree == s_tree]
                        if len(tree) == 0:
                            if tree.label == "n":
                                leafs.append((x, span))
                            text = self.font.render(tree.label, True, color)
                            w = span/2 - text.get_width() / 2
                            self.screen.blit(text, (x + w, y))
                        else:
                            w = span / len(tree)
                            rect = pygame.Rect(x + w/2, y, span - w, 1)
                            pygame.draw.rect(self.screen, color, rect)
                            for i, stree in enumerate(tree):
                                rect = pygame.Rect(x + i*w + w/2 - 1, y, 2, 3)
                                pygame.draw.rect(self.screen, color, rect)
                                draw_tree(x + i*w, y+3, w, stree)
                    span = duration*w
                    draw_tree(start*w+self.MARGIN, y + 15, span, e.brush.tree)
        draw_clip_contents(self.doc, 0, 15 + 15 - self.scroll_y)

        self.screen.set_clip(pygame.Rect(0, 15 + 15, self.SCREEN_WIDTH, self.SCREEN_HEIGHT - 15 + 15))

        y = event_line
        lanes = self.calculate_lanes(event_line)

    def draw_events(self, y):
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        self.screen.set_clip(pygame.Rect(self.MARGIN, 15 + 15, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT - 15 + 15))
        lanes = self.calculate_lanes(y)
        for y, height, drawfuncs, graph in lanes:
            for df in drawfuncs:
                if validate(df, self.doc.descriptors):
                    fn = "draw_drawfunc_" + df.drawfunc
                    getattr(self, fn)(y, height, df, graph)
        self.screen.set_clip(None)

    def draw_drawfunc_string(self, rowy, height, df, graph):
        desc = self.doc.descriptors[df.tag]
        tag = df.tag
        if desc.kind == "control" and df.params["value"] != "value": 
            return
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        rowy += height - 15
        bustable = self.sequencer.busevents.get(tag, [])
        # for ev in events:
        #     if isinstance(ev, BusEvent) and desc.kind == "control":
        #         if ev.patch is None:
        #             bustable.append((ev.index, ev.transition, ev.value))
        #         else:
        #             bars = [ev.index]
        #             patch = self.patches[ev.patch]
        #             offset, offset1 = self.get_offsets(ev.patch, ev.index)
        #             for k in patch.start_bars:
        #                 bustable.append((offset + k, ev.transition, ev.value))
        prev_index = -1
        prev_value = None
        for i, (index, transition, value) in enumerate(bustable):
            if transition and prev_value is not None:
                mp = (index + prev_index)/2
                if self.bar <= mp <= self.bar + self.BARS_VISIBLE:
                    pv = float(prev_value)
                    vv = float(value)
                    if pv < vv:
                        text = self.font.render("<", True, (200, 200, 200))
                        self.screen.blit(text, ((mp - self.bar)*w + self.MARGIN, rowy))
                    elif pv > vv:
                        text = self.font.render(">", True, (200, 200, 200))
                        self.screen.blit(text, ((mp - self.bar)*w + self.MARGIN, rowy))

            if self.bar <= index <= self.bar + self.BARS_VISIBLE:
                text = self.font.render(str(value), True, (200, 200, 200))
                self.screen.blit(text, ((index - self.bar)*w + self.MARGIN, rowy))
            prev_index = index
            prev_value = value

    def draw_drawfunc_band(self, rowy, height, df, graph):
        desc = self.doc.descriptors[df.tag]
        tag = df.tag
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        pass

    def draw_drawfunc_note(self, rowy, height, df, graph):
        desc = self.doc.descriptors[df.tag]
        tag = df.tag
        if graph is None:
            return
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        notable = {}
        bustable = self.sequencer.busevents.get(tag, [])

        colors = [(0,0,128), (0,0,255), (255,128,0), (255, 0, 0), (128,0,0)]

        graph_key_map = {graph: [(0, 0)]}
        self.doc.annotate(graph_key_map, 0)
        graph_key = graph_key_map[graph]
        graph_key.sort(key=lambda x: x[0])
        def get_accidentals(b):
            ix = bisect.bisect_right(graph_key, b, key=lambda z: z[0])
            return music.accidentals(graph_key[ix - 1][1])

        for shift, tag_, args in self.sequencer.oneshots:
            if tag == tag_:
                y = rowy + graph.margin_above * self.STAVE_HEIGHT
                pitch = args.get(df.params["pitch"], music.Pitch(33))
                acci = get_accidentals(shift)
                color = colors[pitch.accidental + 2]
                if pitch.accidental == acci[pitch.position % 7]:
                    color = (255,255,255)
                y += (40 - pitch.position) * self.STAVE_HEIGHT / 12
                if self.bar <= shift <= self.bar + self.BARS_VISIBLE:
                        center_x = (shift - self.bar)*w + self.MARGIN
                        center_y = y
                        half_width  = 2
                        half_height = 1.5
                        points = [
                            (center_x, center_y - half_height),  # top
                            (center_x + half_width, center_y),   # right
                            (center_x, center_y + half_height),  # bottom
                            (center_x - half_width, center_y),   # left
                        ]
                        pygame.draw.polygon(self.screen, color, points)

        for shift, tag_, group_id, args in self.sequencer.gates:
            if tag == tag_:
                offsets = [shift]
                offsets1 = [shift]
                y = rowy + graph.margin_above * self.STAVE_HEIGHT
                if group_id in notable:
                    prev_offsets, prev_y, pitch = notable[group_id]
                    pitch = args.get(df.params["pitch"], pitch)
                else:
                    pitch = args.get(df.params["pitch"], music.Pitch(33))
                acci = get_accidentals(shift)
                color = colors[pitch.accidental + 2]
                if pitch.accidental == acci[pitch.position % 7]:
                    color = (255,255,255)
                y += (40 - pitch.position) * self.STAVE_HEIGHT / 12
                if group_id in notable:
                    self.screen.set_clip(pygame.Rect(self.MARGIN, 0, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT))
                    prev_offsets, prev_y, pitch = notable[group_id]
                    for shift1, shift0 in zip(offsets, prev_offsets):
                        prev_x = (shift0 - self.bar)*w + self.MARGIN
                        now_x = (shift1 - self.bar)*w + self.MARGIN
                        pygame.draw.line(self.screen, color, (prev_x, prev_y), (now_x, prev_y), 3)
                        pygame.draw.line(self.screen, color, (now_x, prev_y), (now_x, y), 3)
                    self.screen.set_clip(pygame.Rect(self.MARGIN, 15 + 15, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT - 15 + 15))
                notable[group_id] = offsets, y, pitch
                #for shift in offsets:
                #    if self.bar <= shift <= self.bar + self.BARS_VISIBLE:
                #        center_x = (shift - self.bar)*w + self.MARGIN
                #        center_y = y
                #        half_width  = 2
                #        half_height = 1.5
                for shift0, shift1 in zip(offsets, offsets1):
                    shift = (shift0 + shift1)/2
                    if self.bar <= shift <= self.bar + self.BARS_VISIBLE:
                        center_x = (shift - self.bar)*w + self.MARGIN
                        center_y = y
                        half_width  = 2 + w*(shift1 - shift0)/2
                        half_height = 1.5
                        points = [
                            (center_x, center_y - half_height),  # top
                            (center_x + half_width, center_y),   # right
                            (center_x, center_y + half_height),  # bottom
                            (center_x - half_width, center_y),   # left
                        ]
                        pygame.draw.polygon(self.screen, (255, 255, 255), points)

        points = []
        for i, (index, transition, pitch) in enumerate(bustable):
            x = (index - self.bar)*w + self.MARGIN
            y = rowy + graph.margin_above * self.STAVE_HEIGHT
            y += (40 - pitch.position) * self.STAVE_HEIGHT / 12
            if not transition and len(points) > 0:
                points.append((x, points[-1][1]))
                points.append((x, y))
            else:
                points.append((x, y))
        if len(points) > 1:
            self.screen.set_clip(pygame.Rect(self.MARGIN, 0, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT))
            pygame.draw.lines(self.screen, (255, 255, 255), False, points)
            self.screen.set_clip(pygame.Rect(self.MARGIN, 15 + 15, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT - 15 + 15))
        for i, (index, transition, pitch) in enumerate(bustable):
            if not isinstance(pitch, music.Pitch):
                continue
            if self.bar <= index <= self.bar + self.BARS_VISIBLE:
                y = rowy + graph.margin_above * self.STAVE_HEIGHT
                center_x = (index - self.bar)*w + self.MARGIN
                center_y = y + (40 - pitch.position) * self.STAVE_HEIGHT / 12
                half_width  = 2
                half_height = 1.5
                points = [
                    (center_x, center_y - half_height),  # top
                    (center_x + half_width, center_y),   # right
                    (center_x, center_y + half_height),  # bottom
                    (center_x - half_width, center_y),   # left
                ]
                pygame.draw.polygon(self.screen, (255, 255, 255), points)

    def draw_drawfunc_rhythm(self, rowy, height, df, graph):
        desc = self.doc.descriptors[df.tag]
        tag = df.tag
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        notable = {}

        for shift, tag_, args in self.sequencer.oneshots:
            if tag == tag_:
                    if self.bar <= shift <= self.bar + self.BARS_VISIBLE:
                        center_x = (shift - self.bar)*w + self.MARGIN
                        center_y = rowy + 8
                        half_width  = 4
                        half_height = 8
                        points = [
                            (center_x, center_y - half_height),  # top
                            (center_x + half_width, center_y),   # right
                            (center_x, center_y + half_height),  # bottom
                            (center_x - half_width, center_y),   # left
                        ]
                        pygame.draw.polygon(self.screen, (255, 255, 255), points)
        for shift, tag_, group_id, args in self.sequencer.gates:
            y = rowy + 8
            if tag == tag_:
                offsets = [shift]
                offsets1 = [shift]
                if group_id in notable:
                    self.screen.set_clip(pygame.Rect(self.MARGIN, 0, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT))
                    prev_offsets, prev_y = notable[group_id]
                    for shift1, shift0 in zip(offsets, prev_offsets):
                        prev_x = (shift0 - self.bar)*w + self.MARGIN
                        now_x = (shift1 - self.bar)*w + self.MARGIN
                        pygame.draw.line(self.screen, (255,255,255), (prev_x, rowy+8), (now_x, rowy+8), 3)
                    self.screen.set_clip(pygame.Rect(self.MARGIN, 15 + 15, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT - 15 + 15))
                notable[group_id] = offsets, y
                for shift0, shift1 in zip(offsets, offsets1):
                    shift = (shift0 + shift1)/2
                    if self.bar <= shift <= self.bar + self.BARS_VISIBLE:
                        center_x = (shift - self.bar)*w + self.MARGIN
                        center_y = rowy + 8
                        half_width  = 4 + (shift1-shift0)/2
                        half_height = 8
                        points = [
                            (center_x, center_y - half_height),  # top
                            (center_x + half_width, center_y),   # right
                            (center_x, center_y + half_height),  # bottom
                            (center_x - half_width, center_y),   # left
                        ]
                        pygame.draw.polygon(self.screen, (255, 255, 255), points)

    def draw_brush_editor(self):
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        x = self.SCREEN_WIDTH/4
        y = self.SCREEN_HEIGHT/2

        self.screen.set_clip(pygame.Rect(self.MARGIN, 0, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT))
        bar_start = min(self.bar_head, self.bar_tail)
        bar_stop = max(self.bar_head, self.bar_tail)
        rect = pygame.Rect((bar_start - self.bar)*w + self.MARGIN, 30, (bar_stop-bar_start)*w, self.SCREEN_HEIGHT - 30)
        pygame.draw.rect(self.screen, (128,200,200), rect, 1)
        self.screen.set_clip(None)

        bx = (self.bar_head - self.bar)*w + self.MARGIN
        pygame.draw.line(self.screen, (0,255,255), (bx, 30), (bx, self.SCREEN_HEIGHT), 2)

        # rect = pygame.Rect(x, y, self.SCREEN_WIDTH/2, self.SCREEN_HEIGHT/2)
        # pygame.draw.rect(self.screen, (30, 30, 30), rect, False)
        # pygame.draw.rect(self.screen, (0, 0, 255), rect, True)

        # sel = self.sel

        # def draw_brushes(brushes, x, y, a):
        #     for e in brushes:
        #         shift = e.shift
        #         brush = e.brush
        #         active = min(2, a + 1*(sel[-1:] == [e]))
        #         color = [(200, 200, 200), (0, 255, 0),     (50, 155, 50),
        #                  (255, 0, 255), (100, 155, 100), (255, 55, 255)][active + 3*(self.reference == brush)]
        #         if isinstance(brush, Clip):
        #             text = self.font.render(f"clip {shift} {brush.duration} {brush.label}", True, color)
        #             self.screen.blit(text, (x, y))
        #             y += 15
        #             if e in sel:
        #                 y = draw_brushes(brush.brushes, x+5, y, active*2)
        #         if isinstance(brush, Clap):
        #             text = self.font.render(f"clap {shift} {brush.duration} {brush.tree}", True, color)
        #             self.screen.blit(text, (x, y))
        #             y += 15
        #         if isinstance(brush, ControlPoint):
        #             text = self.font.render(f"controlpoint {shift} {brush.tag} {' ~'[brush.transition]} {brush.value}", True, color)
        #             self.screen.blit(text, (x, y))
        #             y += 15
        #     return y

        # text = self.font.render(f"document {self.doc.duration}", True, (200, 200, 200))
        # self.screen.blit(text, (x + 5, y))
        # draw_brushes(self.doc.brushes, x + 10, y + 15, 2*(sel == None))

    def handle_brush_editor_key(self, ev):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if ev.key == pygame.K_PAGEUP:
            self.walk_tag_name(direction=False, from_descriptors=shift_held)
        elif ev.key == pygame.K_PAGEDOWN:
            self.walk_tag_name(direction=True, from_descriptors=shift_held)
        elif ev.key == pygame.K_q:
            self.reference = self.sel[-1].brush if self.sel else None
        elif ev.key == pygame.K_w:
            if self.reference:
                self.insert_brush(self.reference.duration, lambda duration: self.reference)
        elif ev.key == pygame.K_e:
            if self.sel:
                brush = self.sel[-1].brush
                brush = self.doc.intro(json_to_brush("", brush.to_json()))
                self.sel[-1].brush = brush
        elif ev.key == pygame.K_o:
            sel = self.sel
            if sel:
                sel[-1].shift = max(0, sel[-1].shift - 1)
            else:
                if all(e.shift > 0 for e in self.doc.brushes):
                    for e in self.doc.brushes:
                        e.shift -= 1
        elif ev.key == pygame.K_p:
            sel = self.sel
            if sel:
                sel[-1].shift = sel[-1].shift + 1
            else:
                for e in self.doc.brushes:
                    e.shift += 1
            a = adjust_boundaries(self.doc)
            self.bar_head -= a
            self.bar_tail -= a
            self.bar = min(self.bar_head, self.bar)
            self.bar = max(self.bar_head - self.BARS_VISIBLE + 1, self.bar)
        elif ev.key == pygame.K_t and shift_held:
            sel = self.sel
            if sel:
                brush = sel[-1].brush
                if isinstance(brush, Clip):
                    adjust_boundaries(brush, self.doc, True)
            else:
                adjust_boundaries(self.doc, self.doc, True)
        elif ev.key == pygame.K_LEFT:
            self.bar_head = max(0, self.bar_head - 1)
            if not shift_held:
                self.bar_tail = self.bar_head
            self.bar = min(self.bar_head, self.bar)
        elif ev.key == pygame.K_RIGHT:
            self.bar_head += 1
            if not shift_held:
                self.bar_tail = self.bar_head
            self.bar = max(self.bar_head - self.BARS_VISIBLE + 1, self.bar)
        elif ev.key == pygame.K_UP and shift_held:
            sel = self.sel
            if sel:
                clip = self.get_brush(sel[:-1])
                i = clip.brushes.index(sel[-1])
                if i > 0:
                    clip.brushes[i-1], clip.brushes[i] = clip.brushes[i], clip.brushes[i-1]
        elif ev.key == pygame.K_DOWN and shift_held:
            sel = self.sel
            if sel:
                clip = self.get_brush(sel[:-1])
                i = clip.brushes.index(sel[-1])
                if i+1 < len(clip.brushes):
                    clip.brushes[i+1], clip.brushes[i] = clip.brushes[i], clip.brushes[i+1]
        elif ev.key == pygame.K_UP:
            brushlist = dfs_list(self.doc.brushes)
            sel = self.sel
            if sel:
                ix = brushlist.index(sel) - 1
                self.sel = brushlist[ix] if ix >= 0 else []
            else:
                self.sel = brushlist[-1] if brushlist else []
        elif ev.key == pygame.K_DOWN:
            brushlist = dfs_list(self.doc.brushes)
            sel = self.sel
            if sel:
                ix = brushlist.index(sel) + 1
                self.sel = brushlist[ix] if ix < len(brushlist) else []
            else:
                self.sel = brushlist[0] if brushlist else []
        elif ev.key == pygame.K_a:
            self.insert_brush(1, lambda duration: (Clap("", duration, measure.Tree.from_string("n"), {})))
        elif ev.key == pygame.K_s:
            self.insert_brush(1, lambda duration: (Clip("", duration, [])))
        elif ev.key == pygame.K_c and self.tag_name in self.doc.descriptors:
            desc = self.doc.descriptors[self.tag_name]
            dspec = dict(desc.spec)
            if "value" in dspec and desc.kind == "control":
                ty = dspec["value"]
                v = music.Pitch(33) if ty == "pitch" else 0
                self.insert_brush(0, lambda duration: (ControlPoint("", tag=self.tag_name, transition=True, value=v)))
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
                a = adjust_boundaries(self.doc)
                self.bar_head -= a
                self.bar_tail -= a
                self.bar = min(self.bar_head, self.bar)
                self.bar = max(self.bar_head - self.BARS_VISIBLE + 1, self.bar)
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
 
    def insert_brush(self, min_duration, mkbrush):
        shift = min(self.bar_head, self.bar_tail)
        duration = max(self.bar_head, self.bar_tail) - shift
        duration = max(min_duration, duration)
        bobj = self.doc.intro(mkbrush(duration))
        self.doc.duration = max(self.doc.duration, shift + duration)
        brushlist = dfs_list(self.doc.brushes)
        sel = self.sel
        if sel:
            if isinstance(sel[-1].brush, Clip):
                brushes = sel[-1].brush.brushes
                i_point = len(brushes)
            elif len(sel) > 1:
                brushes = sel[-2].brush.brushes
                i_point = brushes.index(sel[-1])
                sel = sel[:-1]
            else:
                brushes = self.doc.brushes
                i_point = brushes.index(sel[-1])
                sel = []
            for e in sel:
                if bobj == e.brush:
                    return
                shift = shift - e.shift
        else:
            brushes = self.doc.brushes
            i_point = len(brushes)
            sel = []
        obj = Entity(shift, bobj)
        brushes.insert(i_point, obj)
        self.sel = sel + [obj]
        a = adjust_boundaries(self.doc)
        self.bar_head -= a
        self.bar_tail -= a
        self.bar = min(self.bar_head, self.bar)
        self.bar = max(self.bar_head - self.BARS_VISIBLE + 1, self.bar)

    def draw_lane_editor(self):
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        y = 15 + 15
        lanes = self.calculate_lanes(y)
        self.draw_descriptor_table()

        x = self.SCREEN_WIDTH/4
        y = self.SCREEN_HEIGHT/4
        rect = pygame.Rect(x, y, self.SCREEN_WIDTH/2, self.SCREEN_HEIGHT/2)
        pygame.draw.rect(self.screen, (30, 30, 30), rect, False)
        pygame.draw.rect(self.screen, (0, 255, 0), rect, True)

        py = y
        if self.tag_name is None:
            text = self.font.render("select descriptor with (shift) [pgup] [pgdown]", True, (200, 200, 200))
            self.screen.blit(text, (x, y))
        else:
            for df in self.doc.drawfuncs:
                if df.tag == self.tag_name:
                    break
            else:
                df = None
            if df is None:
                text = self.font.render("no lane for this descriptor, add one with [up] or [down]", True, (200, 200, 200))
                self.screen.blit(text, (x, y))
            else:
                desc = self.doc.descriptors.get(self.tag_name, Desc("", []))
                for drawfuncs in [["string", "band"], ["note"], ["rhythm"]]:
                    px = x + 10
                    for drawfunc in drawfuncs:
                        active = (drawfunc == df.drawfunc)
                        drawfunc = "[" + drawfunc[0] + "]" + drawfunc[1:]
                        text = self.font.render(drawfunc, True, [(200, 200, 200), (0, 255, 0)][active])
                        self.screen.blit(text, (px, py))
                        px += text.get_width() + 10
                    py += 15

                px = x + 10
                for i, (name, ty) in enumerate(drawfunc_table[df.drawfunc], 1):
                    tag = df.params[name]
                    ok = (tag in avail(desc.spec, ty))
                    text = self.font.render("[" + str(i) + "] " + name + "->" + tag, True, [(255, 128, 128), (200, 200, 200)][ok])
                    self.screen.blit(text, (px, py))
                    px += text.get_width() + 10

    def handle_lane_editor_key(self, ev):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if ev.key == pygame.K_PAGEUP:
            self.walk_tag_name(direction=False, from_descriptors=shift_held)
        elif ev.key == pygame.K_PAGEDOWN:
            self.walk_tag_name(direction=True, from_descriptors=shift_held)
        elif ev.key == pygame.K_UP:
            self.walk_lane(False)
        elif ev.key == pygame.K_DOWN:
            self.walk_lane(True)
        elif ev.key == pygame.K_DELETE:
            tag = self.tag_name
            if tag in self.doc.descriptors:
                self.walk_tag_name(direction=True, from_descriptors=shift_held)
                self.erase_drawfunc(tag)
        elif ev.key == pygame.K_PLUS:
            for df in self.doc.drawfuncs:
                if df.tag == self.tag_name:
                    for g in self.doc.graphs:
                        if g.lane == df.lane:
                            g.staves += 1
                            break
                    else:
                        self.doc.graphs.append(PitchLane(df.lane, 1, 0, 0))
                        self.doc.graphs.sort(key=lambda g: g.lane)

    def draw_tag_editor(self):
        y = 15 + 15
        #lanes = self.calculate_lanes(y)

        self.draw_descriptor_table()

        x = self.SCREEN_WIDTH/4
        y = self.SCREEN_HEIGHT/4
        rect = pygame.Rect(x, y, self.SCREEN_WIDTH/2, self.SCREEN_HEIGHT/2)
        pygame.draw.rect(self.screen, (30, 30, 30), rect, False)
        pygame.draw.rect(self.screen, (0, 255, 0), rect, True)

        desc = self.te_desc

        text = self.te_tag_name
        if self.tag_k == 0:
            text = text[:self.tag_i] + "|" + text[self.tag_i:]
        text = self.font.render(text, True, (200, 200, 200))
        self.screen.blit(text, (x + 10, y + 2))

        cc = [(200, 200, 200), (100, 255, 100)]
        p = x + 150
        for model in ["control", "oneshot", "gate"]:
            text = self.font.render(model, True, cc[desc.kind==model])
            self.screen.blit(text, (p, y + 2))
            p += 10 + text.get_width()

        y += 30
        for k, (attr, flavor) in enumerate(desc.spec, 1):
            if self.tag_k == k:
                attr = attr[:self.tag_i] + "|" + attr[self.tag_i:]
            text = self.font.render(attr, True, (200, 200, 200))
            self.screen.blit(text, (x + 10, y + 2))
            p = x + 150
            for model in ["bool", "unipolar", "number", "pitch", "db", "dur"]:
                text = self.font.render(model, True, cc[flavor==model])
                self.screen.blit(text, (p, y + 2))
                p += 10 + text.get_width()
            y += 15

        y += 30
        for name in sorted(self.te_past):
            toward = self.te_past[name]
            if toward is None:
                text = f"{name} being removed"
                text = self.font.render(text, True, (200, 200, 200))
                self.screen.blit(text, (x + 10, y + 2))
                y += 15
            elif name != toward:
                text = f"{name} being renamed to {toward}"
                text = self.font.render(text, True, (200, 200, 200))
                self.screen.blit(text, (x + 10, y + 2))
                y += 15

        old_desc = self.doc.descriptors.get(self.tag_name, Desc(None, []))
        types = dict(desc.spec)
        old_types = dict(old_desc.spec)

        for name in sorted(self.te_future):
            was = self.te_future[name]
            if was is None:
                text = f"{name} introduced"
                text = self.font.render(text, True, (200, 200, 200))
                self.screen.blit(text, (x + 10, y + 2))
                y += 15
            elif old_types[was] != types[name]:
                text = f"{name} changes type"
                text = self.font.render(text, True, (200, 200, 200))
                self.screen.blit(text, (x + 10, y + 2))
                y += 15

        if old_desc.kind is not None and desc.kind != old_desc.kind:
            text = f"{old_desc.kind} transforms to {desc.kind}"
            text = self.font.render(text, True, (200, 200, 200))
            self.screen.blit(text, (x + 10, y + 2))
            y += 15

        y += 15
        if self.te_tag_name != self.tag_name and self.te_tag_name != "" and self.tag_name != None and self.te_tag_name not in self.doc.descriptors:
            text = "[+] to copy"
            text = self.font.render(text, True, (200, 200, 200))
            self.screen.blit(text, (x + 10, y + 2))
            y += 15

        modified = False
        modified |= (self.tag_name != self.te_tag_name)
        modified |= (desc.kind != old_desc.kind)
        modified |= (desc.spec != old_desc.spec)
        if self.tag_name != None and self.te_tag_name != "" and modified:
            text = "shift+[ret] to move/commit"
            text = self.font.render(text, True, (200, 200, 200))
            self.screen.blit(text, (x + 10, y + 2))
            y += 15

        if self.tag_name != None:
            text = "[del] to remove"
            text = self.font.render(text, True, (200, 200, 200))
            self.screen.blit(text, (x + 10, y + 2))
            y += 15

    def handle_tag_editor_key(self, ev):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if ev.key == pygame.K_RETURN and shift_held:
            if self.te_tag_name != "":
                if self.tag_name is not None:
                    old_desc = self.doc.descriptors.pop(self.tag_name)
                else:
                    old_desc = None
                self.doc.descriptors[self.te_tag_name] = Desc(self.te_desc.kind, self.te_desc.spec.copy())
                for df in self.doc.drawfuncs:
                    if df.tag == self.tag_name:
                        df.tag = self.te_tag_name
                if old_desc is not None:
                    if self.te_desc.kind == "control" and self.old_desc != "control":
                        for brush in list(self.doc.labels.values()):
                            if isinstance(brush, ControlPoint) and brush.tag == self.tag_name:
                                self.erase_brush(brush)
                            if isinstance(brush, Clap):
                                brush.generators.pop(self.tag_name, None)
                    else:
                        od = dict(old_desc.spec)
                        nd = dict(self.te_desc.spec)
                        remapper = {}
                        for name, was in self.te_future.items():
                            if was is not None and od[was] == nd[name]:
                                remapper[was] = name
                        remap = lambda args: {remapper[name]: value for name, value in args.items() if name in remapper}
                        for brush in list(self.doc.labels.values()):
                            if isinstance(brush, Clap):
                                gen = brush.generators.pop(self.tag_name, None)
                                if isinstance(gen, ConstGen):
                                    gen.argslist = [remap(args) for args in gen.argslist]
                                    brush.generators[self.te_tag_name] = gen
                                if isinstance(gen, PolyGen):
                                    gen.argslists = [[remap(args) for args in argslist] for argslist in gen.argslists]
                                    brush.generators[self.te_tag_name] = gen
                self.tag_name = self.te_tag_name
                self.te_past = {}
                self.te_future = {name: name for name, _ in self.te_desc.spec}
        elif ev.key == pygame.K_PLUS:
            if self.te_tag_name not in self.doc.descriptors and all(name != "" for name, _ in self.te_desc.spec):
                self.doc.descriptors[self.te_tag_name] = Desc(self.te_desc.kind, self.te_desc.spec.copy())
                self.tag_name = self.te_tag_name
                self.te_past = {}
                self.te_future = {name: name for name, _ in self.te_desc.spec}
        elif ev.key == pygame.K_DELETE:
            if self.tag_name is not None:
                self.doc.descriptors.pop(self.tag_name)
                for df in list(self.doc.drawfuncs):
                    if df.tag == self.tag_name:
                        self.doc.drawfuncs.remove(df)
                for brush in list(self.doc.labels.values()):
                    if isinstance(brush, ControlPoint) and brush.tag == self.tag_name:
                        self.erase_brush(brush)
                    if isinstance(brush, Clap):
                        brush.generators.pop(self.tag_name, None)
                self.tag_name = None
                self.te_past = {}
                self.te_future = {name: None for name, _ in self.te_desc.spec}
        elif ev.key == pygame.K_BACKSPACE and self.tag_k >= 0:
            value = self.get_tag_line()
            i = max(0, self.tag_i - 1)
            value = value[:i] + value[self.tag_i:]
            self.update_tag_line(i, value)
        elif ev.key == pygame.K_TAB:
            desc = self.te_desc
            if self.tag_k == 0:
                ix = ["control", "oneshot", "gate"].index(desc.kind)
                desc.kind = ["oneshot", "gate", "control"][ix]
            else:
                attr, flavor = desc.spec[self.tag_k - 1]
                ix = ["bool", "unipolar", "number", "pitch", "db", "dur"].index(flavor)
                flavor = ["unipolar", "number", "pitch", "db", "dur", "bool"][ix]
                desc.spec[self.tag_k - 1] = attr, flavor
        #elif ev.key == pygame.K_PAGEUP and mods & pygame.KMOD_SHIFT:
        #    if self.tag_name in self.doc.descriptors:
        #        xs = iter(reversed(self.doc.rows))
        #        for xrow in xs:
        #            if self.tag_name in xrow.tags:
        #                break
        #        ix = xrow.tags.index(self.tag_name)
        #        if ix == 0:
        #            for row in xs:
        #                if (row.staves == 0 and len(row.tags) == 0) or row.staves > 0:
        #                    row.tags.append(self.tag_name)
        #                    xrow.tags.remove(self.tag_name)
        #                    break
        #        else:
        #            xrow.tags[ix], xrow.tags[ix-1] = xrow.tags[ix-1], xrow.tags[ix]
        #elif ev.key == pygame.K_PAGEDOWN and mods & pygame.KMOD_SHIFT:
        #    if self.tag_name in self.doc.descriptors:
        #        xs = iter(self.doc.rows)
        #        for xrow in xs:
        #            if self.tag_name in xrow.tags:
        #                break
        #        ix = xrow.tags.index(self.tag_name)
        #        if ix + 1 >= len(xrow.tags):
        #            for row in xs:
        #                if (row.staves == 0 and len(row.tags) == 0) or row.staves > 0:
        #                    row.tags.insert(0, self.tag_name)
        #                    xrow.tags.remove(self.tag_name)
        #                    break
        #        else:
        #            xrow.tags[ix], xrow.tags[ix+1] = xrow.tags[ix+1], xrow.tags[ix]
        elif ev.key == pygame.K_PAGEUP:
            self.walk_tag_name(direction=False, from_descriptors=shift_held)
        elif ev.key == pygame.K_PAGEDOWN:
            self.walk_tag_name(direction=True, from_descriptors=shift_held)
        elif ev.key == pygame.K_RETURN:
            spec = self.te_desc.spec
            if self.tag_k == 0 or spec[self.tag_k-1][0] != "":
                spec.insert(self.tag_k, ("", "number"))
                self.te_future[""] = None
                self.tag_k += 1
                self.tag_i = 0
        elif ev.key == pygame.K_UP and shift_held:
            spec = self.te_desc.spec
            if self.tag_k > 1:
                spec[self.tag_k-2], spec[self.tag_k-1] = spec[self.tag_k-1], spec[self.tag_k-2] 
                self.tag_k -= 1
        elif ev.key == pygame.K_DOWN and shift_held:
            spec = self.te_desc.spec
            if 0 < self.tag_k < len(spec):
                spec[self.tag_k], spec[self.tag_k-1] = spec[self.tag_k-1], spec[self.tag_k] 
                self.tag_k += 1
        elif ev.key == pygame.K_UP:
            if self.tag_k > 0 and self.get_tag_line() == "":
                self.te_desc.spec.pop(self.tag_k - 1)
                past = self.te_future.pop("")
                if past is not None:
                    self.te_past[past] = None
            if self.tag_k > 0:
                self.tag_k = self.tag_k - 1
        elif ev.key == pygame.K_DOWN:
            spec = self.te_desc.spec
            if self.tag_k > 0 and self.get_tag_line() == "":
                if self.tag_k < len(spec):
                    spec.pop(self.tag_k - 1)
                    past = self.te_future.pop("")
                    if past is not None:
                        self.te_past[past] = None
            elif self.tag_k < len(spec):
                self.tag_k = self.tag_k + 1
        elif ev.key == pygame.K_LEFT:
            self.tag_i = max(0, self.tag_i - 1)
        elif ev.key == pygame.K_RIGHT:
            self.tag_i = min(len(self.get_tag_line()), self.tag_i + 1)

    def draw_clap_editor(self):
        sel = self.sel
        if not sel or not isinstance(sel[-1].brush, Clap):
            text = self.font.render("select clap brush in mode=1 first", True, (255, 0, 0))
            x = self.SCREEN_WIDTH / 2 - text.get_width() / 2
            self.screen.blit(text, (x, self.SCREEN_HEIGHT/2))
            return None, None, 0
        clap = sel[-1].brush

        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        x2 = self.bar
        x3 = x2 + self.BARS_VISIBLE - 1
        y = 15 + 15
        self.screen.set_clip(pygame.Rect(self.MARGIN, 0, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT))

        s_tree = clap.tree
        s_tree = s_tree.access(self.p_selection[1:])

        leafs = []

        x = self.MARGIN
        y0 = self.SCREEN_HEIGHT / 4
        span = w*min(4, clap.duration)
        rect = pygame.Rect(x, y0, span, self.SCREEN_HEIGHT / 2)
        pygame.draw.rect(self.screen, (30,30,30), rect, 0, 5)
        pygame.draw.rect(self.screen, (255,255,255), rect, 1, 5)
        def draw_tree(x, y, span, tree):
            color = [(200, 200, 200), (255, 0, 255)][tree == s_tree]
            if len(tree) == 0:
                if tree.label == "n":
                    leafs.append((x, span))
                text = self.font.render(tree.label, True, color)
                w = span/2 - text.get_width() / 2
                self.screen.blit(text, (x + w, y))
            else:
                w = span / len(tree)
                rect = pygame.Rect(x + w/2, y, span - w, 5)
                pygame.draw.rect(self.screen, color, rect)
                for i, stree in enumerate(tree):
                    rect = pygame.Rect(x + i*w + w/2 - 2, y, 4, 20)
                    pygame.draw.rect(self.screen, color, rect)
                    draw_tree(x + i*w, y+20, w, stree)
        draw_tree(x+25, y0 + 15, span-50, clap.tree)

        self.screen.set_clip(None)

        y = 15 + 15 #+ sum(10 for _ in self.patches)
        lanes = self.calculate_lanes(y)

        for y, height, drawfuncs, graph in lanes:
            for k, df in enumerate(drawfuncs):
                if df.tag in clap.generators:
                    center_x = self.MARGIN - 30
                    center_y = y + 15 * k + 8
                    half_width  = 4
                    half_height = 4
                    points = [
                        (center_x, center_y - half_height),  # top
                        (center_x + half_width, center_y),   # right
                        (center_x, center_y + half_height),  # bottom
                        (center_x - half_width, center_y),   # left
                    ]
                    pygame.draw.polygon(self.screen, (255, 255, 255), points)

        y0 = y0 + clap.tree.depth*20 + 30

        if self.tag_name in self.doc.descriptors and self.tag_name in clap.generators:
            desc = self.doc.descriptors[self.tag_name]
            gen  = clap.generators[self.tag_name]
            if isinstance(gen, PolyGen):
                stackc = max(len(a) for a in gen.argslists)
            elif isinstance(gen, ConstGen):
                stackc = len(gen.argslist) 
            stackc = max(1, stackc)
            rowc = len(desc.spec) * stackc
            rowc = max(1, rowc)

            for k, (x, span) in enumerate(leafs):
                rect = pygame.Rect(x, y0, span, 15 * rowc)
                pygame.draw.rect(self.screen, [(60, 60, 60), (30,60,30)][k%2], rect)
                for i in range(0, rowc, 2):
                    rect = pygame.Rect(x, y0 + i*15, span, 15)
                    pygame.draw.rect(self.screen, [(80, 80, 80), (40,80,40)][k%2], rect)

                j = 0
                for j, (_, args) in enumerate(gen.pull(k, (), False)):
                    y = y0 + max(1, len(desc.spec))*j*15
                    for l, (name, ty) in enumerate(desc.spec):
                         value = "n/a"
                         if name in args:
                             value = str(args[name])
                         text = self.font.render(value, True, (200, 200, 200))
                         self.screen.blit(text, (x, y + l*15))
                         pass
                    j += 1
                for j in range(j, stackc):
                    rect = pygame.Rect(x + 2, y0 + max(1, len(desc.spec)) * j * 15, span - 4, len(desc.spec)*15)
                    pygame.draw.rect(self.screen, (0, 0, 0), rect)

            for k, (name, _) in enumerate(desc.spec * stackc):
                text = self.font.render(name, True, (200, 200, 200))
                self.screen.blit(text, (self.MARGIN - text.get_width(), y0 + k*15))

        return clap, leafs, y0

    def handle_clap_editor_key(self, ev):
        sel = self.sel
        if not sel or not isinstance(sel[-1].brush, Clap):
            return
        sel = sel[-1].brush
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if ev.key == pygame.K_RIGHT:
                tree = sel.tree
                tree = tree.access(self.p_selection[1:])
                leaves = tree.root.leaves
                if len(tree) == 0:
                    ix = leaves.index(tree)
                    if ix + 1 < len(leaves):
                        self.p_selection[1:] = leaves[ix + 1].get_path()
                else:
                    self.p_selection[1:] = tree.leaves[0].get_path()
            #elif self.p_head < len(self.starts[self.p_index]) - 1:
            #    self.p_head += 1
            #    if not shift_held:
            #        self.p_tail = self.p_head
        elif ev.key == pygame.K_LEFT:
                tree = sel.tree
                tree = tree.access(self.p_selection[1:])
                leaves = tree.root.leaves
                if len(tree) == 0:
                    ix = leaves.index(tree)
                    if ix - 1 >= 0:
                        self.p_selection[1:] = leaves[ix - 1].get_path()
                else:
                    self.p_selection[1:] = tree.leaves[-1].get_path()
        elif ev.key == pygame.K_UP:
            if len(self.p_selection) > 1:
                self.p_selection.pop()
        elif ev.key == pygame.K_DOWN:
            self.mode += 1
        elif ev.key in (
            pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_0,
            pygame.K_n, pygame.K_r, pygame.K_o, pygame.K_s, pygame.K_t,
        ):
                s0, s1 = self.read_event_range(sel.tree)
                tree = sel.tree
                base = tree.copy()
                tree = base.access(self.p_selection[1:])
                k = sum(1 for leaf in tree.leaves if leaf.label == "n")
                if ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_0):
                    n = int(ev.unicode)
                    pattern = [
                        "bnnnnnnnnnnn",
                        "n",
                        "2nn",
                        "3nnn",
                        "22nn2nn",
                        "5nnnnn",
                        "32nn2nn2nn",
                        "7nnnnnnn",
                        "222nn2nn22nn2nn",
                    ][n]
                    n_tree = measure.Tree.from_string(pattern)
                    tree.label = n_tree.label
                    tree.children = n_tree.children
                    for child in n_tree.children:
                        child.parent = tree
                elif ev.key == pygame.K_n:
                    tree.children = []
                    tree.label = "n"
                elif ev.key == pygame.K_r:
                    tree.children = []
                    tree.label = "r"
                elif ev.key == pygame.K_o:
                    tree.children = []
                    tree.label = "o"
                elif ev.key == pygame.K_s:
                    tree.children = []
                    tree.label = "s"
                k = sum(1 for leaf in tree.leaves if leaf.label == "n")
                if ev.key == pygame.K_t:
                    base = measure.simplify(base)
                    self.p_selection[1:] = []
                if base.is_valid():
                    sel.tree = base
                    for name, gen in sel.generators.items():
                        if isinstance(gen, PolyGen) and k != (s1-s0):
                            gen.argslists[s0:s1] = [[{}] for _ in range(k)]
        elif ev.key == pygame.K_PAGEUP:
            self.walk_tag_name(direction=False, from_descriptors=shift_held)
        elif ev.key == pygame.K_PAGEDOWN:
            self.walk_tag_name(direction=True, from_descriptors=shift_held)

    def read_event_range(self, tree):
        leaves = tree.leaves
        tree = tree.access(self.p_selection[1:])
        ix = leaves.index(tree.first_leaf)
        first = sum(1 for leaf in leaves[:ix] if leaf.label == "n")
        ix = leaves.index(tree.last_leaf)
        last = sum(1 for leaf in leaves[:ix] if leaf.label == "n")
        if tree.last_leaf.label == "n":
            return first, last + 1
        else:
            return first, last

    def draw_event_editor(self):
        clap, leafs, y0 = self.draw_clap_editor()
        if clap is None:
            return
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE

        if self.tag_name in self.doc.descriptors:
            desc = self.doc.descriptors[self.tag_name]
            gen  = clap.generators.get(self.tag_name)
            if isinstance(gen, PolyGen):
                stackc = max(len(a) for a in gen.argslists)
            elif isinstance(gen, ConstGen):
                stackc = len(gen.argslist) 
            else:
                stackc = 1
            stackc = max(1, stackc)
            rowc = len(desc.spec) * stackc
            rowc = max(1, rowc)

            if isinstance(gen, ConstGen) or gen is None:
                tspan = min(4, clap.duration)*w
                rect = pygame.Rect(self.MARGIN + 5, y0 + 15 * self.e_v_focus, tspan - 10, 15)
                pygame.draw.rect(self.screen, (255, 255, 255), rect, 1)
            elif isinstance(gen, PolyGen):
                first, stop = self.read_event_range(clap.tree)
                if first < stop:
                    x0, _ = leafs[first]
                    x1 = leafs[stop-1][0] + leafs[stop-1][1]
                    rect = pygame.Rect(x0, y0 + 15 * self.e_v_focus, x1-x0, 15)
                    pygame.draw.rect(self.screen, (255, 255, 255), rect, 1)

    def handle_event_editor_key(self, ev):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if ev.key == pygame.K_PAGEUP:
            self.walk_tag_name(direction=False, from_descriptors=shift_held)
        elif ev.key == pygame.K_PAGEDOWN:
            self.walk_tag_name(direction=True, from_descriptors=shift_held)
        elif ev.key == pygame.K_LEFT:
            self.e_index = max(0, self.e_index - 1)
        elif ev.key == pygame.K_RIGHT:
            self.e_index = self.e_index + 1
        elif ev.key == pygame.K_UP:
            if self.tag_name in self.doc.descriptors:
                spec = self.doc.descriptors[self.tag_name].spec
            else:
                spec = []
            self.e_v_focus = self.e_v_focus - 1
            if self.e_v_focus < 0:
                self.e_v_focus = 0
                self.mode -= 1
        elif ev.key == pygame.K_DOWN:
            if self.tag_name in self.doc.descriptors:
                spec = self.doc.descriptors[self.tag_name].spec
            else:
                spec = []
            sel = self.sel
            if not sel or not isinstance(sel[-1].brush, Clap):
                return
            clap = sel[-1].brush
            if self.tag_name in clap.generators:
                gen  = clap.generators[self.tag_name]
                if isinstance(gen, PolyGen):
                    stackc = max(len(a) for a in gen.argslists)
                elif isinstance(gen, ConstGen):
                    stackc = len(gen.argslist) 
                self.e_v_focus = self.e_v_focus + 1
                if self.e_v_focus >= len(spec) * stackc:
                    self.e_v_focus -= 1
        elif ev.key == pygame.K_RETURN:
            sel = self.sel
            if not sel or not isinstance(sel[-1].brush, Clap):
                return
            clap = sel[-1].brush
            if self.tag_name in self.doc.descriptors:
                desc = self.doc.descriptors[self.tag_name]
                gen  = clap.generators.get(self.tag_name, None)
                i = self.e_v_focus // max(len(desc.spec), 1) + 1
                if isinstance(gen, PolyGen):
                    first, stop = self.read_event_range(clap.tree)
                    for j in range(first, stop):
                        if len(desc.spec) == 0 and len(gen.argslists[j]) > 0:
                            continue
                        gen.argslists[j].insert(i, {})
                elif isinstance(gen, ConstGen):
                    if not (len(desc.spec) == 0 and len(gen.argslist) > 0):
                        gen.argslist.insert(i, {})
                else:
                    clap.generators[self.tag_name] = ConstGen([{}])
        elif ev.key == pygame.K_DELETE:
            sel = self.sel
            if not sel or not isinstance(sel[-1].brush, Clap):
                return
            clap = sel[-1].brush
            if self.tag_name in self.doc.descriptors:
                desc = self.doc.descriptors[self.tag_name]
                gen  = clap.generators.get(self.tag_name, None)
                i = self.e_v_focus // max(len(desc.spec), 1)
                if isinstance(gen, PolyGen):
                    first, stop = self.read_event_range(clap.tree)
                    for j in range(first, stop):
                        if 0 <= i < len(gen.argslists[j]):
                            del gen.argslists[j][i]
                    if sum(len(arglist) for arglist in gen.argslists) == 0:
                        clap.generators.pop(self.tag_name)
                elif isinstance(gen, ConstGen):
                    del gen.argslist[i]
                    if len(gen.argslist) == 0:
                        clap.generators.pop(self.tag_name)
                else:
                    pass
        elif ev.key == pygame.K_PLUS:
            sel = self.sel
            if not sel or not isinstance(sel[-1].brush, Clap):
                return
            clap = sel[-1].brush
            if self.tag_name in self.doc.descriptors:
                desc = self.doc.descriptors[self.tag_name]
                gen  = clap.generators.get(self.tag_name, None)
                total = sum(1 for leaf in clap.tree.leaves if leaf.label == "n")
                if isinstance(gen, ConstGen):
                    a = [ [args.copy() for args in gen.argslist] for _ in range(total)]
                    clap.generators[self.tag_name] = PolyGen(a)
                elif gen is None:
                    a = [ [{}] for _ in range(total)]
                    clap.generators[self.tag_name] = PolyGen(a)
        elif ev.key == pygame.K_j:
            self.modify_event_field(+1)
        elif ev.key == pygame.K_m:
            self.modify_event_field(-1)
        elif ev.key == pygame.K_h:
            self.modify_event_field(+10)
        elif ev.key == pygame.K_n:
            self.modify_event_field(-10)
        elif ev.key == pygame.K_g:
            self.modify_event_field(+100)
        elif ev.key == pygame.K_b:
            self.modify_event_field(-100)
        elif ev.key == pygame.K_f:
            self.modify_event_field(+1000)
        elif ev.key == pygame.K_v:
            self.modify_event_field(-1000)
        elif ev.key == pygame.K_d:
            self.modify_event_field(0, erase=True)

    def note_editor(self):
        sel = self.sel
        if not sel or not isinstance(sel[-1].brush, Clap):
            return
        brush = sel[-1].brush
        for df in self.doc.drawfuncs:
            if df.tag == self.tag_name and df.drawfunc == "note":
                break
        else:
            return
        for graph in self.doc.graphs:
            if graph.lane == df.lane and isinstance(graph, PitchLane):
                break
        else:
            return
        return brush, df, graph

    def draw_note_editor(self):
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        setup = self.note_editor()
        if setup is None:
            return
        brush, df, graph = setup

        x = self.MARGIN
        y = self.SCREEN_HEIGHT/4
        rect = pygame.Rect(x, y, self.SCREEN_WIDTH - self.MARGIN, self.SCREEN_HEIGHT/2)
        pygame.draw.rect(self.screen, (30, 30, 30), rect, False)
        pygame.draw.rect(self.screen, (0, 255, 0), rect, True)

        def draw_tree(x, y, span, tree):
            color = (200, 200, 200)
            if len(tree) == 0:
                text = self.font.render(tree.label, True, color)
                w = span/2 - text.get_width() / 2
                self.screen.blit(text, (x + w, y))
            else:
                w = span / len(tree)
                rect = pygame.Rect(x + w/2, y, span - w, 1)
                pygame.draw.rect(self.screen, color, rect)
                for i, stree in enumerate(tree):
                    rect = pygame.Rect(x + i*w + w/2 - 1, y, 2, 3)
                    pygame.draw.rect(self.screen, color, rect)
                    draw_tree(x + i*w, y+3, w, stree)
        draw_tree(x, y + 3, min(4, brush.duration)*w, brush.tree)
        y1 = y + self.SCREEN_HEIGHT / 2
        y += 3*brush.tree.depth + 23

        starts, stops = brush.tree.offsets(min(4, brush.duration), 0)

        mx, my = pygame.mouse.get_pos()

        for point in starts + stops:
            if 0 < point < 4:
                pygame.draw.line(self.screen, (70, 70, 70), (x + point*w, y + 1), (x + point*w, y1 - 2))

        y += graph.margin_above * self.STAVE_HEIGHT * 2
        yg = y
        for _ in range(graph.staves):
            for p in range(2, 12, 2):
                pygame.draw.line(self.screen, (70, 70, 70), (x, y + p*(self.STAVE_HEIGHT*2 / 12)), (self.SCREEN_WIDTH, y + p*(self.STAVE_HEIGHT*2 / 12)))
            y += self.STAVE_HEIGHT * 2
        y += graph.margin_below * self.STAVE_HEIGHT * 2

        colors = [(0,0,128), (0,0,255), (255,128,0), (255, 0, 0), (128,0,0)]

        location = sum(e.shift for e in self.sel)

        graph_key_map = {graph: [(0, 0)]}
        self.doc.annotate(graph_key_map, 0)
        graph_key = graph_key_map[graph]
        graph_key.sort(key=lambda x: x[0])
        d_ratio = brush.duration / min(4, brush.duration)
        def get_accidentals(b):
            ix = bisect.bisect_right(graph_key, d_ratio * b + location, key=lambda z: z[0])
            return music.accidentals(graph_key[ix-1][1])

        if self.tag_name in brush.generators:
            gen = brush.generators[self.tag_name]
            for i, (s, e) in enumerate(zip(starts, stops)):
                acci = get_accidentals(s)
                for _, args in gen.pull(i, (), False):
                    pitch = args.get(df.params["pitch"], music.Pitch(33))
                    color = colors[pitch.accidental + 2]
                    if pitch.accidental == acci[pitch.position % 7]:
                        color = (255,255,255)
                    yp = yg + (40 - pitch.position) * self.STAVE_HEIGHT*2 / 12
                    span = (e-s)*w
                    pygame.draw.line(self.screen, color, (x + s*w + span*0.05, yp), (x + e*w - span*0.05, yp), int(self.STAVE_HEIGHT/9))

        for i, (s, e) in enumerate(zip(starts, stops)):
            if s*w <= mx - x <= e*w:
                yp = (my - yg) // (self.STAVE_HEIGHT*2/12) * (self.STAVE_HEIGHT*2/12) + yg
                span = (e-s)*w
                rect = pygame.Rect(x + s*w + span*0.05, yp - self.STAVE_HEIGHT * 0.25 / 2, span*0.9, self.STAVE_HEIGHT * 0.25)
                if self.accidental is None:
                    color = (255,255,255)
                else:
                    color = colors[self.accidental + 2]
                pygame.draw.rect(self.screen, color, rect, 1)

        band1 = ["bb", "b", "n", "s", "ss"]
        band2 = ["draw", "r", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
        px = 0
        py = self.SCREEN_HEIGHT - 64
        for i, text in enumerate(band1):
            selected = (self.accidental == i-2)
            rect = pygame.Rect(px, py, 32, 32)
            pygame.draw.rect(self.screen, (100, 100 + 50 * selected, 100), rect, 0)
            pygame.draw.rect(self.screen, (200, 200, 200), rect, 1)
            text = self.font.render(text, True, (200, 200, 200))
            self.screen.blit(text, (px + 16 - text.get_width()/2, py + 16 - text.get_height()/2))
            px += 32
        px = 0
        py = self.SCREEN_HEIGHT - 32
        for i, text in enumerate(band2):
            if i == 0:
                selected = (self.note_tool == "draw")
            else:
                selected = (self.note_tool == "split" and self.pattern == self.PATTERNS[i-1])
            rect = pygame.Rect(px, py, 32, 32)
            pygame.draw.rect(self.screen, (100, 100 + 50 * selected, 100), rect, 0)
            pygame.draw.rect(self.screen, (200, 200, 200), rect, 1)
            text = self.font.render(text, True, (200, 200, 200))
            self.screen.blit(text, (px + 16 - text.get_width()/2, py + 16 - text.get_height()/2))
            px += 32
        px = self.SCREEN_WIDTH / 2
        py = self.SCREEN_HEIGHT - 32
        band3 = ["r -> n"]
        for i, text in enumerate(band3):
            rect = pygame.Rect(px, py, 64, 32)
            pygame.draw.rect(self.screen, (100, 100 + 50 * selected, 100), rect, 0)
            pygame.draw.rect(self.screen, (200, 200, 200), rect, 1)
            text = self.font.render(text, True, (200, 200, 200))
            self.screen.blit(text, (px + 32 - text.get_width()/2, py + 16 - text.get_height()/2))
            px += 64

    def handle_note_editor_mouse(self, ev):
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        setup = self.note_editor()
        if setup is None:
            return
        brush, df, graph = setup

        if ev.type == pygame.MOUSEBUTTONUP and ev.pos[1] >= self.SCREEN_HEIGHT - 64:
            return
        band1 = ["bb", "b", "n", "s", "ss"]
        band2 = ["draw", "r", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
        px = 0
        py = self.SCREEN_HEIGHT - 64
        for i, text in enumerate(band1):
            rect = pygame.Rect(px, py, 32, 32)
            if rect.collidepoint(ev.pos) and ev.type == pygame.MOUSEBUTTONDOWN:
                acc = i-2
                if self.accidental == acc:
                    self.accidental = None
                else:
                    self.accidental = acc
                return
            px += 32
        px = 0
        py = self.SCREEN_HEIGHT - 32
        for i, text in enumerate(band2):
            rect = pygame.Rect(px, py, 32, 32)
            if rect.collidepoint(ev.pos) and ev.type == pygame.MOUSEBUTTONDOWN:
                if i == 0:
                    self.note_tool = "draw"
                else:
                    self.note_tool = "split"
                    self.pattern = self.PATTERNS[i-1]
                return
            px += 32
        px = self.SCREEN_WIDTH / 2
        py = self.SCREEN_HEIGHT - 32
        band3 = ["r -> n"]
        for i, text in enumerate(band3):
            rect = pygame.Rect(px, py, 64, 32)
            if rect.collidepoint(ev.pos) and ev.type == pygame.MOUSEBUTTONDOWN:
                if i == 0:
                    self.remove_rests()
                return
            px += 64

        x = self.MARGIN
        y = self.SCREEN_HEIGHT/4
        y += 3*brush.tree.depth + 23
        yg = y + graph.margin_above * self.STAVE_HEIGHT * 2
        starts, stops = brush.tree.offsets(min(4, brush.duration), 0)

        location = sum(e.shift for e in self.sel)
        graph_key_map = {graph: [(0, 0)]}
        self.doc.annotate(graph_key_map, 0)
        graph_key = graph_key_map[graph]
        graph_key.sort(key=lambda x: x[0])
        d_ratio = brush.duration / min(4, brush.duration)
        def get_accidentals(b):
            ix = bisect.bisect_right(graph_key, d_ratio * b + location, key=lambda z: z[0])
            return music.accidentals(graph_key[ix-1][1])

        if ev.type == pygame.MOUSEBUTTONDOWN and self.note_tool == "split":
            mx, my = ev.pos
            self.note_tail = None
            for i, (s, e) in enumerate(zip(starts, stops)):
                if s*w <= mx - x <= e*w:
                    self.note_tail = i
        elif ev.type == pygame.MOUSEBUTTONUP and self.note_tool == "split" and self.note_tail is not None:
            mx, my = ev.pos
            note_head = self.note_tail
            for i, (s, e) in enumerate(zip(starts, stops)):
                if s*w <= mx - x <= e*w:
                    note_head = i
            first = min(note_head, self.note_tail)
            last  = max(note_head, self.note_tail)
            def segments(tree):
                segs = []
                for leaf in tree.leaves:
                    if leaf.label == "n" or leaf.label == "r":
                        segs.append([leaf])
                    elif leaf.label == "s":
                        segs[-1].append(leaf)
                return [seg for seg in segs if seg[0].label == "n"]
            xs = segments(brush.tree)
            first_leaf = xs[first][0]
            last_leaf = xs[last][-1]
            def left_corner(leaf):
                while True:
                    cousin = leaf.prev_cousin()
                    if cousin is not None and cousin.label == "o":
                        leaf = cousin
                        continue
                    if leaf.parent and leaf.parent.children[0] is leaf:
                        leaf = leaf.parent
                        continue
                    break
                return leaf
            first_leaf = left_corner(first_leaf)
            def right_corner(leaf):
                while leaf.parent and leaf.parent.children[-1] is leaf:
                    leaf = leaf.parent
                return leaf
            last_leaf = right_corner(last_leaf)

            def extrapolate(tree, path, side):
                for ix in path:
                    tree = tree.children[ix]
                    yield tree
                while tree.children:
                    tree = tree.children[side]
                    yield tree

            lca = brush.tree
            ex1 = extrapolate(lca, first_leaf.get_path(), 0)
            ex2 = extrapolate(lca, last_leaf.get_path(), -1)
            for lca0, lca1 in zip(ex1, ex2):
                if lca0 is lca1:
                    lca = lca0
                    if lca.parent is first_leaf:
                        first_leaf = lca
                    if lca.parent is last_leaf:
                        last_leaf = lca
                else:
                    break
            if lca is first_leaf and lca is last_leaf:
                lca.label = "n"
                lca.children = []
                first_leaf = last_leaf = lca
            else:
                if lca is first_leaf:
                    first_leaf = lca.children[0]
                first_leaf.label = "n"
                first_leaf.children = []
                if lca is last_leaf:
                    last_leaf = lca.children[-1]
                last_leaf.label = "s"
                last_leaf.children = []
                branch0 = first_leaf
                while branch0.parent is not lca:
                    parent = branch0.parent
                    for this in parent.children[parent.children.index(branch0)+1:]:
                        this.label = "s"
                        this.children = []
                    branch0 = parent
                branch1 = last_leaf
                while branch1.parent is not lca:
                    parent = branch1.parent
                    for this in parent.children[:parent.children.index(branch1)]:
                        this.label = "s"
                        this.children = []
                    branch1 = parent
                i = lca.children.index(branch0)
                j = lca.children.index(branch1)
                for this in lca.children[i+1:j]:
                    this.label = "s"
                    this.children = []
                assert first_leaf.label == "n"

            leaves = brush.tree.leaves
            ix0 = leaves.index(first_leaf)
            first1 = sum(1 for leaf in leaves[:ix0] if leaf.label == "n")
            ix1 = leaves.index(last_leaf)
            last1 = sum(1 for leaf in leaves[:ix1] if leaf.label == "n")
            d0 = (last + 1 - first)
            d1 = (last1 + 1 - first1)

            if self.pattern != "n":
                block = leaves[ix0:ix1+1]
                def collect(tree):
                    lst = []
                    while tree.parent:
                        tree = tree.parent
                        lst.append(len(tree))
                    return lst
                exponents = [collections.Counter(collect(leaf)) for leaf in block]

                t_exponent = {p: max(counter.get(p, 0) for counter in exponents) for p in measure.primes}
                for counter, leaf in zip(exponents, block):
                    add_counts = {p: t_exponent[p] - counter.get(p, 0) for p in measure.primes}
                    to_add = []
                    for p, count in add_counts.items():
                        to_add.extend([p] * count)
                    def explode(leaf, to_add):
                        if to_add:
                            leaf.label = ""
                            leaf.children = []
                            for _ in range(to_add[0]):
                                subleaf = measure.Tree("o")
                                leaf.children.append(subleaf)
                                subleaf.parent = leaf
                                explode(subleaf, to_add[1:])
                        else:
                            leaf.label = "o"
                    explode(leaf, to_add)
                leaf.last_leaf.label = "n"
                n_tree = measure.Tree.from_string(self.pattern)
                ll = leaf.last_leaf
                ll.label = n_tree.label
                ll.children = n_tree.children
                for child in n_tree.children:
                    child.parent = ll
                d1 = sum(1 for leaf in ll.leaves if leaf.label == "n")

            for name, gen in brush.generators.items():
                if isinstance(gen, PolyGen) and d1 != d0 and d0 == 1:
                    pat = gen.argslists[first]
                    gen.argslists[first:last+1] = [[a.copy() for a in pat] for _ in range(d1)]
                elif isinstance(gen, PolyGen) and d1 != d0:
                    gen.argslists[first:last+1] = [[{}] for _ in range(d1)]

            tree = measure.simplify(brush.tree.copy())
            if tree and tree.is_valid():
                brush.tree = tree

        elif ev.type == pygame.MOUSEBUTTONDOWN and self.note_tool == "draw":
            mx, my = ev.pos
            position = 40 - int((my - yg) // (self.STAVE_HEIGHT*2/12))
            for i, (s, e) in enumerate(zip(starts, stops)):
                if s*w <= mx - x <= e*w:
                    acci = get_accidentals(s)
                    acc = self.accidental or acci[position%7]
                    total = sum(1 for leaf in brush.tree.leaves if leaf.label == "n")
                    gen = brush.generators.get(self.tag_name, None)
                    if isinstance(gen, ConstGen):
                        a = [ [args.copy() for args in gen.argslist] for _ in range(total)]
                        gen = brush.generators[self.tag_name] = PolyGen(a)
                    elif gen is None:
                        a = [ [] for _ in range(total)]
                        gen = brush.generators[self.tag_name] = PolyGen(a)
                    argslist = gen.argslists[i]
                    gen.argslists[i] = []
                    if ev.button == 1:
                        found = False
                        for args in argslist:
                            pitch = args.get(df.params["pitch"], music.Pitch(33))
                            if pitch.position == position:
                                args[df.params["pitch"]] = music.Pitch(position, acc)
                                found = True
                            gen.argslists[i].append(args)
                        if not found:
                            gen.argslists[i].append({df.params["pitch"]: music.Pitch(position, acc)})
                    elif ev.button == 3:
                        for args in argslist:
                            pitch = args.get(df.params["pitch"], music.Pitch(33))
                            if pitch.position != position:
                                gen.argslists[i].append(args)
                        

    def handle_note_editor_key(self, ev):
        mods = pygame.key.get_mods()
        shift_held = mods & pygame.KMOD_SHIFT
        if ev.key == pygame.K_PAGEUP:
            self.walk_tag_name(direction=False, from_descriptors=shift_held)
        elif ev.key == pygame.K_PAGEDOWN:
            self.walk_tag_name(direction=True, from_descriptors=shift_held)
        elif ev.key == pygame.K_UP:
            self.accidental = min(2, (self.accidental or 0)+1)
        elif ev.key == pygame.K_DOWN:
            self.accidental = max(-2, (self.accidental or 0)-1)
        elif ev.key == pygame.K_MINUS:
            self.accidental = None
        elif ev.key == pygame.K_d:
            self.note_tool = "draw"
        elif ev.key == pygame.K_r:
            self.note_tool = "split"
            self.pattern = "r"
        elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_0):
            self.note_tool = "split"
            n = int(ev.unicode)
            self.pattern = [
                        "bnnnnnnnnnnn",
                        "n",
                        "2nn",
                        "3nnn",
                        "22nn2nn",
                        "5nnnnn",
                        "32nn2nn2nn",
                        "7nnnnnnn",
                        "222nn2nn22nn2nn",
            ][n]
        elif ev.key == pygame.K_q:
            self.remove_rests()

        elif ev.key == pygame.K_t:
            setup = self.note_editor()
            if setup is None:
                return
            brush, df, graph = setup
            tree = measure.simplify(brush.tree.copy())
            if tree and tree.is_valid():
                brush.tree = tree

    def remove_rests(self):
        setup = self.note_editor()
        if setup is None:
            return
        brush, df, graph = setup
        ix = 0
        for leaf in brush.tree.leaves:
            if leaf.label == "n":
                ix += 1
            if leaf.label == "r":
                leaf.label = "n"
                for name, gen in brush.generators.items():
                    if isinstance(gen, PolyGen):
                        gen.argslists.insert(ix, [{}])
                ix += 1


    def modify_control_point(self, amount):
        cp = self.get_brush()
        if isinstance(cp, ControlPoint):
            desc = self.doc.descriptors[cp.tag]
            ty = dict(desc.spec)["value"]
            cp.value = modify(cp.value, amount, ty)
        if isinstance(cp, Key):
            cp.index = max(-7, min(+7, modify(cp.index, amount, "number")))

    def modify_event_field(self, amount, erase=False):
            sel = self.sel
            if not sel or not isinstance(sel[-1].brush, Clap):
                return
            clap = sel[-1].brush
            if self.tag_name in self.doc.descriptors:
                desc = self.doc.descriptors[self.tag_name]
                gen  = clap.generators.get(self.tag_name, None)
                i = self.e_v_focus // max(len(desc.spec), 1)
                n = self.e_v_focus % max(len(desc.spec), 1)
                name, ty = desc.spec[n]
                if isinstance(gen, PolyGen):
                    first, stop = self.read_event_range(clap.tree)
                    for j in range(first, stop):
                        if 0 <= i < len(gen.argslists[j]):
                            d = music.Pitch(33) if ty == "pitch" else 0
                            args = gen.argslists[j][i]
                            args[name] = modify(args.get(name, d), amount, ty)
                            if erase:
                                args.pop(name)
                    if sum(len(arglist) for arglist in gen.argslists) == 0:
                        clap.generators.pop(self.tag_name)
                elif isinstance(gen, ConstGen):
                    if 0 <= i < len(gen.argslist):
                        d = music.Pitch(33) if ty == "pitch" else 0
                        args = gen.argslist[i]
                        args[name] = modify(args.get(name, d), amount, ty)
                        if erase:
                            args.pop(name)
                else:
                    pass

def modify(value, amt, ty):
    if ty == "bool":
       return 1*(not value)
    elif ty == "unipolar":
       return min(1, max(0, value + amt * 0.001))
    elif ty == "number":
       return value + amt
    elif ty == "pitch":
       if -10 < amt < 10:
           return music.Pitch(value.position, min(2, max(-2, value.accidental + amt)))
       elif -100 < amt < 100:
           return music.Pitch(value.position + amt // 10, value.accidental)
       else:
           return music.Pitch(value.position + amt // 100 * 7, value.accidental)
    elif ty == "db":
       return min(10, max(-60, value + amt * 0.1))
    elif ty == "dur":
       return max(0, value + amt * 0.01)
    return value

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

