import numpy as np
import pygame

class ContextMenu:
    def __init__(self, tool, mouse_pos, commands, *args):
        self.view = tool.view
        self.tool = tool
        self.mouse_pos = mouse_pos
        self.commands = commands
        self.args = args
        self.rect = pygame.Rect(mouse_pos - np.array([75, 0]), (150, 10 + 15 * len(commands)))
        if self.rect.x < 0:
            self.rect.x = 0
        if self.rect.y < 0:
            self.rect.y = 0
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
            subrect = pygame.Rect(rect.x, rect.y + i*15, rect.width, 15)
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

