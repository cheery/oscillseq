import pygame
import numpy as np
from supriya import synthdef
from supriya.ugens import In, FFT

buf_size = 1024

@synthdef()
def spectroscope(buffer_id, bus_id):
    source = In.ar(bus=bus_id)
    FFT.kr(
        buffer_id=buffer_id,
        source=source,
        hop=0.5,
        window_type=0)

def prepare(server):
    server.add_synthdefs(spectroscope)
    server.sync()
    group = server.add_group()
    return lambda bus: Spectroscope(server, group, bus)

class Spectroscope:
    def __init__(self, server, group, bus):
        self.sr = server.query_status().target_sample_rate
        self.buffer = server.add_buffer(channel_count=1, frame_count=buf_size)
        server.sync()
        self.synth = group.add_synth(spectroscope, buffer_id=self.buffer, bus_id=bus)
        self.data = [0]*1024

    def close(self):
        self.buffer.free()
        self.synth.free()

    def refresh(self):
        self.data = self.buffer.get_range(0, 1024)

    def draw(self, screen, font, color, x_center, y_top):
        data = fft_buffer_data(self.data, 0)
        ls = lambda x: x ** (1/3)
        i = x_center - (512//2)
        k = 512 / ls(buf_size/2)

        for mag in [0, 100, 440, 1000, 5000, 10000, 20000]:
            x = mag / (self.sr / buf_size)
            text = font.render(str(mag), True, (200, 200, 200))
            x = i + ls(x)*k
            screen.blit(text, (x, y_top - 15))
            pygame.draw.line(screen, (200, 200, 200), (x, y_top), (x, y_top+200))
        pygame.draw.line(screen, (200, 200, 200), (i+512, y_top), (i+512, y_top+200))

        for y in range(5):
            y *= 50
            mag = y
            if y != 0:
                text = font.render(str(-mag), True, (200, 200, 200))
                screen.blit(text, (i, y_top + y - 15))
            pygame.draw.line(screen, (200, 200, 200), (i, y_top + y), (i+512, y_top + y))

        points = [(i + ls(x)*k,  y_top - y) for x,y in data]
        pygame.draw.lines(screen, color, False, points)

def fft_buffer_data(data, i):
    data = np.array(data[::2]) + 1j * np.array(data[1::2])
    data = abs(data) * (2 / (buf_size/2))
    data = 20 * np.log10(np.maximum(data, 0.0000000001))
    data = list(enumerate(data, i))
    return data


