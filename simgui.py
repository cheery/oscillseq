"""
Semi-immediate mode GUI

Explicit state like in IMGUI (you pass all data)
Only traverses your presentation when state changes.
"""
import pygame
from dataclasses import dataclass
from typing import Any

class SIMGUI:
    def __init__(self, present):
        self.present = present
        self.layer = []
        self.state = {}

        self.running = True
        self.mouse_pos = (0, 0)
        self.mouse_pressed = False
        self.mouse_just_pressed = False
        self.mouse_just_released = False
        self.r_mouse_pressed = False
        self.r_mouse_just_pressed = False
        self.r_mouse_just_released = False
        self.keyboard_mod = None
        self.keyboard_key = None
        self.keyboard_text = ""

        self.hot_id = None
        self.active_id = None
        self.r_active_id = None
        self.focused_id = None
        self.next_id = None

        self.font16 = pygame.font.Font(None, 16)
        self.font24 = pygame.font.Font(None, 24)
        self.font32 = pygame.font.Font(None, 32)

        self.present(self)

    def process_events(self):
        self.keyboard_text = ""
        self.keyboard_key = None
        self.keyboard_mod = 0
        self.mouse_just_pressed = False
        self.mouse_just_released = False
        self.r_mouse_just_pressed = False
        self.r_mouse_just_released = False
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.TEXTINPUT:
                self.keyboard_text += ev.text
            elif ev.type == pygame.KEYDOWN:
                self.keyboard_key = ev.key
                self.keyboard_mod = ev.mod
            elif ev.type == pygame.MOUSEMOTION:
                self.mouse_pos = ev.pos
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    self.mouse_pressed = True
                    self.mouse_just_pressed = True
                elif ev.button == 3:
                    self.r_mouse_pressed = True
                    self.r_mouse_just_pressed = True
            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button == 1:
                    self.mouse_pressed = False
                    self.mouse_just_released = True
                elif ev.button == 3:
                    self.r_mouse_pressed = False
                    self.r_mouse_just_released = True
        self.hot_id = None
        should_refresh = False
        for widget in reversed(self.layer):
            s = widget.behavior(self)
            if widget.widget_id in self.state and self.state[widget.widget_id] != s:
                should_refresh = True
            self.state[widget.widget_id] = s
        if not self.mouse_pressed:
            self.active_id = None
        if self.mouse_pressed and self.active_id is None:
            self.active_id = self
        if not self.r_mouse_pressed:
            self.r_active_id = None
        if self.r_mouse_pressed and self.r_active_id is None:
            self.r_active_id = self
        if should_refresh:
            self.layer = []
            self.present(self)

    def draw(self, screen):
        for widget in self.layer:
            widget.draw(self, screen)

    def widget(self, widget, default=None):
        self.layer.append(widget)
        return self.state.get(widget.widget_id, default)

    def button(self, text, rect, widget_id, allow_focus=True):
        return self.widget(ButtonWidget(text, rect, widget_id, allow_focus), False)

    def tab_button(self, group, text, rect, widget_id, allow_focus=True):
        return self.widget(TabButtonWidget(group, text, rect, widget_id, allow_focus), False)

    def surface(self, surface, rect):
        return self.widget(Surface(surface, rect, None))

    def label(self, text, rect):
        surface = self.font24.render(text, True, (200, 200, 200))
        return self.surface(surface, rect)

    def label16c(self, text, rect):
        surface = self.font16.render(text, True, (200, 200, 200))
        return self.surface(surface, surface.get_rect(center=rect.center))


    def cover(self, rect, widget_id):
        return self.widget(Cover(rect, widget_id))

    def textbox(self, state, rect, widget_id):
        return self.widget(TextboxWidget(state, rect, widget_id), False)

    def hslider(self, state, rect, widget_id):
        return self.widget(HSliderWidget(state, rect, widget_id), False)

    def vslider(self, state, rect, widget_id):
        return self.widget(VSliderWidget(state, rect, widget_id), False)

    def grab_active(ui, self):
        if ui.hot_id is None and self.rect.collidepoint(ui.mouse_pos):
            ui.hot_id = self.widget_id
            if ui.mouse_just_pressed and ui.active_id is None:
                ui.active_id = self.widget_id

    def r_grab_active(ui, self):
        if ui.hot_id is None and self.rect.collidepoint(ui.mouse_pos):
            ui.hot_id = self.widget_id
            if ui.r_mouse_just_pressed and ui.r_active_id is None:
                ui.r_active_id = self.widget_id

    def grab_focus(ui, self):
        if ui.focused_id is None or ui.active_id == self.widget_id:
            ui.focused_id = self.widget_id
        if ui.focused_id == self.widget_id:
            if ui.keyboard_key == pygame.K_TAB:
                ui.focused_id = None
                if not ui.keyboard_mod & pygame.KMOD_SHIFT:
                    ui.focused_id = ui.next_id
                ui.keyboard_key = None
                ui.keyboard_mod = 0
        ui.next_id = self.widget_id

    def was_clicked(ui, self):
        return ui.mouse_just_released and ui.hot_id == self.widget_id and ui.active_id == self.widget_id

class Grid:
    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def point(self, i, j):
        return self.x + self.w*i, self.y + self.h*j

    def offset(self, i, j):
        x, y = self.point(i, j)
        return Grid(x, y, self.w, self.h)

    def __call__(self, left, top, right, bottom):
        x0, y0 = self.point(left, top)
        x1, y1 = self.point(right, bottom)
        return pygame.Rect(x0, y0, x1-x0, y1-y0)

@dataclass(eq=False)
class ButtonWidget:
    text : str
    rect : pygame.Rect
    widget_id : Any
    allow_focus : bool

    def behavior(self, ui):
        ui.grab_active(self)
        if self.allow_focus:
            ui.grab_focus(self)
        clicked = ui.was_clicked(self)
        if ui.focused_id == self.widget_id and ui.keyboard_key == pygame.K_SPACE:
            clicked = True
        return clicked

    def draw(self, ui, screen):
        if ui.focused_id == self.widget_id:
            pygame.draw.rect(screen, (100, 100, 255), self.rect.inflate((4,4)), 0, 0)
        pygame.draw.rect(screen, (100, 100, 100), self.rect, 0, 0)

        if ui.hot_id == self.widget_id:
            if ui.active_id == self.widget_id:
                pygame.draw.rect(screen, (250, 250, 250), self.rect, 1, 0)
            else:
                pygame.draw.rect(screen, (250, 250, 100), self.rect, 1, 0)
        else:
            pygame.draw.rect(screen, (250, 100, 100), self.rect, 1, 0)

        text_surface = ui.font24.render(self.text, True, (200,200,200))
        text_rect = text_surface.get_rect(center=self.rect.center)
        screen.blit(text_surface, text_rect)

@dataclass(eq=False)
class TabButtonWidget:
    group : str
    text : str
    rect : pygame.Rect
    widget_id : Any
    allow_focus : bool

    def behavior(self, ui):
        ui.grab_active(self)
        if self.allow_focus:
            ui.grab_focus(self)
        clicked = ui.was_clicked(self)
        if ui.focused_id == self.widget_id and ui.keyboard_key == pygame.K_SPACE:
            clicked = True
        return clicked

    def draw(self, ui, screen):
        selected = (self.group == self.text)
        if ui.focused_id == self.widget_id:
            pygame.draw.rect(screen, (100, 100, 255), self.rect.inflate((4,4)), 0, 0)
        if selected:
            pygame.draw.rect(screen, (80, 80, 80), self.rect, 0, 0)
        else:
            pygame.draw.rect(screen, (100, 100, 100), self.rect, 0, 0)

        if ui.hot_id == self.widget_id:
            if ui.active_id == self.widget_id:
                pygame.draw.rect(screen, (250, 250, 250), self.rect, 1, 0)
            else:
                pygame.draw.rect(screen, (250, 250, 100), self.rect, 1, 0)
        else:
            pygame.draw.rect(screen, (250, 100, 100), self.rect, 1, 0)

        text_surface = ui.font24.render(self.text, True, (200,200,200))
        text_rect = text_surface.get_rect(center=self.rect.center)
        screen.blit(text_surface, text_rect)

@dataclass(eq=False)
class Cover:
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        ui.grab_active(self)

    def draw(self, ui, screen):
        pygame.draw.rect(screen, (100, 100, 100), self.rect, 0, 0)
        pygame.draw.rect(screen, (200, 200, 200), self.rect, 1, 0)

@dataclass
class Surface:
    surface : pygame.Surface
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        return None

    def draw(self, ui, screen):
        screen.blit(self.surface, self.rect)

@dataclass(eq=False)
class Text:
    text : str
    cursor : int
    selection : int

@dataclass(eq=False)
class TextboxWidget:
    state : Text
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        ui.grab_active(self)
        ui.grab_focus(self)
        
        text_changed = False
        text = self.state.text
        cursor = self.state.cursor
        selection = self.state.selection
        
        if ui.mouse_just_pressed and ui.hot_id == self.widget_id:
            cursor = self._pos_from_mouse(ui, text)
            selection = None
        
        if ui.active_id == self.widget_id and ui.mouse_pressed and self.rect.collidepoint(ui.mouse_pos):
            drag_pos = self._pos_from_mouse(ui, text)
            if drag_pos != cursor:
                if selection is None:
                    selection = cursor
                cursor = drag_pos
        
        if ui.focused_id == self.widget_id:
            shift = ui.keyboard_mod & pygame.KMOD_SHIFT
            
            if ui.keyboard_key == pygame.K_LEFT:
                if cursor > 0:
                    if shift:
                        if selection is None:
                            selection = cursor
                        cursor -= 1
                    else:
                        if selection is not None:
                            cursor = min(cursor, selection)
                            selection = None
                        else:
                            cursor -= 1
                else:
                    selection = None
                    
            elif ui.keyboard_key == pygame.K_RIGHT:
                if cursor < len(text):
                    if shift:
                        if selection is None:
                            selection = cursor
                        cursor += 1
                    else:
                        if selection is not None:
                            cursor = max(cursor, selection)
                            selection = None
                        else:
                            cursor += 1
                else:
                    selection = None
                    
            elif ui.keyboard_key == pygame.K_HOME:
                if shift:
                    if selection is None:
                        selection = cursor
                    cursor = 0
                else:
                    cursor = 0
                    selection = None
                    
            elif ui.keyboard_key == pygame.K_END:
                if shift:
                    if selection is None:
                        selection = cursor
                    cursor = len(text)
                else:
                    cursor = len(text)
                    selection = None
                    
            elif ui.keyboard_key == pygame.K_BACKSPACE:
                if selection is not None:
                    start = min(cursor, selection)
                    end = max(cursor, selection)
                    text = text[:start] + text[end:]
                    cursor = start
                    selection = None
                elif cursor > 0:
                    text = text[:cursor-1] + text[cursor:]
                    cursor -= 1
                text_changed = True
                    
            elif ui.keyboard_key == pygame.K_DELETE:
                if selection is not None:
                    start = min(cursor, selection)
                    end = max(cursor, selection)
                    text = text[:start] + text[end:]
                    cursor = start
                    selection = None
                elif cursor < len(text):
                    text = text[:cursor] + text[cursor+1:]
                text_changed = True
            
            if ui.keyboard_text:
                if selection is not None:
                    start = min(cursor, selection)
                    end = max(cursor, selection)
                    text = text[:start] + ui.keyboard_text + text[end:]
                    cursor = start + len(ui.keyboard_text)
                    selection = None
                else:
                    text = text[:cursor] + ui.keyboard_text + text[cursor:]
                    cursor += len(ui.keyboard_text)
                text_changed = True
        
        self.state.text = text
        self.state.cursor = cursor
        self.state.selection = selection
        return text_changed
    
    def _pos_from_mouse(self, ui, text):
        """Calculate cursor position from mouse x coordinate"""
        mouse_x = ui.mouse_pos[0] - self.rect.x - 5
        for i in range(len(text) + 1):
            width = ui.font24.size(text[:i])[0]
            if mouse_x < width:
                return i
        return len(text)
    
    def draw(self, ui, screen):
        text = self.state.text
        cursor = self.state.cursor
        selection = self.state.selection
        
        is_focused = ui.focused_id == self.widget_id
        bg_color = (60, 60, 60) if is_focused else (40, 40, 40)
        pygame.draw.rect(screen, bg_color, self.rect)
        pygame.draw.rect(screen, (150, 150, 150) if is_focused else (100, 100, 100), self.rect, 2)
        
        if selection is not None and is_focused:
            start = min(cursor, selection)
            end = max(cursor, selection)
            
            start_x = self.rect.x + 5 + ui.font24.size(text[:start])[0]
            end_x = self.rect.x + 5 + ui.font24.size(text[:end])[0]
            
            sel_rect = pygame.Rect(start_x, self.rect.y + 5, end_x - start_x, self.rect.height - 10)
            pygame.draw.rect(screen, (80, 120, 180), sel_rect)
        
        if text:
            text_surf = ui.font24.render(text, True, (255, 255, 255))
            screen.blit(text_surf, (self.rect.x + 5, self.rect.y + (self.rect.height - text_surf.get_height()) // 2))
        
        if is_focused:
            cursor_x = self.rect.x + 5 + ui.font24.size(text[:cursor])[0]
            pygame.draw.line(screen, (255, 255, 255),
                           (cursor_x, self.rect.y + 5),
                           (cursor_x, self.rect.y + self.rect.height - 5), 2)

@dataclass(eq=False)
class Slider:
    value : float

@dataclass(eq=False)
class VSliderWidget:
    state : Slider
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        ui.grab_active(self)
        changed = False
        if ui.active_id == self.widget_id:
            y = (ui.mouse_pos[1] - self.rect.top - 8) / (self.rect.height - 16)
            y = min(1, max(0, y))
            self.state.value = y
            changed = True
        return changed

    def draw(self, ui, screen):
        ypos = (self.rect.height - 16) * self.state.value
        pygame.draw.rect(screen, (100,100,100), self.rect, 0, 0)
        pygame.draw.rect(screen, (160,100,100), pygame.Rect(self.rect.left, ypos + self.rect.top, self.rect.width, 16).inflate(-8,-8), 0, 0)

@dataclass(eq=False)
class HSliderWidget:
    state : Slider
    rect : pygame.Rect
    widget_id : Any

    def behavior(self, ui):
        ui.grab_active(self)
        changed = False
        if ui.active_id == self.widget_id:
            y = (ui.mouse_pos[0] - self.rect.left - 8) / (self.rect.width - 16)
            y = min(1, max(0, y))
            self.state.value = y
            changed = True
        return changed

    def draw(self, ui, screen):
        xpos = (self.rect.width - 16) * self.state.value
        pygame.draw.rect(screen, (100,100,100), self.rect, 0, 0)
        pygame.draw.rect(screen, (160,100,100), pygame.Rect(xpos + self.rect.left, self.rect.top, 16, self.rect.height).inflate(-8,-8), 0, 0)
