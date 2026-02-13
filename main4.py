from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from controllers import quick_connect
from descriptors import bus, kinds
from fabric2 import Definitions, Fabric
#from model import Document, Cell, from_file, stringify, reader, to_file
from sequencer import Player, Sequencer, SequenceBuilder2
from track_view3 import TrackView
from view_view3 import ViewView
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

from model2.schema import *
from model2.parse import from_string

demo_seq = """oscillseq aqua

drums {
    0 0 gate kick 10100111 duration 1;
    0 1 gate hat  euclidean 5 16 repeat 1 duration 1;
    0 2 gate mhat euclidean 2 12 repeat 1 duration 1;
    0 3 gate snare euclidean 4 14 duration 1;
}

main {
    0 0 clip drums;
    1 0 clip drums;
    2 0 clip drums;
    3 0 clip drums;
    0 4 gate tone e s s e s s s s s s s s s s repeat 4 duration 4
      / c4 g3 d4 e4 c5 b4 f4 [note:pitch:a];
    0 5 gate tone q e e q e e q q q e e q q q s s s s q q q q
      / c6 e6 d6 f6 e6 c6 e6 d6 f6 c6 c6 [note:pitch:b];
    0 to 10 6 pianoroll a f3 d5;
    0 to 10 14 staves b _._ 0;
}

@synths
  tone musical -122 -39 multi {
    amplitude=0.1454
  }

  kick bd 71 -151 multi {
    snappy=0.19,
    amp2=0.48,
    tone2=96.23
  }

  mhat MT 293 162 multi {
  }

  hat HT 464 159 multi {
  }

  snare sn 278 -148 multi {
    snappy=0.19,
    amp2=0.1818,
    tone2=96.23
  }

@connections
  tone:out   system:out,
  kick:out   system:out,
  mhat:out   system:out,
  hat:out    system:out,
  snare:out  system:out
"""


class DocumentProcessing:
    def __init__(self, doc):
        self.doc = doc
        self.declarations = {}
        self.dimensions   = {}
        for declaration in doc.declarations:
            self.declarations[declaration.name] = declaration

    # TODO: Think how to remove rhythm config from here.
    # or think how to compute this properly...
    def get_dimensions(self, decl, rhythm_config):
        if decl.name in self.dimensions:
            return self.dimensions[decl.name]
        duration = 1
        height   = 1
        for i, e in enumerate(decl.entities):
            s = e.shift
            l = e.lane
            if isinstance(e, ClipEntity):
                d, h = self.get_dimensions(self.declarations[e.name], rhythm_config)
                self.dimensions[decl.name, i] = d, h, None
                duration = max(duration, d+s)
                height   = max(height, l+h)
            elif isinstance(e, CommandEntity):
                d = self.process_component(e.component, rhythm_config)
                self.dimensions[decl.name, i] = d.duration, 1, d
                duration = max(duration, d.duration+s)
                height   = max(height, l + 1)
            elif isinstance(e, PianorollEntity):
                h = math.ceil((int(e.top) - int(e.bot) + 1) / 3)
                self.dimensions[decl.name, i] = e.duration, h, None
                duration = max(duration, e.duration+s)
                height   = max(height, l+h)
            elif isinstance(e, StavesEntity):
                h = 2*(e.above + e.count + e.below)
                self.dimensions[decl.name, i] = e.duration, h, None
                duration = max(duration, e.duration+s)
                height   = max(height, l+h)
        self.dimensions[decl.name] = duration, height
        return duration, height

    def construct(self, sb, decl, shift, key, rhythm_config):
        duration = 1
        for i, e in enumerate(decl.entities):
            k = key + (i,)
            s = shift + e.shift
            if isinstance(e, ClipEntity):
                subdecl = self.declarations[e.name]
                d = self.construct(sb, subdecl, s, k, rhythm_config)
                duration = max(duration, d)
            if isinstance(e, CommandEntity) and e.flavor == "gate":
                pattern = self.process_component(e.component, rhythm_config)
                d = self.construct_gate(sb,
                    e.instrument, pattern, s, k)
                duration = max(duration, d)
        return duration

    def process_component(self, component, rhythm_config):
        if isinstance(component, Ref):
            decl = self.declarations[component.name]
            return self.process_component(decl.component, rhythm_config)
        elif isinstance(component, Overlay):
            pattern = self.process_component(component.base, rhythm_config)
            values = component.to_values()
            return pattern.overlay(values, (component.name, component.dtype, component.view))
        elif isinstance(component, Renamed):
            pattern = self.process_component(component.base, rhythm_config)
            for vv in pattern.values:
                for v in vv:
                    if component.src in v:
                        v[component.dst] = v.pop(component.src)
            return pattern
        elif isinstance(component, Repeated):
            pattern = self.process_component(component.base, rhythm_config)
            events = []
            values = pattern.values * component.count
            for i in range(component.count):
                for s, d in pattern.events:
                    events.append((s + pattern.duration*i, d))
            return Pattern(events, values, pattern.duration*component.count, pattern.views)
        elif isinstance(component, Durated):
            pattern = self.process_component(component.base, rhythm_config)
            events = []
            values = pattern.values
            p = component.duration / pattern.duration
            for s, d in pattern.events:
                events.append((s * p, d * p))
            return Pattern(events, values, component.duration, [])
        elif isinstance(component, WestRhythm):
            return component.to_pattern(rhythm_config)
        elif isinstance(component, StepRhythm):
            return component.to_west().to_pattern(rhythm_config)
        elif isinstance(component, EuclideanRhythm):
            return component.to_west().to_pattern(rhythm_config)
        else:
            assert False

    def construct_gate(self, sb, tag, pattern, shift, key):
        for i, ((start, duration), values) in enumerate(zip(pattern.events, pattern.values)):
            for j, v in enumerate(values):
                sb.note(tag, shift+start, duration, key + (i,j,), v)
        return pattern.duration

    #def quadratic(self):
    # if self.tag == "tempo" and self.value <= 0:
    #     continue
    # sequencer.quadratic(offset, self.tag, self.transition, self.value)
        # sb.quadratic(0, "tempo", False, 85)
        # #sb.control(0, "foo", {})
        # #sb.once(0, "foo", {})

class Editor:
    screen_width = 1200
    screen_height = 600
    fps = 30

    MARGIN = 216
    BARS_VISIBLE = 4
    BAR_WIDTH = (screen_width - MARGIN) / BARS_VISIBLE
    LANE_HEIGHT = 2 * 12
    STAVE_HEIGHT = 2 * 12

    def __init__(self):
        pygame.init()
        pygame.key.set_repeat(500, 50)
        self.screen = pygame.display.set_mode(
            (self.screen_width, self.screen_height))
        pygame.display.set_caption("oscillseq")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Arial', 16)

        self.doc = from_string(demo_seq)
        self.proc = DocumentProcessing(self.doc)

        if len(sys.argv) > 1:
            self.filename = sys.argv[1]
        else:
            self.filename = "unnamed.seq.json"
        # if os.path.exists(self.filename):
        #     self.doc = from_file(self.filename)
        #     if self.filename.endswith(".json"):
        #         self.filename = self.filename[:-5]
        #self.png_directory = os.path.abspath(
        #    os.path.splitext(self.filename)[0] + ".png")
        self.wav_filename = os.path.abspath(
            os.path.splitext(self.filename)[0] + ".wav")
        directory = os.path.dirname(os.path.abspath(self.filename))

        self.transport = Transport(
            synthdef_directory = os.path.join(directory,"synthdefs"))
        self.transport.set_online()
        self.transport.refresh(self.proc)
        self.transport.set_fabric()
        self.transport.toggle_play()

        self.mode = "track"
        self.cell_view = NodeView(self)

    def run(self):
        ui = SIMGUI(self.present)

        while ui.running:
            dt = self.clock.tick(self.fps) / 1000.0
            ui.process_events()
            self.screen.fill((30, 30, 30))
            ui.draw(self.screen)
            pygame.display.flip()

        self.transport.set_offline()
#        self.set_midi_off()
        pygame.quit()
        sys.exit()

    def present(self, ui):
        top_grid = Grid(0, 0, 24, 24)
        bot_grid = Grid(0, self.screen_height - 24, 24, 24)
        main_grid = Grid(self.MARGIN, 24, self.BAR_WIDTH, self.LANE_HEIGHT)

        if self.mode == "track":
            ui.widget(GridWidget(self,
                pygame.Rect(
                    self.MARGIN,
                    24,
                    self.screen_width - self.MARGIN,
                    self.screen_height - 48),
                "grid"))

            def traverse_decl(decl, x, y, kv, d=1):
                views = {}
                for i, e in enumerate(decl.entities):
                    ix = x + e.shift
                    iy = y + e.lane
                    w, h, pat = self.proc.dimensions[decl.name, i]
                    if isinstance(e, CommandEntity):
                        ui.widget(PatLane(f"{e.flavor} {e.instrument}",
                            main_grid(ix, iy, ix+w, iy+h),
                            kv + (i,),
                            pat, main_grid.offset(ix,iy)
                            ))
                        for name, dtype, vw in pat.views:
                            try:
                                views[vw].append((name, dtype, pat, ix))
                            except KeyError:
                                views[vw] = [(name, dtype, pat, ix)]
                    elif isinstance(e, ClipEntity):
                        sdecl = self.proc.declarations[e.name]
                        ui.widget(Lane(e.name,
                            main_grid(ix, iy, ix+w, iy+h),
                            kv + (i,)))
                        subviews = traverse_decl(sdecl, ix, iy, kv + (i,), d+1)
                        for vw, g in subviews.items():
                            try:
                                views[vw].extend(g)
                            except KeyError:
                                views[vw] = list(g)
                for i, e in enumerate(decl.entities):
                    ix = x + e.shift
                    iy = y + e.lane
                    w, h, pat = self.proc.dimensions[decl.name, i]
                    if isinstance(e, PianorollEntity):
                        ui.widget(PianorollWidget(
                            main_grid(ix, iy, ix+w, iy+h),
                            int(e.bot), int(e.top),
                            views.get(e.name, []), main_grid,
                            kv + (i,)))
                    elif isinstance(e, StavesEntity):
                        ui.widget(StavesWidget(
                            main_grid(ix, iy, ix+w, iy+h),
                            e.above, e.count, e.below, e.key,
                            views.get(e.name, []), main_grid,
                            kv + (i,)))
                return views

            main_decl = self.proc.declarations['main']
            w, h = self.proc.get_dimensions(main_decl, default_rhythm_config)
            ui.widget(Lane("main", main_grid(0,0,w,h), "main"))
            traverse_decl(main_decl, 0, 0, ("main",))
            
            ui.widget(TransportVisual(self.transport, main_grid,
                pygame.Rect(
                    self.MARGIN,
                    24,
                    self.screen_width - self.MARGIN,
                    self.screen_height - 48),
                "transport-visual"))
        if self.mode == "synth":
            ui.widget(self.transport.get_spectroscope())
            self.cell_view.present(ui)

        if ui.tab_button(self.mode, "file", bot_grid(0, 0, 5, 1),  "file-tab", allow_focus=False):
            self.mode = "file"
        elif ui.tab_button(self.mode, "track", bot_grid(5, 0, 10, 1),  "track-tab", allow_focus=False):
            self.mode = "track"
        elif ui.tab_button(self.mode, "cell", bot_grid(15, 0, 20, 1),  "cell-tab", allow_focus=False):
            self.mode = "synth"

        # self.midi_status = False
        # self.midi_controllers = []

        # self.timeline_head = 0
        # self.timeline_tail = 0
        # self.timeline_scroll = 0
        # self.timeline_vertical_scroll = 0
        # self.timeline = TimelineControl()

        # self.lane_tag = None

        # self.view_view = ViewView(self)
        # self.track_view = TrackView(self)

        # self.view = "file"
        # #self.layout = TrackLayout(self.doc, offset = 30)
        # self.refresh_layout()

#    def present(self, ui):
#        if self.view == "cell":
#        grid = Grid(0, 24, 24, 24)
#        if self.view == "file":
#            if ui.button(f"record {os.path.basename(self.wav_filename)!r}",
#                grid(2, 2, 20, 3), "record"):
#                self.render_score()
#            if ui.button(f"save {os.path.basename(self.filename)!r}",
#                grid(2, 4, 20, 5), "save"):
#                self.save_file()
#        elif self.view == "track":
#            self.track_view.present(ui)
#        elif self.view == "view":
#            self.view_view.present(ui)
#        elif self.view == "cell":
#        self.transport_bar(ui)
#        self.view_bar(ui)
#

#    def transport_bar(self, ui):
#        grid = Grid(0, 0, 24, 24)
#        if ui.widget(OnlineButton(self, grid(0, 0, 1, 1), "online")):
#            self.set_online()
#        if ui.widget(FabricButton(self, grid(1, 0, 2, 1), "fabric")):
#            self.set_fabric_and_stop()
#        if ui.widget(PlayButton(self, grid(2, 0, 3, 1), "play")):
#            if self.transport_status <= 1:
#                self.set_fabric()
#            self.toggle_play()
#        if ui.button(["midi=off", "midi=on"][self.midi_status],
#            grid(3, 0, 6, 1), "midi status", allow_focus=False):
#            self.toggle_midi()
#        if ui.button(["loop=off", "loop=on"][self.playback_loop],
#            grid(6, 0, 9, 1), "loop status", allow_focus=False):
#            self.playback_loop = not self.playback_loop
#            if (status := self.get_playing()) is not None:
#                self.set_fabric()
#                sequence = self.sequence
#                self.set_playing(Sequencer(sequence, point=sequence.t(status), **self.playback_params(sequence)))
#        ui.widget(Trackline(self, self.timeline,
#            pygame.Rect(self.MARGIN, 0, self.screen_width - self.MARGIN, 24),
#            "trackline"))
#
#    def view_bar(self, ui):
#        grid = Grid(0, self.screen_height, 24, 24)
#
#    def toggle_midi(self):
#        if self.midi_status:
#            self.set_midi_off()
#        else:
#            self.set_midi_on()
#
#    def set_midi_on(self):
#        if not self.midi_status:
#            self.midi_controllers = quick_connect(self)
#            self.midi_status = True
#
#    def set_midi_off(self):
#        self.midi_status = False
#        for controller in self.midi_controllers:
#            controller.close()
#        self.midi_controllers.clear()
#
#    def intro(self):
#        layer("main", keyorder = 1)
#        self.timeline()
#        self.tools()
#
#    def trackview(self):
#        layer("main", keyorder = 1)
#        self.timeline()
#        self.tools()
#
#    def staffview(self):
#        layer("main", keyorder = 1)
#        layer("margin", keyorder = -1)
#        self.timeline()
#        self.tools()
#
#    def cellview(self):
#        layer("main", keyorder = 1)
#        layer("margin", keyorder = -1)
#        self.timeline()
#        self.tools()
#
#    def timeline(self):
#        layer("timeline", keyorder = -2)
#        G = grid(0,0,10,10)
#        offline_button(G(0,0,1,1))
#        fabric_button(G(1,0,2,1))
#        play_toggle(G(2,0,3,1))
#        midi_toggle(G(3,0,8,1))
#        loop_toggle(G(8,0,12,1))
#
#    def tools(self):
#        layer("tools", keyorder = 2, y=self.screen_height)
#        G = grid(0,self.screen_height,20,20)
#        sel_button("trackview", "track", G(0,-1,3,0))
#        sel_button("staffview", "view", G(3,-1,6,0))
#        sel_button("cellview", "cell", G(6,-1,9,0))
#
#
#    def save_file(self):
#        to_file(self.filename, self.doc)
#        print("document saved!")
#
#    def render_score(self):
#        self.transport.set_offline()
#
#        sequence = self.sequence
#        score = supriya.Score(output_bus_channel_count=2)
#        clavier = {}
#        with score.at(0):
#            fabric = Fabric(score, self.doc.cells, self.doc.connections, self.definitions)
#        for command in sequence.com:
#            with score.at(command.time):
#                command.send(clavier, fabric)
#        with score.at(sequence.t(self.doc.duration)):
#            score.do_nothing()
#        supriya.render(score, output_file_path=self.wav_filename)
#        print("saved", self.wav_filename)
#
#        self.transport.set_online()
#        self.transport.refresh()

class Transport:
    def __init__(self, synthdef_directory):
        self.definitions = Definitions(synthdef_directory = synthdef_directory)
        self.status = 0
        self.server = None
        self.fabric = None
        self.clavier = None
        self.player = None
        self.playback_range = None
        self.playback_loop  = True
        self.group_ids = {}
        self.sequence = None
        self.make_spectroscope = None
        self.spectroscope_gui = None

        self.current_synths = []
        self.current_connections = set()

        self.cursor_head = 0
        self.cursor_tail = 0

    def get_spectroscope(self):
        if self.spectroscope_gui is None:
            self.spectroscope_gui = Spectroscope(self)
        return self.spectroscope_gui

    def discard_spectroscope(self):
        if self.spectroscope_gui is not None:
            self.spectroscope_gui.close()
            self.spectroscope_gui = None

    def refresh(self, proc):
        if self.status != 3:
            self.group_ids.clear()
        self.current_synths = proc.doc.synths
        self.current_connections = proc.doc.connections

        sb = SequenceBuilder2(self.group_ids, self.definitions.descriptors(proc.doc.synths))

        duration = proc.construct(sb,
            proc.declarations["main"], 0, ("main",),
            default_rhythm_config)
        self.sequence = sb.build(duration)

        if (point := self.get_playing()) is not None:
            self.set_playing(Sequencer(self.sequence, point=self.sequence.t(point), **self.playback_params(self.sequence)))

    def set_offline(self):
        if self.status > 0:
            self.discard_spectroscope()
            self.set_online()
            self.server.quit()
            self.server = None
        self.status = 0

    def set_online(self):
        if self.status < 1:
            self.server = supriya.Server().boot()
            self.make_spectroscope = spectroscope.prepare(self.server)
        if self.status > 1:
            self.set_fabric()
            self.fabric.close()
            self.fabric = None
            self.clavier = None
        self.status = 1

    def set_fabric(self):
        if self.status < 2:
            self.set_online()
            self.fabric = Fabric(self.server, self.current_synths, self.current_connections, self.definitions)
            self.clavier = {}
        if self.status > 2:
            self.player.close()
            self.player = None
        self.status = 2

    def set_fabric_and_stop(self):
        if self.status > 2:
            self.set_fabric()
            for synth in self.clavier.values():
                synth.set(gate=0)
            self.clavier.clear()
        else:
            self.set_fabric()

    def set_playing(self, sequencer):
        if self.status < 3:
            self.set_fabric()
        if self.player is not None:
            self.player.close()
        self.player = Player(self.clavier, self.fabric, sequencer)
        self.status = 3

    def get_playing(self):
        if self.status == 3:
            return self.player.sequencer.status

    def restart_fabric(self):
        if self.status == 3:
            sequencer = self.player.sequencer
        else:
            sequencer = None
        if self.status >= 2:
            self.set_online()
            self.set_fabric()
        if sequencer:
            self.set_playing(sequencer)

    def toggle_play(self):
        if self.status < 2:
            self.set_fabric()
        elif self.get_playing() is None:
            if self.status == 3:
                self.set_fabric()
            sequence = self.sequence
            self.set_playing(Sequencer(sequence, point=sequence.t(min(self.cursor_head, self.cursor_tail)), **self.playback_params(sequence)))
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

class Spectroscope:
    def __init__(self, transport):
        out = transport.server.audio_output_bus_group
        self.s1 = transport.make_spectroscope(bus=out[0])
        self.s2 = transport.make_spectroscope(bus=out[1])
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


@dataclass
class GridWidget:
    editor : Editor
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        return None
    
    def draw(self, ui, screen):
        w = self.editor.BAR_WIDTH
        lanes = self.editor.LANE_HEIGHT
        for y in range(0, int(self.rect.height + 1), lanes):
            y += self.rect.top
            pygame.draw.line(screen, (50, 50, 50),
                (self.rect.left, y),
                (self.rect.right, y))
        for x in range(0, int(self.rect.width + 1), int(w)):
            x += self.rect.left
            pygame.draw.line(screen, (50, 50, 50),
                (x, self.rect.top),
                (x, self.rect.bottom))

@dataclass
class Lane:
    text : str
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        ui.grab_active(self)
        return ui.was_clicked(self)

    def draw(self, ui, screen):
        rect = self.rect
        pygame.draw.rect(screen, (50, 50, 50), rect, 0, 4)
        pygame.draw.rect(screen, (200, 200, 200), rect, 2, 4)
        surf = ui.font16.render(self.text, True, (200, 200, 200))
        rc = surf.get_rect(top=rect.top + 6, left=rect.left + 6)
        screen.blit(surf, rc)
        
@dataclass
class PatLane(Lane):
    pat : Pattern
    grid : Grid

    def draw(self, ui, screen):
        rect = self.rect
        pygame.draw.rect(screen, (50, 50, 50), rect, 0, 4)
        for start,duration in self.pat.events:
            rc = self.grid(start, 0.6, start+duration, 0.9)
            pygame.draw.rect(screen, (150, 50, 150), rc, 0, 2)
            pygame.draw.rect(screen, (250, 150, 250), rc, 1, 2)
        pygame.draw.rect(screen, (200, 200, 200), rect, 2, 4)

        surf = ui.font16.render(self.text, True, (200, 200, 200))
        rc = surf.get_rect(top=rect.top + 2, left=rect.left + 6)
        screen.blit(surf, rc)

class StavesWidget:
    def __init__(self, rect, above, count, below, key, pats, grid, widget_id):
        self.rect = rect
        self.above = above
        self.count = count
        self.below = below
        self.key = key
        self.pats = pats
        self.grid = grid
        self.widget_id = widget_id

    def behavior(self, ui):
        ui.grab_active(self)
        return ui.was_clicked(self)

    def draw(self, ui, screen):
        rect = self.rect
        pygame.draw.rect(screen, (0,0,0), rect, 0, 3)
        x, y = rect.topleft
        w = rect.width
        k = rect.height / (self.count + self.above + self.below)
        y += self.above * k
        for _ in range(self.count):
            for p in range(2, 12, 2):
                pygame.draw.line(screen, (70, 70, 70), (x, y+p*k/12), (x+w, y+p*k/12))
            y += k
        screen.set_clip(rect)
        colors = [(0,0,128), (0,0,255), (255,128,0), (255, 0, 0), (128,0,0)]
        for name, dtype, pat, x in self.pats:
            for (s,d), vg in zip(pat.events, pat.values):
                a = self.grid.point(s + x, 0)[0]
                b = self.grid.point(s + x + d, 0)[0]
                for v in vg:
                    if isinstance(v[name], int):
                        note = music.Pitch.from_midi(v[name])
                    else:
                        note = v[name]
                    color = colors[note.accidental+2]
                    acci = music.accidentals(self.key)
                    if note.accidental == acci[note.position % 7]:
                        color = (255,255,255)
                    py = rect.top + self.above*k + (40 - note.position) * k / 12
                    rc = pygame.Rect(a, py - k / 24, b-a, k / 12)
                    pygame.draw.rect(screen, color, rc, 1, 2)
        screen.set_clip(None)
        pygame.draw.rect(screen, (200,200,200), rect, 1, 3)
        pygame.draw.rect(screen, (200,200,200), rect, 1, 3)

class PianorollWidget:
    def __init__(self, rect, bot, top, pats, grid, widget_id):
        self.rect = rect
        self.bot  = bot
        self.top  = top
        self.pats = pats
        self.grid = grid
        self.widget_id = widget_id

    def behavior(self, ui):
        ui.grab_active(self)
        return ui.was_clicked(self)

    def draw(self, ui, screen):
        rect = self.rect
        pygame.draw.rect(screen, (0,0,0), rect, 0, 3)
        top = self.top
        bot = self.bot
        x, y = rect.bottomleft
        w = rect.width
        k = rect.height / (top - bot + 1)
        for note in range(bot, top + 1):
            py = y - k*(note - bot)
            rc = pygame.Rect(x, py-k, w, k)
            if note == 69:
                pygame.draw.rect(screen, (100*1.5, 50*1.5, 50*1.5), rc)
            elif note % 12 == 9:
                pygame.draw.rect(screen, (100, 50, 50), rc)
            elif note % 12 in [0, 2, 4, 5, 7, 9, 11]:
                pygame.draw.rect(screen, (50, 50, 50), rc)
            elif note == bot:
                pygame.draw.line(screen, (70, 70, 70), (x, py), (rc.right, py))
            else:
                pygame.draw.line(screen, (50, 50, 50), (x, py), (rc.right, py))
        screen.set_clip(rect)
        for name, dtype, pat, x in self.pats:
            for (s,d), vg in zip(pat.events, pat.values):
                a = self.grid.point(s + x, 0)[0]
                b = self.grid.point(s + x + d, 0)[0]
                for v in vg:
                    note = int(v[name])
                    py = y - k*(note - bot)
                    rc = pygame.Rect(a, py-k, b-a, k)
                    pygame.draw.rect(screen, (255, 255, 255), rc, 1, 2)
        screen.set_clip(None)
        pygame.draw.rect(screen, (200,200,200), rect, 1, 3)

@dataclass
class TransportVisual:
    transport : Transport
    grid : Grid
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        return None

    def draw(self, ui, screen):
        if (t := self.transport.get_playing()) is not None:
            x = self.grid.point(t, 0.0)[0]
            pygame.draw.line(screen, (255,100,100), 
                (x, self.rect.top),
                (x, self.rect.bottom))


@dataclass
class OnlineButton:
    editor : Editor
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        ui.grab_active(self)
        return ui.was_clicked(self)

    def draw(self, ui, screen):
        if self.editor.transport.status == 1:
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
