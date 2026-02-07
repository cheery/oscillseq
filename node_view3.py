from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from descriptors import bus, kinds
from model import Cell, stringify, reader
import node_editor
from node_editor import line_intersect_line
import numpy as np
import math
import music
import pygame
from simgui import SIMGUI, Grid, Text, Slider

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
        self.inputs["output"] = WirePort((400, 0), "input", "output", ("ar", 2), trace=False)
        self.cells = {}

        for cell in cells:
            synth = cell.synth
            synthdef, mdesc = self.view.editor.definitions.definition(synth)
            x,y = cell.pos
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
            y -= total // 2
            self.obstacles.append(obs := pygame.Rect(x-150//2, y, 150, total))
            self.cells[cell.label] = (obs, cell, header, inputs, outputs, params, synthdef)

            for i, (name, ty) in enumerate(inputs):
                pos = x - 150//2, y + i * 24 + 24 + 12
                port = WirePort(pos, "input", f"{cell.label}:{name}", ty.sans_mode)
                self.inputs[port.name] = port

            for i, (name, ty) in enumerate(outputs):
                pos = x + 150//2, y + i * 24 + 24 + 12
                port = WirePort(pos, "output", f"{cell.label}:{name}", ty.sans_mode)
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
            
class Wires:
    def __init__(self, layouter):
        self.layouter = layouter
        self.widget_id = "wires"

    def behavior(self, ui):
        if ui.hot_id is None:
            ui.hot_id = self.widget_id
            if ui.r_mouse_just_pressed and ui.active_id is None:
                ui.r_active_id = self.widget_id
                self.layouter.view.pan_origin = (
                    self.layouter.view.pan_x - ui.mouse_pos[0],
                    self.layouter.view.pan_y - ui.mouse_pos[1])
        if ui.r_active_id == self.widget_id:
            px, py = self.layouter.view.pan_origin
            mx, my = ui.mouse_pos
            self.layouter.view.pan_x = px + mx
            self.layouter.view.pan_y = py + my

    def draw(self, ui, screen):
        for wire, color, _ in self.layouter.wires:
            wire = [(px + self.layouter.view.pan_x,
                     py + self.layouter.view.pan_y) for px, py in wire]
            pygame.draw.lines(screen, color, False, wire, 4)

   # def pick_port(self, pointer):
   #     pointer = np.array(pointer)
   #     for tag, pos in self.inputs.values():
   #         delta = (pointer - pos)
   #         if np.sum(delta*delta) <= 50*50:
   #             return tag, pos
   #     for tag, pos in self.outputs.values():
   #         delta = (pointer - pos)
   #         if np.sum(delta*delta) <= 50*50:
   #             return tag, pos

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
        self.pan_x = editor.screen_width // 2
        self.pan_y = editor.screen_height // 2

    def present(self, ui):
        # SET CLIP (0, 24, WIDTH, HEIGHT-24-24)
        layouter = Layouter(self,
            self.editor.doc.cells,
            self.editor.doc.connections)
        ui.widget(Wires(layouter))
        for cell in self.editor.doc.cells:
            ui.widget(CellBox(layouter, cell.label))
        ui.widget(Ports(layouter))

    def scene_layout(self, scene):
        with frame():
            widget().tag = "editor"
            widget().mouse_hit_rect = False
            layout().shifter = self.pan
            layout().style_position_type = "absolute"
            layout().style_position = edges(0)
            widget().attach(wl := WireLayouter(scene[1]))

            for cell in scene[0]:
                self.node_layout(*cell)

            with self.port_layout(WirePort("input", "output", ('ar', 2), trace=False)):
                layout().style_position = edges(left=50*pc, top=50*pc)
                layout().shifter = AnchorToCenter((400, 0), widget())
                @widget().attach
                def _draw_name_(this, frame):
                    x, y = frame.rect.center
                    surface = self.editor.font.render("output", True, (200, 200, 200))
                    frame.screen.blit(surface, (x + 10, y - surface.get_height()*0.5))

            @widget().attach
            def _draw_disconnector_(this, frame):
                if frame.same(frame.ui.pressed):
                    mt = frame.ui.mouse_tool
                    if isinstance(mt, Introduce):
                        pos = np.array(frame.ui.pointer)
                        pygame.draw.rect(frame.screen, (200, 200, 200), mt.rect.move(pos), 1, 3)
                    elif isinstance(mt, Connector):
                        wire = [np.array(p) + frame.rect.topleft for p in mt.wire]
                        pygame.draw.lines(frame.screen, (200, 200, 200), False, wire, 4)
                    elif isinstance(mt, Disconnector):
                        pos0 = np.array(mt.pos0) + frame.rect.topleft
                        pos1 = np.array(mt.pos1) + frame.rect.topleft
                        pygame.draw.line(frame.screen, (200, 200, 200), pos0, pos1)

            def _mousebuttondown_(this, frame):
                if frame.ev.button == 1:
                    tagpos = wl.pick_port(frame.pointer)
                    if tagpos is None:
                        frame.press(Disconnector(self, wl, frame.pointer))
                    else:
                        frame.press(Connector(self, wl, *tagpos))
                elif frame.ev.button == 3:
                    frame.press(PanOrMenu(self, frame.ev.pos))
                else:
                    raise NoCapture
            widget().post_mousebuttondown = _mousebuttondown_

        @widget().attach
        def _unset_clip_(this, frame):
            frame.screen.set_clip(None)


    #def refresh(self):
    #    scene = []
    #    for cell in self.editor.doc.cells:
    #        scene.append((cell.label, cell.synth, tuple(cell.pos)))
    #    self.scene = tuple(scene), frozenset(self.editor.doc.connections)

    def node_layout(self, tag, synth, pos, preview=False):
        synthdef, mdesc = self.editor.definitions.definition(synth)
        if not preview:
            layout().style_position_type = "absolute"
            layout().style_position = edges(left=50*pc, top=50*pc)
            layout().shifter = AnchorToCenter(pos, widget())
        else:
            layout().style_margin = edges(10)
            layout().style_align_self = "center"
            def _mousebuttondown_(this, frame):
                x, y = frame.ev.pos
                rect = frame.rect.move(-x, -y)
                frame.emit(self.editor.leave_popups)
                frame.emit(self.introduce(rect, synth))
            widget().pre_mousebuttondown = _mousebuttondown_
        layout().tag = "obstacle"
        @widget().attach
        def _draw_rect_(this, frame):
            pygame.draw.rect(frame.screen, (70,70,70), frame.rect, 0, 3)
            if preview:
                    pygame.draw.rect(frame.screen, (70,200,200), frame.rect, 2, 3)
            else:
                cell = self.editor.doc.labels[tag]
                if cell.multi:
                    pygame.draw.rect(frame.screen, (70,200,200), frame.rect, 2, 3)

        with frame():
            layout().style_padding = edges(0, 10, 2.5, 10)
            if preview:
                label(synth)
            else:
                label(f"{tag}:{synth}")
                widget().tag = "header"

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

        with frame():
            layout().style_flow_direction = "row"
            with frame():
                layout().style_flex = 1
                layout().style_flex_grow = 1
                layout().style_padding = edges(left=10, right=5)
                for name, ty in inputs:
                    with frame():
                        label(name)
                        with self.port_layout(WirePort("input", f"{tag}:{name}", ty.sans_mode)):
                            layout().style_position = edges(left = -10, top = 50*pc)
                        layout().style_padding = edges(2.5, 0)
            with frame():
                layout().style_flex = 1
                layout().style_flex_grow = 1
                layout().style_align_items = "flex_end"
                layout().style_padding = edges(left=5, right=10)
                for name, ty in outputs:
                    with frame():
                        label(name)
                        with self.port_layout(WirePort("output", f"{tag}:{name}", ty.sans_mode)):
                            layout().style_position = edges(right = -10, top = 50*pc)
                        layout().style_padding = edges(2.5, 0)

        for name, ty in params:
            with button(self.editor.enter_popup(self.param_editor, tag, name), None, self.reset_param(tag, name), decor=False, keyboard=False):
                layout().style_padding = edges(2.5, 10)
                with label(name):
                    layout().style_align_self = "center"
                with frame():
                    layout().style_height = 10
                    layout().style_min_width = 120
                    widget().tag = name
        layout().style_padding = edges(bottom = 5)

        if not preview:
            def _node_mousebuttondown_(this, frame):
                for header, subframe in this.subscan(frame, lambda x, _: x.tag == "header"):
                    if subframe.inside:
                        if frame.ev.button == 1:
                            rect = frame.rect.move(-np.array(frame.ev.pos))
                            frame.press(DragCell(self, rect, tag, frame.ev.pos))
                            break
                        elif frame.ev.button == 3:
                            frame.emit(self.editor.enter_popup(self.open_node_menu, tag))
                            break
                else:
                    raise NoCapture
            widget().post_mousebuttondown = _node_mousebuttondown_
            @widget().attach
            def _draw_dragging_(this, frame):
                if isinstance(frame.ui.mouse_tool, DragCell) and frame.same(frame.ui.pressed):
                    rect = frame.ui.mouse_tool.rect.move(frame.ui.pointer)
                    pygame.draw.rect(frame.screen, (200, 200, 200), rect, 1, 3)

    def open_palette(self):
        sy = ScrollField()
        @splash_screen(leave_with=self.editor.leave_popups)
        def palette():
            with vscrollable(sy, style_height=100*pc):
                layout().style_flex_direction = "row"
                layout().style_flex_wrap = "wrap"
                for synth in self.editor.definitions.list_available():
                    self.node_layout("", synth, (0,0), preview=True)
        return palette

    def introduce(self, rect, synth):
        get_editor = lambda widget, subframe: widget.tag == "editor"
        for node, frame in self.editor.scan(get_editor):
            frame.press(Introduce(self, rect, synth))

    def open_canvas_menu(self):
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            with button(self.editor.enter_popup(self.open_palette)):
                label(f"new")
        return menu

    def open_node_menu(self, tag):
        cell = self.editor.doc.labels[tag]
        desc = self.editor.definitions.descriptor(cell)
        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            with button(self.toggle_multi(tag)):
                on_off = "on" if cell.multi else "off"
                label(f"multi={on_off}")
            if desc.quadratic_controllable:
                with button(self.editor.enter_popup(self.open_type_param_menu, tag)):
                    label(f"type param={cell.type_param}")
            with button(self.remove_node(tag)):
                label(f"remove")

        return menu

    def toggle_multi(self, tag):
        cell = self.editor.doc.labels[tag]
        cell.multi = not cell.multi
        self.editor.restart_fabric()
        self.editor.leave_popups().invoke()

    def open_type_param_menu(self, tag):
        @context_menu(None, *pygame.mouse.get_pos(), leave_with=self.editor.leave_popups)
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            for name in kinds:
                with button(self.set_type_param(tag, name)):
                    label(name)
        return menu

    def set_type_param(self, tag, type_param):
        cell = self.editor.doc.labels[tag]
        cell.type_param = type_param
        self.editor.leave_popups().invoke()

    def remove_node(self, tag):
        cell = self.editor.doc.labels[tag]
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
        self.editor.restart_fabric()
        self.editor.leave_popups().invoke()

    def param_editor(self, tag, param):
        cell = self.editor.doc.labels[tag]
        desc = self.editor.definitions.descriptor(cell)
        def text_field_value():
            val = cell.params.get(param, None)
            if val is None:
                parameter = desc.synthdef.parameters[param][0]
                val = parameter.value[0]
            return stringify(val)
        textfield = None
        def set_textfield(field, edited=True):
            nonlocal textfield
            textfield = field
            if edited and (val := reader.string_to_value(field.text)) is not None:
                cell.params[param] = val
                if self.editor.fabric:
                    self.editor.fabric.control(tag, **{param: val})
            get_textfield.invalidate()
            self.editor.refresh_layout()
        textfield = TextField(text_field_value(), 0, 0, set_textfield)
        @Hook
        def get_textfield():
            return textfield

        @context_menu(None, *pygame.mouse.get_pos())
        def menu():
            layout().style_padding = edges(10)
            layout().style_gap = gutters(5)
            layout().style_min_width = 100
            if desc.field_type(param) != 'number':
                with frame():
                    layout().style_width = 600
                    layout().style_height = 50
                    @widget().attach
                    def _draw_slider_(this, frame):
                        val = cell.params.get(param, None)
                        if val is None:
                            parameter = desc.synthdef.parameters[param][0]
                            val = parameter.value[0]
                        inset = frame.rect.inflate((-20, -20))
                        pygame.draw.rect(frame.screen, (200, 200, 200), inset, 0, 3)
                        slider = frame.rect.inflate((-40, -40))
                        pygame.draw.rect(frame.screen, (20, 20, 20), slider, 0, 3)
                        t = any_to_slider(val, desc.field_type(param))
                        x = slider.left + slider.width * t
                        knob = pygame.Rect(x - 3, slider.centery - 8, 6, 17)
                        pygame.draw.rect(frame.screen, (50, 50, 50), knob, 0, 3)
                    def _mousebuttondown_(this, frame):
                        frame.press(None)
                        _mousemotion_(this, frame)
                    widget().post_mousebuttondown = _mousebuttondown_
                    def _mousemotion_(this, frame):
                         set_textfield(TextField(text_field_value(), textfield.head, textfield.tail, textfield.edit), False).invoke()
                         slider = frame.rect.inflate((-40, -40))
                         t = (frame.ev.pos[0] - slider.left) / slider.width
                         t = max(0, min(1, t))
                         cell.params[param] = val = slider_to_any(t, desc.field_type(param))
                         if self.editor.fabric:
                             self.editor.fabric.control(tag, **{param: val})
 
                    widget().at_mousemotion = _mousemotion_
            with textbox(get_textfield()):
                layout().style_min_width = 600
        return menu

    def reset_param(self, tag, param):
        cell = self.editor.doc.labels[tag]
        desc = self.editor.definitions.descriptor(cell)
        cell.params.pop(param, None)
        if self.editor.fabric:
            parameter = desc.synthdef.parameters[param][0]
            val = parameter.value[0]
            self.editor.fabric.control(tag, **{param: val})

class CellBox:
    def __init__(self, layout, label):
        self.layout = layout
        self.label = label
        self.rect = layout.cells[label][0]
        self.widget_id = f"cell({label!r})"

    def behavior(self, ui):
        return None

    def draw(self, ui, screen):
        _, cell, header, inputs, outputs, params, synthdef = self.layout.cells[self.label]
        rect = self.rect.move((self.layout.view.pan_x, self.layout.view.pan_y))
        pygame.draw.rect(screen, (100, 100, 100), rect, 0, 3)
        if cell.multi:
            pygame.draw.rect(screen, (100, 250, 250), rect, 1, 3)
        else:
            pygame.draw.rect(screen, (250, 250, 250), rect, 1, 3)
        surf = ui.font24.render(f"{cell.label}:{cell.synth}", True, (200, 200, 200))
        rc = surf.get_rect(center=pygame.Rect(rect.x, rect.y, rect.width, 24).center)
        screen.blit(surf, rc)
        for i, (name, ty) in enumerate(inputs):
            rc = pygame.Rect(rect.x, rect.y + 24 + 24*i, rect.width//2, 24)
            surf = ui.font16.render(f"{name}", True, (200, 200, 200))
            rc = surf.get_rect(centery=rc.centery, left=rc.left+12)
            screen.blit(surf, rc)
        for i, (name, ty) in enumerate(outputs):
            rc = pygame.Rect(rect.x + rect.width // 2, rect.y + 24 + 24*i, rect.width//2, 24)
            surf = ui.font16.render(f"{name}", True, (200, 200, 200))
            rc = surf.get_rect(centery=rc.centery, right=rc.right-12)
            screen.blit(surf, rc)
        for i, (name, ty) in enumerate(params):
            rc = pygame.Rect(rect.x, rect.y + header + 24*i, rect.width, 24)
            surf = ui.font16.render(f"{name}", True, (200, 200, 200))
            r = surf.get_rect(centery=rc.centery, left=rc.left+12)
            screen.blit(surf, r)
            trl = ""
            if self.layout.view.editor.fabric:
                trl = self.layout.view.editor.fabric.trail[self.label].get(name, None)
                if isinstance(trl, float):
                    trl = format(trl, ".4g")
            val = cell.params.get(name, None)
            if val is None:
                parameter = synthdef.parameters[name][0]
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

#class Introduce:
#    def __init__(self, view, rect, synth):
#        self.view = view
#        self.rect = rect
#        self.synth = synth
#
#    def at_mousebuttonup(self, this, frame):
#        point = np.array(frame.ev.pos) - frame.rect.center
#        pos = self.rect.move(point).center
#        pos = int(pos[0]), int(pos[1])
#        cell = Cell("", multi=False, synth=self.synth, pos=pos, params={}, type_param=None)
#        cell = self.view.editor.doc.intro(cell)
#        self.view.editor.doc.cells.append(cell)
#        self.view.editor.refresh_layout()
#        self.view.editor.restart_fabric()
#
#class DragCell:
#    def __init__(self, view, rect, tag, pos):
#        self.view = view
#        self.rect = rect
#        self.tag = tag
#        self.pos = pos
#
#    def at_mousebuttonup(self, this, frame):
#        cell = self.view.editor.doc.labels[self.tag]
#        pos = np.array(frame.ev.pos) - self.pos + cell.pos
#        cell.pos = int(pos[0]), int(pos[1])
#        self.view.editor.refresh_layout()
#
#class Connector:
#    def __init__(self, view, wl, tag, pos):
#        self.view = view
#        self.wl = wl
#        self.tag = tag
#        self.pos = pos
#        self.endpos = pos
#        self.wire = self.wl.router.route(self.pos, self.endpos)
#
#    def at_mousebuttonup(self, this, frame):
#        tagpos = self.wl.pick_port(frame.pointer)
#        if tagpos is None or self.tag.spec != tagpos[0].spec:
#            return
#        tag0 = self.tag
#        tag1 = tagpos[0]
#        if tag1.name in self.wl.outputs:
#            tag0, tag1 = tag1, tag0
#        if tag0.name not in self.wl.outputs or tag1.name not in self.wl.inputs:
#            return
#        connection = tag0.name, tag1.name
#        connections = self.view.editor.doc.connections
#        descrs = self.view.editor.definitions.descriptors(self.view.editor.doc.cells)
#        if connection in connections:
#            return
#        if detect_cycle(tag0.name, tag1.name, connections, descrs):
#            return
#        self.view.editor.doc.connections.add(connection)
#        self.view.editor.restart_fabric()
#        self.view.editor.refresh_layout()
#
#    def at_mousemotion(self, this, frame):
#        self.endpos = frame.pointer
#        self.wire = self.wl.router.route(self.pos, self.endpos)
#
#def detect_cycle(i, o, connections, descriptors):
#    if ":" in i and ":" in o:
#        il,ix = i.split(":")
#        ol,ox = o.split(":")
#        visited = set()
#        def visit(label):
#            visited.add(label)
#            for src,dst in connections:
#                if ":" in src and ":" in dst:
#                    il,ix = src.split(":")
#                    ol,ox = dst.split(":")
#                    if il == label and descriptors[ol].field_mode(ox) == 'in':
#                        visit(ol)
#        visit(ol)
#        return (il in visited)
#    return False
#
#class Disconnector:
#    def __init__(self, view, wl, pos):
#        self.view = view
#        self.wl = wl
#        self.pos0 = pos
#        self.pos1 = pos
#
#    def at_mousebuttonup(self, this, frame):
#        were_removed = False
#        for wire, _, ident in self.wl.wires:
#            wire = list(wire)
#            if any(line_intersect_line(p,q, self.pos0, self.pos1) for p,q in zip(wire, wire[1:])):
#                self.view.editor.doc.connections.remove(ident)
#                were_removed = True
#        if were_removed:
#            self.view.editor.restart_fabric()
#            self.view.editor.refresh_layout()
#
#    def at_mousemotion(self, this, frame):
#        self.pos1 = frame.pointer
#
#class PanOrMenu:
#    def __init__(self, view, pos):
#        self.view = view
#        self.pos  = pos
#
#    def at_mousebuttonup(self, this, frame):
#        if self.pos:
#            frame.emit(self.view.editor.enter_popup(self.view.open_canvas_menu))
#
#    def at_mousemotion(self, this, frame):
#        self.view.pan.x -= frame.ev.rel[0]
#        self.view.pan.y -= frame.ev.rel[1]
#        if self.pos:
#            delta = np.array(self.pos) - frame.ev.pos
#            if np.sum(delta*delta) >= 10:
#                self.pos = None

def color_of_bus(bus):
    if bus == ('ar', 1):
        return (100, 255, 0)
    if bus == ('ar', 2):
        return (255, 0, 0)
    if bus == ('kr', 1):
        return (255, 255, 0)
    return (255, 255, 255)
