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
    (0,4) %note:pitch@b% q c3, q c3, q c3, q c3 {
       synth=tone;
    }
}

main {
    (0,0) &drums;
    (1,0) &drums;
    (2,0) &drums;
    (3,0) &drums;
    (0,5) %%
      q, e, e, q, e, e,
      q, q, q, e, e,
      q, q, q, s, s, s, s,
      q, q, q, q
      / ostinato %note:pitch@b%
        * c6, * e6, * d6, * f6, * e6, * c6, * e6, * d6, * f6, * c6, * c6
    {
        synth=tone;
    }
    (0,6) %%
        |4| [e, s, s, e, s, s, s, s, s, s, s, s, s, s / repeat 4]
        / ostinato %note:pitch% * c4, * g3, * d4, * e4, * c5, * b4, * f4 {
        synth=tone;
    }
}

@synths
  (-122, -39) tone musical multi {
    amplitude=0.1454;
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
            #elif isinstance(e, CommandEntity):
            #    d = self.process_component(e.component, rhythm_config)
            #    self.dimensions[decl.name, i] = d.duration, 1, d
            #    duration = max(duration, d.duration+s)
            #    height   = max(height, l + 1)
            #elif isinstance(e, PianorollEntity):
            #    h = math.ceil((int(e.top) - int(e.bot) + 1) / 3)
            #    self.dimensions[decl.name, i] = e.duration, h, None
            #    duration = max(duration, e.duration+s)
            #    height   = max(height, l+h)
            #elif isinstance(e, StavesEntity):
            #    h = 2*(e.above + e.count + e.below)
            #    self.dimensions[decl.name, i] = e.duration, h, None
            #    duration = max(duration, e.duration+s)
            #    height   = max(height, l+h)
        self.dimensions[decl.name] = duration, height
        return duration, height

    def construct(self, sb, decl, shift, key, rhythm_config):
        bound = shift+1
        for i, e in enumerate(decl.entities):
            k = key + (i,)
            s = shift + e.shift
            if isinstance(e, ClipEntity):
                subdecl = self.declarations[e.name]
                d = self.construct(sb, subdecl, s, k, rhythm_config)
                bound = max(bound, s+d)
            if isinstance(e, BrushEntity):
                config = rhythm_config | e.properties
                expr       = evaluate_all(config, e.expr)
                pattern, d = self.compute_pattern(expr, config)
                match config["brush"]:
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
                cons(sb, config, pattern, s, k)
                bound = max(bound, s+d)
        return bound - shift

    def compute_pattern(self, exprs, config):
        events = []
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

        def resolve_value(v):
            if isinstance(v, Dynamic):
                return dynamics_to_dbfs.get(v.name, None)
            if isinstance(v, Ref):
                return None
            if isinstance(v, Unk):
                return None
            return v

        def compute_note(t, note, duration):
            if isinstance(note, Note):
                match note.style:
                    case "staccato":
                        d = duration * config['staccato']
                    case "tenuto":
                        d = duration * config['tenuto']
                    case None:
                        d = duration * config['normal']
                group = []
                for data in note.group:
                    out = {}
                    for n, v in data.items():
                        v = resolve_value(v)
                        if v is not None:
                            out[n] = v
                    group.append(out)
                events.append((t,d,group))
            elif isinstance(note, Tuplet):
                s = t
                subrate = duration / sum(resolve(n.duration) for n in note.mhs)
                for subnote in note.mhs:
                    subduration = resolve(subnote.duration) * subrate
                    compute_note(s, subnote, subduration)
                    s += subduration
        t = 0.0
        rate = config["beats_per_measure"] / config["beat_division"]
        for expr in exprs:
            duration = resolve(expr.duration) * rate
            compute_note(t, expr, duration)
            t += duration
        return events, t

    def process_component(self, component, rhythm_config):
        if isinstance(component, FromRhythm):
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
            meta = pattern.meta * component.count
            for i in range(component.count):
                for s, d in pattern.events:
                    events.append((s + pattern.duration*i, d))
            return Pattern(events, values, pattern.duration*component.count, pattern.views, meta)
        elif isinstance(component, Durated):
            pattern = self.process_component(component.base, rhythm_config)
            events = []
            values = pattern.values
            meta = pattern.meta
            p = component.duration / pattern.duration
            for s, d in pattern.events:
                events.append((s * p, d * p))
            return Pattern(events, values, component.duration, [], meta)
        elif isinstance(component, WestRhythm):
            return component.to_pattern(rhythm_config)
        elif isinstance(component, StepRhythm):
            return component.to_west().to_pattern(rhythm_config)
        elif isinstance(component, EuclideanRhythm):
            return component.to_west().to_pattern(rhythm_config)
        else:
            assert False

    def construct_gate(self, sb, config, pattern, shift, key):
        tag = config["synth"]
        for i, (start, duration, values) in enumerate(pattern):
            for j, v in enumerate(values):
                sb.note(unwrap(tag), shift+start, duration, key + (i,j,), v)

    def construct_once(self, sb, config, pattern, shift, key):
        tag = config["synth"]
        for i, (start, duration, values) in enumerate(pattern):
            for j, v in enumerate(values):
                sb.once(shift+start, unwrap(tag), v)

    def construct_slide(self, sb, config, pattern, shift, key):
        tag = config["synth"]
        i = None
        for i, (start, duration, values) in enumerate(pattern):
            for j, v in enumerate(values):
                sb.gate(shift+start, unwrap(tag), key, v)
        if i is not None:
            sb.gate(shift+start+duration, tag, key, v)

    def construct_quadratic(self, sb, config, pattern, shift, key):
        tag = config["synth"]
        for i, (start, duration, values) in enumerate(pattern):
            for j, v in enumerate(values):
                sb.quadratic(shift+start, unwrap(tag), bool(v.get("transition", False)), v["value"])

    def construct_control(self, sb, config, pattern, shift, key):
        tag = config["synth"]
        for i, (start, duration, values) in enumerate(pattern):
            for j, v in enumerate(values):
                sb.control(shift+start, unwrap(tag), v)

def unwrap(value):
    return value.name if isinstance(value, (Unk,Ref)) else value

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

        self.transport = Transport(
            synthdef_directory = os.path.join(directory,"synthdefs"))
        self.transport.set_online()
        self.transport.refresh(self.proc)
        self.transport.set_fabric()
        self.transport.toggle_play()

        self.mode = "track"
        self.cell_view = NodeView(self)
        self.selected = "main",
        self.stack_index = None
        self.rhythm_index = None

        self.scroll_ox = None
        self.scroll_x = 0
        self.timeline = TimelineControl()

        self.midi_status = False
        self.midi_controllers = []

        self.selection = None
        self.prompt = Text("", 0, None)
        self.response = ""

    def after_rewrite(self):
        self.proc = DocumentProcessing(self.doc)
        self.transport.refresh(self.proc)

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
        main_grid = Grid(
            self.MARGIN - self.scroll_x * self.BAR_WIDTH,
            24, self.BAR_WIDTH, self.LANE_HEIGHT)
        main_rect = pygame.Rect(self.MARGIN, 24, self.screen_width - self.MARGIN, self.screen_height - 48)

        side_rect = pygame.Rect(0, 24, self.MARGIN, self.screen_height - 48)

        if self.mode == "track":
            ui.widget(GridWidget(self, main_rect, "grid"))
            trackline = None
            edit_widgets = []
            def traverse_decl(decl, x, y, kv, d=1):
                nonlocal trackline
                views = {}
                #for i, e in enumerate(decl.entities):
                #    ix = x + e.shift
                #    iy = y + e.lane
                #    w, h, pat = self.proc.dimensions[decl.name, i]
                #    key = kv + (i,)
                    #if isinstance(e, CommandEntity):
                    #    if self.selected == key and self.stack_index is not None:
                    #        trackline = main_grid(ix, iy, ix+w, iy+h)
                    #    if ui.widget(PatLane(f"{e.flavor} {e.instrument}",
                    #        main_grid(ix, iy, ix+w, iy+h),
                    #        kv + (i,),
                    #        pat, main_grid.offset(ix,iy)
                    #        )):
                    #        self.selected = kv + (i,)
                    #        self.stack_index = None
                    #    for name, dtype, vw in pat.views:
                    #        try:
                    #            views[vw].append((name, dtype, pat, ix, e))
                    #        except KeyError:
                    #            views[vw] = [(name, dtype, pat, ix, e)]
                    #elif isinstance(e, ClipEntity):
                    #    sdecl = self.proc.declarations[e.name]
                    #    if ui.widget(Lane(e.name,
                    #        main_grid(ix, iy, ix+w, iy+h),
                    #        kv + (i,))):
                    #        self.selected = kv + (i,)
                    #        self.stack_index = None
                    #    subviews = traverse_decl(sdecl, ix, iy, kv + (i,), d+1)
                    #    for vw, g in subviews.items():
                    #        try:
                    #            views[vw].extend(g)
                    #        except KeyError:
                    #            views[vw] = list(g)
                #for i, e in enumerate(decl.entities):
                #    ix = x + e.shift
                #    iy = y + e.lane
                #    w, h, pat = self.proc.dimensions[decl.name, i]
                #    if isinstance(e, PianorollEntity):
                #        if ui.widget(e := PianorollWidget(
                #            main_grid(ix, iy, ix+w, iy+h),
                #            int(e.bot), int(e.top),
                #            views.get(e.name, []), main_grid,
                #            kv + (i,))):
                #            self.selected = kv + (i,)
                #            self.stack_index = None
                #        edit_widgets.append(e)
                #    elif isinstance(e, StavesEntity):
                #        if ui.widget(e := StavesWidget(
                #            main_grid(ix, iy, ix+w, iy+h),
                #            e.above, e.count, e.below, e.key,
                #            views.get(e.name, []), main_grid,
                #            kv + (i,))):
                #            self.selected = kv + (i,)
                #            self.stack_index = None
                #        edit_widgets.append(e)
                return views

            main_decl = self.proc.declarations['main']
            w, h = self.proc.get_dimensions(main_decl, default_rhythm_config)
            ui.widget(Lane("main", main_grid(0,0,w,h), "main"))
            traverse_decl(main_decl, 0, 0, ("main",))
            
            ui.widget(TransportVisual(self.transport, main_grid, main_rect,
                "transport-visual"))
            ui.widget(Scroller(self, main_rect, "scroller"))

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
        elif ui.tab_button(self.mode, "cell", bot_grid(10, 0, 15, 1),  "cell-tab", allow_focus=False):
            self.mode = "synth"
        ui.label(self.response, bot_grid(0, -1, 50, 0))
        if ui.textbox(self.prompt, bot_grid(15, 0, 50, 1), "prompt"):
            if self.prompt.return_pressed:
                try:
                    com = command_from_string(self.prompt.text)
                    self.selection, detail, hdr = com.apply(self.doc, self.selection, self.doc)
                    self.response = ""
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.response = repr(e)
                else:
                    self.prompt = Text("", 0, None)
                    self.after_rewrite()
                    self.response = str(self.selection)
                    if detail is not None:
                        self.response += str(" >>> ") + str(detail).replace("\n", " ")

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
    pat : Any #Pattern
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
                for name, dtype, pat, x, e in self.widget.pats:
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
        for name, dtype, pat, x, _ in self.pats:
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
        for name, dtype, pat, x, e in self.pats:
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
class Scroller:
    editor : Editor
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        if self.rect.collidepoint(ui.mouse_pos):
            if ui.r_mouse_just_pressed and ui.r_active_id is None:
                ui.r_active_id = self.widget_id
                editor.scroll_ox = ui.mouse_pos[0], editor.scroll_x
        if ui.r_mouse_pressed and ui.r_active_id == self.widget_id:
            x, orig = editor.scroll_ox
            editor.scroll_x = orig - round((ui.mouse_pos[0]-x) / self.editor.BAR_WIDTH)
            return editor.scroll_x
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

if __name__ == '__main__':
    editor = Editor()
    editor.run()
