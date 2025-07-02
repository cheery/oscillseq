import pygame
import numpy as np
import supriya
from supriya import synthdef
from supriya.ugens import In, FFT, LocalBuf, BufRd, BufRateScale, BufFrames, LFSaw, BufDur, BufSamples, Phasor
from supriya.ugens import ScopeOut2

buf_size = 2048

@synthdef()
def spectroscope(rate, bus_id, scope_id, scope_id_2):
    local_buf = LocalBuf.ir(frame_count=buf_size)
    source = In.ar(bus=bus_id)
    FFT.kr(
        buffer_id=local_buf,
        source=source,
        hop=0.5,
        window_type=0)
    phase = Phasor.ar(
        rate = BufRateScale.kr(buffer_id=local_buf),
        start = 0, 
        stop = BufFrames.kr(buffer_id=local_buf))
    fft = BufRd.ar(buffer_id=local_buf, channel_count=1, interpolation=1, loop=1, phase=phase)
    ScopeOut2.ar(
        source = fft,
        scope_id = scope_id,
        max_frames = 8192,
        scope_frames = buf_size)
    ScopeOut2.ar(
        source = source,
        scope_id = scope_id_2,
        max_frames = 1024,
        scope_frames = 512)

def prepare(server):
    server.add_synthdefs(spectroscope)
    server.sync()
    group = server.add_group()
    return lambda bus: Spectroscope(server, group, bus)

class Spectroscope:
    def __init__(self, server, group, bus):
        self.server = server
        self.sr = server.query_status().target_sample_rate
        #self.buffer = server.add_buffer(channel_count=1, frame_count=buf_size)
        #server.sync()
        self.scopebuffer = server.add_scope_buffer()
        self.scopebuffer2 = server.add_scope_buffer()
        server.sync()
        #self.synth = group.add_synth(spectroscope, buffer_id=self.buffer, bus_id=bus)
        self.synth = group.add_synth(spectroscope, rate=self.sr, bus_id=bus, scope_id=self.scopebuffer, scope_id_2=self.scopebuffer2)
        self.available_frames = 1024
        self.data = [0]*1024
        self.available_frames2 = 2048
        self.data2 = [0]*2048

    def close(self):
        #self.buffer.free()
        self.scopebuffer.free()
        self.synth.free()

    def refresh(self):
        pass#self.data = self.buffer.get_range(0, 1024)
        #print(self.server.shared_memory.describe_scope_buffer(self.scopebuffer))
        try:
            self.available_frames, self.data = self.server.shared_memory.read_scope_buffer(self.scopebuffer)
            self.data = self.data[:self.available_frames]
        except RuntimeError:
            pass
        try:
            self.available_frames2, self.data2 = self.server.shared_memory.read_scope_buffer(self.scopebuffer2)
            self.data2 = self.data2[:self.available_frames2]
        except RuntimeError:
            pass

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
        if len(points) > 2:
            pygame.draw.lines(screen, color, False, points)

        if self.available_frames2 > 2:
            points = enumerate(100 - np.array(self.data2) * 50 + y_top)
            points = [(i + s*(512 / self.available_frames2), y) for s, y in points]
            pygame.draw.lines(screen, (255,255,255), False, points)

def fft_buffer_data(data, i):
    data = np.array(data[::2]) + 1j * np.array(data[1::2])
    data = abs(data) * (2 / (buf_size/2))
    data = 20 * np.log10(np.maximum(data, 0.0000000001))
    data = list(enumerate(data, i))
    return data


