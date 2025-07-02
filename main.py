from dataclasses import dataclass, field
from fractions import Fraction
from model import Entity, ControlPoint, Key, Clip, NoteGen, Clap, DrawFunc, PitchLane, Cell, Document, json_to_brush
from typing import List, Dict, Optional, Callable, Tuple, Any
from sequencer import Player, Sequencer, SequenceBuilder2
from fabric import Definitions, Fabric
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
from brush_editor_view import BrushEditorView, modify
from node_editor_view import NodeEditorView
from lane_editor_view import LaneEditorView, drawfunc_table

# TODO: remove type annotation from buses.

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
                DrawFunc(0, "string", "tempo", {"value": "*"}),
            ],
            cells = [],
            views = [],
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

        self.playback_range = None
        self.playback_loop  = True

        # Sequence is built so it could be visualized.
        self.group_ids = {}
        sb = SequenceBuilder2(self.group_ids, self.definitions.descriptors(self.doc.cells))
        self.doc.construct(sb, 0, ())
        self.sequence = sb.build(self.doc.duration)

        self.transport_bar = TransportBar(self)

        self.toolbar = Toolbar(pygame.Rect(0, self.SCREEN_HEIGHT - 32, self.SCREEN_WIDTH, 32),
            [
                ("track editor", BrushEditorView),
                ("lane editor", LaneEditorView),
                ("cell editor", NodeEditorView)
            ],
            (lambda view: self.change_view(view)),
            (lambda name, cls: isinstance(self.view, cls)))

        self.timeline_head = 0
        self.timeline_tail = 0
        self.timeline_scroll = 0
        self.timeline_vertical_scroll = 0

        self.lane_tag = None
        self.layout = TrackLayout(self.doc, offset = 30)

        self.view = NodeEditorView(self)

    def refresh_layout(self):
        if self.transport_status != 3:
            self.group_ids.clear()
        sb = SequenceBuilder2(self.group_ids, self.definitions.descriptors(self.doc.cells))
        self.doc.construct(sb, 0, ())
        self.sequence = sb.build(self.doc.duration)
        self.layout = TrackLayout(self.doc, offset = 30)
        if (point := self.get_playing()) is not None:
            self.set_playing(Sequencer(self.sequence, point=self.sequence.t(point), **self.playback_params(self.sequence)))

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
                self.change_view(BrushEditorView)
            if ev.key == pygame.K_2:
                self.change_view(LaneEditorView)
            elif ev.key == pygame.K_3:
                self.change_view(NodeEditorView)
            #elif ev.key == pygame.K_4:
            #elif ev.key == pygame.K_5:
            #elif ev.key == pygame.K_6:
            #elif ev.key == pygame.K_7:
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
            loop_point = sequence.end
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

    def get_dfn(self, tag):
        cell = self.doc.labels.get(tag, None)
        if isinstance(cell, Cell):
            return self.definitions.descriptor(cell)
    
    def validate(self, df):
        if dfn := self.get_dfn(df.tag):
            return all(df.params[name] in dfn.avail(ty) for name, ty in drawfunc_table[df.drawfunc])
        return False

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
        self.calculate_brush_lanes()
        self.brush_offset = offset
        self.offset = offset = offset + 15 + (self.brush_heights[self.doc] - 15)
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

    def calculate_brush_lanes(self):
        self.clip_lanes = {}
        self.brush_heights = {}
        def process(brush):
            if brush in self.brush_heights:
                return
            if isinstance(brush, Clip):
                process_clip(brush)
            elif isinstance(brush, Clap) and isinstance(brush.rhythm, measure.Tree):
                self.brush_heights[brush] = 15 + 3 * (brush.rhythm.depth) + 20
            else:
                self.brush_heights[brush] = 15
        def process_clip(clip):
            if clip in self.clip_lanes:
                return
            clip.brushes.sort(key=lambda e: e.shift)
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

    def draw(self, screen, font, editor):
        vs = editor.timeline_vertical_scroll
        SCREEN_WIDTH = screen.get_width()
        SCREEN_HEIGHT = screen.get_height()
        w = (SCREEN_WIDTH - editor.MARGIN) / editor.BARS_VISIBLE

        if isinstance(editor.view, BrushEditorView):
            selection = editor.view.selection
            reference = editor.view.reference
            if not selection:
                text = font.render("document selected", True, (0,255,0))
                screen.blit(text, (10, 15))
        else:
            selection = []
            reference = None

        bs = self.brush_offset - vs
        #screen.set_clip(pygame.Rect(self.MARGIN, 15 + 15, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT - 15 + 15))

        def draw_clip_contents(clip, shift, py, seli):
            assignments, lane_offsets, lane_heights = self.clip_lanes[clip]
            for i, e in zip(assignments, clip.brushes):
                start = (shift + e.shift - editor.timeline_scroll)
                duration = e.brush.duration
                y = lane_offsets[i] + py
                height = self.brush_heights[e.brush]
                if duration == 0:
                    pygame.draw.circle(screen, (200, 200, 200), (start*w + editor.MARGIN, y+7.5), 7.5, 0, True, False, False, True)
                else:
                    rect = pygame.Rect(start*w + editor.MARGIN, y, duration*w, height)
                    pygame.draw.rect(screen, (200,200,200), rect, 1, 3)
                selected = 1*(selection == seli + [e])
                selected += 2*(e.brush == reference)
                name = "???"
                if isinstance(e.brush, Clip):
                    name = f"{e.brush.label}"
                if isinstance(e.brush, Clap):
                    name = f"{e.brush.label}"
                if isinstance(e.brush, ControlPoint):
                    name = f"{e.brush.tag} {' ~'[e.brush.transition]} {e.brush.value}"
                if isinstance(e.brush, Key):
                    name = f"key {e.brush.lanes} {e.brush.index} {music.major[e.brush.index]}"
                text = font.render(name, True, [(200, 200, 200), (0,255,0), (200, 0, 200), (200, 255, 100)][selected])
                screen.blit(text, (start*w + 10 + editor.MARGIN, y))
                if isinstance(e.brush, Clip):
                    draw_clip_contents(e.brush, shift + e.shift, y + 15, seli + [e])
                if isinstance(e.brush, Clap) and isinstance(e.brush.rhythm, measure.Tree):
                    leafs = []
                    def draw_tree(x, y, span, tree):
                        color = (200, 200, 200) #[(200, 200, 200), (255, 0, 255)][tree == s_tree]
                        if len(tree) == 0:
                            if tree.label == "n":
                                leafs.append((x, span))
                            text = font.render(tree.label, True, color)
                            w = span/2 - text.get_width() / 2
                            screen.blit(text, (x + w, y))
                        else:
                            w = span / len(tree)
                            rect = pygame.Rect(x + w/2, y, span - w, 1)
                            pygame.draw.rect(screen, color, rect)
                            for i, stree in enumerate(tree):
                                rect = pygame.Rect(x + i*w + w/2 - 1, y, 2, 3)
                                pygame.draw.rect(screen, color, rect)
                                draw_tree(x + i*w, y+3, w, stree)
                    span = duration*w
                    draw_tree(start*w+editor.MARGIN, y + 15, span, e.brush.rhythm)
        draw_clip_contents(editor.doc, 0, bs, [])

        #screen.set_clip(pygame.Rect(0, 15 + 15, self.SCREEN_WIDTH, self.SCREEN_HEIGHT - 15 + 15))

        pygame.draw.line(screen, (40, 40, 40), (0, self.offset - vs), (SCREEN_WIDTH, self.offset - vs))
        for y, height, drawfuncs, graph in self.lanes:
            y -= vs
            for k, df in enumerate(drawfuncs):
                ok = editor.validate(df)
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
            
class SequencerEditor:

    def __init__(self):

        self.p_selection = [0]

        # Event editor
        self.e_index = 0
        self.e_v_focus = 0

    def draw_events(self, y):
        w = (self.SCREEN_WIDTH - self.MARGIN) / self.BARS_VISIBLE
        self.screen.set_clip(pygame.Rect(self.MARGIN, 15 + 15, w * self.BARS_VISIBLE, self.SCREEN_HEIGHT - 15 + 15))
        lanes = self.calculate_lanes(y)
        for y, height, drawfuncs, graph in lanes:
            for df in drawfuncs:
                if self.validate(df):
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
                        text = font.render("<", True, (200, 200, 200))
                        self.screen.blit(text, ((mp - self.bar)*w + self.MARGIN, rowy))
                    elif pv > vv:
                        text = font.render(">", True, (200, 200, 200))
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

