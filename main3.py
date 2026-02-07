from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from controllers import quick_connect
from descriptors import bus, kinds
from fabric import Definitions, Fabric
from model import Document, Cell, from_file, stringify, reader
from sequencer import Player, Sequencer, SequenceBuilder2
from track_view import TrackView, TimelineScroll
from view_view import ViewView
from node_view3 import NodeView
import numpy as np
import math
import music
import os
import pygame
import spectroscope
import supriya
import sys
from simgui import SIMGUI, Grid, Text, Slider

class Editor:
    screen_width = 1200
    screen_height = 600
    fps = 30

    MARGIN = 216
    BARS_VISIBLE = 4
    BAR_WIDTH = (screen_width - MARGIN) / BARS_VISIBLE
    STAVE_HEIGHT = 3 * 12

    def __init__(self):
        pygame.init()
        pygame.key.set_repeat(500, 50)
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

        self.group_ids = {}

        self.timeline_head = 0
        self.timeline_tail = 0
        self.timeline_scroll = 0
        self.timeline_vertical_scroll = 0
        self.timeline = TimelineControl()

        self.lane_tag = None

        self.cell_view = NodeView(self)

        self.view = "file"
        self.spectros = None
        #self.layout = TrackLayout(self.doc, offset = 30)
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
#        self.view.refresh()
#        root = self.compostor(self.view.scene, self.popups)
#        root.calculate_layout(self.screen_width, self.screen_height, "ltr")

    def present(self, ui):
        if self.view == "cell":
            if self.spectros is None:
                self.spectros = Spectros(self)
            ui.widget(self.spectros)
        else:
            self.discard_spectros()
        grid = Grid(0, 24, 24, 24)
        if self.view == "file":
            if ui.button(f"record {os.path.basename(self.wav_filename)!r}",
                grid(2, 2, 20, 3), "record"):
                self.render_score()
            if ui.button(f"save {os.path.basename(self.filename)!r}",
                grid(2, 4, 20, 5), "save"):
                self.save_file()
        elif self.view == "track":
            pass
        elif self.view == "view":
            pass
        elif self.view == "cell":
            self.cell_view.present(ui)
        self.transport_bar(ui)
        self.view_bar(ui)

    def discard_spectros(self):
        if self.spectros is not None:
            self.spectros.close()
            self.spectros = None

    def transport_bar(self, ui):
        grid = Grid(0, 0, 24, 24)
        if ui.widget(OnlineButton(self, grid(0, 0, 1, 1), "online")):
            self.set_online()
        if ui.widget(FabricButton(self, grid(1, 0, 2, 1), "fabric")):
            self.set_fabric_and_stop()
        if ui.widget(PlayButton(self, grid(2, 0, 3, 1), "play")):
            if self.transport_status <= 1:
                self.set_fabric()
            self.toggle_play()
        if ui.button(["midi=off", "midi=on"][self.midi_status],
            grid(3, 0, 6, 1), "midi status", allow_focus=False):
            self.toggle_midi()
        if ui.button(["loop=off", "loop=on"][self.playback_loop],
            grid(6, 0, 9, 1), "loop status", allow_focus=False):
            self.playback_loop = not self.playback_loop
            if (status := self.get_playing()) is not None:
                self.set_fabric()
                sequence = self.sequence
                self.set_playing(Sequencer(sequence, point=sequence.t(status), **self.playback_params(sequence)))
        ui.widget(Trackline(self, self.timeline,
            pygame.Rect(self.MARGIN, 0, self.screen_width - self.MARGIN, 24),
            "trackline"))

    def view_bar(self, ui):
        grid = Grid(0, self.screen_height, 24, 24)
        if ui.tab_button(self.view, "file", grid(0, -1, 5, 0),  "file-tab", allow_focus=False):
            self.view = "file"
        elif ui.tab_button(self.view, "track", grid(5, -1, 10, 0),  "track-tab", allow_focus=False):
            self.view = "track"
        elif ui.tab_button(self.view, "view", grid(10, -1, 15, 0),  "view-tab", allow_focus=False):
            self.view = "view"
        elif ui.tab_button(self.view, "cell", grid(15, -1, 20, 0),  "cell-tab", allow_focus=False):
            self.view = "cell"

    def set_offline(self):
        if self.transport_status > 0:
            self.discard_spectros()
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

    def intro(self):
        layer("main", keyorder = 1)
        self.timeline()
        self.tools()

    def trackview(self):
        layer("main", keyorder = 1)
        self.timeline()
        self.tools()

    def staffview(self):
        layer("main", keyorder = 1)
        layer("margin", keyorder = -1)
        self.timeline()
        self.tools()

    def cellview(self):
        layer("main", keyorder = 1)
        layer("margin", keyorder = -1)
        self.timeline()
        self.tools()

    def timeline(self):
        layer("timeline", keyorder = -2)
        G = grid(0,0,10,10)
        offline_button(G(0,0,1,1))
        fabric_button(G(1,0,2,1))
        play_toggle(G(2,0,3,1))
        midi_toggle(G(3,0,8,1))
        loop_toggle(G(8,0,12,1))

    def tools(self):
        layer("tools", keyorder = 2, y=self.screen_height)
        G = grid(0,self.screen_height,20,20)
        sel_button("trackview", "track", G(0,-1,3,0))
        sel_button("staffview", "view", G(3,-1,6,0))
        sel_button("cellview", "cell", G(6,-1,9,0))

    def run(self):
        ui = SIMGUI(self.present)

        while ui.running:
            dt = self.clock.tick(self.fps) / 1000.0
            ui.process_events()
            self.screen.fill((30, 30, 30))
            ui.draw(self.screen)
            pygame.display.flip()

        self.set_offline()
        self.set_midi_off()
        pygame.quit()
        sys.exit()

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
        self.refresh_layout()

@dataclass
class OnlineButton:
    editor : Editor
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        ui.grab_active(self)
        return ui.was_clicked(self)

    def draw(self, ui, screen):
        if self.editor.transport_status == 1:
            color = 10, 10, 155
        else:
            color = 100, 100, 100
        pygame.draw.rect(screen, color, self.rect)
        centerx, centery = self.rect.center
        half_width  = 6 / 2
        half_height = 6 / 2
        top = (centerx, centery - half_height)
        rig = (centerx + half_width, centery)
        bot = (centerx, centery + half_height)
        lef = (centerx - half_width, centery)
        pygame.draw.line(screen, (200, 200, 200), top, bot)
        pygame.draw.line(screen, (200, 200, 200), lef, bot)
        pygame.draw.line(screen, (200, 200, 200), bot, rig)
        if ui.active_id == self.widget_id:
            pygame.draw.rect(screen, (50, 150, 50), self.rect, 1)

@dataclass
class FabricButton:
    editor : Editor
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        ui.grab_active(self)
        return ui.was_clicked(self)

    def draw(self, ui, screen):
        if self.editor.transport_status >= 2:
            color = 10, 155, 10
        else:
            color = 100, 100, 100
        pygame.draw.rect(screen, color, self.rect, 0, 0)
        centerx, centery = self.rect.center
        half_width  = 6 / 2
        half_height = 6 / 2
        top = (centerx, centery - half_height)
        rig = (centerx + half_width, centery)
        bot = (centerx, centery + half_height)
        lef = (centerx - half_width, centery)
        pygame.draw.line(screen, (200, 200, 200), top, bot)
        pygame.draw.line(screen, (200, 200, 200), lef, top)
        pygame.draw.line(screen, (200, 200, 200), top, rig)
        if ui.active_id == self.widget_id:
            pygame.draw.rect(screen, (50, 150, 50), self.rect, 1)

@dataclass
class PlayButton:
    editor : Editor
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        ui.grab_active(self)
        return ui.was_clicked(self)

    def draw(self, ui, screen):
        pygame.draw.rect(screen, (200, 200, 200), self.rect, 1, 0)
        if (t := self.editor.get_playing()) is not None:
            pygame.draw.rect(screen, (200, 200, 200),
            self.rect.inflate((-14, -14)), 0, 0)
        else:
            centerx, centery = self.rect.center
            half_width  = 6 / 3
            half_height = 6 / 2
            points = [
                (centerx - half_width, centery - half_height),  # top
                (centerx + half_width, centery),   # right
                (centerx - half_width, centery + half_height),  # bottom
            ]
            pygame.draw.polygon(screen, (200, 200, 200), points)
        if ui.active_id == self.widget_id:
            pygame.draw.rect(screen, (50, 150, 50), self.rect, 1)
                #elif frame.same(frame.ui.focus):
                #    pygame.draw.rect(frame.screen, (50, 50, 150), frame.rect, 1)

@dataclass(eq=False)
class TimelineControl:
    drag_pos : Any = (0,0)
    drag_org : int = 0

@dataclass(eq=False)
class Trackline:
    editor : Editor
    control : TimelineControl
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        if ui.hot_id is None and self.rect.collidepoint(ui.mouse_pos):
            self.hot_id = self.widget_id
            if ui.r_mouse_just_pressed and ui.r_active_id is None:
                ui.r_active_id = self.widget_id
                self.control.drag_pos = ui.mouse_pos
                self.control.drag_org = self.editor.timeline_scroll
        if ui.r_active_id == self.widget_id:
            dx = self.control.drag_pos[0] - ui.mouse_pos[0]
            ix = int(dx // self.editor.BAR_WIDTH)
            self.editor.timeline_scroll = max(0, ix + self.control.drag_org)
            return True
        return False

    def draw(self, ui, screen):
        w = self.editor.BAR_WIDTH
        mg = []
        for i in range(self.editor.BARS_VISIBLE + 1):
            x = i * w + self.rect.left
            if (i + self.editor.timeline_scroll) == self.editor.timeline_head:
                pygame.draw.line(screen, (0, 255, 255),
                                (x, self.rect.top), (x, self.rect.bottom))
            else:
                pygame.draw.line(screen, (200, 200, 200),
                                (x, self.rect.top), (x, self.rect.bottom))
            text = ui.font24.render(
                str(i + self.editor.timeline_scroll), True, (200, 200, 200))
            screen.blit(text, (x + 2, self.rect.centery - text.get_height()/2))
            mg.append(text.get_width())

        if self.editor.playback_range is not None:
            i, j = self.editor.playback_range
            half_width  = 6 / 2
            half_height = 6 / 2
            if self.editor.timeline_scroll <= i < self.editor.timeline_scroll + self.editor.BARS_VISIBLE:
                centerx = (i - self.editor.timeline_scroll) * w + 6 + mg[i - self.editor.timeline_scroll] + self.rect.left
                centery = self.rect.centery
                top = (centerx, centery - half_height)
                rig = (centerx + half_width, centery)
                bot = (centerx, centery + half_height)
                lef = (centerx - half_width, centery)
                pygame.draw.polygon(screen, (200, 200, 200), [top, rig, bot])

            if self.editor.timeline_scroll < j <= self.editor.timeline_scroll + self.editor.BARS_VISIBLE:
                centerx = (j - self.editor.timeline_scroll) * w - 6 + self.rect.left
                centery = self.rect.centery
                top = (centerx, centery - half_height)
                rig = (centerx + half_width, centery)
                bot = (centerx, centery + half_height)
                lef = (centerx - half_width, centery)
                pygame.draw.polygon(screen, (200, 200, 200), [top, bot, lef])

        k = self.editor.doc.duration
        if self.editor.timeline_scroll < k <= self.editor.timeline_scroll + self.editor.BARS_VISIBLE:
            x = (k - self.editor.timeline_scroll) * w + self.rect.left
            pygame.draw.line(screen, (0, 255, 0),
                (x, self.rect.top), (x, self.rect.bottom), 4)

        screen.set_clip(self.rect)
        if (t := self.editor.get_playing()) is not None:
            x = (t - self.editor.timeline_scroll) * w + self.rect.left
            pygame.draw.line(screen, (255, 0, 0),
                (x, self.rect.top), (x, self.rect.bottom))
        screen.set_clip(None)

class Spectros:
    def __init__(self, editor):
        out = editor.server.audio_output_bus_group
        self.s1 = editor.make_spectroscope(bus=out[0])
        self.s2 = editor.make_spectroscope(bus=out[1])
        self.widget_id = object()

    def behavior(self, ui):
        return None

    def draw(self, ui, screen):
        self.s1.refresh()
        self.s2.refresh()
        y0 = screen.get_height()/4 - 100
        y1 = screen.get_height()*3/4 - 100
        self.s1.draw(screen, ui.font24, (255, 0, 0), screen.get_width()/2, y0)
        self.s2.draw(screen, ui.font24, (0, 255, 0), screen.get_width()/2, y1)

    def close(self):
        self.s1.close()
        self.s2.close()


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
