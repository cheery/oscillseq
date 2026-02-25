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
def musical(out=0, note=69, gate=1, volume=0.0):
    amplitude = volume.db_to_amplitude()
    sig = Saw.ar(frequency=note.midi_to_hz()) * amplitude
    sig *= EnvGen.kr(envelope=Envelope.adsr(), gate=gate, done_action=2)
    Out.ar(bus=out, source=[sig, sig])
save(musical,
    out = bus("ar", "out", 2),
    note = pitch,
    volume = db)

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
def pluck(out=0, note=96, gate=1, volume=-6):
    i = WhiteNoise.ar() * 0.1
    sig = CombC.ar(source=i,
        delay_time = 1 / note.midi_to_hz(),
        decay_time = 2.0,
        maximum_delay_time = 0.01)
    sig *= EnvGen.kr(envelope=Envelope.adsr(), gate=gate, done_action=2)
    sig *= volume.db_to_amplitude()
    Out.ar(bus=out, source=(sig,sig))
save(pluck,
    out = bus("ar", "out", 2),
    note = pitch,
    volume = db)

@synthdef()
def thingy(out=0, note=96, freq=30.0, gate=1):
    i = Impulse.ar(frequency=freq)
    sig = CombC.ar(source=i,
        delay_time = 1 / note.midi_to_hz(),
        decay_time = 2.0,
        maximum_delay_time = 0.01)
    sig *= EnvGen.kr(envelope=Envelope.adsr(), gate=gate, done_action=2)
    Out.ar(bus=out, source=(sig,sig))
save(thingy,
    out = bus("ar", "out", 2),
    note = pitch,
    freq = hz)

@synthdef()
def freeverb(out=0, source=0, damping = 0.5, mix = 0.33, room_size = 0.5):
    source = In.ar(bus=source, channel_count=2)
    sig = FreeVerb.ar(source=source,
      damping=damping,
      mix=mix,
      room_size=room_size)
    Out.ar(bus=out, source=sig)
save(freeverb,
    source = bus("ar", "in", 2),
    out = bus("ar", "out", 2),
    damping = unipolar,
    mix = unipolar,
    room_size = unipolar)

@synthdef()
def fm(out=0, note=96, gate=1, a=0.5, b=0.1):#, c=0.5, d=0.1):
    freq = note.midi_to_hz()
    #c = SinOsc.kr(frequency=25.0 * d)*0.5
    sig = SinOsc.ar(frequency=freq + SinOsc.ar(frequency=freq*a)*b*250.0)
    sig *= EnvGen.kr(envelope=Envelope.adsr(), gate=gate, done_action=2)
    Out.ar(bus=out, source=(sig,sig))
save(fm,
    out = bus("ar", "out", 2),
    note = pitch,
    a = unipolar,
    b = unipolar)

@synthdef()
def easyfm(out=0, note=96, volume=-6, gate=1, brightness=0.5):
    freq = note.midi_to_hz()
    modFreq = freq * LinLin.kr(source=brightness,
        input_minimum=0,
        input_maximum=1,
        output_minimum=1,
        output_maximum=4)
    modAmp = freq * LinLin.kr(source=brightness,
        input_minimum=0,
        input_maximum=1,
        output_minimum=0,
        output_maximum=8)
    mod = SinOsc.ar(frequency = modFreq) * modAmp
    sig = SinOsc.ar(frequency = freq + mod)
    sig *= EnvGen.kr(envelope=Envelope.adsr(), gate=gate, done_action=2)
    sig *= volume.db_to_amplitude()
    Out.ar(bus=out, source=(sig,sig))
save(easyfm,
    out = bus("ar", "out", 2),
    note = pitch,
    brightness = unipolar,
    volume = db)

@synthdef()
def easyfm2(out=0, note=96, volume=-6, gate=1, brightness=0.5, roughness=0.0):
    freq = note.midi_to_hz()
    index = LinLin.kr(source=brightness,
        input_minimum=0,
        input_maximum=1,
        output_minimum=0.01,
        output_maximum=10)
    ratio = 2.0 + LinLin.kr(source=roughness,
        input_minimum=0,
        input_maximum=1,
        output_minimum=0,
        output_maximum=0.08)
    modFreq = freq * ratio
    modAmp = freq * index
    mod = SinOsc.ar(frequency = modFreq) * modAmp
    sig = SinOsc.ar(frequency = freq + mod)
    sig *= EnvGen.kr(envelope=Envelope.adsr(), gate=gate, done_action=2)
    sig *= volume.db_to_amplitude()
    Out.ar(bus=out, source=(sig,sig))
save(easyfm2,
    out = bus("ar", "out", 2),
    note = pitch,
    brightness = unipolar,
    roughness = unipolar,
    volume = db)

@synthdef()
def demo_kick(out=0, volume=-6, gate=1):
    env = EnvGen.kr(envelope=Envelope.percussive(), gate=gate, done_action=2)
    sig = SinOsc.ar(frequency=env * 600.0)
    sig *= env
    sig *= volume.db_to_amplitude()
    Out.ar(bus=out, source=(sig,sig))
save(demo_kick,
    out = bus("ar", "out", 2),
    volume = db)

if False:
    import supriya, time, os
    if "SC_JACK_DEFAULT_INPUTS" not in os.environ:
        os.environ["SC_JACK_DEFAULT_INPUTS"] = "system"
    if "SC_JACK_DEFAULT_OUTPUTS" not in os.environ:
        os.environ["SC_JACK_DEFAULT_OUTPUTS"] = "system"
    
    s = supriya.Server().boot()
    s.add_synthdefs(demo_kick)
    s.sync()
    s.add_synth(demo_kick, gate=1)
    time.sleep(2)
    
    s.quit()
