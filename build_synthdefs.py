from descriptors import *
from supriya import Envelope, synthdef, ugens
from supriya.ugens import EnvGen, Out, SinOsc

save = Saver("synthdefs")

@synthdef('ir', 'kr', 'kr', 'kr', 'kr', 'tr')
def quadratic(out=0, a=0, b=0, c=0, t=0, trigger=0):
    x = min(t, ugens.Sweep.kr(trigger=trigger))
    v = a*x*x + b*x + c
    Out.kr(bus=out, source=v)
save(quadratic,
    out = bus("kr", "out", arbitrary, 1),
    a = arbitrary,
    b = arbitrary,
    c = arbitrary,
    t = duration,
    trigger = boolean)

@synthdef()
def simple(out=0):
    sig = SinOsc.ar(frequency=440)
    Out.ar(bus=out, source=[sig, sig])
save(simple,
    out = bus("ar", "out", bipolar, 2))

@synthdef()
def musical(out=0, note=69, gate=1, amplitude=1.0):
    sig = ugens.Saw.ar(frequency=note.midi_to_hz()) * amplitude
    sig *= EnvGen.kr(envelope=Envelope.adsr(), gate=gate, done_action=2)
    Out.ar(bus=out, source=[sig, sig])
save(musical,
    out = bus("ar", "out", bipolar, 2),
    note = pitch,
    amplitude = unipolar)

@synthdef()
def test_signal(out=0, frequency=440, amplitude=0.1):
    shift = (SinOsc.kr(frequency=0.1) * 0.5 + 0.5) * (20000 - 110)
    sine = SinOsc.ar(frequency=frequency + shift) * amplitude
    Out.ar(bus=out, source=[sine, sine])
save(test_signal,
    out = bus("ar", "out", bipolar, 2),
    frequency = hz,
    amplitude = unipolar)

@synthdef()
def white_noise(out=0, amplitude=0.5):
    noise = ugens.WhiteNoise.ar() * amplitude
    Out.ar(bus=out, source=[noise, noise])
save(white_noise,
    out = bus("ar", "out", bipolar, 2),
    amplitude = unipolar)

@synthdef()
def low_pass(out=0, source=0, frequency=440):
    sig = ugens.LPF.ar(
        source = ugens.In.ar(bus=source, channel_count=2),
        frequency=frequency)
    ugens.Out.ar(bus=out, source=sig)
save(low_pass,
    source = bus("ar", "in", bipolar, 2),
    out = bus("ar", "out", bipolar, 2),
    frequency = hz)
