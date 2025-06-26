import json
import os

def read_desc(filename):
    with open(filename, "r") as fd:
        lines = fd.read().strip().splitlines()
    def parse(line):
        name, spec = line.split(":", 1)
        name = name.strip()
        spec = spec.strip()
        if ' ' in spec:
            rate, mode, elem, channel_count = spec.split(' ')
            ty = bus(rate, mode, simple(elem), channel_count)
        else:
            ty = simple(spec)
        return name, ty
    return [parse(line) for line in lines]

class simple:
    def __init__(self, name):
        self.name = name

    def to_text(self):
        return self.name

    def __repr__(self):
        return self.to_text()

class bus:
    def __init__(self, rate, mode, elem, channel_count=1):
        self.rate = rate
        self.mode = mode # in/out/in-feedback
        self.elem = elem
        self.channel_count = channel_count

    def to_text(self):
        assert isinstance(self.elem, simple)
        return f"{self.rate} {self.mode} {self.elem.to_text()} {self.channel_count}"

    def __repr__(self):
        return self.to_text()

boolean  = simple("boolean")
unipolar = simple("unipolar")
number   = simple("number")
bipolar  = simple("bipolar")
pitch    = simple("pitch")
hz       = simple("hz")
db       = simple("db")
duration = simple("duration")

class Saver:
    def __init__(self, directory):
        if not os.path.exists(directory):
            os.mkdir(directory)
        self.directory = directory

    def __call__(self, synthdef, **params):
        desc = "\n".join(f"{n}: {v.to_text()}" for n,v in params.items())
        with open(os.path.join(self.directory, f'{synthdef.effective_name}.synthdef'), 'wb') as fd:
            fd.write(synthdef.compile())
        with open(os.path.join(self.directory, f'{synthdef.effective_name}.desc'), 'w') as fd:
            fd.write(desc)
