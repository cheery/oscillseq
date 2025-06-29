import threading
import time
import supriya
import os
import music
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any

@dataclass
class Sequence:
    tempo : music.TempoEnvelope
    com : List[Any]
    end : float

    def t(self, bar):
        return self.tempo.bar_to_time(bar)

class Sequencer:
    def __init__(self, sequence, point, loop_start, loop_point, end_point):
        self.sequence = sequence
        self.point = point
        self.loop_start = loop_start
        self.loop_point = loop_point
        self.end_point = end_point
        self.time = 0
        self.index = 0

    @property
    def status(self):
        dt = time.monotonic() - self.time
        point = self.point + dt
        if point <= self.end_point:
            return self.sequence.tempo.time_to_bar(point)

    def resume(self, clavier, fabric):
        self.time = time.monotonic()
        goal_clavier, quadratics = {}, {}
        index = 0
        for index, event in enumerate(self.sequence.com):
            if event.time <= self.point:
                event.sim(goal_clavier, quadratics)
            else:
                break
        else:
            index += 1
        for q in quadratics.values():
            q.forward(self.point)
        for group_id in list(clavier):
            if group_id not in goal_clavier:
                clavier.pop(group_id).set(gate=0)
        for command in goal_clavier.values():
            command.send(clavier, fabric)
        self.index = index
        return self._estimate_next_event()

    def sweep(self, clavier, fabric):
        now = time.monotonic()
        dt, self.time = now - self.time, now
        allow_loop = (self.point <= self.loop_point)
        self.point += dt
        if self.point <= self.end_point or self.end_point == self.loop_point:
            target = self.point
            if allow_loop:
                target = min(target, self.loop_point)
            self._seek(target, clavier, fabric)
            if allow_loop and self.loop_point <= self.point:
                dt = self.point - self.loop_point
                self.point = self.loop_start
                self.resume(clavier, fabric)
                self.point += dt
                self._seek(self.point, clavier, fabric)
            return self._estimate_next_event()
        else:
            for synth in clavier.values():
                synth.set(gate=0)
            clavier.clear()

    def _seek(self, target, clavier, fabric):
        while self.index < len(self.sequence.com) and self.sequence.com[self.index].time < target:
            self.sequence.com[self.index].send(clavier, fabric)
            self.index += 1

    def _estimate_next_event(self):
        if self.index < len(self.sequence.com):
            if self.point <= self.loop_point <= self.sequence.com[self.index].time:
                return self.loop_point - self.point
            return max(0.0, self.sequence.com[self.index].time - self.point)
        elif self.loop_point <= self.end_point:
            return max(0.0, self.loop_point - self.point)
        else:
            return max(0.0, self.end_point - self.point)

class Player:
    def __init__(self, clavier, fabric, sequencer):
        self.clavier = clavier
        self.fabric = fabric
        self.sequencer = sequencer
        self.halt = threading.Event()
        self.thread = threading.Thread(daemon=True, target=self._run, args=(clavier, fabric, sequencer))
        self.thread.start()

    def close(self):
        self.halt.set()
        self.thread.join()

    def _run(self, clavier, fabric, sequencer):
        running = True
        dt = sequencer.resume(clavier, fabric)
        while dt is not None:
            if self.halt.wait(timeout=dt):
                break
            dt = sequencer.sweep(clavier, fabric)

@dataclass
class Quadratic: 
    time : float
    tag : str
    a : float
    b : float
    c : float
    t : float

    def send(self, clavier, fabric):
        #print('QUAD', self.time, self.tag)
        if self.tag not in fabric.synths:
            return
        fabric.control(self.tag,
            a=self.a, b=self.b, c=self.c, t=self.t, trigger=1)

    def sim(self, clavier, quadratics):
        quadratics[self.tag] = self

    def forward(self, time):
        dt = time - self.time
        if dt < self.t:
            b = self.a*2*dt + self.b
            c = self.a*dt*dt + self.b*dt + self.c
            return Quadratic(time, self.tag, self.a, b, c, self.t - dt)

@dataclass
class Once:
    time : float
    tag : str
    kwargs : Dict[str, Any]

    def send(self, clavier, fabric):
        #print('ONCE', self.time, self.tag)
        if self.tag not in fabric.synths:
            return
        fabric.synth(self.tag, **self.kwargs)

    def sim(self, clavier, quadratics):
        pass

@dataclass
class Gate:
    time : float
    tag : str
    group_id : int
    kwargs : Dict[str, Any]
    release : bool

    def send(self, clavier, fabric):
        #print('GATE', self.time, self.tag)
        if self.tag not in fabric.synths:
            return
        if self.release and self.group_id in clavier:
            clavier.pop(self.group_id).set(gate=0, **self.kwargs)
        elif self.release:
            fabric.synth(self.tag, gate=0, **self.kwargs)
        elif self.group_id in clavier:
            clavier[self.group_id].set(**self.kwargs)
        else:
            synth = fabric.synth(self.tag, **self.kwargs)
            if synth is not None:
                clavier[self.group_id] = synth

    def sim(self, clavier, quadratics):
        if self.release and self.group_id in clavier:
            clavier.pop(self.group_id)
        elif not self.release:
            if self.group_id in clavier:
                kwargs = clavier[self.group_id].kwargs.copy()
                kwargs.update(self.kwargs)
            else:
                kwargs = self.kwargs
            clavier[self.group_id] = Gate(self.time, self.tag, self.group_id, kwargs, False)

class SequenceBuilder:
    def __init__(self, group_ids):
        self.quadratics = defaultdict(list)
        self.onces = {}
        self.gates = []
        self.group_ids = group_ids

    def quadratic(self, bar, tag, transition, value):
        self.quadratics[tag].append((bar, transition, value))
 
    def once(self, bar, tag, args):
        self.onces.append((bar, tag, args))

    def gate(self, bar, tag, group_key, args):
        if group_key not in self.group_ids:
            self.group_ids[group_key] = len(self.group_ids)
        self.gates.append((bar, tag, self.group_ids[group_key], args))

    def prepare(self):
        for tag, events in self.quadratics.items():
            events.sort(key=lambda x: x[0])
        self.gates.sort(key=lambda x: x[0])
 
    def build(self, end):
        self.prepare()
        releases = {}
        for i, (time, tag, group_id, args) in enumerate(self.gates):
            releases[group_id] = i
 
        def conv(events):
            return [(bar, transition, float(value)) for bar, transition, value in events]
 
        tempo = music.tempo_envelope(
            conv(self.quadratics.get("tempo", [(0.0, False, 15.0)])))
        quadratics = {
            tag: music.envelope(conv(events))
            for tag, events in self.quadratics.items()}
 
        output = []
        output.extend(tempo_events(tempo))
        for name, env in quadratics.items():
            if name != "tempo":
                output.extend(quadratic_events(tempo, env, name))
 
        for bar, tag, args in self.onces:
            time = tempo.bar_to_time(bar)
            output.append(Once(time, tag, args))
 
        for i, (bar, tag, group_id, args) in enumerate(self.gates):
            time = tempo.bar_to_time(bar)
            output.append(Gate(time, tag, group_id, args, (i == releases[group_id])))

        output.sort(key=lambda x: x.time)

        return Sequence(tempo, output, tempo.bar_to_time(end))

def tempo_events(tempo):
    for i, t in enumerate(tempo.xs):
        dt = tempo.xs[i+1] - t if i+1 < len(tempo.xs) else 0
        b = tempo.ks[i]
        c = tempo.ys[i]
        yield Quadratic(t, "tempo", 0, b, c, dt)

def quadratic_events(tempo, env, tag):
    bs = list(set(tempo.bs + env.xs))
    bs.sort()
    for i, b in enumerate(bs):
        t = tempo.bar_to_time(b)
        dt = tempo.bar_to_time(bs[i+1]) - t if i+1 < len(bs) else 0
        m, c = tempo.equation(t)
        k, y = env.equation(b)
        #b(t) = c/60*t + m/120*t*t
        #f(x) = x*k + y
        #f(b(t)) = (c/60*t + m/120*t*t)* k + y
        #f(b(t)) = c/60*k*t + m/120*k*t*t + y
        a = m / 120 * k
        b = c / 60 * k
        c = y
        yield Quadratic(t, tag, a, b, c, dt)
