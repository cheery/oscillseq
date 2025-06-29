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

# TODO: Turn into a text editor component
#    def handle_textinput(self, text):
#        if self.mode == 3:
#            value = self.get_tag_line()
#            i = min(self.tag_i, len(value))
#            value = value[:i] + text + value[i:]
#            if text.isalpha() or text.isdigit() or text == '_':
#                self.update_tag_line(i + len(text), value)
#
#    def get_tag_line(self):
#        lines = [self.te_tag_name or ""] + [x for x, _ in self.te_desc.spec]
#        return lines[self.tag_k]
#
#    def update_tag_line(self, offset, value):
#        desc = self.te_desc
#        if self.tag_k == 0:
#            self.te_tag_name = value
#            self.tag_i = offset
#        else:
#            was, t = desc.spec[self.tag_k - 1]
#            if value not in [name for name, _ in desc.spec]:
#                desc.spec[self.tag_k - 1] = value, t
#                self.tag_i = offset
#                past = self.te_future.pop(was, was)
#                if past is not None:
#                    self.te_past[past] = value
#                self.te_future[value] = past
#    def draw_tag_editor(self):
#        y = 15 + 15
#        #lanes = self.calculate_lanes(y)
#
#        self.draw_descriptor_table()
#
#        x = self.SCREEN_WIDTH/4
#        y = self.SCREEN_HEIGHT/4
#        rect = pygame.Rect(x, y, self.SCREEN_WIDTH/2, self.SCREEN_HEIGHT/2)
#        pygame.draw.rect(self.screen, (30, 30, 30), rect, False)
#        pygame.draw.rect(self.screen, (0, 255, 0), rect, True)
#
#        desc = self.te_desc
#
#        text = self.te_tag_name
#        if self.tag_k == 0:
#            text = text[:self.tag_i] + "|" + text[self.tag_i:]
#        text = self.font.render(text, True, (200, 200, 200))
#        self.screen.blit(text, (x + 10, y + 2))
#
#        cc = [(200, 200, 200), (100, 255, 100)]
#        p = x + 150
#        for model in ["control", "oneshot", "gate"]:
#            text = self.font.render(model, True, cc[desc.kind==model])
#            self.screen.blit(text, (p, y + 2))
#            p += 10 + text.get_width()
#
#        y += 30
#        for k, (attr, flavor) in enumerate(desc.spec, 1):
#            if self.tag_k == k:
#                attr = attr[:self.tag_i] + "|" + attr[self.tag_i:]
#            text = self.font.render(attr, True, (200, 200, 200))
#            self.screen.blit(text, (x + 10, y + 2))
#            p = x + 150
#            for model in ["bool", "unipolar", "number", "pitch", "db", "dur"]:
#                text = self.font.render(model, True, cc[flavor==model])
#                self.screen.blit(text, (p, y + 2))
#                p += 10 + text.get_width()
#            y += 15
#
#        y += 30
#        for name in sorted(self.te_past):
#            toward = self.te_past[name]
#            if toward is None:
#                text = f"{name} being removed"
#                text = self.font.render(text, True, (200, 200, 200))
#                self.screen.blit(text, (x + 10, y + 2))
#                y += 15
#            elif name != toward:
#                text = f"{name} being renamed to {toward}"
#                text = self.font.render(text, True, (200, 200, 200))
#                self.screen.blit(text, (x + 10, y + 2))
#                y += 15
#
#        old_desc = self.doc.descriptors.get(self.tag_name, Desc(None, []))
#        types = dict(desc.spec)
#        old_types = dict(old_desc.spec)
#
#        for name in sorted(self.te_future):
#            was = self.te_future[name]
#            if was is None:
#                text = f"{name} introduced"
#                text = self.font.render(text, True, (200, 200, 200))
#                self.screen.blit(text, (x + 10, y + 2))
#                y += 15
#            elif old_types[was] != types[name]:
#                text = f"{name} changes type"
#                text = self.font.render(text, True, (200, 200, 200))
#                self.screen.blit(text, (x + 10, y + 2))
#                y += 15
#
#        if old_desc.kind is not None and desc.kind != old_desc.kind:
#            text = f"{old_desc.kind} transforms to {desc.kind}"
#            text = self.font.render(text, True, (200, 200, 200))
#            self.screen.blit(text, (x + 10, y + 2))
#            y += 15
#
#        y += 15
#        if self.te_tag_name != self.tag_name and self.te_tag_name != "" and self.tag_name != None and self.te_tag_name not in self.doc.descriptors:
#            text = "[+] to copy"
#            text = self.font.render(text, True, (200, 200, 200))
#            self.screen.blit(text, (x + 10, y + 2))
#            y += 15
#
#        modified = False
#        modified |= (self.tag_name != self.te_tag_name)
#        modified |= (desc.kind != old_desc.kind)
#        modified |= (desc.spec != old_desc.spec)
#        if self.tag_name != None and self.te_tag_name != "" and modified:
#            text = "shift+[ret] to move/commit"
#            text = self.font.render(text, True, (200, 200, 200))
#            self.screen.blit(text, (x + 10, y + 2))
#            y += 15
#
#        if self.tag_name != None:
#            text = "[del] to remove"
#            text = self.font.render(text, True, (200, 200, 200))
#            self.screen.blit(text, (x + 10, y + 2))
#            y += 15
#
#    def handle_tag_editor_key(self, ev):
#        mods = pygame.key.get_mods()
#        shift_held = mods & pygame.KMOD_SHIFT
#        if ev.key == pygame.K_RETURN and shift_held:
#            if self.te_tag_name != "":
#                if self.tag_name is not None:
#                    old_desc = self.doc.descriptors.pop(self.tag_name)
#                else:
#                    old_desc = None
#                self.doc.descriptors[self.te_tag_name] = Desc(self.te_desc.kind, self.te_desc.spec.copy())
#                for df in self.doc.drawfuncs:
#                    if df.tag == self.tag_name:
#                        df.tag = self.te_tag_name
#                if old_desc is not None:
#                    if self.te_desc.kind == "control" and self.old_desc != "control":
#                        for brush in list(self.doc.labels.values()):
#                            if isinstance(brush, ControlPoint) and brush.tag == self.tag_name:
#                                self.erase_brush(brush)
#                            if isinstance(brush, Clap):
#                                brush.generators.pop(self.tag_name, None)
#                    else:
#                        od = dict(old_desc.spec)
#                        nd = dict(self.te_desc.spec)
#                        remapper = {}
#                        for name, was in self.te_future.items():
#                            if was is not None and od[was] == nd[name]:
#                                remapper[was] = name
#                        remap = lambda args: {remapper[name]: value for name, value in args.items() if name in remapper}
#                        for brush in list(self.doc.labels.values()):
#                            if isinstance(brush, Clap):
#                                gen = brush.generators.pop(self.tag_name, None)
#                                if isinstance(gen, ConstGen):
#                                    gen.argslist = [remap(args) for args in gen.argslist]
#                                    brush.generators[self.te_tag_name] = gen
#                                if isinstance(gen, PolyGen):
#                                    gen.argslists = [[remap(args) for args in argslist] for argslist in gen.argslists]
#                                    brush.generators[self.te_tag_name] = gen
#                self.tag_name = self.te_tag_name
#                self.te_past = {}
#                self.te_future = {name: name for name, _ in self.te_desc.spec}
#        elif ev.key == pygame.K_PLUS:
#            if self.te_tag_name not in self.doc.descriptors and all(name != "" for name, _ in self.te_desc.spec):
#                self.doc.descriptors[self.te_tag_name] = Desc(self.te_desc.kind, self.te_desc.spec.copy())
#                self.tag_name = self.te_tag_name
#                self.te_past = {}
#                self.te_future = {name: name for name, _ in self.te_desc.spec}
#        elif ev.key == pygame.K_DELETE:
#            if self.tag_name is not None:
#                self.doc.descriptors.pop(self.tag_name)
#                for df in list(self.doc.drawfuncs):
#                    if df.tag == self.tag_name:
#                        self.doc.drawfuncs.remove(df)
#                for brush in list(self.doc.labels.values()):
#                    if isinstance(brush, ControlPoint) and brush.tag == self.tag_name:
#                        self.erase_brush(brush)
#                    if isinstance(brush, Clap):
#                        brush.generators.pop(self.tag_name, None)
#                self.tag_name = None
#                self.te_past = {}
#                self.te_future = {name: None for name, _ in self.te_desc.spec}
#        elif ev.key == pygame.K_BACKSPACE and self.tag_k >= 0:
#            value = self.get_tag_line()
#            i = max(0, self.tag_i - 1)
#            value = value[:i] + value[self.tag_i:]
#            self.update_tag_line(i, value)
#        elif ev.key == pygame.K_TAB:
#            desc = self.te_desc
#            if self.tag_k == 0:
#                ix = ["control", "oneshot", "gate"].index(desc.kind)
#                desc.kind = ["oneshot", "gate", "control"][ix]
#            else:
#                attr, flavor = desc.spec[self.tag_k - 1]
#                ix = ["bool", "unipolar", "number", "pitch", "db", "dur"].index(flavor)
#                flavor = ["unipolar", "number", "pitch", "db", "dur", "bool"][ix]
#                desc.spec[self.tag_k - 1] = attr, flavor
#        #elif ev.key == pygame.K_PAGEUP and mods & pygame.KMOD_SHIFT:
#        #    if self.tag_name in self.doc.descriptors:
#        #        xs = iter(reversed(self.doc.rows))
#        #        for xrow in xs:
#        #            if self.tag_name in xrow.tags:
#        #                break
#        #        ix = xrow.tags.index(self.tag_name)
#        #        if ix == 0:
#        #            for row in xs:
#        #                if (row.staves == 0 and len(row.tags) == 0) or row.staves > 0:
#        #                    row.tags.append(self.tag_name)
#        #                    xrow.tags.remove(self.tag_name)
#        #                    break
#        #        else:
#        #            xrow.tags[ix], xrow.tags[ix-1] = xrow.tags[ix-1], xrow.tags[ix]
#        #elif ev.key == pygame.K_PAGEDOWN and mods & pygame.KMOD_SHIFT:
#        #    if self.tag_name in self.doc.descriptors:
#        #        xs = iter(self.doc.rows)
#        #        for xrow in xs:
#        #            if self.tag_name in xrow.tags:
#        #                break
#        #        ix = xrow.tags.index(self.tag_name)
#        #        if ix + 1 >= len(xrow.tags):
#        #            for row in xs:
#        #                if (row.staves == 0 and len(row.tags) == 0) or row.staves > 0:
#        #                    row.tags.insert(0, self.tag_name)
#        #                    xrow.tags.remove(self.tag_name)
#        #                    break
#        #        else:
#        #            xrow.tags[ix], xrow.tags[ix+1] = xrow.tags[ix+1], xrow.tags[ix]
#        elif ev.key == pygame.K_PAGEUP:
#            self.walk_tag_name(direction=False, from_descriptors=shift_held)
#        elif ev.key == pygame.K_PAGEDOWN:
#            self.walk_tag_name(direction=True, from_descriptors=shift_held)
#        elif ev.key == pygame.K_RETURN:
#            spec = self.te_desc.spec
#            if self.tag_k == 0 or spec[self.tag_k-1][0] != "":
#                spec.insert(self.tag_k, ("", "number"))
#                self.te_future[""] = None
#                self.tag_k += 1
#                self.tag_i = 0
#        elif ev.key == pygame.K_UP and shift_held:
#            spec = self.te_desc.spec
#            if self.tag_k > 1:
#                spec[self.tag_k-2], spec[self.tag_k-1] = spec[self.tag_k-1], spec[self.tag_k-2] 
#                self.tag_k -= 1
#        elif ev.key == pygame.K_DOWN and shift_held:
#            spec = self.te_desc.spec
#            if 0 < self.tag_k < len(spec):
#                spec[self.tag_k], spec[self.tag_k-1] = spec[self.tag_k-1], spec[self.tag_k] 
#                self.tag_k += 1
#        elif ev.key == pygame.K_UP:
#            if self.tag_k > 0 and self.get_tag_line() == "":
#                self.te_desc.spec.pop(self.tag_k - 1)
#                past = self.te_future.pop("")
#                if past is not None:
#                    self.te_past[past] = None
#            if self.tag_k > 0:
#                self.tag_k = self.tag_k - 1
#        elif ev.key == pygame.K_DOWN:
#            spec = self.te_desc.spec
#            if self.tag_k > 0 and self.get_tag_line() == "":
#                if self.tag_k < len(spec):
#                    spec.pop(self.tag_k - 1)
#                    past = self.te_future.pop("")
#                    if past is not None:
#                        self.te_past[past] = None
#            elif self.tag_k < len(spec):
#                self.tag_k = self.tag_k + 1
#        elif ev.key == pygame.K_LEFT:
#            self.tag_i = max(0, self.tag_i - 1)
#        elif ev.key == pygame.K_RIGHT:
#            self.tag_i = min(len(self.get_tag_line()), self.tag_i + 1)
#
