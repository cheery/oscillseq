import time
import threading
import queue
from pythonosc.udp_client import SimpleUDPClient
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any
import music

class Client:
    def __init__(self):
        self._client = SimpleUDPClient("127.0.0.1", 57120)

    def record(self, filename, form, duration):
        self._client.send_message("/transport/record", [
            filename,
            form,
            duration
        ])

    def play(self):
        self._client.send_message("/transport/play", [])

    def stop(self):
        self._client.send_message("/transport/stop", [])

@dataclass
class Bus:
    busID : str
    a : float
    b : float
    c : float
    t : float

    def send(self, c):
        args = [self.busID, self.a, self.b, self.c, self.t]
        c._client.send_message("/bus/set", args)

    def simulate(self, event_time, onset, buses):
        buses[self.busID] = event_time, self

    def forward(self, dt):
        b = self.a*2*dt + self.b
        c = self.a*dt*dt + self.b*dt + self.c
        return Bus(self.busID, self.a, b, c, self.t - dt)

@dataclass
class Oneshot:
    instID : str
    kwargs : Dict[str, Any]

    def send(self, c):
        args = [self.instID]
        for k, v in self.kwargs.items():
            args.extend((k, float(v) if isinstance(v, (int,float,music.Pitch)) else v))
        c._client.send_message("/instrument/oneshot", args)

    def simulate(self, event_time, onset, buses):
        pass

@dataclass
class Trigger:
    instID : str
    group_id : int
    kwargs : Dict[str, Any]

    def send(self, c):
        args = [self.instID, self.group_id]
        for k, v in self.kwargs.items():
            args.extend((k, float(v) if isinstance(v, (int,float,music.Pitch)) else v))
        c._client.send_message("/instrument/trigger", args)

    def simulate(self, event_time, onset, buses):
        onset[self.group_id] = self

@dataclass
class Control:
    instID : str
    group_id : int
    kwargs : Dict[str, Any]

    def send(self, c):
        args = [self.instID, self.group_id]
        for k, v in self.kwargs.items():
            args.extend((k, float(v) if isinstance(v, (int,float,music.Pitch)) else v))
        c._client.send_message("/instrument/control", args)

    def simulate(self, event_time, onset, buses):
        msg = onset[self.group_id]
        kwargs = msg.kwargs.copy()
        kwargs.update(self.kwargs)
        onset[self.group_id] = Trigger(msg.instID, self.group_id, kwargs)

@dataclass
class Release:
    instID : str
    group_id : int
    kwargs : Dict[str, Any]

    def send(self, c):
        args = [self.instID, self.group_id]
        for k, v in self.kwargs.items():
            args.extend((k, float(v) if isinstance(v, (int,float,music.Pitch)) else v))
        c._client.send_message("/instrument/release", args)

    def simulate(self, event_time, onset, buses):
        onset.pop(self.group_id)

class Sequencer:
    def __init__(self):
        self.busevents = {}
        self.oneshots = []
        self.gates = []
        self.group_ids = {}

    def control(self, bar, tag, transition, value):
        self.busevents.setdefault(tag, []).append((bar, transition, value))

    def oneshot(self, bar, tag, args):
        self.oneshots.append((bar, tag, args))

    def gate(self, bar, tag, group_key, args):
        if group_key not in self.group_ids:
            self.group_ids[group_key] = len(self.group_ids)
        self.gates.append((bar, tag, self.group_ids[group_key], args))

    def prepare(self):
        for tag, events in self.busevents.items():
            events.sort(key=lambda x: x[0])
        self.gates.sort(key=lambda x: x[0])

    def build(self):
        self.prepare()
        # Note that we don't know what to do if there's only one gate event.
        triggers = {}
        releases = {}
        for i, (time, tag, group_id, args) in enumerate(self.gates):
            if group_id not in triggers:
                triggers[group_id] = i
            releases[group_id] = i

        def conv(events):
            return [(bar, transition, float(value)) for bar, transition, value in events]

        tempo = music.tempo_envelope(
            conv(self.busevents.get("tempo", [(0.0, False, 15.0)])))
        busenv = {
            tag: music.envelope(conv(events))
            for tag, events in self.busevents.items()}

        output = []

        output.extend(tempo_events(tempo))
        for name, env in busenv.items():
            if name != "tempo":
                output.extend(bus_events(tempo, env, name))

        for bar, tag, args in self.oneshots:
            time = tempo.bar_to_time(bar)
            output.append((time, Oneshot(tag, args)))

        for i, (bar, tag, group_id, args) in enumerate(self.gates):
            time = tempo.bar_to_time(bar)
            ctl = Control
            if i == triggers[group_id]:
                ctl = Trigger
            elif i == releases[group_id]:
                ctl = Release
            output.append((time, ctl(tag, group_id, args)))

        output.sort(key=lambda x: x[0])
        return tempo, output

def tempo_events(tempo):
    for i, t in enumerate(tempo.xs):
        dt = tempo.xs[i+1] - t if i+1 < len(tempo.xs) else 0
        b = tempo.ks[i]
        c = tempo.ys[i]
        yield t, Bus("tempo", 0, b, c, dt)

def bus_events(tempo, env, busID):
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
        yield t, Bus(busID, a, b, c, dt)

# TODO: Add begin, end time parameters.
# TODO: Add loop parameter.
# TODO: Allow hotswapping the tempo & events list.

class TransportThread(threading.Thread):
    def __init__(self, tempo, events):
        super().__init__()
        self.client = Client()
        self.tempo = tempo
        self.events = events
        self.cmd = queue.Queue()
        #self.lock = threading.Lock()
        self.playing = False
        self.start_time = None
        self.daemon = True
        self.record_path = None
        self.record_format = "wav"
        self.shift = 0.0
        self.duration = 0.0

    def shutdown(self):
        if self.playing:
            self.cmd.put("stop")
        self.cmd.put("shutdown")
        self.join()

    def run(self):
        while self.cmd.get() == 'play':
            self.playing = True
            self.start_time = time.monotonic() - self.shift
            if self.record_path and self.duration > 0.0:
                self.client.record(self.record_path, self.record_format, self.duration)
            else:
                self.client.play()

            t = 0.0
            #nextframe = 0.1
            #busdata = []
            #for i in range(100):
                #b = music.time_to_bar(env1, ts, t + i * 0.001)
            #    b = env1.time_to_bar(t + i * 0.001)
            #    busdata.append(env2.evaluate(b))
            #Bus("sawnote", busdata).send(self.client)
            onset = {}
            buses = {}
            ix = 0
            while ix < len(self.events) and self.events[ix][0] < self.shift:
                msg = self.events[ix][1]
                msg.simulate(self.events[ix][0], onset, buses)
                ix += 1

            for msg in onset.values():
                msg.send(self.client)
            for event_time, msg in buses.values():
                msg = msg.forward(self.shift - event_time)
                msg.send(self.client)

            for event_time, msg in self.events[ix:]:
                t = time.monotonic() - self.start_time
                if t < event_time:
                    try:
                        self.cmd.get(timeout=max(0, event_time - t))
                        self.client.stop()
                        self.playing = False
                        break
                    except queue.Empty:
                        pass
                msg.send(self.client)
                #while t < event_time:
                #    try:
                #        self.cmd.get(timeout=max(0, min(event_time - t, nextframe - t)))
                #        self.client.stop()
                #        self.playing = False
                #        break
                #    except queue.Empty:
                #        t = time.monotonic() - self.start_time

                #        if t >= nextframe:
                #            nextframe = t + 0.1
                #            busdata = []
                #            for i in range(100):
                #                #b = music.time_to_bar(env1, ts, t + i * 0.001)
                #                b = env1.time_to_bar(t + i * 0.001)
                #                busdata.append(env2.evaluate(b))
                #            Bus("sawnote", busdata).send(self.client)
                #if self.playing:
                #    msg.send(self.client)
                #else:
                #    break

            if self.playing:
                self.cmd.get()
                self.client.stop()
                self.playing = False

            #t = time.monotonic() - self.start_time
            #while self.playing:
            #    try:
            #        self.cmd.get(timeout=nextframe - t)
            #        self.client.stop()
            #        self.playing = False
            #    except queue.Empty:
            #        t = time.monotonic() - self.start_time
            #        nextframe = t + 0.1
            #        busdata = []
            #        for i in range(100):
            #            #b = music.time_to_bar(env1, ts, t + i * 0.001)
            #            b = env1.time_to_bar(t + i * 0.001)
            #            busdata.append(env2.evaluate(b))
            #        Bus("sawnote", busdata).send(self.client)

    def get_elapsed(self):
        # returns elapsed since start when playing, else 0
        if self.playing and self.start_time is not None:
            return time.monotonic() - self.start_time
