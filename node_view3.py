from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from descriptors import bus, kinds
from model2.schema import Synth, random_name
import node_editor
from node_editor import line_intersect_line
import numpy as np
import math
import music
import pygame
import balanced
from simgui import SIMGUI, Grid, Text, Slider

new_temporary = "out : ar 2 = SinOsc.ar 440 * 0.1;"
new_temporary = balanced.RopeSegment(new_temporary, balanced.blank, balanced.blank)

@dataclass
class WirePort:
    pos : Tuple[int, int]
    which : str
    name : str
    spec : Tuple[str, int]
    trace : bool = True

class Layouter:
    def __init__(self, view, cells, connections):
        self.view = view
        self.obstacles = []
        self.inputs = {}
        self.outputs = {}
        self.inputs["system", "out"] = WirePort((400, 0), "input", ("system","out"), ("ar", 2), trace=False)
        self.cells = {}

        for cell in cells:
            synth = cell.synth
            nodebox = self.view.compute_nodebox(synth)
            obs = self.compute_obs(nodebox, cell.pos)
            self.obstacles.append(obs)
            self.cells[cell.name] = obs, cell, nodebox

            x, y = cell.pos
            y -= nodebox.total // 2
            for i, (name, ty) in enumerate(nodebox.inputs):
                pos = x - 150//2, y + i * 24 + 24 + 12
                port = WirePort(pos, "input", (cell.name, name), ty.sans_mode)
                self.inputs[port.name] = port

            for i, (name, ty) in enumerate(nodebox.outputs):
                pos = x + 150//2, y + i * 24 + 24 + 12
                port = WirePort(pos, "output", (cell.name, name), ty.sans_mode)
                self.outputs[port.name] = port

        rb = node_editor.WireRouterBuilder(self.obstacles)
        for port in self.inputs.values():
            if port.trace:
                x, y = port.pos
                rb.cast_ray((x-5, y), (-1, 0))
        for port in self.outputs.values():
            if port.trace:
                x, y = port.pos
                rb.cast_ray((x+5, y), (+1, 0))
        self.router = rb.build()

        self.wires = []
        for src, dst in connections:
            s = self.outputs.get(src, None)
            e = self.inputs.get(dst, None)
            if s and e:
                wire = self.router.route(s.pos, e.pos)
                self.wires.append((wire, color_of_bus(s.spec), (src, dst)))

    def compute_obs(self, nodebox, pos):
        x,y = pos
        return pygame.Rect(x-150//2, y - nodebox.total // 2, 150, nodebox.total)

@dataclass
class NodeBox:
    header : int
    total : int
    inputs   : Any
    outputs  : Any
    params   : Any
    synthdef : Any
            
class Wires:
    def __init__(self, layouter):
        self.layouter = layouter
        self.widget_id = "wires"

    def behavior(self, ui):
        view = self.layouter.view
        if ui.hot_id is None:
            ui.hot_id = self.widget_id
            if ui.mouse_just_pressed and ui.active_id is None:
                ui.active_id = self.widget_id
                view.mx_origin = ui.mouse_pos
                view.active_port = self.pick_port(ui)
            if ui.r_mouse_just_pressed and ui.active_id is None:
                ui.r_active_id = self.widget_id
                view.pan_origin = (
                    view.pan_x - ui.mouse_pos[0],
                    view.pan_y - ui.mouse_pos[1])
        if ui.r_active_id == self.widget_id:
            px, py = view.pan_origin
            mx, my = ui.mouse_pos
            view.pan_x = px + mx
            view.pan_y = py + my
        if ui.active_id == self.widget_id and ui.mouse_just_released:
            if view.active_port is None:
                self.erase_connections(ui)
            else:
                other_port = self.pick_port(ui)
                if other_port is not None:
                    self.insert_connection(ui, other_port)
            return object()

    def erase_connections(self, ui):
        view = self.layouter.view
        posa = np.array(ui.mouse_pos) - (view.pan_x, view.pan_y)
        posb = np.array(view.mx_origin) - (view.pan_x, view.pan_y)
        were_removed = False
        for wire, _, ident in self.layouter.wires:
            wire = list(wire)
            if any(line_intersect_line(p,q, posa, posb) for p,q in zip(wire, wire[1:])):
                view.editor.doc.connections.remove(ident)
                were_removed = True
        if were_removed:
            view.editor.transport.refresh(view.editor.proc)
            view.editor.transport.restart_fabric()

    def insert_connection(self, ui, other_port):
        view = self.layouter.view
        x = view.active_port
        y = other_port
        if x.spec != y.spec:
            return
        if x.which == "input" and y.which == "input":
            return
        if x.which == "output" and y.which == "output":
            return
        if x.which == "input":
            conn = y.name,x.name
        else:
            conn = x.name,y.name
        connections = view.editor.doc.connections
        if conn in connections:
            return
        dscr = view.editor.transport.definitions.descriptors(view.editor.doc.synths)
        if detect_cycle(*conn, connections, dscr):
            return
        view.editor.doc.connections.add(conn)
        view.editor.transport.refresh(view.editor.proc)
        view.editor.transport.restart_fabric()
        
    def pick_port(self, ui):
        view = self.layouter.view
        pos = np.array(ui.mouse_pos) - (view.pan_x, view.pan_y)
        for name, port in self.layouter.inputs.items():
            dx = port.pos - pos
            if np.sum(dx*dx) <= 250:
                return port
        for name, port in self.layouter.outputs.items():
            dx = port.pos - pos
            if np.sum(dx*dx) <= 250:
                return port

    def draw(self, ui, screen):
        view = self.layouter.view
        for wire, color, _ in self.layouter.wires:
            wire = [(px + view.pan_x,
                     py + view.pan_y) for px, py in wire]
            pygame.draw.lines(screen, color, False, wire, 4)
        if ui.active_id == self.widget_id:
            if view.active_port is None:
                pygame.draw.line(screen, (200, 200, 200), view.mx_origin, ui.mouse_pos)
            else:
                pos = view.active_port.pos
                pose = np.array(ui.mouse_pos) - (view.pan_x, view.pan_y)
                wire = self.layouter.router.route(pos, pose)
                wire = [np.array(pos) + (view.pan_x, view.pan_y) for pos in wire]
                pygame.draw.lines(screen, (200, 200, 200), False, wire, 4)

class Ports:
    def __init__(self, layouter):
        self.layouter = layouter
        self.widget_id = "ports"

    def behavior(self, ui):
        return None

    def draw(self, ui, screen):
        for label, port in self.layouter.inputs.items():
            x = self.layouter.view.pan_x + port.pos[0]
            y = self.layouter.view.pan_y + port.pos[1]
            pygame.draw.circle(screen, color_of_bus(port.spec), (x,y), 7.5, 0)
            pygame.draw.circle(screen, (255, 255, 255), (x,y), 7.5, 1)
        for label, port in self.layouter.outputs.items():
            x = self.layouter.view.pan_x + port.pos[0]
            y = self.layouter.view.pan_y + port.pos[1]
            pygame.draw.circle(screen, color_of_bus(port.spec), (x,y), 7.5, 0)
            pygame.draw.circle(screen, (255, 255, 255), (x,y), 7.5, 1)

class NodeView:
    def __init__(self, editor):
        self.editor = editor
        self.active_port = None
        self.mx_origin = (0, 0)
        self.mx_param = None
        self.pan_origin = (0, 0)
        self.synth_to_add = None
        self.intros_pan_x = editor.screen_width // 2
        self.intros_pan_y = editor.screen_height // 2
        self.pan_x = editor.screen_width // 2
        self.pan_y = editor.screen_height // 2
        self.intros = False
        self.selection = None
        self.label_ctl = Text("", 0, None)
        self.active_params = []

    def freshen(self):
        synth_name=random_name()
        pos = (0, 0)
        cell = Synth(name=random_name(), multi=False, synth=synth_name, pos=pos, params={}, type_param=None)
        self.editor.doc.synths.append(cell)
        self.editor.transport.definitions.temp_name = synth_name
        self.editor.transport.definitions.temp_data = new_temporary
        self.editor.transport.definitions.temp_refresh()
        connections = self.editor.doc.connections
        connections.add(((cell.name, "out"), ("system", "out")))
        self.editor.transport.refresh(self.editor.proc)
        self.editor.transport.restart_fabric()

    def present(self, ui):
        # SET CLIP (0, 24, WIDTH, HEIGHT-24-24)
        layouter = Layouter(self,
            self.editor.doc.synths,
            self.editor.doc.connections)
        ui.widget(Wires(layouter))
        for cell in self.editor.doc.synths:
            if ui.widget(CellBox(layouter, cell.name)) == 1:
                self.selection = cell.name
                self.label_ctl = Text(cell.name, 0, None)
        ui.widget(Ports(layouter))
        if ui.button("new", pygame.Rect(0, 36, 24*3, 24), "new_node"):
            self.intros = True
        if ui.button("fresh", pygame.Rect(0, self.editor.screen_height - 24*3, 24*3, 24), "fresh_node"):
            self.freshen()

        if self.selection is not None:
            cell = None
            cell_index = None
            for k, synth in enumerate(self.editor.doc.synths):
                if synth.name == self.selection:
                    cell = synth
                    cell_index = k
            if isinstance(cell, Synth):
                if ui.textbox(self.label_ctl, pygame.Rect(0, 36+24*1+12, 24*6, 24*2), "label_ctl"):
                    newtext = self.label_ctl.text
                    #if newtext not in self.editor.doc.labels:
                    if True: # TODO: do this in better way
                        # TODO: do a document-wide renaming tool
                        #cell = self.editor.doc.labels.pop(self.selection)
                        cell.name = newtext
                        #self.editor.doc.labels[newtext] = cell
                        connections = self.editor.doc.connections
                        for src,dst in list(connections):
                            src2 = src
                            dst2 = dst
                            if src[0] == self.selection:
                                src2 = newtext, src[1]
                            if dst[0] == self.selection:
                                dst2 = newtext, dst[1]
                            if (src,dst) != (src2,dst2):
                                connections.discard((src,dst))
                                connections.add((src2,dst2))
                        self.selection = newtext
                    self.editor.transport.refresh(self.editor.proc)
                    self.editor.transport.restart_fabric()
                if ui.button(["multi=off", "multi=on"][cell.multi], pygame.Rect(0, 36+24*3+12, 24*6, 24), "toggle_multi"):
                    cell.multi = not cell.multi
                    self.editor.transport.refresh(self.editor.proc)
                    self.editor.transport.restart_fabric()
                if ui.button("discard", pygame.Rect(0, 36+24*4+12, 24*6, 24), "discard node"):
                    del self.editor.doc.synths[cell_index]
                    #self.editor.doc.labels.pop(cell.label)
                    for src, dst in list(self.editor.doc.connections):
                        do_remove = False
                        do_remove |= src[0] == cell.name
                        do_remove |= dst[0] == cell.name
                        if do_remove:
                            self.editor.doc.connections.discard((src, dst))
                    self.editor.transport.restart_fabric()

                desc = self.editor.transport.definitions.descriptor(cell)
                if desc.quadratic_controllable:
                    ui.label(f"type param={cell.type_param}", pygame.Rect(0, 36+24*5+12, 24*16, 24))
                    for i, kind in enumerate(kinds):
                        if ui.button(f"={kind}", pygame.Rect(4*24*(i%3), 36+24*6+24*(i//3)+12, 24*4, 24), f"typeparam={kind}"):
                            cell.type_param = kind
        for i, mxparam in reversed(list(enumerate(self.active_params))):
            if ui.button(f"rm",
                pygame.Rect(i*75, self.editor.screen_height - 48, 75, 24),
                f"drop:{i}"):
                del self.active_params[i]
            ui.widget(MXParamWidget(self.editor, mxparam, pygame.Rect(i*75, self.editor.screen_height - 64-48-48, 75, 64+48), f"ctl:{i}"))
            ui.label16c(f"{mxparam.label}", pygame.Rect(i*75, self.editor.screen_height - 64-48-48, 75, 24))
            ui.label16c(f"{mxparam.param}", pygame.Rect(i*75, self.editor.screen_height -48-24, 75, 24))
        if self.intros:
            ui.widget(Intros(self))

    def compute_nodebox(self, synth):
        synthdef, mdesc = self.editor.transport.definitions.definition(synth)
        inputs = []
        outputs = []
        params = []
        for name, ty in mdesc.items():
            if isinstance(ty, bus):
                if ty.mode == "out":
                    outputs.append((name, ty))
                else:
                    inputs.append((name, ty))
            else:
                params.append((name, ty))
        header = 24 + max(len(inputs), len(outputs))*24
        body   = 24 * len(params)
        total  = header + body
        return NodeBox(header, total, inputs, outputs, params, synthdef)

    #def param_editor(self, tag, param):
    #    cell = self.editor.doc.labels[tag]
    #    desc = self.editor.definitions.descriptor(cell)
    #    def text_field_value():
    #        val = cell.params.get(param, None)
    #        if val is None:
    #            parameter = desc.synthdef.parameters[param][0]
    #            val = parameter.value[0]
    #        return stringify(val)
    #    textfield = None
    #    def set_textfield(field, edited=True):
    #        nonlocal textfield
    #        textfield = field
    #        if edited and (val := reader.string_to_value(field.text)) is not None:
    #            cell.params[param] = val
    #            if self.editor.fabric:
    #                self.editor.fabric.control(tag, **{param: val})
    #        get_textfield.invalidate()
    #        self.editor.refresh_layout()
    #    textfield = TextField(text_field_value(), 0, 0, set_textfield)
    #    @Hook
    #    def get_textfield():
    #        return textfield

    #    @context_menu(None, *pygame.mouse.get_pos())
    #    def menu():
    #        layout().style_padding = edges(10)
    #        layout().style_gap = gutters(5)
    #        layout().style_min_width = 100
    #        if desc.field_type(param) != 'number':
    #            with frame():
    #                layout().style_width = 600
    #                layout().style_height = 50
    #                @widget().attach
    #                def _draw_slider_(this, frame):
    #                    val = cell.params.get(param, None)
    #                    if val is None:
    #                        parameter = desc.synthdef.parameters[param][0]
    #                        val = parameter.value[0]
    #                    inset = frame.rect.inflate((-20, -20))
    #                    pygame.draw.rect(frame.screen, (200, 200, 200), inset, 0, 3)
    #                    slider = frame.rect.inflate((-40, -40))
    #                    pygame.draw.rect(frame.screen, (20, 20, 20), slider, 0, 3)
    #                    t = any_to_slider(val, desc.field_type(param))
    #                    x = slider.left + slider.width * t
    #                    knob = pygame.Rect(x - 3, slider.centery - 8, 6, 17)
    #                    pygame.draw.rect(frame.screen, (50, 50, 50), knob, 0, 3)
    #                def _mousebuttondown_(this, frame):
    #                    frame.press(None)
    #                    _mousemotion_(this, frame)
    #                widget().post_mousebuttondown = _mousebuttondown_
    #                def _mousemotion_(this, frame):
    #                     set_textfield(TextField(text_field_value(), textfield.head, textfield.tail, textfield.edit), False).invoke()
    #                     slider = frame.rect.inflate((-40, -40))
    #                     t = (frame.ev.pos[0] - slider.left) / slider.width
    #                     t = max(0, min(1, t))
    #                     cell.params[param] = val = slider_to_any(t, desc.field_type(param))
    #                     if self.editor.fabric:
    #                         self.editor.fabric.control(tag, **{param: val})
 
    #                widget().at_mousemotion = _mousemotion_
    #        with textbox(get_textfield()):
    #            layout().style_min_width = 600
    #    return menu

    #def reset_param(self, tag, param):
    #    cell = self.editor.doc.labels[tag]
    #    desc = self.editor.definitions.descriptor(cell)
    #    cell.params.pop(param, None)
    #    if self.editor.fabric:
    #        parameter = desc.synthdef.parameters[param][0]
    #        val = parameter.value[0]
    #        self.editor.fabric.control(tag, **{param: val})

class Intros:
    def __init__(self, view):
        self.view = view
        self.widget_id = "intros"
        self.rects = []
        self.presentation = []
        for i, synth in enumerate(view.editor.transport.definitions.list_available()):
            nodebox = view.compute_nodebox(synth)
            x = math.cos(i)*(i+10)*10
            y = math.sin(i)*(i+10)*10
            obs = pygame.Rect(x, y-nodebox.total//2, 150, nodebox.total)
            self.rects.append(obs)
            self.presentation.append((synth, nodebox))
        self.rects = resolve_overlaps(self.rects)

    def behavior(self, ui):
        view = self.view
        if ui.hot_id is None:
            ui.hot_id = self.widget_id
            if ui.mouse_just_pressed and ui.active_id is None:
                ui.active_id = self.widget_id
                view.mx_origin = ui.mouse_pos
                pos = np.array(ui.mouse_pos) - (view.intros_pan_x, view.intros_pan_y)
                for rect, (synth, nodebox) in zip(self.rects, self.presentation):
                    if rect.collidepoint(pos):
                        rect = rect.move((view.intros_pan_x, view.intros_pan_y))
                        view.synth_to_add = rect, synth
                        break
                else:
                    view.synth_to_add = None
            if ui.r_mouse_just_pressed and ui.active_id is None:
                ui.r_active_id = self.widget_id
                view.pan_origin = (
                    view.intros_pan_x - ui.mouse_pos[0],
                    view.intros_pan_y - ui.mouse_pos[1])
        if ui.active_id == self.widget_id and ui.mouse_just_released:
            if view.synth_to_add is not None:
                dx = (np.array(ui.mouse_pos) - view.mx_origin)
                pos = view.synth_to_add[0].move((dx[0]-view.pan_x, dx[1]-view.pan_y)).center
                pos = int(pos[0]), int(pos[1])
                synth = view.synth_to_add[1]
                cell = Synth(name=random_name(), multi=False, synth=synth, pos=pos, params={}, type_param=None)
                view.editor.doc.synths.append(cell)
                view.editor.transport.refresh(view.editor.proc)
                view.editor.transport.restart_fabric()
            view.intros = False
            view.synth_to_add = None
            return True
        if ui.r_active_id == self.widget_id:
            px, py = view.pan_origin
            mx, my = ui.mouse_pos
            view.intros_pan_x = px + mx
            view.intros_pan_y = py + my

    def draw(self, ui, screen):
        screen.set_clip(pygame.Rect(0,24, screen.get_width(), screen.get_height()-48))
        if self.view.synth_to_add is not None:
            dx = (np.array(ui.mouse_pos) - self.view.mx_origin)
            pygame.draw.rect(screen, (200,200,200), self.view.synth_to_add[0].move(dx), 1, 3)
            return
        pygame.draw.rect(screen, (100,100,100,100), screen.get_rect(), 0, 0)
        for rect, (synth, nodebox) in zip(self.rects, self.presentation):
            rect = rect.move((self.view.intros_pan_x, self.view.intros_pan_y))
            synthdef = nodebox.synthdef
            pygame.draw.rect(screen, (100, 100, 100), rect, 0, 3)
            if nodebox.synthdef.has_gate:
                pygame.draw.rect(screen, (100, 250, 250), rect, 1, 3)
            else:
                pygame.draw.rect(screen, (250, 250, 250), rect, 1, 3)
            surf = ui.font24.render(synth, True, (200, 200, 200))
            rc = surf.get_rect(center=pygame.Rect(rect.x, rect.y, rect.width, 24).center)
            screen.blit(surf, rc)
            for i, (name, ty) in enumerate(nodebox.inputs):
                rc = pygame.Rect(rect.x, rect.y + 24 + 24*i, rect.width//2, 24)
                surf = ui.font16.render(f"{name}", True, (200, 200, 200))
                r = surf.get_rect(centery=rc.centery, left=rc.left+12)
                screen.blit(surf, r)
                pygame.draw.circle(screen, color_of_bus(ty.sans_mode), (rc.left, rc.centery), 7.5, 0)
                pygame.draw.circle(screen, (255,255,255), (rc.left, rc.centery), 7.5, 1)
            for i, (name, ty) in enumerate(nodebox.outputs):
                rc = pygame.Rect(rect.x + rect.width // 2, rect.y + 24 + 24*i, rect.width//2, 24)
                surf = ui.font16.render(f"{name}", True, (200, 200, 200))
                r = surf.get_rect(centery=rc.centery, right=rc.right-12)
                screen.blit(surf, r)
                pygame.draw.circle(screen, color_of_bus(ty.sans_mode), (rc.right, rc.centery), 7.5, 0)
                pygame.draw.circle(screen, (255,255,255), (rc.right, rc.centery), 7.5, 1)
            for i, (name, ty) in enumerate(nodebox.params):
                rc = pygame.Rect(rect.x, rect.y + nodebox.header + 24*i, rect.width, 24)
                surf = ui.font16.render(f"{name}", True, (200, 200, 200))
                r = surf.get_rect(centery=rc.centery, left=rc.left+12)
                screen.blit(surf, r)
                parameter = nodebox.synthdef.parameters[name][0]
                val = format(parameter.value[0], ".4g")
                color = (255, 255, 200)
                surf = ui.font16.render(str(val), True, color)
                r = surf.get_rect(centery=rc.centery, centerx=rc.left + 5*(rc.width/8))
                screen.blit(surf, r)
        screen.set_clip(None)

def resolve_overlaps(rects, max_iterations=1000, push_strength=0.5):
    """
    Pushes overlapping rectangles apart while trying to maintain relative positions.
    
    Args:
        rects: List of pygame.Rect objects
        max_iterations: Maximum number of iterations to run
        push_strength: How much to push overlapping rects (0-1, higher = faster but less stable)
    
    Returns:
        List of pygame.Rect objects with resolved positions
    """
    # Work with copies to avoid modifying originals
    result = [r.copy() for r in rects]
    
    for iteration in range(max_iterations):
        overlaps_found = False
        
        # Check each pair of rectangles
        for i in range(len(result)):
            for j in range(i + 1, len(result)):
                rect1 = result[i]
                rect2 = result[j]
                
                if rect1.colliderect(rect2):
                    overlaps_found = True
                    
                    # Calculate centers
                    cx1, cy1 = rect1.centerx, rect1.centery
                    cx2, cy2 = rect2.centerx, rect2.centery
                    
                    # Calculate push direction
                    dx = cx2 - cx1
                    dy = cy2 - cy1
                    
                    # Handle exact overlap (push in arbitrary direction)
                    if dx == 0 and dy == 0:
                        dx, dy = 1, 0
                    
                    # Normalize direction
                    distance = math.sqrt(dx * dx + dy * dy)
                    dx /= distance
                    dy /= distance
                    
                    # Calculate overlap amount
                    overlap_x = (rect1.width + rect2.width + 84) / 2 - abs(cx2 - cx1)
                    overlap_y = (rect1.height + rect2.height + 84) / 2 - abs(cy2 - cy1)
                    overlap = min(overlap_x, overlap_y)
                    
                    # Push apart
                    push = overlap * push_strength / 2
                    rect1.centerx -= int(dx * push)
                    rect1.centery -= int(dy * push)
                    rect2.centerx += int(dx * push)
                    rect2.centery += int(dy * push)
        
        # Exit early if no overlaps
        if not overlaps_found:
            break
    
    return result

class CellBox:
    def __init__(self, layout, label):
        self.layout = layout
        self.label = label
        self.rect = layout.cells[label][0]
        self.widget_id = f"cell({label!r})"

    def behavior(self, ui):
        pos = np.array(ui.mouse_pos) - (self.layout.view.pan_x, self.layout.view.pan_y)
        if ui.hot_id is None and self.rect.collidepoint(pos):
            ui.hot_id = self.widget_id
            if ui.mouse_just_pressed and ui.active_id is None:
                ui.active_id = self.widget_id
                self.layout.view.mx_origin = ui.mouse_pos
                nodebox = self.layout.cells[self.label][2]
                mx_ix = (pos[1] - self.rect.top - nodebox.header) // 24
                if 0 <= mx_ix <= len(nodebox.params):
                    self.layout.view.mx_param = nodebox.params[mx_ix][0]
                else:
                    self.layout.view.mx_param = None
        if ui.active_id == self.widget_id and ui.mouse_just_released and self.layout.view.mx_param is None:
            r = self.rect.move(np.array(ui.mouse_pos) - self.layout.view.mx_origin)
            pos = r.center
            pos = int(pos[0]), int(pos[1])
            for synth in self.layout.view.editor.doc.synths:
                if synth.name == self.label:
                    synth.pos = pos
            return 1
        if ui.was_clicked(self):
            if self.layout.view.mx_param is not None:
                for mxparam in self.layout.view.active_params:
                    if (mxparam.label,mxparam.param) == (self.label,self.layout.view.mx_param):
                        return 0
                self.layout.view.active_params.append(
                    MXParam(self.layout.view, self.label, self.layout.view.mx_param))
                return 2
            return 1
        return 0

    def draw(self, ui, screen):
        _, cell, nodebox = self.layout.cells[self.label]
        rect = self.rect.move((self.layout.view.pan_x, self.layout.view.pan_y))
        if ui.active_id == self.widget_id and self.layout.view.mx_param is None:
            r = rect.move(np.array(ui.mouse_pos) - self.layout.view.mx_origin)
            pygame.draw.rect(screen, (200, 200, 200), r, 1, 3)
        pygame.draw.rect(screen, (100, 100, 100), rect, 0, 3)
        if cell.multi:
            pygame.draw.rect(screen, (100, 250, 250), rect, 1, 3)
        else:
            pygame.draw.rect(screen, (250, 250, 250), rect, 1, 3)
        surf = ui.font24.render(f"{cell.name}:{cell.synth}", True, (200, 200, 200))
        rc = surf.get_rect(center=pygame.Rect(rect.x, rect.y, rect.width, 24).center)
        screen.blit(surf, rc)
        for i, (name, ty) in enumerate(nodebox.inputs):
            rc = pygame.Rect(rect.x, rect.y + 24 + 24*i, rect.width//2, 24)
            surf = ui.font16.render(f"{name}", True, (200, 200, 200))
            r = surf.get_rect(centery=rc.centery, left=rc.left+12)
            screen.blit(surf, r)
        for i, (name, ty) in enumerate(nodebox.outputs):
            rc = pygame.Rect(rect.x + rect.width // 2, rect.y + 24 + 24*i, rect.width//2, 24)
            surf = ui.font16.render(f"{name}", True, (200, 200, 200))
            r = surf.get_rect(centery=rc.centery, right=rc.right-12)
            screen.blit(surf, r)
        for i, (name, ty) in enumerate(nodebox.params):
            rc = pygame.Rect(rect.x, rect.y + nodebox.header + 24*i, rect.width, 24)
            surf = ui.font16.render(f"{name}", True, (200, 200, 200))
            r = surf.get_rect(centery=rc.centery, left=rc.left+12)
            screen.blit(surf, r)
            trl = ""
            if self.layout.view.editor.transport.fabric:
                trl = self.layout.view.editor.transport.fabric.trail[self.label].get(name, "")
                if isinstance(trl, float):
                    trl = format(trl, ".4g")
            val = cell.params.get(name, None)
            if val is None:
                parameter = nodebox.synthdef.parameters[name][0]
                val = format(parameter.value[0], ".4g")
                color = (255, 255, 200)
            else:
                if isinstance(val, float):
                    val = format(val, ".4g")
                color = (200, 200, 200)
            surf = ui.font16.render(str(val), True, color)
            r = surf.get_rect(centery=rc.centery, centerx=rc.left + 5*(rc.width/8))
            screen.blit(surf, r)
            surf = ui.font16.render(str(trl), True, color)
            r = surf.get_rect(centery=rc.centery, centerx=rc.left + 7*(rc.width/8))
            screen.blit(surf, r)

class MXParam:
    def __init__(self, view, label, param):
        self.param = param
        for synth in view.editor.doc.synths:
            if synth.name == label:
                self.cell = synth
        self.desc = view.editor.transport.definitions.descriptor(self.cell)

    @property
    def label(self):
        return self.cell.name

class MXParamWidget:
    def __init__(self, editor, mxparam, rect, widget_id):
        self.editor = editor
        self.mxparam = mxparam
        self.rect = rect
        self.widget_id = widget_id

    def behavior(self, ui):
        mx = self.mxparam
        ui.grab_active(self)
        changed = False
        if ui.active_id == self.widget_id:
            y = (ui.mouse_pos[1] - self.rect.top - 8) / (self.rect.height - 16)
            y = min(1, max(0, y))
            val = slider_to_any(1 - y, mx.desc.field_type(mx.param))
            mx.cell.params[mx.param] = val
            if self.editor.transport.fabric:
                self.editor.transport.fabric.control(mx.cell.name, **{mx.param: val})
            changed = True
        return changed
        
    def draw(self, ui, screen):
        mx = self.mxparam
        val = mx.cell.params.get(mx.param, None)
        if val is None:
            parameter = mx.desc.synthdef.parameters[mx.param][0]
            val = parameter.value[0]
        pygame.draw.rect(screen, (200,200,200), self.rect, 1)
        x = any_to_slider(val, mx.desc.field_type(mx.param))
        if x is not None:
            posa = self.rect.left,  self.rect.top + (1-x) * self.rect.height
            posb = self.rect.right, self.rect.top + (1-x) * self.rect.height
            pygame.draw.line(screen, (255,255,0), posa, posb, 2)
        txt = format(val, ".4g")
        if mx.desc.field_type(mx.param) == "pitch":
            txt = repr(music.Pitch.from_midi(int(val)))
        surf = ui.font16.render(" " + txt + " ", True, (200,200,200))
        rc = surf.get_rect(center=self.rect.center)
        pygame.draw.rect(screen, (30,30,30,128), rc)
        screen.blit(surf, rc)

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
        return linlin(val, -80, 10, 0, 1)
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
        return linlin(val, 0, 1, -80, 10)
    if ty == 'duration':
        return linlin(val, 0, 1, 0, 10)
    return val

def linlin(val, a0, a1, b0, b1):
    return ((val - a0) / (a1-a0)) * (b1-b0) + b0

def detect_cycle(i, o, connections, descriptors):
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
                    if il == label and descriptors[ol].field_mode(ox) == 'in':
                        visit(ol)
        visit(ol)
        return (il in visited)
    return False

def color_of_bus(bus):
    if bus == ('ar', 1):
        return (100, 255, 0)
    if bus == ('ar', 2):
        return (255, 0, 0)
    if bus == ('kr', 1):
        return (255, 255, 0)
    return (255, 255, 255)
