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
from fabric import Definitions, Cell, Fabric
import music
from descriptors import simple, bus
from node_editor import ray_intersect_aabb, line_intersect_line
import time
import node_editor
import sequencer

# TODO: fx with a,b,c,t,trigger allows linear control.

class NodeEditorView:
    def __init__(self, editor):
        self.editor = editor
        self.tool = NodeEditorTool(self)
        self.s1 = editor.make_spectroscope(bus=0)
        self.s2 = editor.make_spectroscope(bus=1)
        self.layout = layout_gui(self.editor.doc.cells, self.editor.doc.connections, self.editor.definitions)
        self.scroll = np.array([0,0])
        
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
            cell = element.cell
            d = self.editor.definitions.retrieve(cell.definition)
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
            
        
        for point in wire_inputs.values():
                point = point[0] + scroll[0], point[1] + scroll[1]
                pygame.draw.circle(screen, (255, 0, 0), point, 7.5, 0)
                pygame.draw.circle(screen, (255, 255, 0), point, 7.5, 1)
        for point in wire_outputs.values():
                point = point[0] + scroll[0], point[1] + scroll[1]
                pygame.draw.circle(screen, (255, 0, 0), point, 7.5, 0)
                pygame.draw.circle(screen, (255, 255, 0), point, 7.5, 1)
        
        point = 700 - 10, 500
        point = point[0] + scroll[0], point[1] + scroll[1]
        text = font.render(f"output", True, (200, 200, 200))
        screen.blit(text, (point[0] + 10, point[1] - 9))

    def handle_keydown(self, ev):
        pass

    def close(self):
        self.s1.close()
        self.s2.close()

class NodeEditorTool:
    def __init__(self, view):
        self.view = view
        self.mouse_point = 0, 0
        self.mouse_origin = 0, 0
        self.selected = None
        self.port_selected = None
        self.port_wire = []

    def draw(self, screen):
        font = self.view.editor.font
        pos = pygame.mouse.get_pos()
        text = font.render("NODE EDITOR", True, (200,200,200))
        screen.blit(text, pos)

        gui, wire_inputs, wire_outputs, wires, router = self.view.layout
        scroll = self.view.scroll

        if self.port_selected and self.port_wire:
            wire = [(p[0] + scroll[0], p[1] + scroll[1]) for p in self.port_wire]
            pygame.draw.lines(screen, (0,255,0), False, wire, 4)
        
        elif pygame.mouse.get_pressed(num_buttons=3)[0]:
            pos = pygame.mouse.get_pos()
            pos1 = self.mouse_origin[0] + scroll[0], self.mouse_origin[1] + scroll[1]
            pygame.draw.line(screen, (255,0,0), pos, pos1, 5)

    def handle_mousebuttondown(self, ev):
        gui, wire_inputs, wire_outputs, wires, router = self.view.layout
        event = ev
        mouse_point = self.mouse_point
        mouse_origin = self.mouse_origin
        selected = self.selected
        port_selected = self.port_selected
        port_wire = self.port_wire
        scroll = self.view.scroll

        point = event.pos[0] - scroll[0], event.pos[1] - scroll[1]
        mouse_point = event.pos
        mouse_origin = point = event.pos[0] - scroll[0], event.pos[1] - scroll[1]
        selected = "screen"
        for gcell in gui:
            rect = pygame.Rect(gcell.rect.x, gcell.rect.y, gcell.rect.width, 15)
            if rect.collidepoint(point):
                selected = gcell
        if event.button == 1:
            selected = None
            for name, pt in wire_inputs.items():
                delta = np.array(point) - np.array(pt)
                if np.sqrt(np.sum(delta**2)) < 50:
                    port_selected = (name, pt)
            for name, pt in wire_outputs.items():
                delta = np.array(point) - np.array(pt)
                if np.sqrt(np.sum(delta**2)) < 50:
                    port_selected = (name, pt)

        self.mouse_point = mouse_point
        self.mouse_origin = mouse_origin
        self.selected = selected
        self.port_selected = port_selected
        self.port_wire = port_wire

    def handle_mousebuttonup(self, ev):
        gui, wire_inputs, wire_outputs, wires, router = self.view.layout
        scroll = self.view.scroll
        event = ev
        mouse_point = self.mouse_point
        mouse_origin = self.mouse_origin
        selected = self.selected
        port_selected = self.port_selected
        port_wire = self.port_wire
        selected = None
        point = event.pos[0] - scroll[0], event.pos[1] - scroll[1]
        if event.button == 1 and port_selected:
            port_selected1 = None
            for name, pt in wire_inputs.items():
                delta = np.array(point) - np.array(pt)
                if np.sqrt(np.sum(delta**2)) < 50:
                    port_selected1 = (name, pt)
            for name, pt in wire_outputs.items():
                delta = np.array(point) - np.array(pt)
                if np.sqrt(np.sum(delta**2)) < 50:
                    port_selected1 = (name, pt)
            if port_selected1:
                name0 = port_selected[0]
                name1 = port_selected1[0]
                if name1 in wire_outputs:
                    name1, name0 = name0, name1
                if name0 in wire_outputs and name1 in wire_inputs and (name0,name1) not in self.view.editor.doc.connections and not detect_cycle(name0, name1, self.view.editor.doc.connections, self.view.editor.definitions):
                    self.view.editor.doc.connections.add((name0, name1))
                    restart_fabric(self.view.editor)
                    self.view.layout = layout_gui(self.view.editor.doc.cells, self.view.editor.doc.connections, self.view.editor.definitions)
            port_selected = None
        elif event.button == 1:
            were_removed = False
            for wire, color, ident in wires:
                wire = list(wire)
                if any(line_intersect_line(p,q, point, mouse_origin) for p,q in zip(wire, wire[1:])):
                    self.view.editor.doc.connections.remove(ident)
                    were_removed = True
            if were_removed:
                restart_fabric(self.view.editor)
                self.view.layout = layout_gui(self.view.editor.doc.cells, self.view.editor.doc.connections, self.view.editor.definitions)

        self.mouse_point = mouse_point
        self.mouse_origin = mouse_origin
        self.selected = selected
        self.port_selected = port_selected
        self.port_wire = port_wire

    def handle_mousemotion(self, ev):
        gui, wire_inputs, wire_outputs, wires, router = self.view.layout
        scroll = self.view.scroll
        event = ev
        mouse_point = self.mouse_point
        mouse_origin = self.mouse_origin
        selected = self.selected
        port_selected = self.port_selected
        port_wire = self.port_wire
        dx = event.pos[0] - mouse_point[0]
        dy = event.pos[1] - mouse_point[1]
        if selected is not None and selected != "screen":
            selected.cell.pos = selected.cell.pos[0] + dx, selected.cell.pos[1] + dy
            self.view.layout = layout_gui(self.view.editor.doc.cells, self.view.editor.doc.connections, self.view.editor.definitions)
        elif selected == "screen" and event.buttons[2]:
            scroll = scroll[0] + dx, scroll[1] + dy
        elif port_selected:
            pos = np.array(pygame.mouse.get_pos()) - np.array(scroll)
            pt = np.array(port_selected[1])
            port_wire = router.route(pos, pt, add_cost=False)
        mouse_point = event.pos

        self.mouse_point = mouse_point
        self.mouse_origin = mouse_origin
        self.selected = selected
        self.port_selected = port_selected
        self.port_wire = port_wire
        self.view.scroll = scroll

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

def layout_gui(cells, connections, definitions):
    gui = []
    wire_inputs = {}
    wire_outputs = {}
    
    point = 700 - 10, 500
    wire_inputs['output'] = point
    
    for cell in cells:
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
        gui.append(gcell)
        for k, (name, ty) in enumerate(inputs):
            point = rect.x, rect.y + 30*k + 30
            wire_inputs[f"{cell.label}:{name}"] = point
        for k, (name, ty) in enumerate(outputs):
            point = rect.x + 150, rect.y + 30*k + 30
            wire_outputs[f"{cell.label}:{name}"] = point

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
