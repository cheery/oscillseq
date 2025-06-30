from collections import defaultdict, deque
from dataclasses import dataclass, field
from supriya import Envelope, synthdef, ugens
from supriya.ugens import EnvGen, Out, SinOsc
from typing import List, Dict, Set, Optional, Callable, Tuple, Any, Union, DefaultDict
from components import ContextMenu
from model import DrawFunc
import math
import os
import pygame
import supriya
import heapq
import random
import numpy as np
from model import Cell
from fabric import Definitions, Fabric
import music
from descriptors import bus
from node_editor import ray_intersect_aabb, line_intersect_line
import time
import node_editor
import sequencer

# TODO: create a layout object.

class NodeEditorView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = NodeEditorTool(self)
        self.s1 = editor.make_spectroscope(bus=0)
        self.s2 = editor.make_spectroscope(bus=1)
        self.layout = layout_gui(self.editor.doc.cells, self.editor.doc.connections, self.editor.definitions)
        self.scroll = np.array([editor.SCREEN_WIDTH,editor.SCREEN_HEIGHT]) / 2
        
    def draw(self, screen):
        font = self.editor.font
        mouse_pos = pygame.mouse.get_pos()

        half_height = self.editor.SCREEN_HEIGHT / 2
        quad_height = half_height / 2
        self.s1.refresh()
        self.s2.refresh()
        self.s1.draw(screen, font, (255, 0, 0), self.editor.SCREEN_WIDTH/2, quad_height - 100)
        self.s2.draw(screen, font, (0, 255, 0), self.editor.SCREEN_WIDTH/2, half_height + quad_height - 100)

        gui, wire_inputs, wire_outputs, wires, router = self.layout
        scroll = self.scroll

        for wire, color, ident in wires:
            wire = [np.array(p) + self.scroll for p in wire]
            pygame.draw.lines(screen, color, False, wire, 4)

        for element in gui:
            element.draw(screen, font, self.editor.definitions, scroll, self.editor.fabric, mouse_pos)
        
        for point, spec in wire_inputs.values():
            point = point[0] + scroll[0], point[1] + scroll[1]
            pygame.draw.circle(screen, color_of_bus(spec), point, 7.5, 0)
            pygame.draw.circle(screen, (255, 255, 255), point, 7.5, 1)
        for point, spec in wire_outputs.values():
            point = point[0] + scroll[0], point[1] + scroll[1]
            pygame.draw.circle(screen, color_of_bus(spec), point, 7.5, 0)
            pygame.draw.circle(screen, (255, 255, 255), point, 7.5, 1)
        
        point = 400, 0
        point = point[0] + scroll[0], point[1] + scroll[1]
        text = font.render(f"output", True, (200, 200, 200))
        screen.blit(text, (point[0] + 10, point[1] - 9))

    def handle_keydown(self, ev):
        pass

    def close(self):
        self.s1.close()
        self.s2.close()

    def open_cell_menu(self):
        self.tool = CellMenu(self.tool)

    def remove_cell(self, cell):
        self.editor.doc.cells.remove(cell)
        self.editor.doc.labels.pop(cell.label)
        for src, dst in list(self.editor.doc.connections):
            do_remove = False
            if ":" in src:
                do_remove |= src.split(":")[0] == cell.label
            if ":" in dst:
                do_remove |= dst.split(":")[0] == cell.label
            if do_remove:
                self.editor.doc.connections.discard((src, dst))
        restart_fabric(self.editor)
        self.layout = layout_gui(self.editor.doc.cells, self.editor.doc.connections, self.editor.definitions)

    def toggle_multi(self, cell):
        cell.multi = not cell.multi
        restart_fabric(self.editor)

    def in_lane(self, cell):
        for df in self.editor.doc.drawfuncs:
            if df.tag == cell.label:
                return True
        return False

    def toggle_lane(self, cell):
        tag = cell.label
        lane = 0
        for df in self.editor.doc.drawfuncs[:]:
            if df.tag == tag:
                self.editor.doc.drawfuncs.remove(df)
                return
            lane = df.lane + 1
        params = {"value": "n/a"}
        df = DrawFunc(lane, "string", tag, params)
        self.editor.doc.drawfuncs.append(df)
        self.editor.refresh_layout()

class NodeEditorTool:
    def __init__(self, view):
        self.view = view
        self.mouse_point = 0, 0
        self.mouse_origin = 0, 0
        self.port_selected = None
        self.port_wire = []

    def draw(self, screen):
        font = self.view.editor.font

    def handle_mousebuttondown(self, ev):
        gui, wire_inputs, wire_outputs, wires, router = self.view.layout
        point = np.array(ev.pos) - self.view.scroll
        for gcell in gui:
            rect = pygame.Rect(gcell.rect.x, gcell.rect.y, gcell.rect.width, 15)
            if rect.collidepoint(point):
                if ev.button == 1:
                    self.view.tool = CellPositionTool(self, gcell.rect, gcell.cell, point)
                if ev.button == 3:
                    multi_on_off = ["off", "on"][gcell.cell.multi]
                    on_lane = ["put on lane", "remove from lane"][self.view.in_lane(gcell.cell)]
                    self.view.tool = ContextMenu(self, np.array(ev.pos), [
                        (f"multi={multi_on_off}", self.view.toggle_multi),
                        (on_lane, self.view.toggle_lane),
                        ("remove", self.view.remove_cell),
                    ], gcell.cell)
                return
            for ui in gcell.valueparams:
                if ui.rect.collidepoint(point):
                    if ev.button == 1:
                        self.view.tool = KnobMotion(self, ui, gcell.cell)
                        self.view.tool.adjust_slider(ev.pos)
                    elif ev.button == 3:
                        gcell.cell.params.pop(ui.name, None)
                    return
        if ev.button == 3:
            self.view.tool = ScrollingTool(self, np.array(ev.pos))
            return
        if ev.button == 1:
            for name, (pt,bus) in wire_inputs.items():
                delta = np.array(point) - np.array(pt)
                if np.sqrt(np.sum(delta**2)) < 50:
                    self.view.tool = ConnectionTool(self, name, pt, bus)
                    return
            for name, (pt,bus) in wire_outputs.items():
                delta = np.array(point) - np.array(pt)
                if np.sqrt(np.sum(delta**2)) < 50:
                    self.view.tool = ConnectionTool(self, name, pt, bus)
                    return
            self.view.tool = DisconnectionTool(self, point)

    def handle_mousebuttonup(self, ev):
        pass

    def handle_mousemotion(self, ev):
        pass

class CellPositionTool:
    def __init__(self, tool, rect, cell, grip):
        self.view = tool.view
        self.tool = tool
        self.rect = rect
        self.cell = cell
        self.grip = grip

    def draw(self, screen):
        mouse_pos = pygame.mouse.get_pos()
        mouse_point = np.array(mouse_pos) - self.view.scroll
        rect = self.rect.move(mouse_point - self.grip + self.view.scroll)
        pygame.draw.rect(screen, (0, 0, 0), rect, 0, 3)
        pygame.draw.rect(screen, (60, 60, 60), rect.move(5, -5), 0, 3)
        pygame.draw.rect(screen, (200, 200, 200), rect.move(5, -5), 2, 3)

    def handle_mousebuttondown(self, ev):
        pass

    def handle_mousebuttonup(self, ev):
        self.view.tool = self.tool
        mouse_point = np.array(ev.pos) - self.view.scroll
        self.cell.pos = mouse_point - self.grip + np.array(self.cell.pos)
        self.view.layout = layout_gui(self.view.editor.doc.cells, self.view.editor.doc.connections, self.view.editor.definitions)

    def handle_mousemotion(self, ev):
        pass

class ScrollingTool:
    def __init__(self, tool, mouse_grip):
        self.view = tool.view
        self.tool = tool
        self.origin     = mouse_grip
        self.mouse_grip = mouse_grip - self.view.scroll
        self.open_menu  = True

    def draw(self, screen):
        pass

    def handle_mousebuttondown(self, ev):
        pass

    def handle_mousebuttonup(self, ev):
        if self.open_menu:
            self.view.tool = ContextMenu(self.tool, np.array(ev.pos), [
                ("new", self.view.open_cell_menu),
            ])
        else:
            self.view.tool = self.tool

    def handle_mousemotion(self, ev):
        self.view.scroll = np.array(ev.pos) - self.mouse_grip
        dist = np.sqrt(np.sum((np.array(ev.pos) - self.origin)**2))
        if dist >= 10:
            self.open_menu = False

class ConnectionTool:
    def __init__(self, tool, port, point, bus):
        self.view = tool.view
        self.tool = tool
        self.port = port
        self.point = point
        self.bus = bus
        self.wire = []

    def draw(self, screen):
        pos = pygame.mouse.get_pos()
        text = self.view.editor.font.render("CONNECT", True, (0,200,0))
        screen.blit(text, np.array(pos) - np.array([0, text.get_height()]) / 2)

        gui, wire_inputs, wire_outputs, wires, router = self.view.layout

        if self.wire:
            wire = [p + self.view.scroll for p in self.wire]
            pygame.draw.lines(screen, (0,255,0), False, wire, 4)

    def handle_mousebuttondown(self, ev):
        pass

    def handle_mousebuttonup(self, ev):
        gui, wire_inputs, wire_outputs, wires, router = self.view.layout
        point = np.array(ev.pos) - np.array(self.view.scroll)
        selected = None
        for name, (pt,bus) in wire_inputs.items():
            if bus != self.bus:
                continue
            delta = np.array(point) - np.array(pt)
            if np.sqrt(np.sum(delta**2)) < 50:
                selected = name
        for name, (pt,_) in wire_outputs.items():
            if bus != self.bus:
                continue
            delta = np.array(point) - np.array(pt)
            if np.sqrt(np.sum(delta**2)) < 50:
                selected = name
        if selected is not None:
            name0 = self.port
            name1 = selected
            if name1 in wire_outputs:
                name1, name0 = name0, name1
            if name0 in wire_outputs and name1 in wire_inputs and (name0,name1) not in self.view.editor.doc.connections and not detect_cycle(name0, name1, self.view.editor.doc.connections, self.view.editor.definitions):
                self.view.editor.doc.connections.add((name0, name1))
                restart_fabric(self.view.editor)
                self.view.layout = layout_gui(self.view.editor.doc.cells, self.view.editor.doc.connections, self.view.editor.definitions)
        self.view.tool = self.tool

    def handle_mousemotion(self, ev):
        gui, wire_inputs, wire_outputs, wires, router = self.view.layout
        point = np.array(ev.pos) - np.array(self.view.scroll)
        self.wire = router.route(self.point, point, add_cost=False)

class DisconnectionTool:
    def __init__(self, tool, point):
        self.view = tool.view
        self.tool = tool
        self.point = point

    def draw(self, screen):
        pos = pygame.mouse.get_pos()
        text = self.view.editor.font.render("DISCONNECT", True, (200,0,0))
        screen.blit(text, np.array(pos) - np.array([0, text.get_height()]) / 2)
        pygame.draw.line(screen, (255,0,0), pos, self.point + self.view.scroll, 5)

    def handle_mousebuttondown(self, ev):
        pass

    def handle_mousebuttonup(self, ev):
        gui, wire_inputs, wire_outputs, wires, router = self.view.layout
        point = np.array(ev.pos) - self.view.scroll
        were_removed = False
        for wire, color, ident in wires:
            wire = list(wire)
            if any(line_intersect_line(p,q, point, self.point) for p,q in zip(wire, wire[1:])):
                self.view.editor.doc.connections.remove(ident)
                were_removed = True
        if were_removed:
            restart_fabric(self.view.editor)
            self.view.layout = layout_gui(self.view.editor.doc.cells, self.view.editor.doc.connections, self.view.editor.definitions)
        self.view.tool = self.tool

    def handle_mousemotion(self, ev):
        pass

class CellMenu:
    def __init__(self, tool):
        self.view = tool.view
        self.tool = tool
        x = 150
        y = 150
        self.wire_inputs = {}
        self.wire_outputs = {}
        self.gui = []
        for i, name in enumerate(self.view.editor.definitions.list_available()):
            cell = Cell(str(i), False, name, (x,y), {})
            gcell = layout_cell(cell, self.wire_inputs, self.wire_outputs, self.view.editor.definitions)
            self.gui.append(gcell)
            x += 200
            if x >= 1000:
                x = 150
                y += 200

    def draw(self, screen):
        font = self.view.editor.font
        mouse_pos = pygame.mouse.get_pos()
        rect = pygame.Rect(0, 0, self.view.editor.SCREEN_WIDTH, self.view.editor.SCREEN_HEIGHT)
        rect = rect.inflate((-100, -100))
        pygame.draw.rect(screen, (0, 0, 0), rect.move(-2, 2), 0, 3)
        pygame.draw.rect(screen, (60, 60, 60), rect, 0, 3)
        pygame.draw.rect(screen, (200, 200, 200), rect, 2, 3)

        scroll = [0, 0]

        for element in self.gui:
            if element.rect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, (200, 200, 200), element.rect, 2, 3)
            element.draw(screen, font, self.view.editor.definitions, scroll, None, None)

        for point, spec in self.wire_inputs.values():
            point = point[0] + scroll[0], point[1] + scroll[1]
            pygame.draw.circle(screen, color_of_bus(spec), point, 7.5, 0)
            pygame.draw.circle(screen, (255, 255, 255), point, 7.5, 1)
        for point, spec in self.wire_outputs.values():
            point = point[0] + scroll[0], point[1] + scroll[1]
            pygame.draw.circle(screen, color_of_bus(spec), point, 7.5, 0)
            pygame.draw.circle(screen, (255, 255, 255), point, 7.5, 1)

    def handle_mousebuttondown(self, ev):
        self.view.tool = self.tool
        gcell = None
        for element in self.gui:
            if element.rect.collidepoint(ev.pos):
                gcell = element
        if gcell is not None:
            cell = gcell.cell
            cell.label = ""
            cell = self.view.editor.doc.intro(cell)
            cell.pos = tuple(np.array(cell.pos) - self.view.scroll)
            self.view.editor.doc.cells.append(cell)
            self.view.tool = CellPositionTool(self.tool, gcell.rect.move(-self.view.scroll), cell, np.array(ev.pos) - self.view.scroll)
            restart_fabric(self.view.editor)

    def handle_mousebuttonup(self, ev):
        pass

    def handle_mousemotion(self, ev):
        pass


def detect_cycle(i, o, connections, definitions):
    if ":" in i and ":" in o:
        il,ix = i.split(":")
        ol,ox = o.split(":")
        visited = set()
        def visit(label):
            visited.add(label)
            for src,dst in connections:
                if ":" in src and ":" in dst:
                    il,ix = src.split(":")
                    ol,ox = dst.split(":")
                    if il == label:
                        visit(ol)
        visit(ol)
        return (il in visited)
    return False

def restart_fabric(editor):
    if editor.transport_status == 3:
        sequencer = editor.player.sequencer
    else:
        sequencer = None
    if editor.transport_status >= 2:
        editor.set_online()
        editor.set_fabric()
    if sequencer:
        editor.set_playing(sequencer)

# TODO: Make this make sense
class GUICell:
    def __init__(self, cell, rect, inputs, outputs, valueparams):
        self.cell = cell
        self.rect = rect
        self.inputs = inputs
        self.outputs = outputs
        self.valueparams = valueparams

    def draw(element, screen, font, definitions, scroll, fabric, point):
        cell = element.cell
        d = definitions.descriptor(cell)
        x, y = element.rect.x + scroll[0], element.rect.y + scroll[1]
        rect = element.rect.move(scroll)
        pygame.draw.rect(screen, (70, 70, 70), rect, 0, 3)
        if cell.multi:
            pygame.draw.rect(screen, (70, 200, 200), rect, 2, 3)
        text = font.render(f"{cell.label}:{cell.definition}", True, (200, 200, 200))
        screen.blit(text, (x + 5,y))
        
        for k, (name, ty) in enumerate(element.inputs):
            text = font.render(name, True, (200, 200, 200))
            screen.blit(text, (x + 10,y + k*30 + 22))
        
        for k, (name, ty) in enumerate(element.outputs):
            text = font.render(name, True, (200, 200, 200))
            screen.blit(text, (x + 150 - text.get_width() - 10,y + k*30 + 22))
        y += 30 * max(len(element.inputs), len(element.outputs))
        for ui in element.valueparams:
            ui.draw(screen, font, cell, d, fabric, scroll, point)

def layout_cell(cell, wire_inputs, wire_outputs, definitions):
    d = definitions.descriptor(cell)
    inputs = []
    outputs = []
    valueparams = []
    for name, ty in d.mdesc.items():
        if isinstance(ty, bus):
            if ty.mode == "out":
                outputs.append((name, ty))
            else:
                inputs.append((name, ty))
        else:
            valueparams.append((name, ty))

    x, y = cell.pos
    h = 15 + 30 * max(len(inputs), len(outputs)) + 45 * len(valueparams)
    y -= h // 2
    rect = pygame.Rect(x - 75, y, 150, h)

    y += 15 + 30 * max(len(inputs), len(outputs))
    sliders = []
    for name, ty in valueparams:
        sliders.append(ParameterSlider(name, ty, pygame.Rect(x - 75, y, 150, 45)))
        y += 45

    gcell = GUICell(cell, rect, inputs, outputs, valueparams=sliders)
    for k, (name, ty) in enumerate(inputs):
        point = rect.x, rect.y + 30*k + 30
        wire_inputs[f"{cell.label}:{name}"] = point, d.field_bus(name)
    for k, (name, ty) in enumerate(outputs):
        point = rect.x + 150, rect.y + 30*k + 30
        wire_outputs[f"{cell.label}:{name}"] = point, d.field_bus(name)
    return gcell

def layout_gui(cells, connections, definitions):
    gui = []
    wire_inputs = {}
    wire_outputs = {}
    
    point = 400, 0
    wire_inputs['output'] = point, ('ar', 2)
    
    for cell in cells:
        gcell = layout_cell(cell, wire_inputs, wire_outputs, definitions)
        gui.append(gcell)

    rects = [gcell.rect for gcell in gui]

    rb = node_editor.WireRouterBuilder(rects)

    start_time = time.monotonic() * 1000

    for name, ((x,y), _) in wire_inputs.items():
        rb.cast_ray((x-5, y), (-1, 0))
    for name, ((x,y), _) in wire_outputs.items():
        rb.cast_ray((x+5, y), (+1, 0))

    router = rb.build()

    wires = []
    for src, dst in connections:
        s = wire_outputs[src][0]
        e = wire_inputs[dst][0]
        wire = router.route(s, e)
        wires.append((wire, color_of_bus(wire_inputs[dst][1]), (src,dst)))

    return gui, wire_inputs, wire_outputs, wires, router

def color_of_bus(bus):
    if bus == ('ar', 1):
        return (100, 255, 0)
    if bus == ('ar', 2):
        return (255, 0, 0)
    if bus == ('kr', 1):
        return (255, 255, 0)
    return (255, 255, 255)
    
class ParameterSlider:
    def __init__(self, name, ty, rect):
        self.name = name
        self.ty = ty
        self.rect = rect

    def draw(self, screen, font, cell, d, fabric, scroll, point):
        color = (200, 200, 200)
        val = cell.params.get(self.name, None)
        if val is None:
            parameter = d.synthdef.parameters[self.name][0]
            val = parameter.value[0]
            color = (255, 255, 200)
        rect = self.rect.move(scroll)
        if point and rect.collidepoint(point) and (t := any_to_slider(val, self.ty)) is not None:
            inset = rect.inflate((-20, -20))
            pygame.draw.rect(screen, (200,200,200), inset, 0, 3)
            slider = rect.inflate((-40, -40))
            pygame.draw.rect(screen, (20,20,20), slider, 0, 3)
            x = slider.left + slider.width*t
            knob = pygame.Rect(x - 3, slider.centery - 8, 6, 17)
            pygame.draw.rect(screen, (50,50,50), knob, 0, 3)
        else:
            x, y = rect.topleft
            trl = fabric.trail[cell.label].get(self.name, None) if fabric is not None else None
            text = font.render(f"{self.name} : {self.ty}", True, (200, 200, 200))
            screen.blit(text, (x + 75 - text.get_width()//2,y))
            if trl is not None:
                text = font.render(f"{val} [{trl}]", True, color)
            else:
                text = font.render(f"{val}", True, color)
            screen.blit(text, (x + 75 - text.get_width()//2,y + 15))

class KnobMotion:
    def __init__(self, tool, slider, cell):
        self.view = tool.view
        self.tool = tool
        self.slider = slider
        self.cell = cell

    def draw(self, screen):
        pass

    def handle_mousebuttondown(self, ev):
        pass

    def handle_mousebuttonup(self, ev):
        self.view.tool = self.tool

    def handle_mousemotion(self, ev):
        self.adjust_slider(ev.pos)

    def adjust_slider(self, pos):
        slider = self.slider.rect.inflate((-40, -40))
        t = (pos[0] - self.view.scroll[0] - slider.left) / slider.width
        t = max(0, min(1, t))
        self.cell.params[self.slider.name] = slider_to_any(t, self.slider.ty)
        if self.view.editor.fabric:
            self.view.editor.fabric.control(self.cell.label, **self.cell.params)

lhzbound = math.log2(10 / 440)
hhzbound = math.log2(24000 / 440)
whzbound = hhzbound - lhzbound

def any_to_slider(val, ty):
    if ty == 'boolean':
        return int(val)
    if ty == 'unipolar':
        return val
    if ty == 'number':
        return None
    if ty == 'bipolar':
        return linlin(val, -1, 1, 0, 1)
    if ty == 'pitch':
        if isinstance(val, music.Pitch):
            val = int(val)
        return val / 127
    if ty == 'hz':
        if isinstance(val, music.Pitch):
            val = 440 * 2**((int(val) - 69) / 12)
        return (math.log2(val / 440) - lhzbound) / whzbound
    if ty == 'db':
        return linlin(val, -100, 0, 0, 1)
    if ty == 'duration':
        return linlin(val, 0, 10, 0, 1)
    return val

def slider_to_any(val, ty):
    if ty == 'boolean':
        return round(val)
    if ty == 'unipolar':
        return val
    if ty == 'bipolar':
        return linlin(val, 0, 1, -1, 1)
    if ty == 'pitch':
        return int(val * 127)
    if ty == 'hz':
        return 440 * 2**(val * whzbound + lhzbound)
    if ty == 'db':
        return linlin(val, 0, 1, -100, 0)
    if ty == 'duration':
        return linlin(val, 0, 1, 0, 10)
    return val

def linlin(val, a0, a1, b0, b1):
    return ((val - a0) / (a1-a0)) * (b1-b0) + b0

