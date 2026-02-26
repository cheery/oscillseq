from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from controllers import quick_connect
from descriptors import bus, kinds
from fabric2 import Definitions, Fabric
#from model import Document, Cell, from_file, stringify, reader, to_file
from model2 import synthlang
from sequencer import Player, Sequencer, SequenceBuilder2
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
from model2.parse import from_string, from_file, command_from_string

demo_seq = """oscillseq aqua

drums {
    (0,0) %% |1| [/ T_T__TTT] {
       synth=kick;
    }
    (0,1) %% |1| [/ euclidean 5 16] {
       synth=hat;
    }
    (0,2) %% |1| [/ euclidean 2 12] {
       synth=mhat;
    }
    (0,3) %% |1| [/ euclidean 4 14] {
       synth=snare;
    }
    (0,4) %note:pitch% q c3, q c3, q c3, q c3 {
       synth=tone;
    }
}

theme2 {
    (0,0) %note:pitch@a%
      q, e, e, q, e, e,
      q, q, q, e, e,
      q, q, q, s, s, s, s,
      q, q, q, q
      / ostinato %note:pitch@a%
        * c6, * e6, * d6, * f6, * e6, * c6, * e6, * d6, * f6, * c6, * c6
    {
        synth=tone;
    }
    (0,1) @a {
        above=1;
    }
}

theme {
    (0,0) &drums;
    (1,0) &drums;
    (2,0) &drums;
    (3,0) &drums;
    (0,6) %note:pitch@b%
        |4| [e, s, s, e, s, s, s, s, s, s, s, s, s, s / repeat 4]
        / ostinato %note:pitch@b% * c4, * g3, * d4, * e4, * c5, * b4, * f4 {
        synth=tone;
    }
    (0,13) @b {
        view=pianoroll;
    }
}

full {
    (0,0) &theme;
    (4,0) &theme;
    (4,8) &theme2;
    (8,0) &theme;
    (8,8) &theme2;
    (8,16) %note:pitch% e c5, e e5, q c5, e b4, e c5, q c4 / repeat 4 { synth=saw; }
    (12,0) &theme;
    (12,8) &theme2;
    (12,16) %note:pitch% e c5, e e5, q g5, e b4, e c5, q c4 / repeat 4 { synth=saw; }
}

main {
    (0,0) &full;
    (16,0) &full;
    (32,0) &full;
    (32,16) %note:pitch% e c5, e e5, q g5, e b4, e c5, q c4 / repeat 4 { synth=saw; }
}

@synths
  (-122, -39) tone fm multi {
    volume=-0;
  }
  (-122, -89) saw saw multi {
    volume=-0;
  }

  (71, -151) kick bd multi {
    snappy=0.19;
    amp2=0.48;
    tone2=96.23;
  }

  (293, 162) mhat MT multi {
  }

  (464, 159) hat HT multi {
  }

  (278, -148) snare sn multi {
    snappy=0.19;
    amp2=0.1818;
    tone2=96.23;
  }

  (0, 100) comb comb_l {
  }

@connections
  tone:out   system:out,
  saw:out   system:out,
  kick:out   system:out,
  mhat:out   system:out,
  hat:out    system:out,
  snare:out  system:out
"""

demo_seq = """
oscillseq aqua

main {
}
"""

# demo_seq = """
# oscillseq aqua
# 
# main {
#     (0,0) %note:pitch@a% q c4, q c4, q c4, q c4 {
#         synth=easyfm;
#     }
#     (0,1) @a {
#         view=pianoroll;
#         top=a6;
#         bot=a1;
#     }
# }
# 
# @synths
#   (0,0) easyfm easyfm2 multi {
#   }
# 
# @connections
#   easyfm:out system:out
# 
# """


def compute_view_height(config):
    mode = unwrap(config.get('view', Unk('staves')))
    if mode == "pianoroll":
        top = config.get('top', 69 + 12)
        bot = config.get('bot', 69 - 12)
        return math.ceil((int(top) - int(bot) + 1) / 3)
    else:
        above = config.get('above', 0)
        count = config.get('count', 1)
        below = config.get('below', 0)
        return 2*(above + count + below)

class DocumentProcessing:
    def __init__(self, doc):
        self.doc = doc
        self.declarations = {}
        self.dimensions   = {}
        for declaration in doc.declarations:
            self.declarations[declaration.name] = declaration

    def get_dimensions(self, decl, rhythm_config, key):
        duration = 1
        height = 1
        this_config = rhythm_config | decl.properties
        for i, e in enumerate(decl.entities):
            s = e.shift
            l = e.lane
            config = this_config | e.properties
            if isinstance(e, ClipEntity):
                d, h = self.get_dimensions(self.declarations[e.name], config, key + (i,))
                duration = max(duration, d+s)
                height   = max(height, l+h)
            elif isinstance(e, BrushEntity):
                expr = evaluate_all(config, e.expr)
                data, d = self.compute_pattern(expr, config)
                self.dimensions[key + (i,)] = d, 1, config, expr, data
                duration = max(duration, d+s)
                height   = max(height, l + 1)
        for i, e in enumerate(decl.entities):
            s = e.shift
            l = e.lane
            d = duration - e.shift
            config = this_config | e.properties
            if isinstance(e, ViewEntity):
                h = compute_view_height(config)
                d = min(d, config.get('duration', d))
                self.dimensions[key + (i,)] = d, h, config, None, None
                height   = max(height, l+h)
        self.dimensions[key] = duration, height, this_config, None, None
        return duration, height

    def construct(self, sb, decl, shift, key, rhythm_config):
        bound = shift+1
        rhythm_config = rhythm_config | decl.properties
        for i, e in enumerate(decl.entities):
            k = key + (i,)
            s = shift + e.shift
            config = rhythm_config | e.properties
            if isinstance(e, ClipEntity):
                subdecl = self.declarations[e.name]
                d = self.construct(sb, subdecl, s, k, config)
                bound = max(bound, s+d)
            if isinstance(e, BrushEntity):
                expr       = evaluate_all(config, e.expr)
                pattern, d = self.compute_pattern(expr, config)
                match config["brush"]:
                    case Unk("hocket"):
                        cons = self.construct_hocket
                    case Unk("gate"):
                        cons = self.construct_gate
                    case Unk("once"):
                        cons = self.construct_once
                    case Unk("quadratic"):
                        cons = self.construct_quadratic
                    case Unk("slide"):
                        cons = self.construct_slide
                    case Unk("control"):
                        cons = self.construct_control
                    case _:
                        cons=None
                if cons:
                    cons(sb, config, pattern, s, k)
                bound = max(bound, s+d)
        return bound - shift

    def compute_pattern(self, exprs, config):
        events = []
        def is_grace(this):
            return isinstance(this, Note) and this.style == "g"
        def resolve(this):
            if this is None:
                return 1.0
            if isinstance(this.symbol, int):
                duration = this.symbol
            else:
                duration = note_durations[this.symbol]
            dot = duration / 2
            for _ in range(this.dots):
                duration += dot
                dot /= 2
            return float(duration)
        def compute_note(t, note, duration):
            if isinstance(note, Note):
                match note.style:
                    case "s":
                        d = duration * config['staccato']
                    case "t":
                        d = duration * config['tenuto']
                    case "g":
                        d = duration * config['normal']
                    case None:
                        d = duration * config['normal']
                assert isinstance(note.group, Dict), str(note.group)
                events.append((t,d,note.group))
            elif isinstance(note, Tuplet):
                s = t
                grace = 0.0
                total = sum(resolve(n.duration) for n in note.mhs if not is_grace(n))
                subrate = duration / total if total != 0 else duration
                for subnote in note.mhs:
                    subduration = resolve(subnote.duration) * subrate
                    if is_grace(subnote):
                        compute_note(s, subnote, subduration)
                        grace += subduration
                    else:
                        subduration = max(subduration - grace, 0.0)
                        grace    = 0
                        compute_note(s, subnote, subduration)
                        s += subduration
        t = 0.0
        grace = 0.0
        rate = config["beats_per_measure"] / config["beat_division"]
        for expr in exprs:
            duration = resolve(expr.duration) * rate
            if is_grace(expr):
                compute_note(t, expr, duration)
                grace += duration
            else:
                duration = max(duration - grace, 0.0)
                grace    = 0
                compute_note(t, expr, duration)
                t += duration
        return events, t

    def construct_hocket(self, sb, config, pattern, shift, key):
        tag_normal = unwrap(config["synth"])
        for i, (start, duration, group) in enumerate(pattern):
            for j, v in enumerate(self.cartesian(group)):
                tag = v.get("synth", tag_normal)
                sb.note(tag, shift+start, duration, key + (i,j,), prune(v))

    def construct_gate(self, sb, config, pattern, shift, key):
        tag = config["synth"]
        for i, (start, duration, group) in enumerate(pattern):
            for j, v in enumerate(self.cartesian(group)):
                sb.note(unwrap(tag), shift+start, duration, key + (i,j,), prune(v))

    def construct_once(self, sb, config, pattern, shift, key):
        tag = config["synth"]
        for i, (start, duration, group) in enumerate(pattern):
            for j, v in enumerate(self.cartesian(group)):
                sb.once(shift+start, unwrap(tag), prune(v))

    def construct_slide(self, sb, config, pattern, shift, key):
        tag = config["synth"]
        i = None
        for i, (start, duration, group) in enumerate(pattern):
            for j, v in enumerate(self.cartesian(group)):
                sb.gate(shift+start, unwrap(tag), key, prune(v))
        if i is not None:
            sb.gate(shift+start+duration, tag, key, prune(v))

    def construct_quadratic(self, sb, config, pattern, shift, key):
        tag = config["synth"]
        for i, (start, duration, group) in enumerate(pattern):
            for j, v in enumerate(self.cartesian(group)):
                v = prune(v)
                if "value" in v:
                    sb.quadratic(shift+start, unwrap(tag), bool(v.get("transition", False)), v["value"])

    def construct_control(self, sb, config, pattern, shift, key):
        tag = config["synth"]
        for i, (start, duration, group) in enumerate(pattern):
            for j, v in enumerate(self.cartesian(group)):
                sb.control(shift+start, unwrap(tag), prune(v))

    def cartesian(self, group):
        def resolve(v):
            if isinstance(v, Dynamic):
                return dynamics_to_dbfs.get(v.name, None)
            if isinstance(v, Ref):
                return None
            if isinstance(v, Unk):
                return v.name
            return v
        out = [{}]
        for name, values in group.items():
            out = [
                xs | {name: resolve(v)}
                for v in values
                for xs in out]
        return out

def unwrap(value):
    return value.name if isinstance(value, (Unk,Ref)) else value

def prune(values):
    return {key:value for key,value in values.items() if not isinstance(value, str)}

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
        if os.path.exists(self.filename):
            self.doc = from_file(self.filename)
            self.proc = DocumentProcessing(self.doc)
            if self.filename.endswith(".json"):
                self.filename = self.filename[:-5]
        #self.png_directory = os.path.abspath(
        #    os.path.splitext(self.filename)[0] + ".png")
        self.wav_filename = os.path.abspath(
            os.path.splitext(self.filename)[0] + ".wav")
        directory = os.path.dirname(os.path.abspath(self.filename))
        synthdef_directory = os.path.join(directory,"synthdefs")
        # may also accept one level lower.
        if not os.path.exists(synthdef_directory):
            directory = os.path.dirname(directory)
            synthdef_directory = os.path.join(directory,"synthdefs")


        self.transport = Transport(
            synthdef_directory = synthdef_directory)
        self.transport.set_online()
        self.transport.refresh(self.proc)
        self.transport.set_fabric()
        self.transport.toggle_play()

        self.mode = "track"
        self.cell_view = NodeView(self)
        # TODO: this stack is going away in favor of selection/prompt/response
        self.selected = "main",
        self.stack_index = None
        self.rhythm_index = None

        self.scroll_ox = None
        self.scroll_x = 0
        self.timeline = TimelineControl()
        self.track_scroll = (0,0)

        self.midi_status = False
        self.midi_controllers = []

        self.selection = Cont()
        self.response = ""
        self.prompt = Text("", 0, None)
        self.refresh_in = None
        self.query_info_text = Text("", 0, None)

    def run_command(self, com=None):
        was_none = com is None
        try:
            if was_none:
                com = command_from_string(self.prompt.text)
            finger = com.apply(self.selection, self.doc, self)
            self.doc = finger.writeback()
            self.selection = finger.to_command()
            self.response = str(self.selection)
            if was_none:
                self.prompt = Text("", 0, None)
            if isinstance(finger, AttributeFinger):
                self.response += " = " + str(finger.value)
            elif isinstance(finger, CoordsFinger):
                self.response += " : " + type(finger.entity).__name__
            elif isinstance(finger, (SequenceFinger, IndexFinger, RangeFinger)):
                f = formatted(finger.get_header(), finger.get_selection(), False)
                self.response += " := " + pformat_doc(f, 80)
                if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                    txt = ":= " + pformat_doc(f, 80)
                    self.prompt = Text(txt, len(txt), None)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.response = repr(e)
        else:
            self.after_rewrite()

    def after_rewrite(self):
        self.proc = DocumentProcessing(self.doc)
        self.transport.refresh(self.proc)

    def run(self):
        ui = SIMGUI(self.present)

        while ui.running:
            dt = self.clock.tick(self.fps) / 1000.0
            if self.refresh_in is not None:
                self.refresh_in -= dt
                if self.refresh_in <= 0.0:
                    self.refresh_in = None
                    if self.transport.definitions.temp_refresh():
                        self.transport.refresh(self.proc)
                        self.transport.restart_fabric()
                    

            ui.process_events()
            self.screen.fill((30, 30, 30))
            ui.draw(self.screen)
            pygame.display.flip()


        self.transport.set_offline()
        self.set_midi_off()
        pygame.quit()
        sys.exit()

    def present(self, ui):
        top_grid = Grid(0, 0, 24, 24)
        bot_grid = Grid(0, self.screen_height - 24, 24, 24)
        main_grid = Grid(
            self.MARGIN - self.scroll_x * self.BAR_WIDTH,
            24, self.BAR_WIDTH, self.LANE_HEIGHT)
        main_rect = pygame.Rect(self.MARGIN, 24, self.screen_width - self.MARGIN, self.screen_height - 48)

        side_rect = pygame.Rect(0, 24, self.MARGIN, self.screen_height - 48)

        fullfinger = self.selection.apply(None, self.doc, self)
        is_track = isinstance(fullfinger, (SequenceFinger, IndexFinger, RangeFinger))
        if self.mode == "synthdef":
            if ui.textbox(self.query_info_text, pygame.Rect(0, 48, self.MARGIN, 32), "query-info"):
                tx = self.query_info_text.text
                for name in synthlang.available_libraries:
                    if name.startswith(tx):
                        print(synthlang.available_libraries[name])
            if ui.widget(SynthdefEditor(self, main_rect, "synthdef-editor")):
                self.refresh_in = 0.5
        elif self.mode == "track" and is_track:
            main_grid = Grid(
                self.MARGIN - self.track_scroll[0] * self.BAR_WIDTH / 4,
                24 - self.track_scroll[1] * self.LANE_HEIGHT, self.BAR_WIDTH / 4, self.LANE_HEIGHT)

            config, views = fullfinger.get_config_views(default_rhythm_config)
            finger, spath = fullfinger.get_track_selection()

            ui.label(str(list(views.keys())), top_grid(0,1,10,2))
            ui.widget(TrackEditorWidget(
                self,
                main_grid,
                main_rect,
                config,
                finger,
                fullfinger,
                spath,
                views,
                "track-editor"))
        elif self.mode == "track":
            ui.widget(GridWidget(self, main_rect, "grid"))
            edit_widgets = []
            def traverse_decl(decl, x, y, kv, d=1):
                views = {}
                for i, e in enumerate(decl.entities):
                    ix = x + e.shift
                    iy = y + e.lane
                    key = kv + (i,)
                    w, h, config, expr, data = self.proc.dimensions[key]
                    if isinstance(e, BrushEntity):
                    #    if self.selected == key and self.stack_index is not None:
                    #        trackline = main_grid(ix, iy, ix+w, iy+h)
                        brush = config["brush"]
                        synth = config["synth"]
                        if ui.widget(PatLane(f"{brush} {synth}",
                            main_grid(ix, iy, ix+w, iy+h),
                            key,
                            config, expr, data, main_grid.offset(ix,iy)
                            )):
                            self.selected = key
                            self.stack_index = None
                        for name, dtype, vw in e.header:
                            views.setdefault(vw,[]).append((name, dtype, data, ix, e))
                    elif isinstance(e, ClipEntity):
                        sdecl = self.proc.declarations[e.name]
                        if ui.widget(Lane(e.name,
                            main_grid(ix, iy, ix+w, iy+h),
                            key)):
                            self.selected = key
                            self.stack_index = None
                        subviews = traverse_decl(sdecl, ix, iy, key, d+1)
                        for vw, g in subviews.items():
                            views.setdefault(vw,[]).extend(g)
                for i, e in enumerate(decl.entities):
                    if not isinstance(e, ViewEntity):
                        continue
                    ix = x + e.shift
                    iy = y + e.lane
                    key = kv + (i,)
                    w, h, config, expr, data = self.proc.dimensions[key]
                    ui.widget(ViewWidget(
                        config,
                        main_grid(ix, iy, ix+w, iy+h),
                        views.get(e.name, []),
                        main_grid,
                        key))
                    #edit_widgets.append(e)
                return views

            main_decl = self.proc.declarations['main']
            w, h = self.proc.get_dimensions(main_decl, default_rhythm_config, ("main",))
            ui.widget(Lane("main", main_grid(0,0,w,h), "main"))
            traverse_decl(main_decl, 0, 0, ("main",))
            
            ui.widget(TransportVisual(self.transport, main_grid, main_rect,
                "transport-visual"))
            if what := ui.widget(Scroller(self, main_rect, main_grid, "scroller")):
                if what[0] == "pick":
                    com = SearchCoords(ByName(Cont(), "main"), *what[1])
                    self.run_command(com)
                elif what[0] == "scroll":
                    editor.scroll_x = what[1]

            ui.widget(Sidepanel(side_rect, "sidepanel"))
            if self.selected is not None:
                y = 24
                top = self.proc.declarations[self.selected[0]]
                sel = (self.selected[0],)
                if ui.button(top.name, pygame.Rect(0, y, self.MARGIN, 24), sel):
                    self.selected = sel
                    self.stack_index = None
                y += 24
                for i in self.selected[1:]:
                    sel += (i,)
                    if isinstance(top, ClipDecl):
                        mid = top.entities[i]
                        if isinstance(mid, ClipEntity):
                            top = self.proc.declarations[mid.name]
                            if ui.button(top.name, pygame.Rect(0, y, self.MARGIN, 24), sel):
                                self.selected = sel
                                self.stack_index = None
                            y += 24
                        if isinstance(mid, CommandEntity):
                            if ui.button(f"{mid.flavor} {mid.instrument}",
                                pygame.Rect(0, y, self.MARGIN, 24),
                                sel):
                                self.selected = sel
                                self.stack_index = None
                            top = mid
                        if isinstance(mid, StavesEntity):
                            if ui.button(f"staves {mid.name}",
                                pygame.Rect(0, y, self.MARGIN, 24),
                                sel):
                                self.selected = sel
                                self.stack_index = None
                        if isinstance(mid, PianorollEntity):
                            if ui.button(f"pianoroll {mid.name}",
                                pygame.Rect(0, y, self.MARGIN, 24),
                                sel):
                                self.selected = sel
                                self.stack_index = None
                y += 12 + 24
                #if isinstance(top, CommandEntity):
                #    comp = top.component
                #    k = 0
                #    while comp:
                #        kur = "-> " if k == self.stack_index else ""
                #        if isinstance(comp, FromRhythm):
                #            if ui.button(kur + f"{comp.name}",
                #                pygame.Rect(0, y, self.MARGIN, 24), (sel, k)):
                #                self.stack_index = k
                #            comp = None
                #        elif isinstance(comp, Overlay):
                #            if ui.button(kur + f"{comp.name}:{comp.dtype}:{comp.view}",
                #                pygame.Rect(0, y, self.MARGIN, 24), (sel, k)):
                #                self.stack_index = k
                #            comp = comp.base
                #        elif isinstance(comp, Repeated):
                #            if ui.button(kur + f"repeat {comp.count}",
                #                pygame.Rect(0, y, self.MARGIN, 24), (sel, k)):
                #                self.stack_index = k
                #            comp = comp.base
                #        elif isinstance(comp, Renamed):
                #            if ui.button(kur + f"rename {comp.src} to {comp.dst}",
                #                pygame.Rect(0, y, self.MARGIN, 24), (sel, k)):
                #                self.stack_index = k
                #            comp = comp.base
                #        elif isinstance(comp, Durated):
                #            if ui.button(kur + f"duration {comp.duration}",
                #                pygame.Rect(0, y, self.MARGIN, 24), (sel, k)):
                #                self.stack_index = k
                #            comp = comp.base
                #        elif isinstance(comp, WestRhythm):
                #            if ui.button(kur + "rhythm",
                #                pygame.Rect(0, y, self.MARGIN, 24), (sel, k)):
                #                self.stack_index = k
                #            comp = None
                #        elif isinstance(comp, StepRhythm):
                #            if ui.button(kur + "step",
                #                pygame.Rect(0, y, self.MARGIN, 24), (sel, k)):
                #                self.stack_index = k
                #            comp = None
                #        elif isinstance(comp, EuclideanRhythm):
                #            if ui.button(kur + "euclidean",
                #                pygame.Rect(0, y, self.MARGIN, 24), (sel, k)):
                #                self.stack_index = k
                #            comp = None
                #        else:
                #            assert False, comp
                #        y += 24
                #        k += 1
                #    if self.stack_index is not None and trackline is not None:
                #        comp = top.component
                #        for _ in range(self.stack_index):
                #            comp = comp.base
                #        modrect = pygame.Rect(trackline.left, self.screen_height - 24 - self.LANE_HEIGHT * 4, trackline.width, self.LANE_HEIGHT * 4)
                #        u = Grid(self.MARGIN, modrect.top, 24, self.LANE_HEIGHT)
                #        if isinstance(comp, Overlay):
                #            for widget in edit_widgets:
                #                if ui.widget(Editing(widget, top, comp)):
                #                    self.after_rewrite()
                #        elif isinstance(comp, WestRhythm):
                #            W = sum(float(e.duration) for e in comp.sequence)
                #            g = Grid(modrect.left, modrect.top, modrect.width / W, self.LANE_HEIGHT)
                #            t = 0.0
                #            for k, x in enumerate(comp.sequence):
                #                d = float(x.duration)
                #                if ui.button(str(x), g(t, 2, t+d, 3), f"step-{k}"):
                #                    self.rhythm_index = k
                #                t += d
                #            if self.rhythm_index is not None:
                #                X = comp.sequence[self.rhythm_index]
                #                p = comp.sequence[self.rhythm_index].duration.symbol
                #                n = comp.sequence[self.rhythm_index].duration.dots
                #                if ui.button("+|", u(18, 1, 20, 2), "set-left"):
                #                    comp.sequence.insert(self.rhythm_index, Note(Duration("q", 0), None, None))
                #                    self.after_rewrite()
                #                if len(comp.sequence) > 1 and ui.button("DEL", u(20, 1, 22, 2), "set-del"):
                #                    del comp.sequence[self.rhythm_index]
                #                    self.rhythm_index = None
                #                if ui.button("|+", u(22, 1, 24, 2), "set-right"):
                #                    comp.sequence.insert(self.rhythm_index+1, Note(Duration("q", 0), None, None))
                #                    self.rhythm_index += 1
                #                    self.after_rewrite()
                #                if ui.button("'", u(4, 1, 5, 2), "set-stac"):
                #                    if isinstance(X, Rest):
                #                        comp.sequence[self.rhythm_index] = Note(X.duration, None, None)
                #                    comp.sequence[self.rhythm_index].style = "staccato"
                #                    self.after_rewrite()
                #                if ui.button(" ", u(5, 1, 6, 2), "set-normal"):
                #                    if isinstance(X, Rest):
                #                        comp.sequence[self.rhythm_index] = Note(X.duration, None, None)
                #                    comp.sequence[self.rhythm_index].style = None
                #                    self.after_rewrite()
                #                if ui.button("_", u(6, 1, 7, 2), "set-ten"):
                #                    if isinstance(X, Rest):
                #                        comp.sequence[self.rhythm_index] = Note(X.duration, None, None)
                #                    comp.sequence[self.rhythm_index].style = "tenuto"
                #                    self.after_rewrite()
                #                if ui.button("~", u(7, 1, 8, 2), "set-rest"):
                #                    comp.sequence[self.rhythm_index] = Rest(X.duration)
                #                    self.after_rewrite()
                #                for i, dyn in enumerate(dynamics_to_dbfs, 10):
                #                    if ui.button(dyn, u(i, 0, i+1, 1), "set-" + dyn):
                #                        comp.sequence[self.rhythm_index].dynamic = dyn
                #                        self.after_rewrite()
                #                if ui.button("", u(i+1, 0, i+2, 1), "set-nodyn"):
                #                    comp.sequence[self.rhythm_index].dynamic = None
                #                    self.after_rewrite()
                #                for i, m in enumerate("vutseqhwx"):
                #                    if ui.button(m, u(i, 0, i+1, 1), "set-" + m):
                #                        comp.sequence[self.rhythm_index].duration = Duration(m, n)
                #                        self.after_rewrite()
                #                if ui.button(".-", u(0, 1, 1, 2), "less-dots"):

                #                    n = max(0, n-1)
                #                    comp.sequence[self.rhythm_index].duration = Duration(p, n)
                #                    self.after_rewrite()
                #                if ui.button(".+", u(1, 1, 2, 2), "more-dots"):

                #                    n = n+1
                #                    comp.sequence[self.rhythm_index].duration = Duration(p, n)
                #                    self.after_rewrite()
                #            
                #        elif isinstance(comp, StepRhythm):
                #            g = Grid(modrect.left, modrect.top, modrect.width / len(comp.sequence), self.LANE_HEIGHT)
                #            if ui.button("+", u(1, 0, 2, 1), "more-rhythm"):
                #                comp.sequence.append(0)
                #                self.after_rewrite()
                #            if ui.button("-", u(0, 0, 1, 1), "less-rhythm"):
                #                if len(comp.sequence) > 1:
                #                    comp.sequence.pop()
                #                self.after_rewrite()
                #            for k, x in enumerate(comp.sequence):
                #                if ui.button(str(x), g(k, 1, k+1, 2), f"step-{k}"):
                #                    comp.sequence[k] = 1 - x
                #                    self.after_rewrite()
                #        elif isinstance(comp, EuclideanRhythm):
                #            if ui.button("P+", u(1, 0, 2, 1), "more-pulses"):
                #                comp.pulses = min(comp.steps, comp.pulses+1)
                #                self.after_rewrite()
                #            if ui.button("P-", u(0, 0, 1, 1), "less-pulses"):
                #                comp.pulses = max(0, comp.pulses - 1)
                #                self.after_rewrite()
                #            if ui.button("S+", u(3, 0, 4, 1), "more-steps"):
                #                comp.steps = comp.steps + 1
                #                self.after_rewrite()
                #            if ui.button("S-", u(2, 0, 3, 1), "less-steps"):
                #                comp.steps = max(1, comp.steps - 1)
                #                comp.pulses = min(comp.pulses, comp.steps)
                #                self.after_rewrite()
                #            if ui.button("<-", u(4, 0, 5, 1), "rot-left"):
                #                comp.rotation = comp.rotation + 1
                #                self.after_rewrite()
                #            if ui.button("->", u(5, 0, 6, 1), "rot-right"):
                #                comp.rotation = comp.rotation - 1
                #                self.after_rewrite()
                #            ui.label(f"{comp.pulses} {comp.steps} {comp.rotation}", u(0, 1, 10, 2))
                #        else:   
                #            if ui.button("modify", modrect, "modify-it"):
                #                pass

        if self.mode == "synth":
            ui.widget(self.transport.get_spectroscope())
            self.cell_view.present(ui)
        if self.mode == "file":
            if ui.button(f"record {os.path.basename(self.wav_filename)!r}", main_grid(0, 0, 4, 1), "record-button"):
                self.render_score()
            if ui.button(f"save {os.path.basename(self.filename)!r}", main_grid(0, 2, 4, 3), "save-button"):
                self.save_file()

        if ui.tab_button(self.mode, "file", bot_grid(0, 0, 5, 1),  "file-tab", allow_focus=False):
            self.mode = "file"
        elif ui.tab_button(self.mode, "track", bot_grid(5, 0, 10, 1),  "track-tab", allow_focus=False):
            self.mode = "track"
        elif ui.tab_button(self.mode, "synth", bot_grid(10, 0, 15, 1),  "cell-tab", allow_focus=False):
            self.mode = "synth"
        elif ui.tab_button(self.mode, "synthdef", bot_grid(15, 0, 20, 1),  "edit-tab", allow_focus=False):
            self.mode = "synthdef"
        ui.label(self.response, bot_grid(0, -1, 50, 0))
        if ui.textbox(self.prompt, bot_grid(20, 0, 50, 1), "prompt"):
            if self.prompt.return_pressed:
                self.run_command()

        self.transport_bar(ui, top_grid)

        # self.timeline_head = 0
        # self.timeline_tail = 0
        # self.timeline_scroll = 0
        # self.timeline_vertical_scroll = 0

        # self.lane_tag = None

        # self.view_view = ViewView(self)
        # self.track_view = TrackView(self)

        # self.view = "file"
        # #self.layout = TrackLayout(self.doc, offset = 30)
        # self.refresh_layout()

    def transport_bar(self, ui, grid):
        grid = Grid(0, 0, 24, 24)
        if ui.widget(OnlineButton(self, grid(0, 0, 1, 1), "online")):
            self.transport.set_online()
        if ui.widget(FabricButton(self, grid(1, 0, 2, 1), "fabric")):
            self.transport.set_fabric_and_stop()
        if ui.widget(PlayButton(self, grid(2, 0, 3, 1), "play")):
            if self.transport.status <= 1:
                self.transport.set_fabric()
            self.transport.toggle_play()
        if ui.button(["midi=off", "midi=on"][self.midi_status],
            grid(3, 0, 6, 1), "midi status", allow_focus=False):
            self.toggle_midi()
        if ui.button(["loop=off", "loop=on"][self.transport.playback_loop],
            grid(6, 0, 9, 1), "loop status", allow_focus=False):
            self.transport.playback_loop = not self.transport.playback_loop
            if (status := self.transport.get_playing()) is not None:
                self.transport.set_fabric()
                sequence = self.transport.sequence
                self.transport.set_playing(Sequencer(sequence, point=sequence.t(status), **self.transport.playback_params(sequence)))
        ui.widget(Trackline(self, self.timeline,
            pygame.Rect(self.MARGIN, 0, self.screen_width - self.MARGIN, 24),
            "trackline"))

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

    def save_file(self):
        with open(self.filename, "w", encoding='utf-8') as fd:
            fd.write(repr(self.doc))
        print("document saved!")

    def render_score(self):
        self.transport.set_offline()

        proc = self.proc
        sb = SequenceBuilder2(self.transport.group_ids, self.transport.definitions.descriptors(proc.doc.synths))
        duration = proc.construct(sb,
            proc.declarations["main"], 0, ("main",),
            default_rhythm_config)
        sequence = sb.build(duration)

        score = supriya.Score(output_bus_channel_count=2)
        clavier = {}
        with score.at(0):
            fabric = Fabric(score, self.doc.synths, self.doc.connections, self.transport.definitions)
        for command in sequence.com:
            with score.at(command.time):
                command.send(clavier, fabric)
        with score.at(sequence.t(duration)):
            score.do_nothing()
        supriya.render(score, output_file_path=self.wav_filename)
        print("saved", self.wav_filename)

        self.transport.set_online()
        self.transport.refresh(self.proc)

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
class TrackEditorWidget:
    editor : Editor
    grid : Grid
    rect : pygame.Rect
    config : Dict[str, Value]
    finger : Finger
    fullfinger : Finger
    spath : List[Any]
    views : Dict[str, Dict[str, Value]]
    widget_id : Any

    def behavior(self, ui):
        editor = self.editor
        if self.rect.collidepoint(ui.mouse_pos):
            if ui.mouse_just_pressed and ui.active_id is None:
                ui.active_id = self.widget_id
            if ui.r_mouse_just_pressed and ui.r_active_id is None:
                ui.r_active_id = self.widget_id
                editor.scroll_ox = ui.mouse_pos, editor.track_scroll
        if ui.r_mouse_pressed and ui.r_active_id == self.widget_id:
            (mx, my), (ox, oy) = editor.scroll_ox
            editor.track_scroll = (
                ox - round((ui.mouse_pos[0]-mx) / self.grid.w),
                oy - round((ui.mouse_pos[1]-my) / self.grid.h))
            return ("scroll", editor.track_scroll)
        output = None

        ui.grab_focus(self)

        finger = self.fullfinger
        if ui.focused_id == self.widget_id:
            count = None
            if isinstance(finger, SequenceFinger):
                count = finger.expr.length
                finger = finger.range_of(count, 0)
            elif isinstance(finger, IndexFinger):
                count = finger.parent.expr.length
            elif isinstance(finger, RangeFinger):
                count = finger.parent.expr.length
            if count is not None:
                if ui.keyboard_key == pygame.K_LEFT:
                    if isinstance(finger, IndexFinger):
                        finger = finger.parent.range_of(finger.index, finger.index)
                    elif isinstance(finger, RangeFinger):
                        head = max(0, finger.head-1)
                        if ui.keyboard_mod & pygame.KMOD_SHIFT:
                            finger = finger.parent.range_of(head, finger.tail)
                        else:
                            finger = finger.parent.range_of(head, head)
                    editor.run_command(cmd := finger.to_command())
                    return "run", cmd
                if ui.keyboard_key == pygame.K_RIGHT:
                    if isinstance(finger, IndexFinger):
                        finger = finger.parent.range_of(finger.index+1, finger.index+1)
                    elif isinstance(finger, RangeFinger):
                        head = min(count, finger.head+1)
                        if ui.keyboard_mod & pygame.KMOD_SHIFT:
                            finger = finger.parent.range_of(head, finger.tail)
                        else:
                            finger = finger.parent.range_of(head, head)
                    editor.run_command(cmd := finger.to_command())
                    return "run", cmd
                if ui.keyboard_key == pygame.K_UP:
                    editor.run_command(cmd := Up(finger.to_command()))
                    return "run", cmd
                if ui.keyboard_text in note_durations:
                    finger = finger.write_sequence(Note.mk(Duration(ui.keyboard_text,0), None, {}))
                    self.editor.doc = finger.writeback()
                    editor.run_command(cmd := finger.to_command())
                    return "run", cmd

        selection = ByRef(self.finger.to_command())
        k = 0
        def point_header(header, t):
            nonlocal k, output
            i = t
            rect = self.grid(k,i,(k+1),i+1)
            i += 1
            for name, dtype, view in header:
                rect = self.grid(k,i,(k+1),i+1)
                i += 1
            k += 1
            return i
        def point_notes(exprs, t, header, selection):
            nonlocal k, output
            h = t
            for ix, node in enumerate(exprs):
                this = IndexOf(selection, ix)
                
                if isinstance(node, Note):
                    i = t
                    rect = self.grid(k,i,(k+1),i+1)
                    if ui.mouse_just_pressed and rect.collidepoint(ui.mouse_pos):
                        editor.run_command(this)
                        output = "run", this
                    i += 1
                    for name, dtype, view in header:
                        data = node.group.get(name, None)
                        if view is not None and view != "+" and view in self.views:
                            config = self.views[view]
                            H = compute_view_height(config)
                            rect = self.grid(k,i,(k+1),i+H)
                            if ui.mouse_just_pressed and rect.collidepoint(ui.mouse_pos):
                                on_pianoroll, pitch = point_view(config, rect, ui.mouse_pos)
                                group = node.group.copy()
                                previous = group.pop(name, [])
                                now = []
                                if on_pianoroll:
                                    m = int(pitch)
                                    for n in previous:
                                        if int(n) != m:
                                            now.append(n)
                                    if len(now) == len(previous):
                                        now.append(pitch)
                                else:
                                    m = pitch.position
                                    for n in previous:
                                        p = (n if isinstance(n, music.Pitch) else music.Pitch.from_midi(int(n))).position
                                        if p != m:
                                            now.append(n)
                                    if len(now) == len(previous):
                                        now.append(pitch)
                                now.sort(key=int)
                                group[name] = now
                                that = WriteSequence(this, Note.mk(node.duration, node.style, group))
                                editor.run_command(that)
                                output = "run", that
                            i += H
                        else:
                            rect = self.grid(k,i,(k+1),i+1)
                            if ui.mouse_just_pressed and rect.collidepoint(ui.mouse_pos):
                                editor.run_command(this)
                                output = "run", this
                            i += 1
                    k += 1
                    h = max(h,i)
                elif isinstance(node, Tuplet):
                    s = k
                    i = point_notes(node.mhs, t, header, LhsOf(this))
                    e = k = max(k,s+2)
                    g = self.grid(s,i,(k),i+1)
                    if ui.mouse_just_pressed and g.collidepoint(ui.mouse_pos):
                        editor.run_command(this)
                        output = "run", this
                    h = max(h,i+1)
                    k = e
                elif isinstance(node, Fx):
                    s = k
                    i = point_notes(node.lhs, t, header, LhsOf(this))
                    e = k = max(k,s+2)
                    g = self.grid(s,i,(k),i+1)
                    k = s
                    if node.rhs != empty:
                        hdr = decorated_header(node.header, node.rhs)
                        p = point_notes(node.rhs, i+1, hdr, RhsOf(this))
                        q = point_header(hdr, i+1)
                        h = max(h,p,q)
                    else:
                        h = max(h,i+1)
                    k = max(k,e)
                    if ui.mouse_just_pressed and g.collidepoint(ui.mouse_pos):
                        editor.run_command(this)
                        output = "run", this
            return h

        brush = self.finger.entity
        hdr = decorated_header(brush.header, brush.expr)
        point_header(hdr, 0)
        point_notes(brush.expr, 0, hdr, selection)
        return output

    def draw(self, ui, screen):
        k = 0
        def draw_header(header, t):
            nonlocal k
            i = t
            surf = ui.font16.render("rhythm", True, (200, 200, 200))
            rect = surf.get_rect(center=self.grid(k,i,(k+1),i+1).center)
            screen.blit(surf, rect)
            i += 1
            for name, dtype, view in header:
                if view == "+":
                    name = "(" + name + ")"
                surf = ui.font16.render(name, True, (200, 200, 200))
                rect = surf.get_rect(center=self.grid(k,i,(k+1),i+1).center)
                screen.blit(surf, rect)
                i += 1
            k += 1
            return i
        def shift(name, spath):
            if isinstance(spath, list) and len(spath) > 0 and spath[0] == name:
                return spath[1:]
            return None
        def on_start(spath):
            if isinstance(spath, list) and len(spath) == 1 and isinstance(spath[0], tuple):
                return spath[0][0]
        def on_stop(spath):
            if isinstance(spath, list) and len(spath) == 1 and isinstance(spath[0], tuple):
                return spath[0][1]
        def on_empty(spath):
            if is_here(spath):
                return True
            return isinstance(spath, list) and len(spath) == 1 and spath[0] == (0,0)
        def is_here(spath):
            return isinstance(spath, list) and len(spath) == 0
        def draw_notes(exprs, t, header, spath_here):
            nonlocal k
            h = t
            if exprs == empty:
                if is_here(spath_here) or on_empty(spath_here):
                    g = self.grid(k - 0.1, t, k + 4 + 0.1, h)
                    pygame.draw.rect(screen, (100, 100, 200), g, 4, 3)
                k += 4
                return t+1
            sel_start_k = None
            sel_stop_k = None
            if is_here(spath_here):
                sel_start_k = k
            for pos, node in enumerate(exprs):
                spath = shift(pos, spath_here)
                if is_here(spath) or on_start(spath_here) == pos:
                    sel_start_k = k
                if on_stop(spath_here) == pos:
                    sel_stop_k = k
                if isinstance(node, Note):
                    i = t
                    D = str(node.duration) if node.duration else "*"
                    if node.style:
                        D = " " + node.style
                    surf = ui.font16.render(D, True, (200, 200, 200))
                    rect = surf.get_rect(center=self.grid(k,i,(k+1),i+1).center)
                    screen.blit(surf, rect)
                    i += 1
                    for name, dtype, view in header:
                        data = node.group.get(name, None)
                        if view is not None and view != "+" and view in self.views:
                            config = self.views[view]
                            H = compute_view_height(config)
                            G = self.grid(k,i,(k+1),i+H).inflate((-4, 0))
                            draw_view(screen, config, G)
                            draw_view_note(screen, config, G, data)
                            i += H
                        else:
                            if data is None:
                                data = "_"
                            else:
                                data = ":".join(str(x) for x in data)
                            surf = ui.font16.render(data, True, (200, 200, 200))
                            rect = surf.get_rect(center=self.grid(k,i,(k+1),i+1).center)
                            screen.blit(surf, rect)
                            i += 1
                    k += 1
                    h = max(h,i)
                elif isinstance(node, Tuplet):
                    s = k
                    i = draw_notes(node.mhs, t, header, shift("mhs", spath))
                    e = k = max(k,s+2)
                    #if is_here(spath):
                    #    g = self.grid(s, t, k, i)
                    #    pygame.draw.rect(screen, (100, 200, 200), g, 4, 3)
                    g=self.grid(s,i,(k),i+1)
                    pygame.draw.rect(screen, (200, 200, 200), g, 0, 4)
                    surf = ui.font16.render(str(node.duration) if node.duration else "*", True, (30,30,30))
                    rect = surf.get_rect(center=g.center)
                    screen.blit(surf, rect)
                    h = max(h,i+1)
                    k = e
                elif isinstance(node, Fx):
                    s = k
                    i = draw_notes(node.lhs, t, header, shift("lhs", spath))
                    e = k = max(k,s+2)
                    #if is_here(spath):
                    #    g = self.grid(s, t, k, i)
                    #    pygame.draw.rect(screen, (100, 200, 200), g, 4, 3)
                    g = self.grid(s,i,(k),i+1)
                    pygame.draw.rect(screen, (100, 200, 100), g, 0, 4)
                    surf = ui.font16.render("/ " + " ".join(str(a) for a in node.args), True, (30,30,30))
                    rect = surf.get_rect(center=g.center)
                    screen.blit(surf, rect)
                    k = s
                    if node.rhs != empty:
                        hdr = decorated_header(node.header, node.rhs)
                        p = draw_notes(node.rhs, i+1, hdr, shift("rhs", spath))
                        q = draw_header(hdr, i+1)
                        h = max(h,p,q)
                    else:
                        h = max(h,i+1)
                        if on_empty(shift("rhs", spath)):
                            pygame.draw.rect(screen, (100, 200, 200), g, 4, 3)
                    k = max(k,e)
                if on_start(spath_here) == pos+1:
                    sel_start_k = k
                if is_here(spath) or on_stop(spath_here) == pos+1:
                    sel_stop_k = k
            if is_here(spath_here):
                sel_stop_k = k
            if sel_start_k is not None and sel_stop_k is not None:
                g = self.grid(sel_start_k - 0.1, t, sel_stop_k + 0.1, h)
                pygame.draw.rect(screen, (100, 100, 200), g, 4, 3)
            return h

        brush = self.finger.entity
        hdr = decorated_header(brush.header, brush.expr)
        draw_header(hdr, 0)
        draw_notes(brush.expr, 0, hdr, self.spath)

def decorated_header(header, exprs):
    def decorate_header(headset, exprs):
        for node in exprs:
            if isinstance(node, Note):
                headset.update(node.group)
            elif isinstance(node, Tuplet):
                decorate_header(headset, node.mhs)
            elif isinstance(node, Fx):
                decorate_header(headset, node.lhs)
        return headset
    headset = decorate_header(set(), exprs)
    for name, x, y in header:
        headset.discard(name)
    return header + [(name, None, "+") for name in sorted(headset)]

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
    config : Dict[str, Value]
    expr : SequenceNode
    data : List[Tuple[float, float, List[Dict[str, Value]]]]
    grid : Grid

    def draw(self, ui, screen):
        rect = self.rect
        pygame.draw.rect(screen, (50, 50, 50), rect, 0, 4)

        for start,duration,g in self.data:
            if any(len(vs) == 0 for vs in g.values()):
                continue
            rc = self.grid(start, 0.6, start+duration, 0.9)
            pygame.draw.rect(screen, (150, 50, 150), rc, 0, 2)
            pygame.draw.rect(screen, (250, 150, 250), rc, 1, 2)
        pygame.draw.rect(screen, (200, 200, 200), rect, 2, 4)

        surf = ui.font16.render(self.text, True, (200, 200, 200))
        rc = surf.get_rect(top=rect.top + 2, left=rect.left + 6)
        screen.blit(surf, rc)

class Editing:
    def __init__(self, widget, top, comp):
        self.widget = widget
        self.top = top
        self.comp = comp
        self.rect = widget.rect
        self.widget_id = widget.widget_id, "editing"

    def behavior(self, ui):
        ui.grab_active(self)
        note_edited = None
        if ui.hot_id == self.widget_id and isinstance(self.widget, StavesWidget):
            ox, oy = self.rect.topleft
            k = self.rect.height / (self.widget.count + self.widget.above + self.widget.below)
            note_pos = int(round((oy + self.widget.above*k - ui.mouse_pos[1]) / (k / 12) + 40))
            note_edited = music.Pitch(note_pos, 0)
        if ui.hot_id == self.widget_id and isinstance(self.widget, PianorollWidget):
            k = self.rect.height / (self.widget.top - self.widget.bot + 1)
            note_pos = int(round((self.rect.bottom - ui.mouse_pos[1])/k)) + self.widget.bot
            note_edited = music.Pitch.from_midi(note_pos)
        if note_edited is not None:
            if ui.mouse_just_pressed:
                for name, dtype, pat, x, e in self.widget.data:
                    if self.top is e:
                        for (s,d), vg, m in zip(pat.events, pat.values, pat.meta):
                            a = self.widget.grid.point(s + x, 0)[0]
                            b = self.widget.grid.point(s + x + d, 0)[0]
                            if a <= ui.mouse_pos[0] <= b:
                                vals = self.comp.data[m[self.comp.name]]
                                for i,v in enumerate(vals):
                                    if isinstance(v, int):
                                        v = music.Pitch.from_midi(v)
                                    if v.position == note_edited.position:
                                        vals.pop(i)
                                        break
                                else:
                                    vals.append(note_edited)
                                return True

    def draw(self, ui, screen):
        pass

@dataclass(eq=False)
class ViewWidget:
    config : Dict[str, Value]
    rect : pygame.Rect
    data : Any
    grid : Grid
    widget_id : Any

    def behavior(self, ui):
        return None

    def draw(self, ui, screen):
        draw_view(screen, self.config, self.rect)
        draw_view_data(screen, self.config, self.rect, self.data, self.grid)
        pygame.draw.rect(screen, (200,200,200), self.rect, 1, 3)

def draw_view(screen, config, rect):
    mode = unwrap(config.get("view", Unk("staves")))
    if mode == "pianoroll":
        top = int(config.get('top', 69 + 12))
        bot = int(config.get('bot', 69 - 12))
        pygame.draw.rect(screen, (0,0,0), rect, 0, 3)
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
    else:
        above = int(config.get('above', 0))
        count = int(config.get('count', 1))
        below = int(config.get('below', 0))
        key = int(config.get('key', 0))
        pygame.draw.rect(screen, (0,0,0), rect, 0, 3)
        x, y = rect.topleft
        w = rect.width
        k = rect.height / (count + above + below)
        y += above * k
        for _ in range(count):
            for p in range(2, 12, 2):
                pygame.draw.line(screen, (70, 70, 70), (x, y+p*k/12), (x+w, y+p*k/12))
            y += k

def draw_view_note(screen, config, rect, data):
    mode = unwrap(config.get("view", Unk("staves")))
    if data is None:
        pygame.draw.line(screen, (200,200,200), rect.topleft, rect.bottomright)
    elif mode == "pianoroll":
        top = int(config.get('top', 69 + 12))
        bot = int(config.get('bot', 69 - 12))
        x, y = rect.bottomleft
        w = rect.width
        k = rect.height / (top - bot + 1)
        screen.set_clip(rect)
        a = rect.left + 10
        b = rect.right - 10
        for v in data:
            tone = int(v)
            py = y - k*(tone - bot)
            rc = pygame.Rect(a, py-k, b-a, k)
            pygame.draw.rect(screen, (255, 255, 255), rc, 1, 2)
        screen.set_clip(None)
    else:
        above = int(config.get('above', 0))
        count = int(config.get('count', 1))
        below = int(config.get('below', 0))
        key = int(config.get('key', 0))
        screen.set_clip(rect)
        colors = [(0,0,128), (0,0,255), (255,128,0), (255, 0, 0), (128,0,0)]
        k = rect.height / (count + above + below)
        a = rect.left + 10
        b = rect.right - 10
        for tone in data:
            if isinstance(tone, int):
                tone = music.Pitch.from_midi(tone)
            color = colors[tone.accidental+2]
            acci = music.accidentals(key)
            if tone.accidental == acci[tone.position % 7]:
                color = (255,255,255)
            py = rect.top + above*k + (40 - tone.position) * k / 12
            rc = pygame.Rect(a, py - k / 24, b-a, k / 12)
            pygame.draw.rect(screen, color, rc, 1, 2)
        screen.set_clip(None)

def draw_view_data(screen, config, rect, data, grid):
    mode = unwrap(config.get("view", Unk("staves")))
    if mode == "pianoroll":
        top = int(config.get('top', 69 + 12))
        bot = int(config.get('bot', 69 - 12))
        x, y = rect.bottomleft
        w = rect.width
        k = rect.height / (top - bot + 1)
        screen.set_clip(rect)
        for name, dtype, data, x, e in data:
            for s,d, vg in data:
                a = grid.point(s + x, 0)[0]
                b = grid.point(s + x + d, 0)[0]
                for v in vg.get(name,()):
                    tone = int(v)
                    py = y - k*(tone - bot)
                    rc = pygame.Rect(a, py-k, b-a, k)
                    pygame.draw.rect(screen, (255, 255, 255), rc, 1, 2)
        screen.set_clip(None)
    else:
        above = int(config.get('above', 0))
        count = int(config.get('count', 1))
        below = int(config.get('below', 0))
        key = int(config.get('key', 0))
        screen.set_clip(rect)
        colors = [(0,0,128), (0,0,255), (255,128,0), (255, 0, 0), (128,0,0)]
        k = rect.height / (count + above + below)
        for name, dtype, data, x, _ in data:
            for s,d, vg in data:
                a = grid.point(s + x, 0)[0]
                b = grid.point(s + x + d, 0)[0]
                for tone in vg.get(name,()):
                    if isinstance(tone, int):
                        tone = music.Pitch.from_midi(tone)
                    color = colors[tone.accidental+2]
                    acci = music.accidentals(key)
                    if tone.accidental == acci[tone.position % 7]:
                        color = (255,255,255)
                    py = rect.top + above*k + (40 - tone.position) * k / 12
                    rc = pygame.Rect(a, py - k / 24, b-a, k / 12)
                    pygame.draw.rect(screen, color, rc, 1, 2)
        screen.set_clip(None)

def point_view(config, rect, mouse_pos):
    mode = unwrap(config.get("view", Unk("staves")))
    if mode == "pianoroll":
        top = int(config.get('top', 69 + 12))
        bot = int(config.get('bot', 69 - 12))
        x, y = rect.bottomleft
        w = rect.width
        k = rect.height / (top - bot + 1)
        note_pos = int(round((rect.bottom - mouse_pos[1])/k)) + bot
        note_edited = music.Pitch.from_midi(note_pos)
        return True, note_edited
    else:
        above = int(config.get('above', 0))
        count = int(config.get('count', 1))
        below = int(config.get('below', 0))
        key = int(config.get('key', 0))
        ox, oy = rect.topleft
        k = rect.height / (count + above + below)
        note_pos = int(round((oy + above*k - mouse_pos[1]) / (k / 12) + 40))
        note_acc = music.accidentals(key)[note_pos % 7]
        note_edited = music.Pitch(note_pos, note_acc)
        return False, note_edited

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
class Scroller:
    editor : Editor
    rect : pygame.Rect
    grid : Grid
    widget_id : Any

    def behavior(self, ui):
        if self.rect.collidepoint(ui.mouse_pos):
            if ui.mouse_just_pressed and ui.active_id is None:
                ui.active_id = self.widget_id
            if ui.r_mouse_just_pressed and ui.r_active_id is None:
                ui.r_active_id = self.widget_id
                editor.scroll_ox = ui.mouse_pos[0], editor.scroll_x
        if ui.mouse_just_released and ui.active_id == self.widget_id:
            mx, my = ui.mouse_pos
            x = (mx - self.grid.x) // self.grid.w
            y = (my - self.grid.y) // self.grid.h
            return ("pick", (x, y))
        if ui.r_mouse_pressed and ui.r_active_id == self.widget_id:
            x, orig = editor.scroll_ox
            editor.scroll_x = orig - round((ui.mouse_pos[0]-x) / self.editor.BAR_WIDTH)
            return ("scroll", editor.scroll_x)
        return None

    def draw(self, ui, screen):
        pass

@dataclass
class Sidepanel:
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        return None

    def draw(self, ui, screen):
        pygame.draw.rect(screen, (30, 30, 30), self.rect)

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
        if self.editor.transport.status >= 2:
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
        if (t := self.editor.transport.get_playing()) is not None:
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
                self.control.drag_org = self.editor.scroll_x
        if ui.r_active_id == self.widget_id:
            dx = self.control.drag_pos[0] - ui.mouse_pos[0]
            ix = int(dx // self.editor.BAR_WIDTH)
            self.editor.scroll_x = max(0, ix + self.control.drag_org)
            return True
        return False

    def draw(self, ui, screen):
        w = self.editor.BAR_WIDTH
        mg = []
        for i in range(self.editor.BARS_VISIBLE + 1):
            x = i * w + self.rect.left
            if (i + self.editor.scroll_x) == self.editor.transport.cursor_head:
                pygame.draw.line(screen, (0, 255, 255),
                                (x, self.rect.top), (x, self.rect.bottom))
            else:
                pygame.draw.line(screen, (200, 200, 200),
                                (x, self.rect.top), (x, self.rect.bottom))
            text = ui.font24.render(
                str(i + self.editor.scroll_x), True, (200, 200, 200))
            screen.blit(text, (x + 2, self.rect.centery - text.get_height()/2))
            mg.append(text.get_width())

        if self.editor.transport.playback_range is not None:
            i, j = self.editor.transport.playback_range
            half_width  = 6 / 2
            half_height = 6 / 2
            if self.editor.scroll_x <= i < self.editor.scroll_x + self.editor.BARS_VISIBLE:
                centerx = (i - self.editor.scroll_x) * w + 6 + mg[i - self.editor.scroll_x] + self.rect.left
                centery = self.rect.centery
                top = (centerx, centery - half_height)
                rig = (centerx + half_width, centery)
                bot = (centerx, centery + half_height)
                lef = (centerx - half_width, centery)
                pygame.draw.polygon(screen, (200, 200, 200), [top, rig, bot])

            if self.editor.scroll_x < j <= self.editor.scroll_x + self.editor.BARS_VISIBLE:
                centerx = (j - self.editor.scroll_x) * w - 6 + self.rect.left
                centery = self.rect.centery
                top = (centerx, centery - half_height)
                rig = (centerx + half_width, centery)
                bot = (centerx, centery + half_height)
                lef = (centerx - half_width, centery)
                pygame.draw.polygon(screen, (200, 200, 200), [top, bot, lef])

        screen.set_clip(self.rect)
        if (t := self.editor.transport.get_playing()) is not None:
            x = (t - self.editor.scroll_x) * w + self.rect.left
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

@dataclass
class SynthdefEditor:
    editor : Editor
    rect : pygame.Rect
    widget_id : Any

    def __post_init__(self):
        if self.editor.transport.definitions.temp_name is None:
            self.editor.cell_view.freshen()

    def behavior(self, ui):
        text_changed = False

        ui.grab_active(self)
        ui.grab_focus(self)
        dfs = self.editor.transport.definitions
        shift = ui.keyboard_mod & pygame.KMOD_SHIFT

        if ui.mouse_just_pressed and ui.hot_id == self.widget_id:
            dfs.temp_head = self._pos_from_mouse(ui)
            dfs.temp_tail = dfs.temp_head
        
        if ui.active_id == self.widget_id and ui.mouse_pressed and self.rect.collidepoint(ui.mouse_pos):
            dfs.temp_head = self._pos_from_mouse(ui)

        if ui.focused_id != self.widget_id:
            return text_changed

        if ui.keyboard_key == pygame.K_LEFT:
            if dfs.temp_head > 0:
                dfs.temp_head -= 1
                if not shift:
                    dfs.temp_tail = dfs.temp_head
        elif ui.keyboard_key == pygame.K_RIGHT:
            if dfs.temp_head < dfs.temp_data.length:
                dfs.temp_head += 1
                if not shift:
                    dfs.temp_tail = dfs.temp_head
        elif ui.keyboard_key == pygame.K_UP:
            row = dfs.temp_data.row(dfs.temp_head)
            if row > 0:
                dfs.temp_head = dfs.temp_head - dfs.temp_data.rowpos(row) + dfs.temp_data.rowpos(row-1)
                if not shift:
                    dfs.temp_tail = dfs.temp_head
        elif ui.keyboard_key == pygame.K_DOWN:
            row = dfs.temp_data.row(dfs.temp_head)
            if row < dfs.temp_data.newlines:
                dfs.temp_head = dfs.temp_head - dfs.temp_data.rowpos(row) + dfs.temp_data.rowpos(row+1)
                if not shift:
                    dfs.temp_tail = dfs.temp_head

        elif ui.keyboard_key == pygame.K_HOME:
            dfs.temp_head = dfs.temp_data.rowpos(dfs.temp_data.row(dfs.temp_head))
            if not shift:
                dfs.temp_tail = dfs.temp_head
        elif ui.keyboard_key == pygame.K_END:
            row = dfs.temp_data.row(dfs.temp_head)
            if row < dfs.temp_data.newlines:
                dfs.temp_head = dfs.temp_data.rowpos(row + 1)
            else:
                dfs.temp_head = dfs.temp_data.length
            if not shift:
                dfs.temp_tail = dfs.temp_head
        elif ui.keyboard_key == pygame.K_BACKSPACE:
            start = min(dfs.temp_head, dfs.temp_tail)
            stop  = max(dfs.temp_head, dfs.temp_tail)
            if start > 0 and start==stop:
                start -= 1
            dfs.temp_data = dfs.temp_data.erase(start,stop)
            dfs.temp_head = start
            dfs.temp_tail = start
            text_changed = True
        elif ui.keyboard_key == pygame.K_DELETE:
            start = min(dfs.temp_head, dfs.temp_tail)
            stop  = max(dfs.temp_head, dfs.temp_tail)
            if stop < dfs.temp_data.length and start==stop:
                stop += 1
            dfs.temp_data = dfs.temp_data.erase(start,stop)
            dfs.temp_head = start
            dfs.temp_tail = start
            text_changed = True
        elif ui.keyboard_key == pygame.K_RETURN:
            start = min(dfs.temp_head, dfs.temp_tail)
            stop  = max(dfs.temp_head, dfs.temp_tail)
            dfs.temp_data = dfs.temp_data.erase(start,stop).insert(start, "\n")
            dfs.temp_head = start + 1
            dfs.temp_tail = start + 1
            text_changed = True
        elif ui.keyboard_text:
            start = min(dfs.temp_head, dfs.temp_tail)
            stop  = max(dfs.temp_head, dfs.temp_tail)
            dfs.temp_data = dfs.temp_data.erase(start,stop).insert(start, ui.keyboard_text)
            dfs.temp_head = start + len(ui.keyboard_text)
            dfs.temp_tail = start + len(ui.keyboard_text)
            text_changed = True
        return text_changed

    def _pos_from_mouse(self, ui):
        dfs = self.editor.transport.definitions
        data = dfs.temp_data
        lines = "".join(data).splitlines()
        row = (ui.mouse_pos[1] - self.rect.y) // 24 - 1
        if 0 <= row < len(lines):
            rp = data.rowpos(row)
            text = lines[row]
            mouse_x = ui.mouse_pos[0] - self.rect.x - 5
            for i in range(len(text) + 1):
                width = ui.font24.size(text[:i])[0]
                if mouse_x < width:
                    return rp + i
            return rp + len(text)
        return 0

    def refresh_synthdef(self):
        self.editor.transport.definitions.temp_refresh()

    def draw(self, ui, screen):
        is_focused = ui.focused_id == self.widget_id
        bg_color = (60, 60, 60) if is_focused else (40, 40, 40)
        pygame.draw.rect(screen, bg_color, self.rect, 0, 6)
        pygame.draw.rect(screen, (150, 150, 150) if is_focused else (100, 100, 100), self.rect, 2, 6)

        dfs = self.editor.transport.definitions
        data = dfs.temp_data
        y = self.rect.top

        start = min(data.length, max(0, min(dfs.temp_head, dfs.temp_tail)))
        stop  = min(data.length, max(0, max(dfs.temp_head, dfs.temp_tail)))
        y0 = data.row(start)
        y1 = data.row(stop)

        for k, line in enumerate("".join(data).splitlines()):
            y += 24
            line_surf = ui.font24.render(line, True, (255, 255, 255))
            z = start - data.rowpos(y0)
            w = stop  - data.rowpos(y1)
            if y0 == k and y1 == k:
                start_x = self.rect.x + 5 + ui.font24.size(line[:z])[0]
                end_x = self.rect.x + 5 + ui.font24.size(line[:w])[0]
                sel_rect = pygame.Rect(start_x, y - 5, end_x - start_x + 2, 24)
                pygame.draw.rect(screen, (80, 120, 180), sel_rect)
            if y0 < k and k < y1:
                start_x = self.rect.x + 5
                end_x = self.rect.x + 5 + ui.font24.size(line)[0]
                sel_rect = pygame.Rect(start_x, y - 5, end_x - start_x + 2, 24)
                pygame.draw.rect(screen, (80, 120, 180), sel_rect)
            if y0 == k and k < y1:
                start_x = self.rect.x + 5 + ui.font24.size(line[:z])[0]
                end_x = self.rect.x + 5 + ui.font24.size(line)[0]
                sel_rect = pygame.Rect(start_x, y - 5, end_x - start_x + 2, 24)
                pygame.draw.rect(screen, (80, 120, 180), sel_rect)
            if y0 < k and k == y1:
                sel_rect = pygame.Rect(start_x, y - 5, end_x - start_x + 2, 24)
                start_x = self.rect.x + 5
                end_x = self.rect.x + 5 + ui.font24.size(line[:w])[0]
                pygame.draw.rect(screen, (80, 120, 180), sel_rect)
            screen.blit(line_surf, (self.rect.x + 5, y))
        
#        if selection is not None and is_focused:
#            start = min(cursor, selection)
#            end = max(cursor, selection)
#            
#            start_x = self.rect.x + 5 + ui.font24.size(text[:start])[0]
#            end_x = self.rect.x + 5 + ui.font24.size(text[:end])[0]
#            
#        
#        if is_focused:
#            cursor_x = self.rect.x + 5 + ui.font24.size(text[:cursor])[0]
#            pygame.draw.line(screen, (255, 255, 255),
#                           (cursor_x, self.rect.y + 5),
#                           (cursor_x, self.rect.y + self.rect.height - 5), 2)


if __name__ == '__main__':
    editor = Editor()
    editor.run()
