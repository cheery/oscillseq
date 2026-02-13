from descriptors import *
from supriya import Envelope, synthdef
from supriya.ugens import *

save = Saver("synthdefs")

@synthdef()
def saw(out=0, note=69, gate=1, volume=0):
    sig = Saw.ar(frequency=note.midi_to_hz())
    sig *= EnvGen.kr(envelope=Envelope.adsr(), gate=gate, done_action=2)
    sig *= volume.db_to_amplitude()
    Out.ar(bus=out, source=[sig, sig])

save(saw,
    out = bus("ar", "out", 2),
    note = pitch,
    volume = db)

@synthdef()
def flutelike(out=0, note=69, gate=1, volume=0):
    sig = Pulse.ar(frequency=note.midi_to_hz())
    sig *= EnvGen.kr(envelope=Envelope.adsr(0.5, 0, 1.0, 0.5), gate=gate, done_action=2)
    sig *= volume.db_to_amplitude()
    Out.ar(bus=out, source=[sig, sig])

save(flutelike,
    out = bus("ar", "out", 2),
    note = pitch,
    volume = db)

@synthdef()
def resonant_low_pass(out=0, source=0, freq=440, rcq=0.5):
    sig = RLPF.ar(
        source = In.ar(bus=source, channel_count=2),
        frequency = freq,
        reciprocal_of_q = rcq)
    Out.ar(bus=out, source=sig)

save(resonant_low_pass,
    out = bus("ar", "out", 2),
    source = bus("ar", "in", 2),
    freq = hz,
    rcq = unipolar)

@synthdef('ir', 'kr', 'kr', 'kr', 'kr', 'tr')
def quadratic(out=0, a=0, b=0, c=0, t=0, trigger=0):
    x = min(t, Sweep.kr(trigger=trigger))
    v = a*x*x + b*x + c
    Out.kr(bus=out, source=v)
save(quadratic,
    out = bus("kr", "out"))

@synthdef()
def simple(out=0):
    sig = SinOsc.ar(frequency=440)
    Out.ar(bus=out, source=[sig, sig])
save(simple,
    out = bus("ar", "out", 2))

@synthdef()
def musical(out=0, note=69, gate=1, amplitude=1.0):
    sig = Saw.ar(frequency=note.midi_to_hz()) * amplitude
    sig *= EnvGen.kr(envelope=Envelope.adsr(), gate=gate, done_action=2)
    Out.ar(bus=out, source=[sig, sig])
save(musical,
    out = bus("ar", "out", 2),
    note = pitch,
    amplitude = unipolar)

@synthdef()
def test_signal(out=0, frequency=440, amplitude=0.1):
    shift = (SinOsc.kr(frequency=0.1) * 0.5 + 0.5) * (20000 - 110)
    sine = SinOsc.ar(frequency=frequency + shift) * amplitude
    Out.ar(bus=out, source=[sine, sine])
save(test_signal,
    out = bus("ar", "out", 2),
    frequency = hz,
    amplitude = unipolar)

@synthdef()
def white_noise(out=0, amplitude=0.5):
    noise = WhiteNoise.ar() * amplitude
    Out.ar(bus=out, source=[noise, noise])
save(white_noise,
    out = bus("ar", "out", 2),
    amplitude = unipolar)

@synthdef()
def low_pass(out=0, source=0, frequency=440):
    sig = LPF.ar(
        source = In.ar(bus=source, channel_count=2),
        frequency=frequency)
    Out.ar(bus=out, source=sig)
save(low_pass,
    source = bus("ar", "in", 2),
    out = bus("ar", "out", 2),
    frequency = hz)

@synthdef()
def comb_l(out=0, source=0, decay_time=0.1, delay_time=0.2):
    i = In.ar(bus=source, channel_count=2)
    sig = CombL.ar(source=i,
        decay_time = decay_time,
        delay_time = delay_time,
        maximum_delay_time = 0.5)
    Out.ar(bus=out, source=sig)
save(comb_l,
    source = bus("ar", "in", 2),
    out = bus("ar", "out", 2),
    decay_time = duration,
    delay_time = duration)

@synthdef()
def pluck(out=0, note=96, gate=1):
    i = WhiteNoise.ar() * 0.1
    sig = CombC.ar(source=i,
        delay_time = 1 / note.midi_to_hz(),
        decay_time = 2.0,
        maximum_delay_time = 0.01)
    sig *= EnvGen.kr(envelope=Envelope.adsr(), gate=gate, done_action=2)
    Out.ar(bus=out, source=(sig,sig))
save(pluck,
    out = bus("ar", "out", 2),
    note = pitch)
