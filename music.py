import bisect
import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any
from model2.wadler_lindig import pformat_doc, text, sp, nl, pretty

class Pitch:
    def __init__(self, position, accidental=0):
        self.position = position
        self.accidental = accidental
        assert position is not None
        assert accidental is not None

    def __pretty__(self):
        cls = "cdefgab"[self.position%7]
        octave = self.position//7
        if self.accidental < 0:
            t = "b" * -self.accidental
        else:
            t = "s" * self.accidental
        return text(f"{cls}{t}{octave}")

    def __repr__(self):
        return pformat_doc(pretty(self), 80)

    def to_pair(self):
        return self.position, self.accidental

    def __eq__(self, other):
        return self.to_pair() == other.to_pair()

    def __hash__(self):
        return hash(self.to_pair())

    def __float__(self):
        return float(resolve_pitch(self))

    def __int__(self):
        return resolve_pitch(self)

    def __str__(self):
        cls = "CDEFGAB"[self.position%7]
        octave = self.position//7
        if self.accidental == 0:
            return cls + str(octave)
        elif self.accidental in [-1, +1]:
            return cls + str(octave) + char_accidental[self.accidental]
        elif self.accidental in [-2, +2]:
            return cls + str(octave) + char_accidental[self.accidental // 2]*2

    @classmethod
    def from_midi(cls, midi):
        octave = (midi // 12) - 1
        pclass = midi % 12
        position = [0,0,1,1,2,3,3,4,4,5,5,6][pclass] + octave*7
        accidental = [0,1,0,1,0,0,1,0,1,0,1,0][pclass]
        return cls(position, accidental)

base_key = [0,2,4,5,7,9,11]
def resolve_pitch(note):
    octave = note.position // 7
    pc = base_key[note.position % 7]
    return (octave+1)*12 + pc + note.accidental

char_accidental = {
   -2: chr(119083),
   -1: chr(0x266d),
    0: chr(0x266e),
   +1: chr(0x266f),
   +2: chr(119082),
}

def envelope(events):
    xs = [e[0] for e in events]
    ys = [e[2] for e in events]
    ks = []

    for i in range(len(events)-1):
        k_i = 0.0
        if events[i+1][1]:
            x_i,    _, y_i    = events[i]
            x_next, _, y_next = events[i + 1]
            dt = x_next - x_i
            if dt != 0:
                k_i = (y_next - y_i) / dt
        ks.append(k_i)
    ks.append(0.0)
    if xs[0] > 0.0:
        xs.insert(0, 0.0)
        ys.insert(0, ys[0])
        ks.insert(0, 0.0)
    return Envelope(xs, ys, ks)

def tempo_envelope(events):
    xs = []
    ys = [e[2] for e in events]
    ks = []
    bs = [e[0] for e in events]
    assert all(y > 0 for y in ys), "tempo envelope must be positive"
    t_i = 120*bs[0]/(ys[0]+ys[0])
    xs.append(t_i)
    for i in range(len(events)-1):
        k_i = 0.0
        b_i, _, y_i = events[i]
        b_n, _, y_n = events[i + 1]
        db = b_n - b_i
        if events[i+1][1]:
            dt = 120*db/(y_i+y_n)
            if dt > 0:
                k_i = (y_n-y_i) / dt
        else:
            dt = 120*db/(y_i+y_i)
        t_i += dt
        xs.append(t_i)
        ks.append(k_i)
    ks.append(0.0)
    if xs[0] > 0.0:
        xs.insert(0, 0.0)
        ys.insert(0, ys[0])
        ks.insert(0, 0.0)
        bs.insert(0, 0.0)
    return TempoEnvelope(xs, ys, ks, bs)

@dataclass
class Envelope:
    xs : List[float]
    ys : List[float]
    ks : List[float]

    def evaluate(self, p):
        #if p <= self.xs[0]:
        #    return self.ys[0]
        i = bisect.bisect_right(self.xs, p) - 1
        x_i = self.xs[i]
        y_i = self.ys[i]
        k_i = self.ks[i]
        return (p - x_i) * k_i + y_i

    def equation(self, p):
        i = bisect.bisect_right(self.xs, p) - 1
        x_i = self.xs[i]
        y_i = self.ys[i]
        k_i = self.ks[i]
        return k_i, (p - x_i) * k_i + y_i

    def is_positive(self, allow_zero=False):
        minima = self.xs[0]
        for i in range(len(self.xs) - 1):
            x_i = self.xs[i]
            y_i = self.ys[i]
            k_i = self.ks[i]
            x_next = self.xs[i+1]
            minima = min(minima, y_i)
            minima = min(minima, (x_next-x_i)*k_i + y_i)
        minima = min(minima, self.ys[-1])
        if self.ks[-1] >= 0:
            if allow_zero:
                return minima >= 0
            else:
                return minima > 0
        else:
            return False

@dataclass
class TempoEnvelope(Envelope):
    bs : List[float]

    def time_to_bar(self, t):
        i = bisect.bisect_right(self.xs, t) - 1
        x_i = self.xs[i]
        y_i = self.ys[i]
        k_i = self.ks[i]
        b_i = self.bs[i]
        dt = t - x_i
        return b_i + y_i/60*dt + k_i/120*dt*dt

    def bar_to_time(self, b):
        i = bisect.bisect_right(self.bs, b) - 1
        x_i = self.xs[i]
        y_i = self.ys[i]
        k_i = self.ks[i]
        b_i = self.bs[i]
        s = (y_i / 60)
        d = (k_i / 120)
        db = b - b_i
        if k_i == 0:
            return x_i + db / s
        else:
            return x_i + (-s + math.sqrt(s*s + 4*d*db)) / (2*d)

# These were in use when tempo was still counted as linear function of beat instead of time.
def tempo_segments(env):
    time = env.xs[0] * 60 / env.ys[0]
    for i in range(len(env.xs) - 1):
        yield time
        x_i = env.xs[i]
        y_i = env.ys[i]
        k_i = env.ks[i]
        x_next = env.xs[i+1]
        dx = x_next - x_i
        if dx != 0:
            if k_i == 0:
                time += dx * 60 / y_i
            else:
                time += 60 / k_i * math.log((k_i * dx + y_i) / y_i)
    yield time

def bar_to_time(env, ts, p):
    if p <= env.xs[0]:
        return p * 60 / env.ys[0]
    i = bisect.bisect_right(env.xs, p) - 1
    x_i = env.xs[i]
    y_i = env.ys[i]
    k_i = env.ks[i]
    t_i = ts[i]
    dx = p - x_i
    if k_i == 0:
        return t_i + dx * 60 / y_i
    else:
        return t_i + 60 / k * math.log((k_i * dx + y_i) / y_i)

def time_to_bar(env, ts, p):
    if p <= ts[0]:
        return p * env.ys[0] / 60
    i = bisect.bisect_right(ts, p) - 1
    x_i = env.xs[i]
    y_i = env.ys[i]
    k_i = env.ks[i]
    t_i = ts[i]
    dt = p - t_i
    if k_i == 0:
        return x_i + dt * y_i / 60
    else:
        return x_i + y_i * (math.exp(k_i*dt / 60) - 1) / k_i

# order of sharps in a canonical key
         #F C G D A E B
sharps = [3,0,4,1,5,2,6]

def accidentals(index):
    accidentals = [0]*7
    for i in range(0, index):
        accidentals[sharps[i]] += 1
    for i in range(index, 0):
        accidentals[sharps[i]] -= 1
    return accidentals

major = {
    -7: "Cb",
    -6: "Gb",
    -5: "Db",
    -4: "Ab",
    -3: "Eb",
    -2: "Bb",
    -1: "F",
    0: "C",
    1: "G",
    2: "D",
    3: "A",
    4: "E",
    5: "B",
    6: "F#",
    7: "C#",
}
