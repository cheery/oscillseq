from collections import defaultdict, deque
from dataclasses import dataclass, field
from supriya import Envelope, synthdef, ugens
from supriya.ugens import EnvGen, Out, SinOsc
from typing import List, Dict, Set, Optional, Callable, Tuple, Any, Union, DefaultDict
import math
import os
import pygame
import supriya
import heapq
import random
import numpy as np
#from controllers import quick_connect
#controllers = quick_connect(fabric, "m")
#for controller in controllers:
#    controller.close()
from model import Cell
from fabric import Definitions, Fabric
import music
from descriptors import simple, bus
from node_editor import ray_intersect_aabb, line_intersect_line
import time
import node_editor
import sequencer

# TODO: fx with a,b,c,t,trigger allows linear control.
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
            element.draw(screen, font, self.editor.definitions, scroll)
        
        for point in wire_inputs.values():
                point = point[0] + scroll[0], point[1] + scroll[1]
                pygame.draw.circle(screen, (255, 0, 0), point, 7.5, 0)
                pygame.draw.circle(screen, (255, 255, 0), point, 7.5, 1)
        for point in wire_outputs.values():
                point = point[0] + scroll[0], point[1] + scroll[1]
                pygame.draw.circle(screen, (255, 0, 0), point, 7.5, 0)
                pygame.draw.circle(screen, (255, 255, 0), point, 7.5, 1)
        
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
                    self.view.tool = ContextMenu(self, np.array(ev.pos), [
                        ("remove", self.view.remove_cell)
                    ], gcell.cell)
                return
        if ev.button == 3:
            self.view.tool = ScrollingTool(self, np.array(ev.pos))
            return
        if ev.button == 1:
            for name, pt in wire_inputs.items():
                delta = np.array(point) - np.array(pt)
                if np.sqrt(np.sum(delta**2)) < 50:
                    self.view.tool = ConnectionTool(self, name, pt)
                    return
            for name, pt in wire_outputs.items():
                delta = np.array(point) - np.array(pt)
                if np.sqrt(np.sum(delta**2)) < 50:
                    self.view.tool = ConnectionTool(self, name, pt)
                    return
            self.view.tool = DisconnectionTool(self, point)

    def handle_mousebuttonup(self, ev):
        pass

    def handle_mousemotion(self, ev):
        pass

class ContextMenu:
    def __init__(self, tool, mouse_pos, commands, *args):
        self.view = tool.view
        self.tool = tool
        self.mouse_pos = mouse_pos
        self.commands = commands
        self.args = args
        self.rect = pygame.Rect(mouse_pos - np.array([75, 0]), (150, 10 + 15 * len(commands)))
        self.selected = None

    def draw(self, screen):
        mouse_pos = pygame.mouse.get_pos()
        rect = self.rect
        pygame.draw.rect(screen, (0, 0, 0), rect.move(-2, 2), 0, 3)
        pygame.draw.rect(screen, (60, 60, 60), rect, 0, 3)
        pygame.draw.rect(screen, (200, 200, 200), rect, 2, 3)
        rect = rect.inflate((-10, -10))
        x, y = rect.x, rect.y
        self.selected = None
        for i, (name, _) in enumerate(self.commands):
            subrect = pygame.Rect(rect.x, rect.y, rect.width, 15)
            if subrect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, (0, 0, 255), subrect, 0, 0)
                self.selected = i
            text = self.view.editor.font.render(name, True, (200,200,200))
            screen.blit(text, (x, y))
            y += 15

    def handle_mousebuttondown(self, ev):
        self.view.tool = self.tool
        if self.selected is not None:
            self.commands[self.selected][1](*self.args)

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
    def __init__(self, tool, port, point):
        self.view = tool.view
        self.tool = tool
        self.port = port
        self.point = point
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
        for name, pt in wire_inputs.items():
            delta = np.array(point) - np.array(pt)
            if np.sqrt(np.sum(delta**2)) < 50:
                selected = name
        for name, pt in wire_outputs.items():
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
            if x >= 800:
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
            element.draw(screen, font, self.view.editor.definitions, scroll)

        for point in self.wire_inputs.values():
            point = point[0] + scroll[0], point[1] + scroll[1]
            pygame.draw.circle(screen, (255, 0, 0), point, 7.5, 0)
            pygame.draw.circle(screen, (255, 255, 0), point, 7.5, 1)
        for point in self.wire_outputs.values():
            point = point[0] + scroll[0], point[1] + scroll[1]
            pygame.draw.circle(screen, (255, 0, 0), point, 7.5, 0)
            pygame.draw.circle(screen, (255, 255, 0), point, 7.5, 1)

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

    def draw(element, screen, font, definitions, scroll):
        cell = element.cell
        d = definitions.retrieve(cell.definition)
        x, y = element.rect.x + scroll[0], element.rect.y + scroll[1]
        rect = pygame.Rect(element.rect.x + scroll[0],
                           element.rect.y + scroll[1],
                           element.rect.width,
                           element.rect.height)
        pygame.draw.rect(screen, (70, 70, 70), rect, 0, 3)
        text = font.render(f"{cell.label}:{cell.definition}", True, (200, 200, 200))
        screen.blit(text, (x,y))
        
        for k, (name, ty) in enumerate(element.inputs):
            text = font.render(name, True, (200, 200, 200))
            screen.blit(text, (x + 10,y + k*30 + 22))
        
        for k, (name, ty) in enumerate(element.outputs):
            text = font.render(name, True, (200, 200, 200))
            screen.blit(text, (x + 150 - text.get_width() - 10,y + k*30 + 22))
        y += 30 * max(len(element.inputs), len(element.outputs))
        for k, (name, ty) in enumerate(element.valueparams):
            color = (200, 200, 200)
            val = cell.params.get(name, None)
            if val is None:
                parameter = d.synthdef.parameters[name][0]
                val = parameter.value[0]
                color = (255, 255, 200)
            #print(d.synthdef.constants)
            text = font.render(f"{name} : {ty}", True, (200, 200, 200))
            screen.blit(text, (x + 75 - text.get_width()//2,y + k*45 + 15))
            text = font.render(f"{val}", True, color)
            screen.blit(text, (x + 75 - text.get_width()//2,y + k*45 + 30))

def layout_cell(cell, wire_inputs, wire_outputs, definitions):
    d = definitions.retrieve(cell.definition)
    inputs = []
    outputs = []
    valueparams = []
    for name, ty in d.desc:
        if isinstance(ty, bus):
            if ty.mode == "out":
                outputs.append((name, ty))
            else:
                inputs.append((name, ty))
        else:
            valueparams.append((name, ty))
    h = 15 + max(len(inputs), len(outputs))*30 + len(valueparams) * 45
    x, y = cell.pos
    rect = pygame.Rect(x - 75, y - h // 2, 150, h)
    gcell = GUICell(cell, rect, inputs, outputs, valueparams)
    for k, (name, ty) in enumerate(inputs):
        point = rect.x, rect.y + 30*k + 30
        wire_inputs[f"{cell.label}:{name}"] = point
    for k, (name, ty) in enumerate(outputs):
        point = rect.x + 150, rect.y + 30*k + 30
        wire_outputs[f"{cell.label}:{name}"] = point
    return gcell

def layout_gui(cells, connections, definitions):
    gui = []
    wire_inputs = {}
    wire_outputs = {}
    
    point = 400, 0
    wire_inputs['output'] = point
    
    for cell in cells:
        gcell = layout_cell(cell, wire_inputs, wire_outputs, definitions)
        gui.append(gcell)

    rects = [gcell.rect for gcell in gui]

    rb = node_editor.WireRouterBuilder(rects)

    start_time = time.monotonic() * 1000

    for name, (x,y) in wire_inputs.items():
        rb.cast_ray((x-5, y), (-1, 0))
    for name, (x,y) in wire_outputs.items():
        rb.cast_ray((x+5, y), (+1, 0))

    router = rb.build()

    wires = []
    for src, dst in connections:
        s = wire_outputs[src]
        e = wire_inputs[dst]
        wire = router.route(s, e)
        wires.append((wire, (255,255,255), (src,dst)))

    return gui, wire_inputs, wire_outputs, wires, router
